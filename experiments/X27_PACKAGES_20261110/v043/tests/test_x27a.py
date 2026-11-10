import unittest

from x27.analysis import run_apparatus_factorial, run_memory_apparatus_interaction, run_payload_bypass_positive_control, run_x27a_matrix
from x27.model import ModelConfig, SubstituteCalibration


class X27ATests(unittest.TestCase):
    def setUp(self):
        self.calibration = SubstituteCalibration(True, True, True, True, True)

    def test_full_memory_payload_matrix(self):
        result = run_x27a_matrix()
        self.assertEqual(set(result["cells"]), {"00", "01", "10", "11"})
        self.assertEqual(result["H_M"], "PASS")
        self.assertEqual(result["H_P"], "PASS")
        self.assertEqual(result["delta_M"], {"P0": 1.0, "P1": 1.0})
        self.assertEqual(result["delta_P"], {"M0": 0.0, "M1": 0.0})

    def test_payload_bypass_positive_control(self):
        result = run_payload_bypass_positive_control()
        self.assertTrue(result["payload_read_detected"])
        self.assertEqual(result["H_P"], "FAIL")

    def test_apparatus_class_and_token_specificity(self):
        result = run_apparatus_factorial(calibration=self.calibration)
        self.assertEqual(result["H_A_class"], "PASS")
        self.assertEqual(result["H_A_token"], "NOT_CLAIMED")
        self.assertEqual(result["TV_distances"], {"A1_vs_A0": 1.0, "A2_vs_A0": 1.0, "A1_vs_A2": 0.0})
        self.assertEqual(result["apparatus_use_trace"], {"A0": False, "A1": True, "A2": True})

        token_result = run_apparatus_factorial(
            calibration=self.calibration,
            config=ModelConfig(required_token_signature="token-original"),
        )
        self.assertEqual(token_result["H_A_token"], "PASS")
        self.assertEqual(token_result["H_A_token_symmetric_specificity"], "PASS")
        self.assertEqual(token_result["H_A1_necessity_under_original_token"], "PASS")
        self.assertEqual(token_result["H_A_token_directions"]["original_required"]["status"], "PASS")
        self.assertEqual(token_result["H_A_token_directions"]["substitute_required"]["status"], "PASS")

        reverse_token_result = run_apparatus_factorial(
            calibration=self.calibration,
            config=ModelConfig(required_token_signature="token-substitute"),
        )
        self.assertEqual(reverse_token_result["H_A_token"], "PASS")
        self.assertEqual(reverse_token_result["H_A_token_symmetric_specificity"], "PASS")

    def test_memory_apparatus_interaction_is_separate(self):
        result = run_memory_apparatus_interaction()
        self.assertEqual(result["H_MA"], "PASS")
        self.assertGreater(result["mixed_difference_TV_norm"], 0)


if __name__ == "__main__":
    unittest.main()
