import unittest

from x27.analysis import g0_report, hq_partition
from x27.controls import run_e2_checks, run_pc_nc_controls


class HQAndControlTests(unittest.TestCase):
    def test_synthetic_lumpability_controls(self):
        controls = run_pc_nc_controls()["H_Q_synthetic"]
        self.assertTrue(controls["PC8_nonaggregability_detected"])
        self.assertTrue(controls["PC9_aggregability_confirmed"])

    def test_g0_reachable_closure_is_finite(self):
        a = g0_report(module="A")
        b = g0_report(module="B-LITE")
        self.assertEqual(a["status"], "PASS")
        self.assertEqual(b["status"], "PASS")
        self.assertLessEqual(a["reachable_count"], 350_000)
        self.assertLessEqual(b["reachable_count"], 350_000)

    def test_exact_hq_partition_uses_terminals_as_outputs_not_members(self):
        result = hq_partition(module="B-LITE")
        self.assertEqual(result["status"], "COMPUTED_EXACTLY")
        self.assertEqual(result["context_label"], "LEGACY_R2_LIKE_CAUSAL_M_PROD_READ")
        self.assertTrue(result["causal_prod_read_on_continue"])
        self.assertTrue(result["M_prod_interventions_allowed"])
        self.assertFalse(result["transferable_to_R1"])
        self.assertFalse(result["full_causal_trace_equivalence"])
        self.assertEqual(result["J_trace"], "diagnostic event journal; excluded from partition observation")
        self.assertIn("stage", result["O_D"])
        self.assertIn("resources", result["O_eval"])
        self.assertFalse(result["publishable_as_frozen_HQ_result"])
        self.assertEqual(result["result_status"], "LEGACY_REPRODUCTION_ONLY_NOT_TRANSFERABLE")
        self.assertFalse(result["R1_context_included"])
        self.assertTrue(result["R2_like_context_included"])
        self.assertGreater(result["predictive_classes"], 0)
        self.assertGreater(result["terminal_nodes_recorded"], 0)
        self.assertGreater(result["terminal_output_classes"], 0)
        self.assertFalse(result["terminal_states_in_partition_domain"])
        decision_stages = set(result["decision_region_stages"])
        # The published classes contain decision nodes only; terminal outcomes
        # are separate leaves and helper stages remain internal to refinement.
        self.assertTrue(all(row["size"] == len(row["members"]) for row in result["partition_classes"]))
        self.assertGreater(result["nondecision_helper_classes"], 0)

    def test_e2_and_pc_nc(self):
        self.assertTrue(run_e2_checks()["all_pass"])
        summary = run_pc_nc_controls()["summary"]
        self.assertEqual(summary["pc_pass"], summary["pc_total"])
        self.assertEqual(summary["nc_pass"], summary["nc_total"])


if __name__ == "__main__":
    unittest.main()
