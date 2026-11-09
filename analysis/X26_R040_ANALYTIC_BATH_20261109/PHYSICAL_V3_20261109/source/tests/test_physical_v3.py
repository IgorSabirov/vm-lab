import copy
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from x26r040.physical import *
from x26r040.add_mapping import combinatorial_invariants
from x26r040.integrated import preflight_full_pipeline

ROOT=Path(__file__).resolve().parents[1]

class V3(unittest.TestCase):
    def setUp(self): self.m=json.loads((ROOT/'PHYSICAL_MANIFEST.json').read_text())
    def test_manifest_and_legacy_rejection(self):
        self.assertTrue(preflight(self.m)['submit_allowed'])
        self.assertFalse(preflight_full_pipeline({'schema':1})['submit_allowed'])
        self.m['phi']['t0']=None
        self.assertFalse(preflight(self.m)['submit_allowed'])
    def test_bad_finite_input(self):
        self.m['accuracy'][0]['rtol']=float('inf')
        self.assertFalse(preflight(self.m)['submit_allowed'])
    def test_K_counterexamples(self):
        self.assertEqual(combinatorial_invariants([5,10])['K'],0)
        self.assertEqual(combinatorial_invariants([9,6])['K'],2)
        self.assertFalse(combinatorial_invariants([1,2])['E0'])
    def test_half_counts_and_geometry(self):
        cs=prepare_cases(self.m)
        for c in cs:
            for s in c['steps']:
                self.assertEqual(s['invariants_before']['pure_half_counts'],s['invariants_after']['pure_half_counts'])
        phi=cs[0]['phi'][1]
        self.assertEqual(phi['effective_barriers']['V2'],phi['effective_barriers']['12'])
        self.assertEqual(cs[0]['invariants']['pure_half_counts'],cs[1]['invariants']['pure_half_counts'])
    def test_transfer_rejects_inf_and_bad_unitary(self):
        d=np.array([1,-1,0])/np.sqrt(2);p=projector_from_dark_vector(d)
        with self.assertRaises(ValueError):check_moving_projector_transport(p,p,2*np.eye(3),float('inf'))
        with self.assertRaises(ValueError):projector_from_dark_vector(d*1.000005)
        t=np.eye(3);t[[0,2]]=t[[2,0]]
        self.assertFalse(check_moving_projector_transport(p,p,t)['projector_intertwining_pass'])
    def test_complex_json_roundtrip(self):
        a=np.array([[1+2j,3],[4,5-6j]])
        b=decode(json.loads(json.dumps(encode({'a':a,'b':[1j]}))))
        np.testing.assert_array_equal(a,b['a']);self.assertEqual(b['b'][0],1j)
    def test_workload_unique(self):
        ts=tasks(self.m)
        self.assertEqual(len(ts),249);self.assertEqual(len({x['id'] for x in ts}),249)
        self.assertEqual(sum(t['kind']=='cycle' for t in ts),180)
    def test_forecast_covers_every_frozen_task(self):
        from x26r040.physical_cli import calibration_tasks,forecast
        ts=tasks(self.m);selected=calibration_tasks(ts)
        self.assertEqual(len(selected),104)
        measurements=[{'task':t,'seconds':.01*(1+t.get('N',1))} for t in selected]
        f=forecast(self.m,ts,measurements,.5,.2)
        self.assertEqual({x['task_id'] for x in f['terms']},{x['id'] for x in ts})
        self.assertGreater(f['lower_seconds'],0)
        self.assertLess(f['lower_seconds'],f['expected_seconds'])
        self.assertGreater(f['upper_seconds'],f['expected_seconds'])
    def test_continuous_state_chain_and_balance(self):
        # Tiny isolated implementation fixture, not main physical workload.
        self.m['psi']['duration']=.4;self.m['psi']['hold_duration']=.3;self.m['samples']=5
        cs=prepare_cases(self.m)
        with tempfile.TemporaryDirectory() as td:
            for route in ['coherent','thermal']:
                task={'id':route,'kind':'cycle','case':'active_word','route':route,'control':'active','N':16,'res':1}
                r=cycle(self.m,cs[0],task,Path(td))
                self.assertTrue(r['technical_pass'],r['checks'])
                data=np.load(Path(td)/r['states_file']);T=data['T']
                np.testing.assert_allclose(data['rho_after'],T@data['rho_load']@T.conj().T,atol=1e-11)
                self.assertLess(abs(r['checks']['energy_balance_residual']),2e-6)
                self.assertLessEqual(r['resource']['consumed'],r['resource']['reserved_fuel'])
                dump(Path(td)/'roundtrip.json',r)
    def test_negative_controls(self):
        self.m['psi']['duration']=.4;self.m['psi']['hold_duration']=.3;self.m['samples']=5
        cs=prepare_cases(self.m)
        with tempfile.TemporaryDirectory() as td:
            for route in ['coherent','thermal']:
                t={'id':route,'kind':'cycle','case':'active_word','route':route,'control':'loader_off','N':16,'res':1}
                r=cycle(self.m,cs[0],t,Path(td));self.assertLess(abs(r['p_final']),1e-9)
                t['control']='no_resource';r=cycle(self.m,cs[0],t,Path(td))
                self.assertEqual(r['physical_status'],'RESOURCE_BLOCKED_BEFORE_PREPARATION')
                self.assertFalse(r['evolution_executed'])
    def test_ramp_null_and_moving(self):
        with tempfile.TemporaryDirectory() as td:
            for fam in ['g_only','moving_dark']:
                t={'id':fam,'kind':'ramp','family':fam,'duration':.3,'N':16,'res':1}
                r=ramp(self.m,t,Path(td));self.assertTrue(r['technical_pass'],r)
                if fam=='g_only':self.assertLess(abs(r['leakage_final']),1e-9)
    def test_merge_roles_remain_distinct_internal_modes(self):
        c=load_verified_carrier(ROOT/'carrier.py')
        s=advance_one_add_step([1,2,0,0],{'V':0,'1':1,'2':3},c.full_step)
        self.assertEqual(s['anchors_after']['V'],s['anchors_after']['1'])
        law=copy.deepcopy(self.m['phi']);law['radius']=0
        p=map_local_motifs_to_r040(s['word_after'],s['anchors_after'],law)
        self.assertEqual(R040Parameters(**p['parameters']).H3.shape,(3,3))

if __name__=='__main__':unittest.main()
