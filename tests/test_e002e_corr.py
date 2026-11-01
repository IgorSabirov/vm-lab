"""Independent physical and report checks; no full-network NESS is solved."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from scipy import sparse as sp
from scipy.linalg import expm
from e002e_exp.space import Space, liouvillian
from e002e_exp.model import make_full
from e002e_exp.export import write_manifest
from e002e_exp.runtime import kernel_hash, environment, compare_environment
from e002e_corr_exp.core import marginals, replacement, prepare, propagate, analyze, threshold_decision, physicality
from e002e_corr_exp.plan import PROTOCOL, workload, cases, preflight, protocol_hash, implementation_hash, thread_preflight
from e002e_corr_exp.task import run, solve_baseline, select_observables, run_case, output_balance, atomic_npz
from e002e_corr_exp.verify import verify_report
from e002e_corr_exp.reporting import render_result
from e002e_corr_exp.budget import forecast_components


def classical_model():
    # Correlated classical four-state process is an essential positive control:
    # CORR must NOT mistake a signal here for a quantum-specific mechanism.
    space = Space(np.zeros(4, int)); H = sp.csr_matrix((4,4), dtype=complex)
    jumps = []
    for a,b,rate in ((0,2,1.),(2,0,.1),(1,3,.2),(3,1,1.4),
                     (0,1,.3),(1,0,.3),(2,3,.3),(3,2,.3)):
        C = sp.csr_matrix(([np.sqrt(rate)], ([b],[a])), shape=(4,4), dtype=complex)
        jumps.append((f'{a}_{b}',C))
    na = sp.diags([0.,0.,1.,1.]); nb = sp.diags([0.,1.,0.,1.]); F = .5*na
    obs = dict(F=F,J_h=F,source=F,inventory=nb,h6=F,P_m6_N2=sp.eye(4),K=na-nb)
    return dict(space=space,H=H,jumps=jumps,L=liouvillian(H,jumps,space),observables=obs,
                n=[na,nb],currents=[F,0*F,0*F])


def trajectories(model, states, H=1.):
    initial,_ = prepare(model,states[0],(2,2)); reference,_=prepare(model,states[1],(2,2))
    return [propagate(model,x,horizon=H,dt=dt,sample_interval=.02,physicality_interval=.5)
            for x,dt in ((initial,.005),(initial,.01),(reference,.005))]


class PreparationTests(unittest.TestCase):
    def setUp(self):
        v = np.array([0.,1.,1.,0.])/np.sqrt(2)
        self.rho=.8*np.outer(v,v)+.2*np.eye(4)/4

    def test_full_complex_marginals_not_only_diagonals(self):
        U = np.array([[1,1j],[1j,1]])/np.sqrt(2)
        rho = np.kron(U,np.eye(2))@self.rho@np.kron(U.conj().T,np.eye(2))
        a,b=marginals(rho,(2,2)); prod=replacement(rho,b,(2,2))
        aa,bb=marginals(prod,(2,2))
        np.testing.assert_allclose(a,aa,atol=1e-14);np.testing.assert_allclose(b,bb,atol=1e-14)
        self.assertGreater(np.linalg.norm(prod-rho),.1)
        self.assertGreaterEqual(np.linalg.eigvalsh(prod).min(),0.)

    def test_fixed_reference_channel_is_linear(self):
        tau=np.diag([.3,.7]); other=np.diag([.1,.2,.3,.4])
        np.testing.assert_allclose(replacement(.4*self.rho+.6*other,tau,(2,2)),
                                   .4*replacement(self.rho,tau,(2,2))+.6*replacement(other,tau,(2,2)),atol=1e-14)

    def test_product_is_fixed_point(self):
        a=np.array([[.6,.1j],[-.1j,.4]]);b=np.array([[.4,.2],[.2,.6]])
        np.testing.assert_allclose(replacement(np.kron(a,b),b,(2,2)),np.kron(a,b),atol=1e-14)

    def test_invalid_reference_rejected(self):
        for tau in (np.diag([1.1,-.1]),np.eye(2),np.full((2,2),np.nan)):
            with self.assertRaises(ValueError):replacement(self.rho,tau,(2,2))

    def test_subsystem_order_and_charge(self):
        space=Space(np.array([0,1,1,2])); model=dict(space=space,H=sp.eye(4))
        x=space.pack(self.rho); initial,record=prepare(model,x,(2,2))
        np.testing.assert_allclose(space.unpack(initial[:,1]),np.eye(4)/4,atol=1e-14)
        self.assertGreater(record['trace_distance'],.1)
        np.testing.assert_allclose(marginals(np.diag([.1,.2,.3,.4]),(2,2))[0],np.diag([.3,.7]))

    def test_full_charge_algebra_product_needs_no_projection(self):
        charges=np.repeat([k.bit_count() for k in range(8)],27); space=Space(charges)
        rng=np.random.default_rng(43);rho=np.zeros((216,216),complex)
        for g in space.groups:
            a=rng.normal(size=(len(g),3))+1j*rng.normal(size=(len(g),3))
            rho[np.ix_(g,g)]=a@a.conj().T
        rho/=np.trace(rho);x=space.pack(rho)
        pair,p=prepare(dict(space=space,H=sp.eye(216)),x)
        self.assertLess(max(p['sector_errors'].values()),1e-12)
        self.assertEqual(space.size,14580); self.assertFalse(p['universal_cptp_channel'])
        a,b=marginals(rho,(8,27))
        np.testing.assert_allclose(space.unpack(pair[:,1]),np.kron(a,b),atol=1e-15)
        bad=rho.copy();bad[0,27]=bad[27,0]=.001
        with self.assertRaisesRegex(ValueError,'outside'):space.pack(bad)

    def test_full_psd_does_not_trust_incomplete_groups(self):
        space=Space(np.zeros(4,int)); space.groups=[np.array([0,1])]
        x=space.pack(np.diag([.5,.5,.1,-.1]))
        with self.assertRaises(ArithmeticError):physicality(space,x,1e-9)


class PropagationTests(unittest.TestCase):
    def setUp(self):
        self.model=classical_model();self.states,self.raw,_=solve_baseline(self.model)

    def test_rk4_against_independent_dense_exponential(self):
        initial,_=prepare(self.model,self.states[0],(2,2))
        r=propagate(self.model,initial,horizon=1.,dt=.01,sample_interval=.02,physicality_interval=.5)
        truth=expm(self.model['L'].toarray())@initial
        np.testing.assert_allclose(r['final'],truth,atol=3e-10,rtol=0)
        self.assertEqual(r['steps'],100);self.assertEqual(len(r['flux']),101)

    def test_classical_correlations_can_produce_signal(self):
        runs=trajectories(self.model,self.states)
        result=analyze(*runs,baseline_flux=self.raw[0]['F'],reference_flux=self.raw[1]['F'],policy=PROTOCOL)
        self.assertGreater(result['primary']['value'],.001)
        self.assertEqual(result['primary']['status'],'MARGINAL_SUFFICIENCY_REJECTED_AT_DECLARED_RESOLUTION')
        self.assertAlmostEqual(runs[0]['flux'][0,0],runs[0]['flux'][0,1],places=13)

    def test_zero_generator_is_negative_control(self):
        model=dict(self.model,L=0*self.model['L']);initial,_=prepare(model,self.states[0],(2,2))
        r=propagate(model,initial,horizon=1.,dt=.01,sample_interval=.02,physicality_interval=.5)
        self.assertLess(abs(r['flux'][:,1]-r['flux'][:,0]).max(),1e-14)

    def test_bad_grids_and_nonfinite_input_fail(self):
        initial,_=prepare(self.model,self.states[0],(2,2))
        for dt in (.03,-.01,float('nan')):
            with self.assertRaises(ValueError):propagate(self.model,initial,horizon=1.,dt=dt,sample_interval=.02,physicality_interval=.5)
        initial[0,0]=np.nan
        with self.assertRaises(ValueError):propagate(self.model,initial,horizon=1.,dt=.01,sample_interval=.02,physicality_interval=.5)

    def test_refinement_failure_blocks_verdict(self):
        runs=trajectories(self.model,self.states);runs[1]['raw'][1,0,0]+=.001
        with self.assertRaises(ArithmeticError):analyze(*runs,baseline_flux=self.raw[0]['F'],reference_flux=self.raw[1]['F'],policy=PROTOCOL)

    def test_conditional_floor_not_weakened(self):
        runs=trajectories(self.model,self.states)
        p=runs[0]['names'].index('P_m6_N2')
        for r in runs:r['raw'][:,p,:]=1e-6
        result=analyze(*runs,baseline_flux=self.raw[0]['F'],reference_flux=self.raw[1]['F'],policy=PROTOCOL)
        self.assertTrue(all(x['cut']['value'] is None for x in result['conditional']))

    def test_interval_boundary_is_unresolved(self):
        self.assertEqual(threshold_decision(.001,0.,.001)['status'],'UNRESOLVED')
        self.assertEqual(threshold_decision(.002,.001,.001)['status'],'UNRESOLVED')
        self.assertEqual(threshold_decision(0.,1e-9,.001)['status'],'MARGINAL_SUFFICIENCY_NOT_REJECTED_IN_WINDOW')

    def test_reference_common_mode_drift_is_not_hidden_by_delta(self):
        runs=trajectories(self.model,self.states)
        runs[2]['flux'][-1,:]+=2*PROTOCOL['maximum_sham_drift']
        with self.assertRaisesRegex(ArithmeticError,'drift'):
            analyze(*runs,baseline_flux=self.raw[0]['F'],reference_flux=self.raw[1]['F'],policy=PROTOCOL)

    def test_reference_preparation_checks_its_own_flux(self):
        raw=copy.deepcopy(self.raw);raw[1]['F']+=1e-4
        with self.assertRaisesRegex(ArithmeticError,'initial flux'):
            run_case(self.model,self.states,raw,mode='production',horizon=1.,dimensions=(2,2))

    def test_analytic_amplitude_damping_and_checkpoint_cadence(self):
        space=Space(np.zeros(2,int)); C=sp.csr_matrix([[0,1],[0,0]],dtype=complex)
        H=sp.csr_matrix((2,2),dtype=complex); excited=sp.diags([0.,1.])
        model=dict(space=space,L=liouvillian(H,[('decay',C)],space),observables={'F':excited})
        x=space.pack(np.diag([0.,1.])); calls=[]
        r=propagate(model,np.column_stack((x,x)),horizon=1.,dt=.005,sample_interval=.02,
                    physicality_interval=.5,checkpoint=lambda step,t,y:calls.append(step))
        self.assertLess(np.max(abs(r['flux'][:,0]-np.exp(-r['time']))),PROTOCOL['maximum_sham_drift'])
        self.assertEqual(calls,[0,100,200]);self.assertEqual(r['checkpoint_calls'],3)

    def test_tiny_grid_roundoff_tolerated_but_shift_rejected(self):
        runs=trajectories(self.model,self.states);runs[1]['sample_time']+=1e-15
        analyze(*runs,baseline_flux=self.raw[0]['F'],reference_flux=self.raw[1]['F'],policy=PROTOCOL)
        runs[1]['sample_time']+=1e-8
        with self.assertRaisesRegex(ValueError,'grids'):
            analyze(*runs,baseline_flux=self.raw[0]['F'],reference_flux=self.raw[1]['F'],policy=PROTOCOL)


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        # Report verifier's repository-input loader is isolated here; the real
        # pinned_file byte/hash validation has separate source-integrity tests.
        loader=patch('e002e_corr_exp.verify.pinned_file',side_effect=lambda spec:self.pinned_calibration)
        loader.start();self.addCleanup(loader.stop)

    def test_failure_is_saved_before_any_assembly_and_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d,patch('e002e_corr_exp.task.make_full') as builder:
            with self.assertRaises(ValueError):run({'mode':'production'},d)
            builder.assert_not_called()
            self.assertEqual(json.loads((Path(d)/'report/status.json').read_text())['status'],'FAILED')
            with self.assertRaises(ValueError):verify_report(Path(d)/'report')
            with self.assertRaises(FileExistsError):run({'mode':'production'},d)

    def _worker(self, mode):
        model=classical_model();states,raw,_=solve_baseline(model)
        cs=cases()
        env=environment()
        gate=dict(cases=cs,evidence={c['id']:dict(raw=raw[0]) for c in cs},
                  counts=workload(1.),horizon=1.,environment=compare_environment(env,env) if mode=='production' else
                  dict(comparable=False,reason='BOUNDED_FIRST_CALIBRATION_NO_CORRELATION_CUT'))
        cfg=dict(mode=mode,source_commit='0'*40,forecast=dict(expected_seconds=1.,lower_seconds=.01,upper_seconds=10.),
                 protocol_sha256=protocol_hash(),implementation_sha256=implementation_hash(),
                 calibration={'path':'synthetic_calibration.json','sha256':'0'*64},
                 memory_budget=dict(peak_additional_bytes=2**30,reserve_bytes=2**28))
        self.pinned_calibration=dict(status='CALIBRATION_COMPLETE',runtime_review_status='REVIEWED',
                 report_commit='1'*40,protocol_sha256=protocol_hash(),implementation_sha256=implementation_hash(),
                 counts=workload(PROTOCOL['calibration_horizon']),environment=env,
                 production_forecast=cfg['forecast'],memory_budget=cfg['memory_budget'])
        return model,gate,cfg

    def test_complete_worker_and_semantic_tamper(self):
        with patch.dict(PROTOCOL,dict(horizon=1.,dimensions=[2,2])):
            model,gate,cfg=self._worker('production')
            with tempfile.TemporaryDirectory() as d,patch('e002e_corr_exp.task.preflight',return_value=gate),patch('e002e_corr_exp.task.make_full',return_value=model):
                result=run(cfg,d);self.assertEqual(result['actual_counts'],workload(1.))
                report=Path(d)/'report';verify_report(report,Path(d)/'full',lambda case:model)
                human=report/'RESULT.md';original=human.read_text();human.write_text(original+'false acceptance\n');write_manifest(report)
                with self.assertRaisesRegex(ValueError,'Human report'):verify_report(report)
                human.write_text(original);write_manifest(report)
                full_files=list((Path(d)/'full').rglob('*.npz'));self.assertEqual(len(full_files),12)
                self.assertFalse(list(Path(d).rglob('*.tmp.npz')))
                series=report/(cases()[0]['id']+'_series.npz');original_bytes=series.read_bytes()
                with np.load(series,allow_pickle=False) as data:arrays={k:data[k].copy() for k in data.files}
                fi=list(arrays['names']).index('F')
                for label in ('fine','coarse','reference'):arrays[label+'_raw'][:,fi,:]+=.001
                np.savez_compressed(series,**arrays);write_manifest(report)
                with self.assertRaisesRegex(ValueError,'Raw F'):verify_report(report)
                series.write_bytes(original_bytes);write_manifest(report)
                env_path=report/'environment_before.json';env_original=env_path.read_text()
                modified=json.loads(env_original);modified['cpu_model']='UNMATCHED_CPU'
                env_path.write_text(json.dumps(modified))
                metric_path=report/'metrics.json';metric_original=metric_path.read_text()
                m=json.loads(metric_original);m['environment_after']['cpu_model']='UNMATCHED_CPU'
                # Saved comparison stays true and all displayed runtime fields
                # remain a self-consistent PASS, but pinned CPU disagrees.
                self.assertEqual(m['runtime_gate']['status'],'PASS')
                metric_path.write_text(json.dumps(m));write_manifest(report)
                with self.assertRaisesRegex(ValueError,'pinned calibration'):verify_report(report)
                env_path.write_text(env_original);metric_path.write_text(metric_original);write_manifest(report)
                p=report/(cases()[0]['id']+'_case.json');r=json.loads(p.read_text());r['result']['primary']['status']='FALSE_SUCCESS';p.write_text(json.dumps(r));write_manifest(report)
                with self.assertRaisesRegex(ValueError,'verdict'):verify_report(report)

    def test_calibration_does_not_prepare_product_state(self):
        with patch.dict(PROTOCOL,dict(calibration_horizon=1.,dimensions=[2,2])):
            model,gate,cfg=self._worker('calibration')
            with tempfile.TemporaryDirectory() as d,patch('e002e_corr_exp.task.preflight',return_value=gate),patch('e002e_corr_exp.task.make_full',return_value=model),patch('e002e_corr_exp.task.prepare',side_effect=AssertionError('Held-out intervention accessed')):
                run(cfg,d);verify_report(Path(d)/'report')
                result=json.loads((Path(d)/'report'/(cases()[0]['id']+'_case.json')).read_text())['result']
                self.assertNotIn('primary',result)
                report=Path(d)/'report';m=json.loads((report/'metrics.json').read_text())
                m['runtime_gate']['status']='PASS';(report/'metrics.json').write_text(json.dumps(m))
                records=[json.loads(p.read_text()) for p in report.glob('*_case.json')]
                text=render_result(cfg,m,records)
                for name in ('RESULT.md','README.md'):(report/name).write_text(text)
                write_manifest(report)
                with self.assertRaisesRegex(ValueError,'Runtime gate'):verify_report(report)

    def test_preflight_requires_reviewed_calibration_and_fixed_science(self):
        from e002e_exp.runtime import ROOT
        records={c['id']:json.loads((ROOT/'results/E002e_BASELINE_v001_r001/files'/(c['id']+'.json')).read_text()) for c in cases()}
        review=dict(status='REVIEWED_AND_CHECKED',implementation_sha256=implementation_hash(),reviewed_source_commit='1'*40)
        evidence=dict(schema='E002e_CORR_evidence_v1',protocol_sha256=protocol_hash(),baselines=[dict(case_id=k,path=k) for k in records])
        forecast=dict(expected_seconds=10.,lower_seconds=5.,upper_seconds=20.)
        cal=dict(status='CALIBRATION_COMPLETE',runtime_review_status='PENDING',report_commit='2'*40,
                 implementation_sha256=implementation_hash(),protocol_sha256=protocol_hash(),counts=workload(2.),
                 environment={},production_forecast=forecast,memory_budget={})
        items=dict(review=review,evidence=evidence,cal=cal,**records)
        cfg=dict(mode='production',protocol_sha256=protocol_hash(),implementation_sha256=implementation_hash(),
                 source_commit='0'*40,technical_review={'path':'review'},evidence={'path':'evidence'},
                 calibration={'path':'cal'},forecast=forecast,memory_budget={})
        current=dict(requested_threads={k:'1' for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS')},threadpools=[{'num_threads':1}])
        with patch.dict('os.environ',{'VM_SOURCE_COMMIT':'0'*40}),patch('e002e_corr_exp.plan.pinned_file',side_effect=lambda x:items[x['path']]),patch('e002e_corr_exp.plan.compare_environment',return_value={'comparable':True}),patch('e002e_corr_exp.plan.memory_preflight',return_value={'status':'PASS'}):
            with self.assertRaisesRegex(ValueError,'Calibration'):preflight(cfg,current)
            cal['runtime_review_status']='REVIEWED';self.assertEqual(preflight(cfg,current)['counts'],workload())
            with self.assertRaisesRegex(ValueError,'override'):preflight(dict(cfg,primary_threshold=10),current)
            with self.assertRaises(ValueError):preflight(dict(cfg,forecast=dict(forecast,expected_seconds=20)),current)

    def test_bad_report_physics_is_rejected_after_rehash(self):
        with patch.dict(PROTOCOL,dict(horizon=1.,dimensions=[2,2])):
            model,gate,cfg=self._worker('production')
            with tempfile.TemporaryDirectory() as d,patch('e002e_corr_exp.task.preflight',return_value=gate),patch('e002e_corr_exp.task.make_full',return_value=model):
                run(cfg,d);report=Path(d)/'report';p=report/(cases()[0]['id']+'_case.json')
                r=json.loads(p.read_text());r['case']['epsilon']=8.;p.write_text(json.dumps(r));write_manifest(report)
                with self.assertRaisesRegex(ValueError,'physics'):verify_report(report)

    def test_full_builder_interface_without_full_ness(self):
        self.assertEqual(kernel_hash(),'1efb3a9e9bb911df13f19f2adab775c736882ba17c191e9b2dde4e5e067e808e')
        for c in cases():
            m=select_observables(make_full(c,assemble=False))
            self.assertNotIn('L',m);self.assertEqual(m['space'].size,14580)
            self.assertEqual(m['observables']['F'].shape,(216,216))
            balance=output_balance(m);self.assertEqual(balance['status'],'OPERATOR_IDENTITY_VERIFIED')
            self.assertAlmostEqual(balance['kappa_out'],.5)
        self.assertEqual(workload(),dict(NESS=3,refinement_NESS=3,propagations=9,block_steps=30000,checkpoint_writes=189,block_rhs_calls=120000,scalar_rhs_equivalents=240000))

    def test_dependency_hash_covers_numerics(self):
        before=implementation_hash();original=Path.read_bytes
        def altered(p):
            data=original(p)
            return data+b'\n# changed dependency\n' if p.name=='numerics.py' else data
        with patch.object(Path,'read_bytes',altered):self.assertNotEqual(before,implementation_hash())
        self.assertEqual(before,implementation_hash())

    def test_source_bytes_must_match_frozen_commit(self):
        from e002e_exp.runtime import ROOT
        from e002e_corr_exp.evidence import build
        pins=json.loads((ROOT/'experiments/e002e_corr/input_integrity.json').read_text())
        pins['checks'][0]['sha256']='0'*64
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'pins.json';p.write_text(json.dumps(pins))
            with self.assertRaisesRegex(ValueError,'differs'):build(Path(d)/'output',p)

    def test_thread_contract_requires_requested_and_observed_one(self):
        good=dict(requested_threads={k:'1' for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS')},threadpools=[{'num_threads':1}])
        self.assertEqual(thread_preflight(good)['status'],'PASS')
        for bad in ({},dict(good,threadpools=[]),dict(good,threadpools=[{'num_threads':2}])):
            with self.assertRaises(ValueError):thread_preflight(bad)

    def test_failed_atomic_checkpoint_cleans_own_temporary_file(self):
        with tempfile.TemporaryDirectory() as d,patch('e002e_corr_exp.task.os.replace',side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):atomic_npz(Path(d)/'checkpoint.npz',state=np.eye(2))
            self.assertEqual(list(Path(d).iterdir()),[])

    def test_forecast_counts_both_publications_and_verifications(self):
        phases=[dict(assembly=0.,baseline=0.,propagation=0.,checkpoint_io_seconds=0.,total=0.)]
        timing=dict(summary_publications_seconds=[.2,.8],core_verifications_seconds=[.3,.7],first_report_export_seconds=.6)
        c=forecast_components(phases,timing,workload(2.),2.)
        self.assertEqual([c[k] for k in ('first_summary_publication','second_summary_publication','first_verification','second_verification')],[2.,8.,3.,7.])
        self.assertAlmostEqual(c['report_non_summary_export'],4.)
        with self.assertRaises(ValueError):forecast_components(phases,dict(timing,core_verifications_seconds=[.3]),workload(2.),2.)


if __name__=='__main__':unittest.main()
