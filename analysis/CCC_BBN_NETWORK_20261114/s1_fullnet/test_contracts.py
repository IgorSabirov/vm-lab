import copy
import importlib.util
from pathlib import Path
import sys
import unittest
import numpy as np
import common as c
import verify

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

adapter=module('clock_adapter',c.PKG.parent/'prelaunch/s1_adapter.py')
pipeline=module('research_pipeline',c.REPO/'infra/research_pipeline.py')

class Contracts(unittest.TestCase):
    def test_exact_clock_round_trip(self):
        u=np.geomspace(.01,2e6,50)
        for alpha in (0.,-1.5426109418e-18,-1e-7):
            clock=adapter.Clock(3.66,alpha)
            np.testing.assert_allclose(clock.to_standard(clock.to_scaled(u)),u,rtol=2e-15)
        with self.assertRaises(ValueError):adapter.Clock(3.66,1.).to_scaled(1.)
    def test_only_clock_mode_changes(self):
        params=[c.config_for(r,Path('/tmp/s1_contract_cache')) for r in ('CONTROL','S1','NEGATIVE')]
        self.assertEqual(params[0],params[1]);self.assertEqual(params[0],params[2])
    def test_frozen_envelope_and_negative_detection(self):
        env=verify.make_envelope();self.assertEqual(env,c.read(c.PKG/'ENVELOPE.json'))
        trace=c.read(c.REFERENCE_ROOT/'runs/F0/TRACE.json')
        self.assertTrue(verify.trace_compare(trace,trace,env)['pass'])
        altered=copy.deepcopy(trace);altered['eras'][2]['Y'][-1][0]+=.01
        self.assertGreater(verify.trace_compare(trace,altered,env)['max_ratio'],100)
    def test_trace_grid_damage_rejected(self):
        trace=c.read(c.REFERENCE_ROOT/'runs/F0/TRACE.json');other=copy.deepcopy(trace)
        other['eras'][1]['T_MeV'][3]*=1.001
        with self.assertRaises(ValueError):verify.trace_compare(trace,other,c.read(c.PKG/'ENVELOPE.json'))
    def test_dependency_cycle_and_unreviewed_execution_rejected(self):
        plan=c.read(c.PKG.parent/'pipeline/PIPELINE.json')
        pipeline.validate_definition(plan)
        cyclic=copy.deepcopy(plan);cyclic['stages'][0]['depends']=['S1_FULLNET']
        with self.assertRaises(ValueError):pipeline.validate_definition(cyclic)
        bad=copy.deepcopy(plan);bad['stages'][1]['implementation']='arbitrary_command'
        with self.assertRaises(ValueError):pipeline.validate_definition(bad)
        missing=copy.deepcopy(plan);missing['stages'][2]['automatic']=True
        with self.assertRaises(ValueError):pipeline.validate_definition(missing)
    def test_scientific_budgets_retained(self):
        plan=c.read(c.PKG/'PLAN.json')
        self.assertEqual(plan['numerical_budget'],c.read(c.PARENT_ROOT/'N1_PREREGISTRATION.json')['numerical_budget'])
        gate=verify.scalar_compare({'Y_n':3.996227098409122e-16},{'Y_n':3.9962849937164786e-16},plan)
        self.assertFalse(gate['Y_n']['pass'])
    def test_engineering_success_does_not_complete_numerical_contract(self):
        stage={'status_field':'numerical_status','expected_status':'CONDITIONAL_INVARIANCE_PASS'}
        self.assertFalse(pipeline.contract_complete({'status':'ENGINEERING_PASS','numerical_status':'CONDITIONAL_INVARIANCE_REVIEW_REQUIRED'},stage))
        self.assertFalse(pipeline.contract_complete({'status':'ENGINEERING_FAIL','numerical_status':'CONDITIONAL_INVARIANCE_PASS'},stage))
        self.assertTrue(pipeline.contract_complete({'status':'ENGINEERING_PASS','numerical_status':'CONDITIONAL_INVARIANCE_PASS'},stage))

if __name__=='__main__':unittest.main()
