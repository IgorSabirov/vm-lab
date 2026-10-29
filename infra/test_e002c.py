"""Numerical and mutation tests for E002c §9; small runs only, no VM launch."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from scipy import sparse as sp
from e002_exp.model import build_model,build_liouvillian,make_direct_rhs,adjoint_jump,maxabs
from e002c_exp.model import BASE,ONE,TWO,RR,operators,initial,build,sector_hamiltonian,dark_projectors
from e002c_exp.diagnostics import (partial_transpose,negativity,node_blocks,schmidt_alpha,witnesses,
                                   deterministic_eigh,conditional_fraction,quality)
from e002c_exp.fitting import search
from e002c_exp.engine import run_group,compare_pair,stationarity
from e002c_exp.task import run,preflight,calibration_cases,grouped,ROOT
from e002c_exp.export import manifest,export_case,extrema,compact_result
from e002c_exp.verify import verify,InvalidReport

CASE=dict(model='QS',phi_over_pi=0.,detuning=0.,dephasing=.05,dt=.01,horizon=2.,id='TEST',family='test')

def pure(v):return np.outer(v,v.conj())
def ket(i,d=8):v=np.zeros(d,complex);v[i]=1;return v

def repack(report):manifest(report,report.parent/'full')

class Algebra(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qs=build(CASE);cls.rr=build(dict(CASE,model='RR_QS'))
        cls.ic=build(dict(CASE,model='IC1_QS'),[.1,.2,.3])

    def test_pinned_baseline_exact(self):
        for model,pars in ((self.qs,BASE),(self.rr,dict(BASE,g=0.,gamma_r=0.,rr_rates=RR))):
            h,j,*_=build_model(pars)
            self.assertLess(maxabs(h-model['H']),1e-14)
            for (a,x),(b,y) in zip(j,model['jumps']):
                self.assertEqual(a,b);self.assertLess(maxabs(x-y),1e-14)

    def test_masks_and_partial_trace(self):
        o=operators();m=o['masks']
        self.assertLess(maxabs(sum(m)-sp.eye(27)),1e-14)
        for i in range(8):
            for j in range(8):self.assertLess(maxabs(m[i]@m[j]-(m[i] if i==j else 0*m[i])),1e-14)
        rng=np.random.default_rng(31);v=rng.normal(size=216)+1j*rng.normal(size=216);v/=np.linalg.norm(v)
        r=pure(v);blocks=node_blocks(r)
        self.assertTrue(np.allclose(blocks[0],np.einsum('aebe->ab',r.reshape(8,27,8,27))))
        self.assertTrue(np.allclose(blocks[0],blocks[1:].sum(axis=0)))
        self.assertGreater(np.trace(blocks[-1]).real,0)

    def test_single_excitation_polynomial(self):
        for bits in np.ndindex(2,2,2):
            a,b,c=bits;v=a+b+c-2*(a*b+a*c+b*c)+3*a*b*c
            self.assertEqual(v,int(sum(bits)==1))

    def test_dark_phase_and_isolation(self):
        d=(ket(0,3)-ket(1,3))/np.sqrt(2)
        k,p,iso,inter,info=dark_projectors(sector_hamiltonian(7))
        self.assertTrue(np.allclose(p@d,d));self.assertAlmostEqual(np.trace(iso).real,0)
        k,p,*_=dark_projectors(sector_hamiltonian(7,np.pi/2))
        self.assertAlmostEqual(np.trace(k).real,1);self.assertAlmostEqual(np.trace(p).real,0)
        _,p,*_=dark_projectors(sector_hamiltonian(7,np.pi))
        self.assertFalse(np.allclose(p@d,d));self.assertAlmostEqual(np.trace(p).real,1)
        _,p,iso,inter,_=dark_projectors(sector_hamiltonian(0))
        self.assertAlmostEqual(np.trace(iso).real,2);self.assertLess(np.linalg.norm(inter),1e-12)
        self.assertTrue(np.allclose(p,iso))

    def test_complex_V_and_detuning(self):
        h=sector_hamiltonian(6,theta=[.3,1.1,-.7],amplitudes=[1,1.3,.8])
        _,p,*_=dark_projectors(h);self.assertAlmostEqual(np.trace(p).real,1)
        h[1,1]=.4;_,p,*_=dark_projectors(h);self.assertAlmostEqual(np.trace(p).real,0)

    def test_gauge_covariance_and_tree_phase(self):
        for mask,phi in ((7,np.pi),(6,1.37),(3,-.7)):
            h=sector_hamiltonian(mask,phi);u=np.diag(np.exp(1j*np.array([.7,-.2,.31])))
            _,d,*_=dark_projectors(h);_,dg,*_=dark_projectors(u@h@u.conj().T)
            self.assertTrue(np.allclose(dg,u@d@u.conj().T,atol=1e-10))
            n=np.diag([0,0,1]);j=1j*(h@n-n@h);r=pure(np.array([1,1j,-1])/np.sqrt(3))
            self.assertAlmostEqual(np.trace(r@j).real,np.trace(u@r@u.conj().T@u@j@u.conj().T).real)
        h0=sector_hamiltonian(6,0);h1=sector_hamiltonian(6,1.37)
        self.assertTrue(np.allclose(np.linalg.eigvalsh(h0),np.linalg.eigvalsh(h1)))

    def test_phase_sign_matches_full_model(self):
        m=build(dict(CASE,phi_over_pi=.5,detuning=.3));idx=ONE*27+26
        h=m['H'].toarray()[np.ix_(idx,idx)]
        target=sector_hamiltonian(7,np.pi/2,.3)
        self.assertTrue(np.allclose(h,target))
        self.assertFalse(np.allclose(h,sector_hamiltonian(7,-np.pi/2,.3)))

    def test_liouvillian_direct_and_balances(self):
        rng=np.random.default_rng(7);v=rng.normal(size=216)+1j*rng.normal(size=216);v/=np.linalg.norm(v);r=pure(v).reshape(-1,order='F')
        for m in (self.qs,self.rr,self.ic):
            rhs=make_direct_rhs(m['H'],m['jumps'])
            self.assertLess(np.max(abs(m['L']@r-rhs(r))),1e-12)
            self.assertLess(max(m['checks'].values()),1e-10)
        o=operators();feed=[c for k,c in self.ic['jumps'] if k.startswith('feed')]
        self.assertEqual(len(feed),3)
        for c in feed:
            self.assertLess(maxabs(adjoint_jump(c,sum(o['pr'])+sum(o['pl']))),1e-12)
            for n in o['n']:self.assertLess(maxabs(adjoint_jump(c,n)),1e-12)

    def test_frozen_dark_is_not_pumped_steady(self):
        h=np.zeros((8,8),complex);h[np.ix_(ONE,ONE)]=sector_hamiltonian(7)
        # Full number-conserving hopping operator, including two excitations.
        o=operators();hfull=build(CASE)['H'].toarray();h=hfull[26::27,26::27]
        sink=sp.csr_matrix(o['up'][2].getH().toarray()[26::27,26::27]*np.sqrt(.5))
        source=sp.csr_matrix(o['up'][0].toarray()[26::27,26::27]*np.sqrt(.5))
        L=build_liouvillian(sp.csr_matrix(h),[('sink',sink)])
        d=(ket(4)-ket(2))/np.sqrt(2)
        for v in (ket(0),d):self.assertLess(np.linalg.norm(L@pure(v).reshape(-1,order='F')),1e-12)
        self.assertAlmostEqual(np.linalg.norm(source@d)**2,.25)
        pumped=build_liouvillian(sp.csr_matrix(h),[('sink',sink),('source',source)])
        self.assertGreater(np.linalg.norm(pumped@pure(d).reshape(-1,order='F')),1e-3)
        nullity=int(np.sum(abs(np.linalg.eigvals(pumped.toarray()))<1e-9))
        self.assertEqual(nullity,1)  # checked spectrum, not inferred from jump activity

class Entanglement(unittest.TestCase):
    def test_Bell_W_GHZ_and_product(self):
        bell=(ket(4)-ket(2))/np.sqrt(2);w=(ket(4)+ket(2)+ket(1))/np.sqrt(3);ghz=(ket(0)+ket(7))/np.sqrt(2)
        self.assertAlmostEqual(schmidt_alpha(bell),1)
        self.assertAlmostEqual(schmidt_alpha(w),2/3)
        self.assertAlmostEqual(schmidt_alpha(ghz),.5)
        pair=np.trace(pure(bell).reshape(2,2,2,2,2,2),axis1=2,axis2=5).reshape(4,4)
        self.assertAlmostEqual(negativity(pair,[2,2],[0])[0],.5)
        _,a,o=witnesses(pure(bell));self.assertGreaterEqual(min(a-o),-1e-12)
        _,a,o=witnesses(pure(w));self.assertLess(min(a-o),-.3)
        self.assertLess(schmidt_alpha(ghz)-np.vdot(ghz,pure(ghz)@ghz).real,0)
        product=np.ones(8)/np.sqrt(8);_,a,o=witnesses(pure(product))
        self.assertGreaterEqual(min(a-o),-1e-12)
        # Postselecting this product onto ONE would produce W; evaluate on the full state.
        self.assertGreater(schmidt_alpha(w)-np.vdot(w,pure(product)@w).real,0)

    def test_PT_involution_and_known_spectrum(self):
        r=pure((ket(0)+ket(7))/np.sqrt(2))
        for cut in range(3):
            self.assertTrue(np.allclose(partial_transpose(partial_transpose(r,[2,2,2],[cut]),[2,2,2],[cut]),r))
            self.assertAlmostEqual(negativity(r,[2,2,2],[cut])[0],.5)
        self.assertEqual(negativity(np.eye(8)/8,[2,2,2],[0])[0],0)

    def test_deterministic_degeneracy(self):
        a=np.eye(3)/3
        self.assertTrue(np.allclose(deterministic_eigh(a),np.eye(3)))
        v=deterministic_eigh(np.diag([.1,.2,.2]));self.assertTrue(np.allclose(v.conj().T@v,np.eye(3)))

    def test_small_weight_null_and_physicality_failure(self):
        self.assertIsNone(conditional_fraction(1e-8,1e-6)['value'])
        self.assertEqual(conditional_fraction(.1,.2)['value'],.5)
        m=build(CASE);r=initial().reshape(216,216,order='F');r[0,0]-=.001;r[-1,-1]+=.001
        with self.assertRaises(ValueError):quality(r,m['L'])

class Planning(unittest.TestCase):
    def test_declared_plan(self):
        p=json.loads((ROOT/'experiments/e002c/plan.json').read_text())
        self.assertEqual(len(p['cases']),72);self.assertEqual(sum(x['main_steps'] for x in p['cases']),1600000)
        self.assertEqual(len(p['conditional_ic_cases']),24);self.assertEqual(sum(x['main_steps'] for x in p['conditional_ic_cases']),560000)
        self.assertEqual(len(calibration_cases()),8);self.assertEqual(len(grouped(p['cases'])),64)
        self.assertEqual(sum(len(g)==2 for g in grouped(p['cases'])),8)

    def test_optimizer_budget_no_hop(self):
        seen=[]
        def ev(alpha,index):seen.append(index);return np.r_[alpha,alpha],True,None
        r=search(ev,np.ones(6)*.2,np.ones(3)*.1)
        self.assertLessEqual(r['calls'],48);self.assertEqual(r['computations'],len(seen))
        self.assertEqual(r['calls'],r['computations']+r['cache_hits']);self.assertFalse(r['hop_in_objective'])
        valid=[x for x in r['records'] if x['valid']]
        chosen=min(valid,key=lambda x:(x['maximum_error'],x['objective'],tuple(x['alpha'])))
        self.assertEqual(r['selected']['alpha'],chosen['alpha'])
        def fail(alpha,index):return np.zeros(6),False,'nonstationary'
        self.assertIsNone(search(fail,np.ones(6),np.ones(3)*.1)['selected'])

    def test_missing_calibration_forecast_disk_blocks(self):
        identity={'source_commit':'a'*40}
        for cfg in ({},dict(mode='production',run_id='X'),dict(mode='calibration',run_id='X',forecast={})):
            with self.assertRaises(ValueError):preflight(cfg,identity,10*1024**3)
        cfg=json.loads((ROOT/'config.json').read_text())
        with self.assertRaises(ValueError):preflight(cfg,identity,100)
        self.assertTrue(preflight(cfg,identity,10*1024**3))

    def test_pair_extension_both_or_neither(self):
        calls=[]
        class Fake:
            def __init__(self,case,*a):self.case=case;self.failure=None
            def advance(self,t):calls.append((self.case['id'],t));return {'pass_gate':self.case['id']=='fine'}
            def finish(self):return self.case
        cases=[dict(id='coarse',horizon=200),dict(id='fine',horizon=200)]
        with patch('e002c_exp.engine.Trajectory',Fake):run_group(cases,Path('.'))
        self.assertEqual(calls,[('coarse',200),('fine',200),('coarse',400.),('fine',400.)])

class EndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)
        cls.metrics,cls.checks=run(dict(mode='smoke',run_id='LOCAL_E002c_SMOKE',local_source_commit='LOCAL_TEST',forecast={}),cls.root)
        cls.report=cls.root/'report'
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_smoke_rk4_and_reader(self):
        self.assertEqual(self.metrics['work']['steps'],1800)
        self.assertTrue(all(x['pass_gate'] for x in self.checks['pairs'].values()))
        self.assertEqual(len(verify(self.report)['cases']),6)

    def mutated(self,mutate):
        import shutil
        with tempfile.TemporaryDirectory() as td:
            dst=Path(td);shutil.copytree(self.report,dst/'report');(dst/'full').mkdir()
            mutate(dst/'report');repack(dst/'report')
            with self.assertRaises((InvalidReport,KeyError,FileNotFoundError,ValueError)):verify(dst/'report')

    def test_hash_and_missing_file_mutations(self):
        p=self.report/'series/SMOKE_QS_0.01.npz';original=p.read_bytes()
        try:
            p.write_bytes(original+b'corruption')
            with self.assertRaises(InvalidReport):verify(self.report)
        finally:p.write_bytes(original)
        self.mutated(lambda d:(d/'series/SMOKE_QS_0.01.npz').unlink())

    def change_npz(self,report,relative,change):
        p=report/relative
        with np.load(p,allow_pickle=False) as z:a={k:z[k] for k in z.files}
        change(a);np.savez(p,**a)

    def test_missing_mask_and_double_current(self):
        sc=json.loads((self.report/'schema.json').read_text());sn=sc['series']
        for col in ('p_m0','h'):
            self.mutated(lambda d:self.change_npz(d,'series/SMOKE_QS_0.01.npz',lambda a:a['values'].__setitem__((-1,sn.index(col)),a['values'][-1,sn.index(col)]+.1)))

    def test_wrong_PT_and_witness_sign(self):
        sc=json.loads((self.report/'schema.json').read_text());dn=sc['diagnostics']
        for col in ('N_s0_cut0','W_s0'):
            self.mutated(lambda d:self.change_npz(d,'diagnostics/SMOKE_QS_0.01.npz',lambda a:a['values'].__setitem__((-1,dn.index(col)),a['values'][-1,dn.index(col)]+.1)))
        self.mutated(lambda d:self.change_npz(d,'evidence/SMOKE_QS_0.01.npz',lambda a:a['alpha'].__setitem__((-1,0,0),a['alpha'][-1,0,0]+.1)))

    def test_wrong_counter_and_unfinished_export(self):
        def change(d,file,fn):
            p=d/file;a=json.loads(p.read_text());fn(a);p.write_text(json.dumps(a))
        self.mutated(lambda d:change(d,'metrics.json',lambda a:a['cases'][0].__setitem__('steps',99)))
        self.mutated(lambda d:change(d,'checks.json',lambda a:a.__setitem__('export_complete',False)))

class Orchestration(unittest.TestCase):
    def test_production_search_failure_retains_screen(self):
        self.exercise(False)

    def test_production_match_adds_exact_declared_transfer(self):
        self.exercise(True)

    def exercise(self,matched):
        from e002c_exp import task
        target=json.loads((ROOT/'data/e002b_targets.json').read_text())['candidates']['QS']
        refs={**{'pL'+e:target['edges'][e]['pL'] for e in ('01','12','02')},
              **{'ell'+e:target['edges'][e]['loss'] for e in ('01','12','02')},'h':.1,'F':.1}
        recorded=[]
        def fake_group(cases,full,alpha,extend,disk_floor):
            recorded.extend(cases)
            return [dict(summary=dict(case=c,horizon=200.,steps=round(200/c['dt']),rhs_calls=4*round(200/c['dt']),
                  scalar_records=1001,diagnostic_records=101,snapshots=11,reference=refs,failed=None,
                  stationarity={'pass_gate':True},tau90=20.,state_status='stationary'),names=[],dnames=[]) for c in cases]
        fit=dict(computations=48,executed_steps=480000,selected={'alpha':[.1]*3} if matched else None,
                 selected_alpha_sha256='a'*64)
        def summ(results,pairs,mode):return dict(cases=[r['summary'] for r in results],joint=[],gaps=[],phase=[],interactions=[])
        with tempfile.TemporaryDirectory() as td, patch.object(task,'preflight',return_value=True), \
             patch.object(task.fitting,'perform',return_value=fit), patch.object(task,'run_group',side_effect=fake_group), \
             patch.object(task,'compare_pair',return_value={'pass_gate':True}), \
             patch.object(task,'export_case',return_value={'h_t_positive':[0.,.2,.1,2.,1000]}), \
             patch.object(task,'summarize',side_effect=summ), patch('e002c_exp.verify.verify',return_value={}):
            m,c=task.run(dict(mode='production',run_id='MOCK_ONLY',local_source_commit='LOCAL_TEST',
                  forecast={'seconds_per_step':.002,'fixed_seconds':90}),td)
            self.assertEqual(len(recorded),98 if matched else 72)
            self.assertEqual(m['work']['steps'],2700000 if matched else 2080000)
            self.assertEqual(m['ic_status'],'transport_close_5pct' if matched else 'no_match_found_within_declared_search')
            self.assertEqual(sum(x['model'] in ('QS','RR_QS') for x in recorded),72)
            self.assertTrue(c['work_volume_pass'])

if __name__=='__main__':unittest.main()
