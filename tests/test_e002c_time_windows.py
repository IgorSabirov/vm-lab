"""Regression for T400 data leaking into the fixed [190,200] reference."""
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from e002c_exp.windows import integral_mean


class TimeWindows(unittest.TestCase):
    def test_extended_nonconstant_series_uses_exact_window(self):
        for spacing in (.2,2.):
            with self.subTest(spacing=spacing):
                t=np.arange(round(400/spacing)+1)*spacing
                a=np.column_stack([t,t,t*t,np.ones(len(t))])
                expected=dict(linear=195.,quadratic=(200**3-190**3)/30,constant=1.)
                got=integral_mean(a,list(expected),200.)
                np.testing.assert_allclose(list(got.values()),list(expected.values()),atol=1e-10,rtol=0)
                self.assertEqual(got,integral_mean(a[t<=200+1e-8],list(expected),200.))
                a[t>200+1e-8,1:]=1e12
                self.assertEqual(integral_mean(a,list(expected),200.),got)

    def test_final_t400_reference_is_not_changed_to_t200(self):
        t=np.arange(0.,402.,2.)
        self.assertEqual(integral_mean(np.column_stack([t,t]),['x'],400.),{'x':395.})

    def test_incomplete_or_duplicate_window_is_not_a_mean(self):
        for times in (np.arange(0.,6.,2.),np.array([190,192,194,196,198]),
                      np.array([190,192,194,196,200,202]),np.array([190,192,194,196,200,200])):
            with self.subTest(times=times):
                self.assertIsNone(integral_mean(np.column_stack([times,np.ones(len(times))]),['x'],200.))

    def test_verifier_rejects_old_window_and_accepts_bounded_window(self):
        from fixtures_e002c import fixture,make_case,repack
        from e002c_exp.verify import verify,InvalidReport
        with tempfile.TemporaryDirectory() as temp:
            case=make_case('QS_extended',horizon=400.)
            report=fixture(Path(temp),[case])
            verify(report)
            metrics=json.loads((report/'metrics.json').read_text())
            # The old unbounded integral spans 210 units and divides by 10.
            metrics['cases'][0]['transition_reference']={k:21*v for k,v in case['summary']['reference'].items()}
            (report/'metrics.json').write_text(json.dumps(metrics))
            repack(report)
            with self.assertRaisesRegex(InvalidReport,'Transition mean mismatch'):
                verify(report)
            metrics['cases'][0]['transition_reference']=integral_mean(case['series'],case['names'],200.)
            (report/'metrics.json').write_text(json.dumps(metrics))
            repack(report)
            self.assertEqual(verify(report)['status'],'VERIFIED_EXPORTED_ARRAYS')


if __name__=='__main__':
    unittest.main()
