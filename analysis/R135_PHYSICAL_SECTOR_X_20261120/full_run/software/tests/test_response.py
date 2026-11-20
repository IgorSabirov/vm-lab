import json
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from r135.response import (generator_response,equilibrium_response,relaxation_estimate,
                           check_linear_response,analyze_two_time,run,validate_generator)


class ResponseTests(unittest.TestCase):
    def test_known_two_state_decay_and_kubo(self):
        q=[[-2,2],[3,-3]];pi=[.6,.4];t=np.linspace(0,2,501)
        y=generator_response(q,[0,1],[-1,1],t,pi)
        np.testing.assert_allclose(y,np.exp(-5*t),atol=2e-15)
        result=relaxation_estimate(t,y)
        self.assertTrue(result['resolved']);self.assertAlmostEqual(result['tau'],.2,places=10)
        self.assertLess(abs(result['integral_tau']-.2),1e-5)
        r=equilibrium_response(q,pi,[0,1],t,2)
        np.testing.assert_allclose(r,.6*np.exp(-5*t),atol=2e-15)

    def test_unresolved_tail_censored_without_fictitious_time(self):
        t=np.linspace(0,.1,40);r=relaxation_estimate(t,np.exp(-t/10))
        self.assertFalse(r['resolved']);self.assertIsNone(r['tau']);self.assertGreater(r['tau_lower_bound'],0)
        self.assertIn('horizon',r['reason'])
        flat=relaxation_estimate(t,np.ones_like(t))
        self.assertFalse(flat['resolved'])

    def test_nonmarkov_and_zero_overlap_rejected(self):
        with self.assertRaises(ValueError):validate_generator([[-1,-1],[1,-1]])
        with self.assertRaises(ValueError):validate_generator([[-1,1],[1,-1]],[.2,.8])
        with self.assertRaises(ValueError):relaxation_estimate(np.arange(4),[0,0,0,0])

    def test_two_time_and_linearity(self):
        t=np.linspace(0,6,101)
        rows=[{'preparation_time':p,'delay':float(x),'response':float(np.exp(-x/tau))}
              for p,tau in ((0,.5),(1,1)) for x in t]
        result=analyze_two_time(rows)
        self.assertAlmostEqual(result[0]['tau'],.5,places=10)
        self.assertAlmostEqual(result[1]['tau'],1,places=10)
        self.assertTrue(check_linear_response([.01,.02],[np.exp(-t),np.exp(-t)],1e-3)['passed'])
        self.assertFalse(check_linear_response([.01,.02],[np.exp(-t),np.exp(-t/2)],1e-3)['passed'])

    def test_stage_does_not_relabel_model_clock(self):
        spec={'kind':'generator','source':'diagnostic chain','operator':'state 1 occupation','phase':'cold',
              'mode_kind':'within_phase','generator':[[-2,2],[3,-3]],'stationary':[.6,.4],
              'observable':[0,1],'perturbation':[-1,1],'time':np.linspace(0,2,30).tolist(),'H_s_inv':1}
        with tempfile.TemporaryDirectory() as td:
            run({'response':spec},{},Path(td))
            text=(Path(td)/'relaxation_times.csv').read_text()
            self.assertIn('model_time',text)
            matching=json.loads((Path(td)/'operator_matching.json').read_text())
            self.assertFalse(matching['physical_clock_calibration_declared'])


if __name__=='__main__':unittest.main()
