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
from e002e_exp.runtime import kernel_hash
from e002e_corr_exp.core import marginals, replacement, prepare, propagate, analyze, threshold_decision
from e002e_corr_exp.plan import PROTOCOL, workload, cases, preflight, protocol_hash
from e002e_corr_exp.task import run, solve_baseline, select_observables, run_case
from e002e_corr_exp.verify import verify_report


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


class IntegrationTests(unittest.TestCase):
    def test_failure_is_saved_before_any_assembly_and_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d,patch('e002e_corr_exp.task.make_full') as builder:
            with self.assertRaises(ValueError):run({'mode':'production'},d)
            builder.assert_not_called()
            self.assertEqual(json.loads((Path(d)/'report/status.json').read_text())['status'],'FAILED')
            with self.assertRaises(ValueError):verify_report(Path(d)/'report')
            with self.assertRaises(FileExistsError):run({'mode':'production'},d)

    def _worker(self, mode):
        model=classical_model();states,raw,_=solve_baseline(model)
        cs=[dict(id='test_'+m,model=m) for m in PROTOCOL['models']]
        gate=dict(cases=cs,evidence={c['id']:dict(raw=raw[0]) for c in cs},
                  counts=workload(1.),horizon=1.,environment={'comparable':False})
        cfg=dict(mode=mode,source_commit='0'*40,forecast=dict(expected_seconds=1.,lower_seconds=.01,upper_seconds=10.),
                 memory_budget=dict(peak_additional_bytes=2**30,reserve_bytes=2**28))
        return model,gate,cfg

    def test_complete_worker_and_semantic_tamper(self):
        with patch.dict(PROTOCOL,dict(horizon=1.,dimensions=[2,2])):
            model,gate,cfg=self._worker('production')
            with tempfile.TemporaryDirectory() as d,patch('e002e_corr_exp.task.preflight',return_value=gate),patch('e002e_corr_exp.task.make_full',return_value=model):
                result=run(cfg,d);self.assertEqual(result['actual_counts'],workload(1.))
                report=Path(d)/'report';verify_report(report)
                p=report/'test_QS_case.json';r=json.loads(p.read_text());r['result']['primary']['status']='FALSE_SUCCESS';p.write_text(json.dumps(r));write_manifest(report)
                with self.assertRaisesRegex(ValueError,'verdict'):verify_report(report)

    def test_calibration_does_not_prepare_product_state(self):
        with patch.dict(PROTOCOL,dict(calibration_horizon=1.,dimensions=[2,2])):
            model,gate,cfg=self._worker('calibration')
            with tempfile.TemporaryDirectory() as d,patch('e002e_corr_exp.task.preflight',return_value=gate),patch('e002e_corr_exp.task.make_full',return_value=model),patch('e002e_corr_exp.task.prepare',side_effect=AssertionError('Held-out intervention accessed')):
                run(cfg,d);verify_report(Path(d)/'report')
                result=json.loads((Path(d)/'report/test_QS_case.json').read_text())['result']
                self.assertNotIn('primary',result)

    def test_full_builder_interface_without_full_ness(self):
        self.assertEqual(kernel_hash(),'1efb3a9e9bb911df13f19f2adab775c736882ba17c191e9b2dde4e5e067e808e')
        for c in cases():
            m=select_observables(make_full(c,assemble=False))
            self.assertNotIn('L',m);self.assertEqual(m['space'].size,14580)
            self.assertEqual(m['observables']['F'].shape,(216,216))
        self.assertEqual(workload(),dict(NESS=3,refinement_NESS=3,propagations=9,block_steps=30000,block_rhs_calls=120000,scalar_rhs_equivalents=240000))


if __name__=='__main__':unittest.main()
