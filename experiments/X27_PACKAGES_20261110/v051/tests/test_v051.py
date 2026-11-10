from __future__ import annotations
import unittest
from fractions import Fraction

from x27v051.audit import calibrate_a2, run_nc13, run_nc15, run_nc16
from x27v051.engine import (
    estimate_readiness, functional_repair_contrast, simulate_task2,
    run_b_lite, run_dose_sweep, state_digest, validate_read_before_action,
    trusted_prehistory_events, validate_causal_record_chain,
)
from x27v051.evaluation import (capability_matrix, capability_factorial_contrasts,
                                  run_apparatus_class_contrast, score_b_lite_run,
                                  validate_full_causal_chain, run_capability_cell)
from x27v051.hq import exact_partition, generate_intervention_sequences
from x27v051.metrics import direct_total_variation, point_mass, total_variation, validate_distribution
from x27v051.model import Apparatus, BState, MemoryRecord, RepairRecord, TraceEvent
from x27v051.oracle import evaluator_tasks, evaluate
from x27v051.policies import (
    PolicyObservation, PolicyAccessViolation, invoke_policy, invoke_candidate,
)
from x27v051.resources import apply_operation, saturation_probe
from x27v051.model import ResourceVector


class OraclePolicyTests(unittest.TestCase):
    def test_capability_matrix_is_40_rows(self):
        rows = capability_matrix()
        self.assertEqual(len(rows), 40)
        self.assertEqual({r['policy'] for r in rows}, {'pi_M','pi_P','pi_fixed','pi_none','pi_input'})

    def test_public_input_rejects_evaluator_fields_and_unknown_keys(self):
        for key in ("tau", "evaluator_key", "task_id", "opaque_identifier", "oracle_target", "Y_star"):
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    PolicyObservation((("command", "emit_the_supplied_binary_content"),
                                       ("public_hint", 0), (key, "forbidden")),
                                      allowed_sources=(), readers={})
        with self.assertRaises(ValueError):
            PolicyObservation((("command", "emit_the_supplied_binary_content"),
                               ("public_hint", 0), ("unregistered", 1)),
                              allowed_sources=(), readers={})
        with self.assertRaises(ValueError):
            PolicyObservation((("command", "emit_the_supplied_binary_content"),
                               ("command", "emit_the_supplied_binary_content"),
                               ("public_hint", 0)), allowed_sources=(), readers={})

    def test_pi_fixed_and_pi_input_are_currently_observationally_identical(self):
        from x27v051.policies import POLICY_CAPABILITIES
        rows = capability_matrix()
        fixed = [r["Y_action"] for r in rows if r["policy"] == "pi_fixed"]
        by_input = [r["Y_action"] for r in rows if r["policy"] == "pi_input"]
        self.assertEqual(fixed, by_input)
        self.assertEqual(POLICY_CAPABILITIES["pi_input"], ())
        self.assertTrue(all(r["read_source"] is None for r in rows if r["policy"] == "pi_input"))

    def test_task_id_not_in_policy_observation(self):
        obs = PolicyObservation((("command", "emit_the_supplied_binary_content"), ("public_hint", 0)),
                                allowed_sources=(), readers={})
        self.assertEqual(set(PolicyObservation.__slots__),
                         {"public_input", "_allowed_sources", "_readers"})
        action, access = invoke_policy("pi_input", obs)
        self.assertEqual(action, 0)
        self.assertEqual(access, ())
        with self.assertRaises(PolicyAccessViolation):
            _ = obs.task_id
        with self.assertRaises(PolicyAccessViolation):
            _ = obs._readers

    def test_policy_reads_only_its_granted_source_capability(self):
        obs = PolicyObservation((("command", "emit_the_supplied_binary_content"), ("public_hint", 0)), allowed_sources=("M_task",),
                                readers={"M_task": lambda: 1, "P_res": lambda: 0})
        action, access = invoke_policy("pi_M", obs)
        self.assertEqual(action, 1)
        self.assertEqual(access, ("read:M_task",))
        value, attempted, blocked = invoke_candidate(lambda context: context.read_residual_payload(), obs)
        self.assertTrue(blocked)
        self.assertIsNone(value)
        self.assertEqual(attempted, ("read:P_res", "blocked_read:P_res"))

    def test_exact_factorial_contrasts_follow_source_policy_contract(self):
        matrix = capability_matrix()
        result = capability_factorial_contrasts(matrix)
        self.assertTrue(result["source_factor_patterns_match_policy_contract"])
        self.assertEqual(len(result["results"]), 10)
        for key, contrasts in result["results"].items():
            policy = key.split("/", 1)[1]
            if policy == "pi_M":
                self.assertEqual(contrasts["delta_M_by_P"], {"0": "1", "1": "1"})
                self.assertEqual(contrasts["delta_P_by_M"], {"0": "0", "1": "0"})
            elif policy == "pi_P":
                self.assertEqual(contrasts["delta_M_by_P"], {"0": "0", "1": "0"})
                self.assertEqual(contrasts["delta_P_by_M"], {"0": "1", "1": "1"})
            else:
                self.assertEqual(set(contrasts["delta_M_by_P"].values()), {"0"})
                self.assertEqual(set(contrasts["delta_P_by_M"].values()), {"0"})

    def test_hardware_class_contrast_preserves_a0_a1_a2_claims(self):
        result = run_apparatus_class_contrast()
        self.assertEqual(result["H_A_class"], "PASS")
        self.assertEqual(result["H_A_token"], "NOT_CLAIMED")
        for key, case in result["cases"].items():
            self.assertEqual(case["TV_distances"], {"A1_vs_A0": "1", "A2_vs_A0": "1", "A1_vs_A2": "0"})
            self.assertTrue(case["apparatus_used"]["A1"])
            self.assertTrue(case["apparatus_used"]["A2"])
            self.assertFalse(case["apparatus_used"]["A0"])
            self.assertFalse(case["causal_apparatus_use"]["A0"])
            self.assertTrue(case["causal_apparatus_use"]["A1"])
            self.assertTrue(case["causal_apparatus_use"]["A2"])
            self.assertEqual(case["probe_operand_from_public_input"], 0)
            self.assertTrue(case["oracle_correctness_scored_but_not_used_as_hardware_gate"])
            if key.endswith("_B"):
                self.assertFalse(case["profiles"]["A1"][1])
                self.assertFalse(case["profiles"]["A2"][1])
            for name in ("A0", "A1", "A2"):
                self.assertFalse(any(e["event_type"] == "read_event" for e in case["traces"][name]))

    def test_factorial_contrasts_reject_missing_cell(self):
        with self.assertRaises(ValueError):
            capability_factorial_contrasts(capability_matrix()[:-1])

    def test_memory_aligned_cells_are_correct_for_pi_M(self):
        rows = [r for r in capability_matrix() if r["policy"] == "pi_M"]
        aligned = [r for r in rows if r["M_matches_oracle"]]
        misaligned = [r for r in rows if not r["M_matches_oracle"]]
        self.assertEqual(len(aligned), 4)
        self.assertEqual(len(misaligned), 4)
        self.assertTrue(all(r["Y_correct"] is True for r in aligned))
        self.assertTrue(all(r["Y_correct"] is False for r in misaligned))

    def test_readout_fidelity_and_oracle_correctness_are_distinct(self):
        rows = [r for r in capability_matrix() if r['policy'] == 'pi_M']
        self.assertTrue(all(r['readout_fidelity'] for r in rows))
        self.assertTrue(any(r['Y_correct'] is False for r in rows))
        self.assertTrue(any(r['Y_correct'] is True for r in rows))

    def test_capability_trace_contains_full_provenance_sourceoff_read_action_chain(self):
        rows = [r for r in capability_matrix() if r["policy"] in ("pi_M", "pi_P")]
        self.assertTrue(all(r["causal_source_use"] for r in rows))
        for row in rows:
            events = row["trace"]
            kinds = [event["event_type"] for event in events]
            if row["policy"] == "pi_M":
                required = ["C_write_event_exogenous", "C_memory_transfer_event_exogenous",
                            "D_receive_memory_event_exogenous", "source_off_event", "read_event", "action_event"]
            else:
                required = ["C_residual_payload_write_event_exogenous",
                            "C_residual_payload_transfer_event_exogenous",
                            "D_receive_payload_event_exogenous", "source_off_event", "read_event", "action_event"]
            indices = [kinds.index(kind) for kind in required]
            self.assertEqual(indices, sorted(indices))

    def test_full_causal_chain_binds_one_record_across_receipt_read_and_action(self):
        row = run_capability_cell("eval_case_opaque_A", "pi_M", 0, 1)
        self.assertTrue(row.causal_source_use)
        self.assertTrue(validate_full_causal_chain(row.trace, "M_task", "Task1"))
        altered = list(row.trace)
        receipt_index = next(i for i, event in enumerate(altered)
                             if event.event_type == "D_receive_memory_event_exogenous")
        receipt = altered[receipt_index]
        details = dict(receipt.details)
        details["record_id"] = "different-record"
        altered[receipt_index] = TraceEvent(receipt.event_type, receipt.stage, receipt.time,
                                            tuple(sorted(details.items())))
        self.assertFalse(validate_full_causal_chain(altered, "M_task", "Task1"))
        forged_creator = list(row.trace)
        read_i = next(i for i, event in enumerate(forged_creator)
                      if event.event_type == "read_event" and dict(event.details).get("source") == "M_task")
        read = forged_creator[read_i]
        read_details = dict(read.details)
        read_details["creator_id"] = "forged-creator"
        forged_creator[read_i] = TraceEvent(read.event_type, read.stage, read.time,
                                            tuple(sorted(read_details.items())))
        self.assertFalse(validate_full_causal_chain(forged_creator, "M_task", "Task1"))
        reordered = list(row.trace)
        read_index = next(i for i, event in enumerate(reordered)
                          if event.event_type == "read_event" and dict(event.details).get("source") == "M_task")
        off_index = next(i for i, event in enumerate(reordered) if event.event_type == "source_off_event")
        reordered[read_index], reordered[off_index] = reordered[off_index], reordered[read_index]
        self.assertFalse(validate_full_causal_chain(reordered, "M_task", "Task1"))

    def test_abstaining_policy_has_no_action_event(self):
        row = next(r for r in capability_matrix() if r["policy"] == "pi_none")
        self.assertIsNone(row["Y_action"])
        self.assertEqual(row["Y_status"], "ABSTAINED")
        self.assertFalse(any(e["event_type"] == "action_event" for e in row["trace"]))
        self.assertTrue(any(e["event_type"] == "abstain_event" for e in row["trace"]))

    def test_memory_and_apparatus_binary_domains_reject_booleans(self):
        with self.assertRaises(ValueError):
            MemoryRecord("M_task", 1, True, 0, "C")
        with self.assertRaises(ValueError):
            MemoryRecord("M_task", 1, 0, False, "C")
        with self.assertRaises(ValueError):
            Apparatus("original", True, True, "port-main", "id", "C", "token")

    def test_oracle_is_keyed_by_hidden_tau_and_public_input_not_identifier(self):
        tasks = evaluator_tasks()
        self.assertEqual(len(tasks), 2)
        self.assertTrue(all(not hasattr(task, "target") for task in tasks))
        self.assertEqual(tasks[0].public_input, tasks[1].public_input)
        target_a, correct_a = evaluate(tasks[0].tau, tasks[0].public_input, 0)
        target_b, correct_b = evaluate(tasks[1].tau, tasks[1].public_input, 0)
        self.assertEqual((target_a, correct_a), (0, True))
        self.assertEqual((target_b, correct_b), (1, False))
        with self.assertRaises(KeyError):
            evaluate("unknown_tau", tasks[0].public_input, 0)

    def test_nc15_exact_half_and_invariance(self):
        result = run_nc15()
        self.assertEqual(result['correct'], 100)
        self.assertTrue(result['accuracy_exactly_one_half'])
        self.assertTrue(result['identifier_relabel_invariant'])
        self.assertTrue(result['identifier_fields_absent_from_public_input'])
        self.assertEqual(set(result['public_input_keys']), {'command', 'public_hint'})
        self.assertTrue(result['pass'])

    def test_nc16_static_and_runtime_access_blocked(self):
        result = run_nc16()
        self.assertTrue(result['static']['pass'])
        self.assertEqual(result['static']['engine_forbidden_evaluator_imports'], [])
        self.assertEqual(result['static']['engine_evaluator_identifier_names'], [])
        self.assertFalse(result['static']['run_b_lite_has_evaluator_argument'])
        self.assertIn('scoring_boundary', result['static'])
        self.assertTrue(result['no_oracle_target_or_identifier_access'])
        self.assertTrue(result['pass'])
        self.assertGreaterEqual(len(result['runtime_attempts']), 10)
        self.assertTrue(result['runtime_attempts']['opaque_identifier']['blocked'])


    def test_executor_engine_has_no_oracle_or_evaluator_dependency(self):
        import ast
        import inspect
        import x27v051.engine as engine
        source = inspect.getsource(engine)
        tree = ast.parse(source)
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        self.assertFalse(any(name.endswith(('.oracle', '.evaluation')) for name in imported))
        self.assertFalse(any(name in {'evaluator_key', 'oracle_target', 'Y_star', 'tau'}
                             for node in ast.walk(tree) if isinstance(node, ast.Name)
                             for name in [node.id]))
        self.assertNotIn('evaluator_key', inspect.signature(engine.run_b_lite).parameters)



