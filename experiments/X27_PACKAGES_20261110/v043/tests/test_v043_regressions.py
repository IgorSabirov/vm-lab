import unittest
from copy import deepcopy
from fractions import Fraction

from x27.analysis import partition_refinement, run_apparatus_factorial, total_variation
from x27.controls import run_pc_nc_controls
from x27.engine import (
    advance_stage,
    canonical_state_payload,
    estimate_readiness,
    make_initial_state,
    run_b_lite,
    run_task1_probe,
    state_digest,
    trusted_prehistory_events,
)
from x27.model import (
    Apparatus,
    Arm,
    Disturbance,
    MemoryRecord,
    ModelConfig,
    RepairRecord,
    Stage,
)


class V043RegressionTests(unittest.TestCase):
    def _stage4_snapshot(self):
        state = make_initial_state(
            task_memory=MemoryRecord.make(0, record_id="M_task", creator_id="C_task"),
            prod_memory=RepairRecord.make("r0", record_id="M_prod"),
            residual_payload=MemoryRecord.make(1, record_id="P_res", creator_id="C_payload"),
        )
        while state.stage < int(Stage.READINESS):
            state = advance_stage(
                state,
                arm=Arm.R_INT,
                disturbance=Disturbance.NONE,
                causal_prod_read=False,
            ).state
        return state

    # F1: readiness must never be vacuously robust.
    def test_readiness_rejects_empty_stress_set(self):
        with self.assertRaisesRegex(ValueError, "must not be empty"):
            estimate_readiness(self._stage4_snapshot(), stress_scenarios=())

    def test_readiness_rejects_incomplete_stress_set(self):
        with self.assertRaisesRegex(ValueError, "must equal the protocol set"):
            estimate_readiness(
                self._stage4_snapshot(),
                stress_scenarios=(Disturbance.DELAY, Disturbance.LOSS_E),
            )

    def test_readiness_rejects_duplicate_stress_set(self):
        with self.assertRaisesRegex(ValueError, "must not contain duplicates"):
            estimate_readiness(
                self._stage4_snapshot(),
                stress_scenarios=(
                    Disturbance.DELAY,
                    Disturbance.LOSS_E,
                    Disturbance.LOSS_M,
                    Disturbance.LOSS_M,
                ),
            )

    # F2: recursive state identity includes nested provenance and IDs.
    def test_state_digest_changes_for_nested_provenance_and_identity(self):
        state = self._stage4_snapshot()
        baseline = state_digest(state)
        state_payload = canonical_state_payload(state)
        self.assertEqual(
            state_payload["fields"]["task_memory"]["fields"]["creator_id"],
            "C_task",
        )
        object.__setattr__(state.task_memory, "creator_id", "C_task_mutated")
        self.assertNotEqual(baseline, state_digest(state))

    def test_digest_changes_for_prod_and_payload_creator_ids(self):
        for object_name, mutation in (
            ("prod_memory", "creator_id"),
            ("residual_payload", "creator_id"),
            ("apparatus", "creator_id"),
        ):
            with self.subTest(object_name=object_name):
                state = deepcopy(self._stage4_snapshot())
                before = state_digest(state)
                target = getattr(state, object_name)
                object.__setattr__(target, mutation, f"{object_name}:changed")
                self.assertNotEqual(before, state_digest(state))

    # F4/F15 regression part: exact non-negative rational probability laws only.
    def test_tv_rejects_negative_probability_mass(self):
        with self.assertRaisesRegex(ValueError, "non-negative"):
            total_variation({"a": 2, "b": -1}, {"a": 1})

    def test_tv_rejects_float_probability_mass(self):
        with self.assertRaisesRegex(TypeError, "int or Fraction"):
            total_variation({"a": 0.5, "b": Fraction(1, 2)}, {"a": 1})

    def test_tv_rejects_boolean_probability_mass(self):
        with self.assertRaisesRegex(TypeError, "int or Fraction"):
            total_variation({"a": True}, {"a": 1})

    def test_tv_exact_invariants(self):
        p = {"a": Fraction(1, 3), "b": Fraction(2, 3)}
        q = {"a": Fraction(2, 3), "b": Fraction(1, 3)}
        self.assertEqual(total_variation(p, p), 0)
        self.assertEqual(total_variation(p, q), total_variation(q, p))
        self.assertEqual(total_variation(p, q), Fraction(1, 3))

    def test_partition_refinement_rejects_negative_transition_mass(self):
        states = {"s"}
        with self.assertRaisesRegex(ValueError, "non-negative"):
            partition_refinement(
                states,
                lambda _state: ("act",),
                lambda _state, _action: {"terminal_a": Fraction(2), "terminal_b": Fraction(-1)},
                lambda state: state,
                terminal_output_key=lambda token: token,
            )

    def test_partition_refinement_rejects_float_transition_mass(self):
        states = {"s"}
        with self.assertRaisesRegex(TypeError, "int or Fraction"):
            partition_refinement(
                states,
                lambda _state: ("act",),
                lambda _state, _action: {"terminal_a": 0.5, "terminal_b": Fraction(1, 2)},
                lambda state: state,
                terminal_output_key=lambda token: token,
            )

    # F5: checksum failure is not a missing read event.
    def test_task1_checksum_error_is_distinct_from_missing_read(self):
        common = dict(
            residual_payload=MemoryRecord.make(0, record_id="P_res"),
            apparatus=Apparatus.a1(),
        )
        corrupted = run_task1_probe(
            task_memory=MemoryRecord.make(0).corrupted(),
            read_source="M_task",
            **common,
        )
        missing = run_task1_probe(
            task_memory=MemoryRecord.make(0),
            read_source="none",
            **common,
        )
        self.assertEqual(corrupted.profile.y_status, "INTEGRITY_ERROR")
        self.assertEqual(missing.profile.y_status, "MISSING_READ_EVENT")

    def test_b_lite_task1_integrity_error_persists_to_final_state(self):
        result = run_b_lite(
            arm=Arm.R_INT,
            task_memory=MemoryRecord.make(0).corrupted(),
            causal_prod_read=True,
        )
        self.assertEqual(result.state_final.task1_status, "INTEGRITY_ERROR")
        self.assertEqual(result.state_final.task2_status, "INTEGRITY_ERROR")

    # F6: delay is completed before Task-2 read.
    def test_delay_timeout_event_uses_post_delay_time(self):
        config = ModelConfig(max_time=5, delay_steps=1)
        result = run_b_lite(arm=Arm.R_INT, disturbance=Disturbance.DELAY, config=config, causal_prod_read=False)
        timeout = next(event for event in result.events if event.event_type == "timeout_event" and dict(event.details).get("phase") == "delay_or_read_deadline")
        end = next(event for event in result.events if event.event_type == "delay_end_event")
        self.assertEqual(end.time, 6)
        self.assertEqual(timeout.time, 7)

    def test_delay_event_order_and_read_timestamp(self):
        result = run_b_lite(arm=Arm.R_INT, disturbance=Disturbance.DELAY, causal_prod_read=False)
        by_type = {event.event_type: event for event in result.events if event.event_type in {
            "delay_start_event", "delay_end_event"
        }}
        read = next(event for event in result.events if event.event_type == "read_event" and dict(event.details).get("task") == 2)
        self.assertEqual(by_type["delay_start_event"].time, 5)
        self.assertEqual(by_type["delay_end_event"].time, 6)
        self.assertEqual(read.time, 6)

    # F7: PC7 uses the full joint result profile and an independent direct sum.
    def test_pc7_full_profile_tv_matches_independent_direct_sum(self):
        controls = run_pc_nc_controls()
        contrast = controls["r2_contrast"]
        self.assertTrue(controls["positive_controls"]["PC7_causal_production_memory_restore"] == "PASS")
        self.assertEqual(contrast["TV_full_joint_profile"], "1")
        self.assertEqual(contrast["TV_estimator_matches_independent_sum"], True)
        self.assertEqual(contrast["TV_full_joint_profile"], contrast["TV_independent_direct_sum"])
        self.assertIn("Y_function_T1", contrast["profile_fields"])
        self.assertIn("Y_function_T2", contrast["profile_fields"])
        self.assertIn("R_final", contrast["profile_fields"])
        self.assertEqual(contrast["differing_profile_fields"], ["R_final"])
        self.assertEqual(contrast["differing_resource_components"], ["U"])
        self.assertFalse(contrast["functional_outcome_difference_detected"])

    # F8: do not attribute fixture/absence objects to C production.
    def test_provenance_events_are_object_specific_for_a0_a1_a2(self):
        memory = MemoryRecord.make(0)
        prod = RepairRecord.make("r0")
        records = {}
        for name, apparatus in (("A0", Apparatus.a0()), ("A1", Apparatus.a1()), ("A2", Apparatus.a2())):
            records[name] = {event.event_type for event in trusted_prehistory_events(
                memory=memory, prod_memory=prod, apparatus=apparatus,
                residual_payload=MemoryRecord.make(1, record_id="P_res"),
            )}
        self.assertIn("C_produce_event_exogenous", records["A1"])
        self.assertNotIn("C_produce_event_exogenous", records["A0"])
        self.assertNotIn("C_produce_event_exogenous", records["A2"])
        self.assertIn("apparatus_absence_declared_event", records["A0"])
        self.assertIn("test_fixture_provide_event_exogenous", records["A2"])
        self.assertIn("C_apparatus_transfer_event_exogenous", records["A1"])
        self.assertIn("test_fixture_transfer_event_exogenous", records["A2"])

    def test_foreign_memory_creator_is_not_logged_as_c_write(self):
        foreign = MemoryRecord.make(0, creator_id="external-lab")
        event_types = {event.event_type for event in trusted_prehistory_events(
            memory=foreign, prod_memory=None, apparatus=Apparatus.a0()
        )}
        self.assertNotIn("C_write_event_exogenous", event_types)
        self.assertIn("memory_provenance_declared_event_exogenous", event_types)

    # NC13: the stage-4 guard detects every nested provenance mutation.
    def test_nc13_detects_nested_provenance_mutations(self):
        controls = run_pc_nc_controls()
        self.assertTrue(controls["negative_controls"]["NC13_nested_state_mutations_detected"] == "PASS")
        self.assertTrue(all(controls["NC13_nested_mutations"].values()))
        self.assertGreaterEqual(len(controls["NC13_nested_mutations"]), 10)
        self.assertEqual(controls["negative_controls"]["NC14_task_memory_integrity_error_distinct_from_missing_read"], "PASS")


if __name__ == "__main__":
    unittest.main()
