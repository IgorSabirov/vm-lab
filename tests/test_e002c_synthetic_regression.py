"""Protocol regressions with no engine/run imports and no evolution of trajectories."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np
from e002c_exp.ic_status import decide_ic_status
from e002c_exp.comparability import comparison_gate
from e002c_exp.diagnostics import coherence_values,coherence_quality
from e002c_exp.analysis import comparison_tables
from e002c_exp.verify import verify,verify_protocol_tables,InvalidReport
from fixtures_e002c import fixture,make_case,repack

class StatusTable(unittest.TestCase):
    def test_all_valid_transitions_and_boundaries(self):
        selected={'selected':{'alpha':[.1]*3}};valid={'structural_pass':True}
        rows=[(None,None,None,'not_run','not_evaluated'),
          ({'selected':None},None,None,'no_match_found_within_declared_search','not_evaluated'),
          (selected,None,None,'structural_candidate_found_validation_pending','not_evaluated'),
          (selected,{'structural_pass':False},None,'structural_candidate_rejected_by_validation','not_evaluated'),
          (selected,valid,None,'structural_PASS','transport_pending'),
          (selected,valid,{'evaluable':False},'structural_PASS','transport_not_evaluable')]
        for error,status in ((0.,'transport_close_5pct'),(.05,'transport_close_5pct'),(np.nextafter(.05,1),'transport_close_10pct'),(.10,'transport_close_10pct'),(np.nextafter(.10,1),'structural_matched_hop_mismatch')):
            rows.append((selected,valid,dict(evaluable=True,relative_error=float(error)),'structural_PASS',status))
        for f,v,t,s,tr in rows:
            with self.subTest(s=s,tr=tr,t=t):self.assertEqual(decide_ic_status(f,v,t),dict(ic_structural_status=s,ic_transport_status=tr))

    def test_impossible_transitions_fail(self):
        rows=[(None,{'structural_pass':True},None),({'selected':None},None,{'evaluable':False}),
              ({'selected':{}},{'structural_pass':False},{'evaluable':False}),
              ({'selected':{}},{'structural_pass':True},{'evaluable':True,'relative_error':float('nan')})]
        for args in rows:
            with self.subTest(args=args),self.assertRaises(ValueError):decide_ic_status(*args)

class CoherenceContract(unittest.TestCase):
    def test_physical_complex_block_and_sign(self):
        b=np.zeros((9,8,8),complex);b[8,2,2]=b[8,4,4]=.25;b[8,2,4]=.2+.1j;b[8,4,2]=.2-.1j
        self.assertGreaterEqual(np.linalg.eigvalsh(b[8])[0],-1e-14)
        names,values=coherence_values(b);v=dict(zip(names,values))
        self.assertEqual(v['C01_m7_re'],.2);self.assertEqual(v['C01_m7_im'],.1)
        self.assertEqual(v['c01_m7_re'],.4);self.assertEqual(v['c01_m7_im'],.2)
        self.assertNotEqual(b[8,2,4],b[8,4,2])
        b[8,2,4]=.25+.1j;b[8,4,2]=.25-.1j
        self.assertLess(np.linalg.eigvalsh(b[8])[0],0.)  # The proposed .25+.1i fixture is not PSD.

    def test_floor_and_low_weight_boundary(self):
        for weight,quality,defined in ((1e-6,'undefined',False),(np.nextafter(1e-6,1),'low_weight',True),(np.nextafter(1e-5,0),'low_weight',True),(1e-5,'ok',True)):
            b=np.zeros((9,8,8),complex);b[8,2,2]=b[8,4,4]=weight/2;b[8,2,4]=.2j*weight;b[8,4,2]=-.2j*weight
            n,v=coherence_values(b);v=dict(zip(n,v))
            self.assertEqual(coherence_quality(weight),quality);self.assertTrue(np.isfinite(v['C01_m7_im']))
            self.assertEqual(np.isfinite(v['c01_m7_im']),defined)
            if defined:self.assertAlmostEqual(v['c01_m7_im'],.2)

    def test_psd_tolerance_is_not_conditional_accuracy(self):
        w=np.nextafter(1e-6,1);a=np.array([[w/2,w/2+1e-8],[w/2+1e-8,w/2]])
        self.assertAlmostEqual(np.linalg.eigvalsh(a)[0],-1e-8)
        self.assertGreater(abs(a[0,1]/w),.5)

class ComparisonContract(unittest.TestCase):
    def summary(self,id='s',T=200.,stationary=True,refinement='passed',failed=None,model='QS',phi=0.,gamma=.05):
        ref=dict(h=0.,I01=0.,I12=0.,I02=0.,pL01=.2,pL12=.2,pL02=.2,ell01=.02,ell12=.02,ell02=.02,inventory=2.,pump=.1,**{'break':.1})
        return dict(case=dict(id=id,model=model,dt=.01,phi_over_pi=phi,detuning=0.,dephasing=gamma,family='synthetic'),horizon=T,reference=ref,transition_reference=ref.copy(),stationarity=dict(pass_gate=stationary),refinement_status=refinement,failed=failed)

    def test_comparison_classes(self):
        a=self.summary()
        rows=[(self.summary(T=200),True),(self.summary(T=400),False),(self.summary(stationary=False),False),
              (self.summary(refinement='failed'),False),(self.summary(failed='unphysical'),False)]
        for b,expected in rows:self.assertEqual(comparison_gate([a,b],True)['comparable'],expected)
        b=self.summary(T=400,stationary=False)
        self.assertTrue(comparison_gate([a,b],True,'transition_200')['comparable'])
        self.assertEqual(comparison_gate([a,self.summary(refinement='not_refined')],True)['evidence_level'],'SCREENING_ONLY')
        self.assertFalse(comparison_gate([a,self.summary(refinement='not_refined')],False)['comparable'])

    def test_every_comparison_section_and_mirrored_verifier(self):
        cases=[]
        for model in ('QS','RR_QS'):
            for gamma in (0.,.05):
                for phi in (0.,.5):cases.append(self.summary(f'{model}_{phi}_{gamma}',T=400 if model=='QS' and phi==0 and gamma==.05 else 200,model=model,phi=phi,gamma=gamma))
        cases += [self.summary(f'QS_{phi}',model='QS',phi=phi) for phi in (-.5,1.)]
        m=dict(cases=cases,**comparison_tables(cases,True,1e-5),transition_comparisons=comparison_tables(cases,True,1e-5,'transition_200'),
               fit=None,ic_validation=None,ic_transport=None,**decide_ic_status(None,None))
        checks={'pairs':{'synthetic_gate':{'pass_gate':True,'errors':{}}}}
        verify_protocol_tables(m,checks)
        for section in ('gaps','phase','interactions','gap_phase','flux_spans'):
            rows=[r for r in m[section] if not r['comparison']['comparable']]
            self.assertTrue(rows,section);self.assertEqual(rows[0]['status'],'not_comparable')
            bad=copy.deepcopy(m);next(r for r in bad[section] if not r['comparison']['comparable'])['status']='flux_response'
            with self.subTest(section=section),self.assertRaises(InvalidReport):verify_protocol_tables(bad,checks)
        self.assertTrue(all(r['comparison']['comparable'] for r in m['transition_comparisons']['phase']))
        self.assertTrue(all(r['status']=='no_resolved_finite_time_difference' for r in m['transition_comparisons']['phase']))

class ReportFixture(unittest.TestCase):
    def mutate(self,mutation,results=None,rejected=False):
        with tempfile.TemporaryDirectory() as td:
            report=fixture(td,results,rejected);verify(report);mutation(report);repack(report)
            with self.assertRaises((InvalidReport,ValueError,KeyError)):verify(report)

    def npz(self,p,mutate):
        with np.load(p,allow_pickle=False) as z:arrays={k:z[k] for k in z.files}
        mutate(arrays);np.savez(p,**arrays)
    def obj(self,p,mutate):
        a=json.loads(p.read_text());mutate(a);p.write_text(json.dumps(a,allow_nan=False))

    def test_one_case_full_fixture_including_certificates(self):
        with tempfile.TemporaryDirectory() as td:
            p=fixture(td);self.assertEqual(verify(p)['status'],'VERIFIED_EXPORTED_ARRAYS')
        self.assertNotIn('e002c_exp.engine',sys.modules);self.assertNotIn('e002c_exp.task',sys.modules)

    def test_null_contract_and_wrong_complex_conjugate(self):
        def edit(report,col,amount):
            dn=json.loads((report/'schema.json').read_text())['diagnostics']
            self.npz(report/'diagnostics/QS_coarse.npz',lambda a:a['values'].__setitem__((0,dn.index(col)),amount))
        self.mutate(lambda p:edit(p,'c01_m7_im',.2))
        self.mutate(lambda p:edit(p,'c01_m6_im',np.nan))
        # Swap signs of BOTH numerator and conditional value: ratio alone would pass.
        def conjugate(report):
            dn=json.loads((report/'schema.json').read_text())['diagnostics']
            def change(a):
                for col in ('C01_m6_im','c01_m6_im'):a['values'][:,dn.index(col)]*=-1
            self.npz(report/'diagnostics/QS_coarse.npz',change)
        self.mutate(conjugate)

    def test_rejected_candidate_not_no_match(self):
        self.mutate(lambda p:self.obj(p/'metrics.json',lambda a:a.__setitem__('ic_structural_status','no_match_found_within_declared_search')),rejected=True)

    def test_mixed_horizon_gap_and_transition(self):
        results=[make_case('Q0',dt=.01),make_case('Q1',dt=.005),make_case('R0','RR_QS',dt=.01,horizon=400),make_case('R1','RR_QS',dt=.005,horizon=400)]
        self.mutate(lambda p:self.obj(p/'metrics.json',lambda a:a['gaps'][0].__setitem__('status','transport_gap')),results)

    def test_false_dt_pass(self):
        results=[make_case('Q0',dt=.01),make_case('Q1',dt=.005)]
        def edit(p):
            dn=json.loads((p/'schema.json').read_text())['diagnostics'];j=dn.index('rhs')
            self.npz(p/'diagnostics/Q1.npz',lambda a:a['values'].__setitem__((0,j),.1))
            self.obj(p/'extrema.json',lambda a:a['Q1']['diagnostic'][j-1].__setitem__(2,.1))
        self.mutate(edit,results)

    def test_current_and_mask_current_mutations(self):
        def edit(p,section,col):
            sc=json.loads((p/'schema.json').read_text());j=sc[section].index(col)
            self.npz(p/section/'QS_coarse.npz',lambda a:a['values'].__setitem__((0,j),.1))
        self.mutate(lambda p:edit(p,'series','h'));self.mutate(lambda p:edit(p,'diagnostics','I12_m7'))

if __name__=='__main__':unittest.main()