class RepairAndDoseTests(unittest.TestCase):
    def test_health_and_task2_gate_truth_table(self):
        result = functional_repair_contrast()['results']
        load1, load2 = result['load_1'], result['load_2']
        self.assertEqual(load1['TV_func'], '0')
        self.assertEqual(load1['TV_state_profile'], '1')
        self.assertEqual(load2['TV_func'], '1')
        self.assertEqual(load2['TV_state_profile'], '1')
        self.assertTrue(functional_repair_contrast()['R2_PASS'])
        self.assertTrue(functional_repair_contrast()['R2_NULL_CONTROL_PASS'])

    def test_r0_repair_has_zero_health_gain_and_is_not_necessary_at_load1(self):
        no_repair = run_b_lite('R0', 3, load=1)
        repaired = run_b_lite('R_int', 3, load=1)
        self.assertTrue(no_repair.executed.success)
        self.assertTrue(repaired.executed.success)
        self.assertEqual(repaired.repair_health_gain, 0)
        self.assertTrue(no_repair.readiness.v_rob)
        self.assertFalse(repaired.readiness.v_rob)

    def test_pre_task2_repair_failure_is_not_reported_as_task2_status(self):
        run = run_b_lite("R_int", 1, load=1)
        payload = run.as_dict()
        self.assertFalse(run.task2_reached)
        self.assertIsNone(run.state_after_repair.task2_status)
        self.assertIsNone(payload["Y_task2"])
        self.assertEqual(payload["Y_status2"], "NOT_REACHED")
        self.assertIsNone(payload["R_post2"])
        self.assertIsNotNone(payload["R_at_terminal_before_task2"])
        self.assertEqual(payload["pre_task2_terminal_cause"], "RESOURCE_EXHAUSTED")

    def test_dose_thresholds_are_computed_not_hardcoded(self):
        result = run_dose_sweep()
        self.assertEqual(result['E_star_nominal'], 3)
        self.assertEqual(result['E_star_robust'], 4)
        self.assertTrue(result['nominality_monotone'])
        self.assertTrue(result['robustness_monotone'])
        self.assertEqual([r['E_initial'] for r in result['rows']], [1,2,3,4])
        self.assertTrue(result['readiness_execution_consistent_on_evaluable_cells'])
        self.assertTrue(result['pre_readiness_failures_classified'])
        self.assertTrue(all(r['V_nom'] == r['Y_task2_executed'] for r in result['rows'] if r['Y_task2_attempted']))
        self.assertEqual(result['rows'][0]['readiness_status'],
                         'READINESS_NOT_REACHED_PRE_REPAIR_TERMINAL')
        self.assertEqual(result['rows'][0]['Y_task2_status'], 'NOT_REACHED')
        self.assertEqual(result['rows'][0]['pre_task2_terminal_cause'], 'RESOURCE_EXHAUSTED')
        pre_repair = run_b_lite('R_int', 1)
        self.assertFalse(pre_repair.task2_reached)
        self.assertIsNone(pre_repair.as_dict()['Y_task2'])
        self.assertEqual(pre_repair.as_dict()['Y_status2'], 'NOT_REACHED')
        self.assertEqual(result['rows'][1]['readiness_status'],
                         'EVALUATED_FROM_STAGE4_SNAPSHOT')
        self.assertEqual(result['rows'][1]['Y_task2_status'], 'RESOURCE_EXHAUSTED')

    def test_readiness_rejects_empty_duplicate_and_incomplete_scenarios(self):
        snapshot = run_b_lite('R_int', 3).state_after_repair
        for bad in ((), ('omega_delay','omega_delay'), ('omega_delay',)):
            with self.assertRaises(ValueError):
                estimate_readiness(snapshot, bad)

    def test_readiness_is_pure(self):
        run = run_b_lite('R_int', 3)
        self.assertTrue(run.readiness.purity_pass)
        self.assertTrue(run.readiness.order_independent)
        self.assertEqual(run.readiness.digest_before, run.readiness.digest_after)

    def test_mprod_action_follows_read_instruction(self):
        contrast = functional_repair_contrast()['results']['load_2']
        self.assertTrue(contrast['causal_read_r0'])
        self.assertTrue(contrast['causal_read_r1'])

    def test_b_lite_causal_traces_bind_creator_version_and_record_id(self):
        run = run_b_lite("R_int", 3, causal_prod_read=True,
                         prod_memory=RepairRecord.make("r0", creator_id="C"), load=1)
        self.assertTrue(validate_causal_record_chain(run.events, "M_task", "Task1", run.state_after_repair.task_memory))
        self.assertTrue(validate_causal_record_chain(run.events, "M_task", "Task2", run.state_after_repair.task_memory))
        self.assertTrue(validate_causal_record_chain(run.events, "M_prod", "repair", run.state_after_repair.prod_memory))

        changed = list(run.events)
        read_i = next(i for i, event in enumerate(changed)
                      if event.event_type == "read_event" and dict(event.details).get("source") == "M_prod")
        read = changed[read_i]
        details = dict(read.details)
        details["creator_id"] = "forged-creator"
        changed[read_i] = TraceEvent(read.event_type, read.stage, read.time,
                                     tuple(sorted(details.items())))
        self.assertFalse(validate_causal_record_chain(changed, "M_prod", "repair", run.state_after_repair.prod_memory))

    def test_r1_protocol_is_fixed_and_causal_prod_read_is_rint_only(self):
        run = run_b_lite('R_int', 3, causal_prod_read=False,
                         prod_memory=RepairRecord.make('r1'))
        self.assertEqual(run.repair_instruction, 'r0')
        self.assertFalse(any(e.event_type == 'read_event' and
                             dict(e.details).get('source') == 'M_prod'
                             for e in run.events))
        with self.assertRaises(ValueError):
            run_b_lite('R_ext', 3, causal_prod_read=True)

    def test_execution_result_contains_no_evaluator_score_and_scoring_is_posthoc(self):
        result = run_b_lite("R_int", 3, load=1)
        before = state_digest(result.state_after_repair)
        execution_payload = result.as_dict()
        self.assertNotIn("Y_correct", execution_payload)
        self.assertNotIn("Y_task1_correct", execution_payload)
        self.assertNotIn("Y_task2_correct", execution_payload)
        self.assertNotIn("evaluator_key", execution_payload)
        scored = score_b_lite_run(result, "eval_case_opaque_B")
        self.assertIsNotNone(scored.y_task2_correct)
        self.assertEqual(before, state_digest(result.state_after_repair))

    def test_b_lite_task_outputs_are_scored_against_independent_oracle(self):
        result = run_b_lite("R_int", 3, load=1)
        scored = score_b_lite_run(result, "eval_case_opaque_B")
        self.assertEqual(result.state_after_repair.task1_action, 0)
        self.assertFalse(scored.y_task1_correct)
        self.assertEqual(result.executed.y_action, 0)
        self.assertFalse(scored.y_task2_correct)
        self.assertTrue(result.executed.success)  # execution success is not oracle correctness
        self.assertNotIn("Y_correct", result.as_dict())
        self.assertNotIn("evaluator_key", result.as_dict())

    def test_task2_checksum_error_is_distinct_from_missing_read(self):
        snapshot = BState(
            task_memory=MemoryRecord("M_task", 1, 0, 0, "C"),
            prod_memory=RepairRecord.make("r0"),
            apparatus=Apparatus.a1(1),
            resources=ResourceVector(2, 1, 1, 0),
            stage=4, time=4, source_off=True,
        )
        result = simulate_task2(snapshot, "omega_0", load=1)
        self.assertFalse(result.success)
        self.assertEqual(result.status, "INTEGRITY_ERROR")
        self.assertTrue(any(e.event_type == "integrity_error_event" for e in result.events))
        self.assertFalse(any(e.event_type == "read_event" and dict(e.details).get("source") == "M_task"
                             for e in result.events))

    def test_delay_occurs_before_task2_read(self):
        result = run_b_lite("R_int", 4, load=1, disturbance="omega_delay")
        events = result.executed.events
        delay_end = next(e for e in events if e.event_type == "delay_end_event")
        read = next(e for e in events if e.event_type == "read_event" and dict(e.details).get("task") == "Task2")
        action = next(e for e in events if e.event_type == "action_event" and dict(e.details).get("task") == "Task2")
        self.assertLess(delay_end.time, read.time + 1)
        self.assertEqual(read.time, 6)
        self.assertEqual(action.time, 7)
        self.assertEqual(result.executed.finish_time, 8)

    def test_provenance_events_are_object_specific(self):
        memory = MemoryRecord.make(0, "M_task", creator_id="external-lab")
        prod = RepairRecord.make("r0", creator_id="C")
        a0 = {e.event_type for e in trusted_prehistory_events(memory, prod, Apparatus.a0())}
        a1 = {e.event_type for e in trusted_prehistory_events(memory, prod, Apparatus.a1())}
        a2 = {e.event_type for e in trusted_prehistory_events(memory, prod, Apparatus.a2())}
        self.assertIn("external_record_provenance_event_exogenous", a1)
        self.assertIn("external_record_transfer_event_exogenous", a1)
        self.assertIn("D_receive_memory_event_exogenous", a1)
        self.assertNotIn("C_write_event_exogenous", a1)
        self.assertIn("external_record_transfer_event_exogenous", a1)
        self.assertIn("C_produce_event_exogenous", a1)
        self.assertIn("source_off_event", a1)
        self.assertNotIn("C_produce_event_exogenous", a0)
        self.assertNotIn("C_produce_event_exogenous", a2)
        self.assertIn("apparatus_absence_declared_event", a0)
        self.assertIn("test_fixture_provide_event_exogenous", a2)

    def test_read_verdict_is_source_and_task_specific(self):
        events = (
            TraceEvent("read_event", 3, 3, (("source", "M_prod"), ("task", "repair"))),
            TraceEvent("action_event", 3, 3, (("task", "repair"), ("operand", "r0"))),
            TraceEvent("action_event", 2, 2, (("task", "Task1"), ("operand", 0))),
        )
        self.assertEqual(validate_read_before_action(events, "M_task", "Task1"), "MISSING_READ_EVENT")
        valid = (
            TraceEvent("read_event", 1, 1, (("source", "M_task"), ("task", "Task1"))),
            TraceEvent("action_event", 2, 2, (("task", "Task1"),)),
        )
        self.assertEqual(validate_read_before_action(valid, "M_task", "Task1"), "CAUSAL_READ_VALID")
        reversed_events = tuple(reversed(valid))
        self.assertEqual(validate_read_before_action(reversed_events, "M_task", "Task1"), "READ_NOT_BEFORE_ACTION")


