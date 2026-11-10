import unittest

from x27.engine import run_b_lite
from x27.model import Arm, Disturbance, MemoryRecord, ModelConfig, RepairRecord


class BLiteTests(unittest.TestCase):
    def test_internal_restore_nominal_pass_robust_fail(self):
        result = run_b_lite(arm=Arm.R_INT, causal_prod_read=False)
        self.assertTrue(result.task2_success)
        self.assertEqual(result.state_final.resources.as_tuple(), (0, 1, 3, 0))
        self.assertTrue(result.readiness.v_nom)
        self.assertFalse(result.readiness.v_rob)
        self.assertEqual(result.state_final.time, 7)
        ledger = [dict(event.details) for event in result.events if event.event_type == "resource_operation_event"]
        self.assertEqual([row["operation"] for row in ledger], ["TASK_1", "REPAIR_r0", "TASK_2"])
        self.assertEqual(ledger[0]["before_E"], 3)
        self.assertEqual(ledger[0]["cost_E"], 1)
        self.assertEqual(ledger[-1]["after_W"], 3)

    def test_execution_time_is_inside_the_declared_horizon(self):
        short_horizon = ModelConfig(max_time=7, delay_steps=1)
        nominal = run_b_lite(arm=Arm.R_INT, config=short_horizon, disturbance=Disturbance.NONE)
        delayed = run_b_lite(arm=Arm.R_INT, config=short_horizon, disturbance=Disturbance.DELAY)
        self.assertTrue(nominal.task2_success)
        self.assertEqual(nominal.state_final.time, 7)
        self.assertFalse(delayed.task2_success)
        self.assertEqual(delayed.state_final.task2_status, "TIMEOUT")
        self.assertEqual(delayed.state_final.time, 8)
        self.assertFalse(any(event.event_type == "action_event" for event in delayed.events if dict(event.details).get("task") == 2))

    def test_delay_is_one_tick_and_within_horizon(self):
        result = run_b_lite(arm=Arm.R_INT, disturbance=Disturbance.DELAY, causal_prod_read=False)
        self.assertTrue(result.task2_success)
        self.assertEqual(result.state_final.time, 8)
        start = next(e for e in result.events if e.event_type == "delay_start_event")
        end = next(e for e in result.events if e.event_type == "delay_end_event")
        read = next(e for e in result.events if e.event_type == "read_event" and dict(e.details).get("task") == 2)
        self.assertEqual((start.time, end.time, read.time), (5, 6, 6))
        self.assertLess(start.time, end.time)

    def test_loss_energy_fails_task2_but_loss_material_does_not(self):
        energy = run_b_lite(arm=Arm.R_INT, disturbance=Disturbance.LOSS_E, causal_prod_read=False)
        material = run_b_lite(arm=Arm.R_INT, disturbance=Disturbance.LOSS_M, causal_prod_read=False)
        self.assertFalse(energy.task2_success)
        self.assertEqual(energy.state_final.task2_status, "RESOURCE_EXHAUSTED")
        self.assertTrue(material.task2_success)

    def test_readiness_estimator_is_pure_and_enumerates_all_scenarios(self):
        result = run_b_lite(arm=Arm.R_INT, causal_prod_read=False)
        report = result.readiness
        self.assertTrue(report.purity_pass)
        self.assertTrue(report.order_independent)
        self.assertEqual(report.state_hash_before, report.state_hash_after)
        self.assertEqual(
            [item.disturbance for item in report.scenarios],
            ["omega_0", "omega_delay", "omega_loss_E", "omega_loss_M"],
        )
        self.assertEqual(len(report.scenarios), 4)

    def test_r0_and_external_control(self):
        r0 = run_b_lite(arm=Arm.R0, causal_prod_read=False)
        rext = run_b_lite(arm=Arm.R_EXT, causal_prod_read=False)
        self.assertFalse(r0.task2_success)
        self.assertEqual(r0.state_final.task2_status, "APPARATUS_DEGRADED")
        self.assertTrue(rext.task2_success)
        self.assertTrue(rext.state_final.external_donor_used)
        self.assertFalse(rext.state_final.internal_restore_used)
        injection = next(dict(event.details) for event in rext.events if event.event_type == "resource_operation_event" and dict(event.details).get("operation") == "EXTERNAL_INJECTION")
        self.assertEqual(injection["spill_inflow_E"], 0)
        self.assertEqual(injection["before_E"], 2)
        self.assertEqual(injection["after_E"], 3)
        self.assertEqual(injection["inflow_E"], 1)

    def test_r2_is_causal_and_distinguishes_r0_r1_resource_profiles(self):
        r0 = run_b_lite(arm=Arm.R_INT, prod_memory=RepairRecord.make("r0"), causal_prod_read=True)
        r1 = run_b_lite(arm=Arm.R_INT, prod_memory=RepairRecord.make("r1"), causal_prod_read=True)
        self.assertTrue(r0.task2_success and r1.task2_success)
        self.assertEqual(r0.state_final.resources.as_tuple(), (0, 1, 3, 0))
        self.assertEqual(r1.state_final.resources.as_tuple(), (0, 1, 3, 1))
        self.assertEqual(r1.state_final.resources.unavailable - r0.state_final.resources.unavailable, 1)
        self.assertTrue(any(e.event_type == "read_event" and dict(e.details).get("source") == "M_prod" for e in r0.events))
        self.assertTrue(any(e.event_type == "repair_action" and dict(e.details).get("read_source") == "M_prod" for e in r1.events))

    def test_fixed_protocol_r1_does_not_claim_mprod_causality(self):
        result = run_b_lite(arm=Arm.R_INT, prod_memory=RepairRecord.make("r1"), causal_prod_read=False)
        self.assertTrue(result.task2_success)
        self.assertFalse(any(e.event_type == "read_event" and dict(e.details).get("source") == "M_prod" for e in result.events))
        repair = next(e for e in result.events if e.event_type == "repair_action")
        self.assertEqual(dict(repair.details)["read_source"], "frozen_protocol")

    def test_corrupt_main_record_fails_integrity(self):
        corrupt = MemoryRecord.make(0).corrupted()
        result = run_b_lite(arm=Arm.R_INT, task_memory=corrupt, causal_prod_read=False)
        self.assertFalse(result.task2_success)

    def test_mprod_read_does_not_substitute_for_missing_mtask_read(self):
        corrupt = MemoryRecord.make(0).corrupted()
        result = run_b_lite(arm=Arm.R_INT, task_memory=corrupt, causal_prod_read=True)
        self.assertEqual(result.state_final.task1_status, "INTEGRITY_ERROR")
        self.assertTrue(any(e.event_type == "read_event" and dict(e.details).get("source") == "M_prod" for e in result.events))
        self.assertFalse(any(e.event_type == "read_event" and dict(e.details).get("source") == "M_task" and dict(e.details).get("task") == 1 for e in result.events))

    def test_producer_history_is_marked_exogenous(self):
        result = run_b_lite(arm=Arm.R_INT, causal_prod_read=False)
        receive = next(e for e in result.events if e.event_type == "D_receive_event_exogenous")
        self.assertFalse(dict(receive.details)["production_and_transfer_simulated"])
        self.assertTrue(any(e.event_type == "source_off_event" for e in result.events))


if __name__ == "__main__":
    unittest.main()
