from pathlib import Path
import json
import sys
import tempfile
import unittest

PAIR=Path(__file__).resolve().parents[1]/'paired'
sys.path.insert(0,str(PAIR))
from pair import audit, measured_blocks

class PairedThermometry(unittest.TestCase):
    def test_real_published_marginals_and_density_threshold(self):
        data=audit()
        self.assertEqual(data,json.loads((PAIR/'results.json').read_text()))
        self.assertGreater(data['required_rho_for_95'],1)
        self.assertLess(data['best_case_95_interval'][0],0)
        self.assertAlmostEqual(data['crossing_density_ratio']*data['common_g_t_ratio'],1)
        self.assertGreater(data['examples_TB_over_TA']['1.0'],1)
        self.assertLess(data['examples_TB_over_TA']['0.98'],1)

    def test_block_covariance_and_common_scales(self):
        header='block_id,T_A_nK,n_A_per_um2,T_B_nK,n_B_per_um2\n'
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'input.csv'
            p.write_text(header+'x,40,3,42,3.15\ny,38,2,39.9,2.1\nz,30,3,31.5,3.15\n')
            obj=measured_blocks(p,.64)
            self.assertEqual(obj['independent_blocks'],3)
            self.assertAlmostEqual(obj['temperature_nK']['mean_B_minus_A'],1.8)
            self.assertAlmostEqual(obj['reduced_temperature']['mean_B_minus_A'],0)
            p.write_text(header+'x,40,3,41,3\nx,40,3,41,3\n')
            with self.assertRaises(ValueError): measured_blocks(p,.64)
