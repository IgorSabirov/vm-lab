#!/usr/bin/env python3
from __future__ import annotations
import unittest
import numpy as np

from x26_core import (
    Continuum,
    evaluate_bic,
    fano_zero_without_bic_control,
    independent_continua_control,
    perturbation_diagnostics,
    same_channel_two_mode_counterexample,
    tuned_friedrich_wintgen_model,
)
from add_adapter import validate_finite_closed_orbit_lift


class X26Tests(unittest.TestCase):
    def setUp(self):
        self.cont = Continuum(-1.0, 1.0, ("shared",))
        self.model = tuned_friedrich_wintgen_model(continuum=self.cont)

    def test_tuned_shared_continuum_has_embedded_bic(self):
        result = evaluate_bic(self.model, 0.1)
        self.assertTrue(result["inside_continuum"])
        self.assertEqual(result["rank_W"], 1)
        self.assertTrue(result["has_nontrivial_dark_kernel"])
        self.assertLess(result["dark_amplitude_norm"], 1e-10)
        self.assertLess(result["dark_eigen_residual"], 1e-10)
        self.assertLess(result["dark_width"], 1e-10)
        self.assertTrue(result["continuum_norm_finite"])
        self.assertTrue(result["BIC_candidate"])

    def test_independent_continua_remove_dark_kernel(self):
        model = independent_continua_control(continuum=Continuum(
            -1.0, 1.0, ("which_path_1", "which_path_2")
        ))
        result = evaluate_bic(model, 0.1)
        self.assertEqual(result["rank_W"], 2)
        self.assertFalse(result["has_nontrivial_dark_kernel"])
        self.assertFalse(result["BIC_candidate"])

    def test_fano_zero_is_not_bic(self):
        result = fano_zero_without_bic_control()
        self.assertTrue(result["amplitude_is_zero"])
        self.assertFalse(result["BIC"])
        self.assertGreater(result["finite_resonance_width"], 0)

    def test_same_channel_two_resonances_counterexample(self):
        result = same_channel_two_mode_counterexample()
        self.assertEqual(result["K_sector_metadata"], {"K1": 1, "K2": 0})
        self.assertTrue(result["BIC_control_result"]["BIC_candidate"])

    def test_perturbation_diagnostics_do_not_claim_protection(self):
        result = perturbation_diagnostics(self.model, 0.1, [1e-2, 5e-3, 2e-3, 1e-3, 5e-4])
        self.assertEqual(result["protection_classification"], "NOT_CLASSIFIED_NO_DECLARED_SYMMETRY")
        self.assertTrue(all(x == 1 for x in result["families"]["rank_preserving_common_rescale"]["rank_W"]))
        self.assertTrue(all(x == 2 for x in result["families"]["which_path_extra_channel"]["rank_W"]))

    def test_closed_finite_orbit_lift(self):
        # 3-cycle with constant K1,K2 gives a valid finite permutation lift.
        result = validate_finite_closed_orbit_lift([1, 2, 0], [1, 1, 1], [0, 0, 0])
        self.assertEqual(result.status, "PASS_CONDITIONAL_FINITE_ORBIT_LIFT")

    def test_nonclosed_subset_not_promoted_to_unitary(self):
        result = validate_finite_closed_orbit_lift([1, 2, 2], [1, 1, 1], [0, 0, 0])
        self.assertEqual(result.status, "FAIL_NOT_A_FINITE_PERMUTATION")


if __name__ == "__main__":
    unittest.main(verbosity=2)
