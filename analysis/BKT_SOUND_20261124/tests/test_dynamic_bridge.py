import json
from pathlib import Path
import sys
import unittest

import numpy as np

EOS = Path(__file__).resolve().parents[1]/'eos'
sys.path.insert(0,str(EOS))
from dynamic_bridge import calculate


class DynamicBridge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = calculate()

    def test_linear_contrasts(self):
        p = self.report['plateau']
        self.assertAlmostEqual(p['AB']['Z_diag'],1.023893,places=5)
        self.assertAlmostEqual(p['B_vs_first5']['Z_diag'],3.541927,places=5)
        self.assertLess(p['B_vs_first5']['Z_min_abs_PSD'],1.96)
        self.assertGreater(p['B_vs_first4']['Z_min_abs_PSD'],1.96)
        self.assertAlmostEqual(p['six_common']['Q']-p['Q_first5'],p['B_vs_first5']['Z_diag']**2)

    def test_peak_pole_and_spectrum(self):
        report = self.report
        self.assertLess(report['thresholds']['B']['23']['peak']['Z_gap_min'],1.645)
        self.assertGreater(report['thresholds']['B']['23']['pole']['Z_gap_min'],1.645)
        self.assertEqual([x['nonzero_S2_peak'] for x in report['normal_response_example']['samples']],
                         [True,False,False])
        spectrum = report['cold_spectrum']
        self.assertEqual(spectrum['n_bins'],16)
        self.assertLess(spectrum['error_after_relabel'],1e-12)
        self.assertLess(spectrum['error_to_analytic'],1e-12)
        scores = spectrum['chi2_descriptive']
        self.assertLess(scores['two_modes'],15)
        self.assertGreater(scores['swapped_weights'],190)

    def test_twist_controls(self):
        twist = self.report['twist']
        np.testing.assert_allclose(twist['cycle_det'],[320,322,324])
        np.testing.assert_allclose(twist['open_path_det'],[377]*3)
        values = list(twist['canonical_one_particle_F2_by_kBT'].values())
        self.assertTrue(values[0]>values[1]>values[2]>0)
        saved = json.loads((EOS/'dynamic_bridge.json').read_text())
        np.testing.assert_allclose(saved['cold_spectrum']['frequency_obs_se_reconstruction'],
                                   self.report['cold_spectrum']['frequency_obs_se_reconstruction'],rtol=1e-10)
