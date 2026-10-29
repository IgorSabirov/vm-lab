import copy,json,os,tempfile,time,unittest
import shutil
from pathlib import Path
from unittest.mock import patch
import numpy as np
from scipy import sparse as sp
from scipy.integrate import simpson
from prepare_e002_config import make,rates
from e002_exp.damage import apply,kraus,complete
from e002_exp.model import build_model,measurement_model,ketbra,tensor,maxabs
from sqrt_exp.model import measurement_model as legacy
from e002_exp.metrics import deficit,recovery,classify
from e002_exp.task import execute,validate_config
from e002_exp.report import rr_matching,apply_acceptance,prepare,finalize
from verify_e002_report import verify
ROOT=Path(__file__).resolve().parents[1]

def config():return make(json.loads((ROOT/'data/e002_rr_target.json').read_text()))

class E002Tests(unittest.TestCase):
    def test_review_rr_guards_and_rates(self):
        c=config();b=c['rr_target']
        for model in ['RR','RR2','RR_J0']:
            with self.assertRaisesRegex(ValueError,'RR requires g=0'):
                build_model({**c['models'][model],'g':.5})
        for name,factor in [('RR',1),('RR2',2)]:
            a=copy.deepcopy(b)
            for e,(alpha,beta) in c['models'][name]['rr_rates'].items():
                a['event_rate__idle_'+e]=beta*b['pL'+e]
                a['event_rate__renew_'+e]=alpha*b['pR'+e]
            self.assertTrue(rr_matching(a,b,factor,1e-10)['passed'])
            if name=='RR2':
                for wrong in ['double_idle_only','missing_beta']:
                    damaged=copy.deepcopy(a)
                    for e,(_,beta) in c['models']['RR']['rr_rates'].items():
                        rate=2*beta if wrong=='double_idle_only' else beta+.11
                        damaged['event_rate__idle_'+e]=rate*b['pL'+e]
                    self.assertFalse(rr_matching(damaged,b,2,.10)['passed'])
        # Gate labels cannot silently reinstate a conditional idle in RR.
        m=measurement_model({**c['models']['RR'],'gate_idle':'Pi','gamma_r':.05},c['acceptance'])
        self.assertEqual(maxabs(m['rows'][m['index']['I_idle_sink']]),0)
        self.assertTrue(all(v==0 for k,v in m['checks'].items() if k.startswith('rr_H_form_zero')))

    def test_review_late_failure_and_missing_baseline(self):
        for name in ['inventory_budget','runtime_gate','export_budget']:
            r=dict(primary_outcome='network_repair_controlled',RR2_outcome='network_repair_controlled',qualifiers=[{'candidate':True}],failure=None,task_exit_code=0)
            apply_acceptance(r,[dict(name=name,passed=False)])
            self.assertEqual(r['primary_outcome'],'metric_undefined');self.assertFalse(r['qualifiers'][0]['candidate'])
            self.assertEqual(r['provisional_outcomes']['primary_outcome'],'network_repair_controlled')
            self.assertIn(name,r['acceptance_blockers'])
        c=config();c['cases']=[x for x in c['cases'] if x['id']!='PP_none_fine']
        with self.assertRaisesRegex(ValueError,'PP_none_fine'):validate_config(c)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'full').mkdir()
            r,checks=prepare(root,config(),dict(run_id='E002_partial_test',source_commit='a'*40),dict(cases=[],checks=[],failure={'message':'interrupted'}))
            self.assertIn('PP_none_fine',next(x for x in checks if x['name']=='required_baselines')['missing'])
            finalize(root,r,checks,1.)
            self.assertEqual(r['primary_outcome'],'metric_undefined');self.assertEqual(r['acceptance_status'],'BLOCKED')

    def test_review_coherences_and_partial_trace(self):
        # Independent exact action on all nine local matrix units. In particular
        # feed kills |L><R|; it does not turn that coherence into an R population.
        maps={'link':([0,1],2,0),'feed':([0,1],2,1),'resource':([0,2],1,0)}
        for kind in ['none','link','feed','resource','hard']:
            for a in range(3):
                for b in range(3):
                    x=ketbra(3,a,b);actual=sum(k@x@k.getH() for k in kraus(kind));expected=0*x
                    if kind=='none':expected=x
                    elif kind=='hard':expected=ketbra(3,0,0) if a==b else expected
                    else:
                        keep,destroy,target=maps[kind]
                        if a in keep and b in keep:expected=x
                        elif a==b==destroy:expected=ketbra(3,target,target)
                    self.assertLess(maxabs(actual-expected),1e-12)
        with self.assertRaises(ValueError):apply(np.zeros(216**2),'linke')
        rng=np.random.default_rng(52);z=rng.normal(size=(216,3))+1j*rng.normal(size=(216,3));rho=z@z.conj().T;rho/=np.trace(rho)
        v=rho.reshape(-1,order='F')
        direct=np.array([[np.trace(rho[27*i:27*(i+1),27*j:27*(j+1)]) for j in range(8)] for i in range(8)])
        existing=np.einsum('abcb->ac',v.reshape((216,216),order='F').reshape(8,27,8,27))
        alternative=np.einsum('abcb->ac',v.reshape(27,8,27,8,order='F').transpose(1,0,3,2))
        np.testing.assert_allclose(existing,direct,atol=1e-12);np.testing.assert_array_equal(existing,alternative)
        for kind in maps.keys()|{'hard','none'}:
            out=apply(v,kind,(1,)).reshape(216,216,order='F')
            got=np.array([[np.trace(out[27*i:27*(i+1),27*j:27*(j+1)]) for j in range(8)] for i in range(8)])
            np.testing.assert_allclose(got,direct,atol=1e-12)

    def test_kraus_wrong_edge_and_trace(self):
        rng=np.random.default_rng(29);a=rng.normal(size=(216,3))+1j*rng.normal(size=(216,3));rho=a@a.conj().T;rho/=np.trace(rho);v=rho.reshape(-1,order='F')
        for kind in ['none','link','feed','resource','hard']:
            self.assertLess(complete(kraus(kind)),1e-12)
            out=apply(v,kind).reshape(216,216,order='F')
            self.assertAlmostEqual(np.trace(out).real,1,places=12);self.assertGreaterEqual(np.linalg.eigvalsh(out).min(),-1e-10)
        with self.assertRaises(ValueError):complete(kraus('link')[:1])
        def pops(vec):
            rr=vec.reshape(216,216,order='F');out=[]
            for e in range(3):
                fs=[sp.eye(d) for d in (2,2,2,3,3,3)];fs[e+3]=ketbra(3,2,2);out.append(np.trace(tensor(fs)@rr).real)
            return np.array(out)
        before=pops(v);correct=pops(apply(v,'link',(0,)));wrong=pops(apply(v,'link',(1,)))
        np.testing.assert_allclose(correct,[0,before[1],before[2]],atol=1e-12)
        with self.assertRaises(AssertionError):np.testing.assert_allclose(wrong,[0,before[1],before[2]],atol=1e-12)

    def test_metrics_known_answers(self):
        t=np.linspace(0,10,1001);y=1-np.exp(-t)
        self.assertAlmostEqual(deficit(t,y,1,.001),1-np.exp(-10),places=8)
        self.assertEqual(deficit(t,np.ones_like(t)*1.2,1,.001),0)
        self.assertIsNone(deficit(t,np.zeros_like(t),0,1e-8))
        # Supply=2, output=1.5; sink stores .5 per unit time.
        a={k:np.zeros_like(t) for k in ['sink_flux','I_hop_sink','I_form_sink','I_idle_sink','n2','inventory','pump_flux','break_flux']}
        a.update(sink_flux=t*0+1.5,I_hop_sink=t*0+2,n2=.5*t)
        r=recovery(t,a,{'sink_flux':1.5,'I_hop_sink':2},{'sink_flux':1.5,'I_hop_sink':2},15)
        self.assertAlmostEqual(r['integrals']['residual'],0,places=12)
        self.assertEqual(classify({'Lambda_hop':None},{'Lambda_hop':1},True,True),'metric_undefined')

    def test_rr_and_unchanged_gate_operators(self):
        c=config();target=c['rr_target']
        for name in ['PP','PQ','PS','QP','QQ','QS']:
            a=measurement_model(c['models'][name],c['acceptance']);b=legacy(c['models'][name],c['acceptance'])
            self.assertEqual(maxabs(a['L']-b['L']),0)
            self.assertEqual(a['names'],b['names']);self.assertEqual(maxabs(a['rows']-b['rows']),0)
        for name,factor in [('RR',1),('RR2',2)]:
            p=c['models'][name];m=measurement_model(p,c['acceptance'])
            for e,(alpha,beta) in p['rr_rates'].items():
                l=target['pL'+e];r=target['pR'+e]
                self.assertAlmostEqual(alpha*r,(beta+.11)*l,places=12)
                self.assertAlmostEqual((beta+.11)*l,factor*(target['event_rate__idle_'+e]+.11*l),places=12)
            # Exact tensor factorization I_nodes x edge operator, stronger than a population check.
            for label,j in m['jumps']:
                if not label.startswith(('renew_','idle_')):continue
                block=j[:27,:27];self.assertLess(maxabs(j-sp.kron(sp.eye(8),block)),1e-12)
            self.assertLess(maxabs(m['rows'][m['index']['I_form_sink']]),1e-12)
            self.assertLess(maxabs(m['rows'][m['index']['I_idle_sink']]),1e-12)
        self.assertEqual(len(c['cases']),50);self.assertEqual(c['runtime_forecast']['main_steps'],2190000)
        qq0=measurement_model({**c['models']['QQ'],'J':0.},c['acceptance'])
        for key in ['I_hop_sink','I_form_sink','I_idle_sink']:
            self.assertLess(maxabs(qq0['rows'][qq0['index'][key]]),1e-12)

    def test_short_all_cases_and_export(self):
        c=config();c.update(required_free_disk_bytes=0,rho_start=0.,rho_interval=.5,positivity_interval=1.,pre_window=1.)
        for case in c['cases']:case.update(horizon=2.,damage_time=1.)
        c['runtime_forecast'].update(main_steps=sum(round(x['horizon']/x['dt']) for x in c['cases']),expected_seconds=100.,lower_seconds=0.,upper_seconds=600.)
        before=Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);src=root/'src';src.mkdir();(src/'config.json').write_text(json.dumps(c));job=root/'job';job.mkdir()
            try:
                os.chdir(job)
                with patch.dict(os.environ,{'VM_JOB_ID':'E002_local_test_v001','VM_SOURCE_COMMIT':'a'*40}):code=execute(c,src,time.monotonic())
            finally:os.chdir(before)
            m=json.loads((job/'report/metrics.json').read_text());checks=json.loads((job/'report/checks.json').read_text())
            self.assertEqual(code,0,[x for x in checks if not x['passed']]);self.assertEqual(len(m['cases']),50)
            self.assertEqual(m['primary_outcome'],'metric_undefined')
            self.assertLess((job/'report/RESULT.md').stat().st_size,24577)
            import csv
            for cid,r in m['cases'].items():
                with (job/'report/series'/f'{cid}.csv').open() as stream:rows=list(csv.DictReader(stream))
                ts=np.array([float(x['time']) for x in rows])
                f=np.array([float(x['sink_flux']) for x in rows])
                self.assertAlmostEqual(simpson(f,x=ts),r['recovery']['integrals']['sink_flux'],places=12)
            self.assertIsNone(m['cases']['RR_J0_link_coarse']['recovery']['Lambda_hop'])
            self.assertIsNone(m['cases']['RR_J0_link_coarse']['recovery']['shares'])
            artifacts={'files/'+str(p.relative_to(job/'report')):p.read_bytes() for p in (job/'report').rglob('*') if p.is_file()}
            self.assertTrue(verify(artifacts)['passed'])
            # Exercise the actual finalizer, not just the acceptance helper:
            # a newly computed runtime failure must withdraw a positive candidate.
            late=copy.deepcopy(m);late['provisional_outcomes']={k:'network_repair_controlled' for k in ['primary_outcome','RR2_outcome']}
            late_root=root/'late';(late_root/'report').mkdir(parents=True)
            late_checks=[copy.deepcopy(x) for x in checks if x['name']!='runtime_gate']
            finalize(late_root,late,late_checks,1000.)
            self.assertIn('runtime_gate',late['acceptance_blockers']);self.assertEqual(late['primary_outcome'],'metric_undefined')
            # The independent reader gets only the exported package. All mutations
            # below must fail; checks/metrics PASS labels alone are not evidence.
            for mutation in ['integral','baseline','extremum','missing_case','manifest_size','machine_share']:
                with self.subTest(mutation=mutation):
                    bad=dict(artifacts);mm=json.loads(bad['files/metrics.json']);rr=mm['cases']['PP_link_coarse']
                    if mutation=='integral':rr['recovery']['integrals']['sink_flux']+=1
                    if mutation=='baseline':rr['reference']['sink_flux']+=1
                    if mutation=='extremum':rr['recovery_statistics']['sink_flux']['max']+=1
                    if mutation=='missing_case':del mm['cases']['PP_link_coarse']
                    if mutation=='machine_share':rr['recovery']['machine_share']+=1
                    bad['files/metrics.json']=json.dumps(mm).encode()
                    if mutation=='manifest_size':
                        manifest=json.loads(bad['files/data_manifest.json']);manifest['full_files'][0]['bytes']+=1
                        bad['files/data_manifest.json']=json.dumps(manifest).encode()
                    with self.assertRaises(AssertionError):verify(bad)
            if os.environ.get('E002_TEST_KEEP_REPORT'):
                shutil.copytree(job/'report',os.environ['E002_TEST_KEEP_REPORT'],dirs_exist_ok=True)

if __name__=='__main__':unittest.main()