class ResourceAndExactMathTests(unittest.TestCase):
    def test_component_capacity_and_spill(self):
        self.assertTrue(saturation_probe()['pass'])
        self.assertEqual(saturation_probe()['kept'], (4,3,0,0))
        self.assertEqual(saturation_probe()['spill_inflow'], (1,0,0,0))

    def test_atomic_exhaustion_no_byproduct(self):
        r = ResourceVector(0,2,0,0)
        out = apply_operation(r, name='test', cost=(1,1,0,0), byproduct=(0,0,1,0))
        self.assertTrue(out.exhausted)
        self.assertEqual(out.resources.as_tuple(), (0,2,0,0))
        self.assertEqual(out.spill_byproduct, (0,0,0,0))

    def test_tv_exactness_and_bounds(self):
        p = {'x': Fraction(1,1)}
        q = {'y': Fraction(1,1)}
        self.assertEqual(total_variation(p,p), Fraction(0,1))
        self.assertEqual(total_variation(p,q), Fraction(1,1))
        self.assertEqual(direct_total_variation(p,q), total_variation(p,q))

    def test_tv_rejects_invalid_masses(self):
        for d in ({'a':2,'b':-1}, {'a':0.5,'b':0.5}, {'a':True}, {'a':2}):
            with self.assertRaises((TypeError,ValueError)):
                validate_distribution(d)


