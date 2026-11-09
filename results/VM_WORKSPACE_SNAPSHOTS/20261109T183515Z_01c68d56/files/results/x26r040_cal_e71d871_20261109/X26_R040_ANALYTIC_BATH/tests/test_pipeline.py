import json
import unittest
from pathlib import Path

from x26r040.runner import run_spectral

ROOT = Path(__file__).resolve().parents[1]


def synthetic_manifest():
    data = json.loads((ROOT / "configs/R040_SPECTRAL_INPUT.template.json").read_text())
    data["model_assumptions_accepted"] = True
    data["energy_unit"] = "arb_energy_synthetic_test_only"
    data["model"].update({
        "E_V": 0.2, "E_1": 0.2, "E_2": 0.1,
        "t_1": 0.15, "t_2": 0.3, "gamma_d": 0.3,
        "kappa": 1.0, "g": 0.22,
    })
    for name in data["provenance"]:
        data["provenance"][name] = {
            "source": "MODEL_ASSUMPTION",
            "evidence_ref": None,
            "assumption": "Synthetic integration fixture only; not physical input and not ADD-derived.",
        }
    data["continuum_scan"]["ring_sizes"] = [32, 64, 128]
    data["pole_search"]["seeds"] = [[-0.5, -0.05]]
    data["freeze_state"] = "FROZEN"
    data["freeze_record_ref"] = "synthetic-test-fixture-only"
    data["freeze_record_sha256"] = "a" * 64
    data["runtime_gate"] = {
        "status": "CALIBRATED", "calibration_ref": "synthetic-test-only",
        "calibration_sha256": "b" * 64, "forecast_ref": "synthetic-test-only",
        "forecast_sha256": "c" * 64, "environment_fingerprint": "d" * 64,
        "forecast_seconds": 10.0, "lower_seconds": 5.0, "upper_seconds": 15.0,
        "hard_wall_seconds": 20.0, "memory_limit_mib": 1024, "disk_limit_mib": 256,
    }
    return data


class TestIntegratedPipeline(unittest.TestCase):
    def test_synthetic_conditional_pipeline_executes_end_to_end(self):
        report = run_spectral(synthetic_manifest())
        self.assertEqual(report["epistemic_class"], "CONDITIONAL_MODEL_RUN_NOT_ADD_DERIVED")
        self.assertEqual(report["direct_bic"]["verdict"], "BIC_IN_CONDITIONAL_R040_TIGHT_BINDING_MODEL")
        self.assertEqual(report["loading"]["static_no_loading_control_status"], "EXECUTED")
        self.assertTrue(report["technical_checks"]["overall_technical_pass"])
        self.assertEqual(report["second_sheet_poles"][0]["status"], "SECOND_SHEET_RESONANCE")
        self.assertEqual(report["status"], "TECHNICAL_CHECKS_PASS_CONDITIONAL_R040_MODEL")

    def test_detuned_pipeline_does_not_fail_static_no_load_as_a_scientific_control(self):
        data = synthetic_manifest()
        data["model"]["E_V"] = 0.8
        report = run_spectral(data)
        self.assertEqual(report["direct_bic"]["verdict"], "DARK_VECTOR_NOT_EIGENSTATE")
        self.assertEqual(report["loading"]["static_no_loading_control_status"], "NOT_APPLICABLE")
        self.assertTrue(report["technical_checks"]["overall_technical_pass"])
        self.assertIsNone(report["technical_checks"]["static_no_loading_control_pass"])


if __name__ == "__main__":
    unittest.main()
