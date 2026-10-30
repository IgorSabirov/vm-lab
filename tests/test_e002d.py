import json,os,shutil,tempfile,time,unittest
from pathlib import Path
import numpy as np
from scipy import sparse as sp
from e002_exp.model import build_liouvillian,make_direct_rhs,rk4,maxabs
from e002c_exp.model import build as base_build,initial
from e002c_exp.diagnostics import node_blocks
from e002d_exp.model import build,jump_diagonals,damping,consequence_map
from e002d_exp.plan import case,cases,counts
from e002d_exp.task import run
from e002d_exp.verify import verify
from e002d_exp.analysis import analyze

class E002dTests(unittest.TestCase):
    def test_plan(self):
        self.assertEqual(counts('production'),dict(trajectories=36,steps=1160000,rhs_calls=4640000))
        self.assertEqual(counts('production',400.)['steps'],2320000)
        self.assertEqual(counts('calibration')['steps'],9000)
        cs=cases('production');self.assertEqual(sum(c['dt']==.005 for c in cs),22)
        self.assertEqual(len(set(c['id'] for c in cs)),36)

    def test_consequence_independent_composite(self):
        for x in consequence_map().values():self.assertLess(x['difference_error'],1e-12)
        ds=jump_diagonals('AB','T',.1)
        independent=damping(ds);wrong=damping([('wrong',sum(d for _,d in ds))])
        self.assertGreater(np.max(abs(independent-wrong)),.05)
        self.assertTrue(np.array_equal(np.diag(independent),np.zeros(216)))

    def test_baseline_and_full_jump_reference(self):
        rng=np.random.default_rng(17);a=rng.normal(size=(216,6))+1j*rng.normal(size=(216,6))
        rho=a@a.conj().T;rho/=np.trace(rho);v=rho.reshape(-1,order='F')
        for model in ('QS','RR_QS'):
            c=case(model,'base','base',0.,.005,2.);old=base_build(c);new=build(c)
            self.assertEqual(maxabs(old['L']-new['L']),0.)
            self.assertEqual(maxabs(old['rows']-new['rows'][:len(old['names'])]),0.)
            for target,kind in [('A','T'),('A','C'),('B','T'),('B','C'),('AB','T'),('AB','C')]:
                cc=case(model,target,kind,.2,.005,2.);m=build(cc)
                independent=build_liouvillian(m['H'],m['jumps'])
                self.assertLess(maxabs(m['L']-independent),1e-12)
                self.assertEqual(maxabs(m['H']-old['H']),0.)
                self.assertLess(np.max(abs(m['L']@v-make_direct_rhs(m['H'],m['jumps'])(v))),1e-12)
                nodes=node_blocks(rho);values=m['rows']@v
                for key,mask,a,b in [('A',2,5,6),('B',4,3,6),('N1_A',2,1,2),('N1_B',4,1,4)]:
                    actual=values[m['names'].index('C_'+key+'_re')]+1j*values[m['names'].index('C_'+key+'_im')]
                    self.assertLess(abs(actual-nodes[mask+1,a,b]),1e-12)

    def test_end_to_end_and_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            config=dict(mode='smoke',run_id='E002d_LOCAL_SMOKE_001',local_source_commit='LOCAL_TEST',
                forecast=dict(expected_seconds=30.,lower_seconds=0.,upper_seconds=120.))
            metrics,checks=run(config,tmp)
            self.assertEqual(checks['technical_status'],'PASS')
            self.assertEqual(metrics['work']['actual']['steps'],1200)
            self.assertTrue(all(p['pass_gate'] for p in metrics['analysis']['pairs'].values()))
            report=Path(tmp)/'report';self.assertEqual(verify(report)['status'],'PASS')
            p=next((report/'windows').glob('*.npz'));data=p.read_bytes();p.write_bytes(data+b'X')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):verify(report)

    def test_signed_effect_and_failed_refinement(self):
        results=[]
        for model in ('QS','RR_QS'):
            for dt in (.005,.01):
                for target,kind,value in [('base','base',1.),('A','T',.8 if model=='QS' else 1.),('A','C',1.)]:
                    c=case(model,target,kind,0. if target=='base' else .1,dt,200.)
                    times=np.arange(190.,202.,2.)
                    results.append(dict(summary=dict(case=c,horizon=200.,stationarity={'pass_gate':True},refinement_status='not_refined'),
                        names=['h'],dnames=['dummy'],series=np.column_stack([times,np.full(6,value)]),
                        diagnostics=np.column_stack([times,np.zeros(6)])))
        row=analyze(results,'production')['comparisons'][0]
        self.assertAlmostEqual(row['Q'],-.2);self.assertEqual(row['status'],'RESOLVED_NEGATIVE')
        r=next(r for r in results if r['summary']['case']['model']=='QS' and r['summary']['case']['kind']=='T' and r['summary']['case']['dt']==.01)
        r['series'][:,1]+=.01
        self.assertEqual(analyze(results,'production')['comparisons'][0]['status'],'REFINEMENT_FAILED')

if __name__=='__main__':unittest.main()