class ControlsAndHQTests(unittest.TestCase):
    def test_nc13_nested_provenance_purity(self):
        self.assertTrue(run_nc13()['pass'])

    def test_a2_calibration_rejects_wrong_apparatus_roles(self):
        from x27v051.audit import calibrate_a2
        from x27v051.model import Apparatus
        wrong_role = Apparatus("original", 2, True, "port-main", "a2-wrong-role", "fixture", "token")
        result = calibrate_a2(a2=wrong_role)
        self.assertFalse(result["checks"]["object_role_validation"])
        self.assertFalse(result["valid"])

    def test_a2_calibration_is_computed(self):
        result = calibrate_a2()
        self.assertTrue(result['valid'])
        self.assertTrue(all(type(v) is bool for v in result['checks'].values()))
        self.assertEqual(result['H_A_token'], 'NOT_CLAIMED')

    def test_hq_sequence_family_has_stage_specific_controls(self):
        a = generate_intervention_sequences('A')
        b = generate_intervention_sequences('B-LITE')
        self.assertNotEqual(a['sequence_count'], b['sequence_count'])
        self.assertTrue(any('stage3:do(M_prod)=r1' in seq for seq in b['sequences']))
        self.assertFalse(any('do(M_prod)' in label for seq in a['sequences'] for label in seq))
        required_continue = {f'continue@stage{i}' for i in range(7)}
        for schedule in a['sequences'] + b['sequences']:
            self.assertTrue(required_continue.issubset(set(schedule)))
            controls = [x for x in schedule if ':do(' in x]
            self.assertLessEqual(len(controls), 2)
            seen = set()
            for control in controls:
                stage, action = control.split(':', 1)
                operator = action.split('=', 1)[0]
                slot = (stage, operator)
                self.assertNotIn(slot, seen)
                seen.add(slot)

    def test_exact_partition_refinement(self):
        def transition(s, action):
            if s == 2:
                return ('output', ('end', 1))
            return ('state', s+1)
        result = exact_partition((0,1,2), ('continue',), transition, lambda _: 'same')
        self.assertEqual(result['class_count'], 3)
        self.assertTrue(result['rounds'] >= 1)


if __name__ == '__main__':
    unittest.main()
