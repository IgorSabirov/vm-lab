import json
from pathlib import Path
import sys
import unittest

import numpy as np

EOS = Path(__file__).resolve().parents[1]/'eos'
sys.path.insert(0,str(EOS))
from scale_audit import calculate, channels, isothermal_gradient


class ScaleAudit(unittest.TestCase):
    def test_gradient_and_fraction_normalization(self):
        for p in np.array([[1.26852,.57862,.160042],[1.06822,.32232,.016756]]):
            steps = 1e-6*np.eye(3)
            observed = [(channels(*(p+d))[0]-channels(*(p-d))[0])/2e-6 for d in steps]
            np.testing.assert_allclose(observed,isothermal_gradient(*p),rtol=1e-8)
            self.assertAlmostEqual(channels(*p)[0], np.prod(p[:2])**2/(p[1]**2+p[2]*(p[0]**2-p[1]**2)))

    def test_replay_and_row_identity(self):
        result, table = calculate()
        saved = json.loads((EOS/'scale_audit.json').read_text())
        for old,new in zip(saved['rows'],result['rows'],strict=True):
            for s in ['nominal','critical']:
                self.assertAlmostEqual(old['scenarios'][s]['B'],new['scenarios'][s]['B'],places=9)
        self.assertEqual([r['n_drive_freq'] for r in table if r['full_spectrum']],[16,11])
        self.assertEqual(sum(r['q_nom_per_um'] is None for r in table),7)
        self.assertEqual(sum(r['D2_halfbar'] is not None for r in table),6)
        self.assertEqual(sum(r['DT_halfbar'] is not None for r in table),3)
        self.assertTrue(all(r['D1_halfbar'] is not None for r in table))
        self.assertLess(result['D2_graph_AB']['max_central_disagreement_between_plots'],.02)
        self.assertAlmostEqual(result['A_profiled_temperature']['density_correlated']['delta_loss'],1.41741,places=4)
