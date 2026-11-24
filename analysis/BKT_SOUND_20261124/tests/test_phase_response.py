import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np

PHASE = Path(__file__).resolve().parents[1] / 'paired' / 'phase'


class PhaseResponse(unittest.TestCase):
    def test_experimental_replay(self):
        # The offline package calls the same module from its own directory.
        spec = importlib.util.spec_from_file_location('e55_phase_replay', PHASE / 'analyze.py')
        module = importlib.util.module_from_spec(spec)
        with patch.object(sys, 'path', [str(PHASE), *sys.path]):
            spec.loader.exec_module(module)
            replay = module.calculate()
        stored = json.loads((PHASE / 'results.json').read_text())
        lags = [row['lag_deg'] for row in replay['printed_phases']]
        np.testing.assert_allclose(lags, [23.94, 70.28, 139.37], atol=.01)
        for row, ref in zip(replay['phase_laws'], stored['phase_laws'], strict=True):
            self.assertAlmostEqual(row['rms_after_delay_deg'], ref['rms_after_delay_deg'], places=4)
        for family, reference in [('modal', 13.21), ('rank_one', 16.89)]:
            fit = replay['spectra']['fits'][family]
            self.assertEqual(fit['dof'], 11)
            self.assertAlmostEqual(fit['chi2'], reference, places=2)
            np.testing.assert_allclose(fit['predictions'], stored['spectra']['fits'][family]['predictions'],
                                       rtol=2e-4, atol=2e-5)
        width = replay['width_contrasts']['physical_boot_cov']
        self.assertAlmostEqual(width['correlation'], -.78557136, places=6)
        self.assertAlmostEqual(width['difference_1_minus_2']['sd'] / width['sum']['sd'], 2.35385, places=3)
        self.assertIsNone(replay['matched_observed_width_ratio'])
