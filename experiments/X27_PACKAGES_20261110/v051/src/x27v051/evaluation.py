"""Evaluator-only composition layer for X27 v0.5.1.

This module joins hidden evaluator context to executor outputs only after the
policy/transition kernel has produced its action. Neither policies.py nor
engine.py imports the oracle. Evaluator identifiers and targets stay here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from .engine import BLiteRun, validate_read_before_action
from .model import Apparatus, MemoryRecord, ResourceVector, Status, TraceEvent
from .policies import POLICY_CAPABILITIES, PolicyObservation, invoke_policy
from .oracle import evaluator_task, evaluator_tasks, evaluate
from .resources import TASK_COST, TASK_BYPRODUCT, apply_operation

@dataclass(frozen=True, slots=True)
class CapabilityResult:
    evaluator_key: str
    opaque_identifier: str
    policy: str
    memory_bit: int
    payload_bit: int
    memory_matches_oracle: bool
    payload_matches_oracle: bool
    read_source: Optional[str]
    readout_value: Optional[int]
    action_operand: Optional[int]
    y_action: Optional[int]
    y_correct: Optional[bool]
    y_status: str
    y_score_status: str
    readout_fidelity: Optional[bool]
    causal_source_use: bool
    resources_post: tuple[int, int, int, int]
    trace: tuple[TraceEvent, ...]

    def row(self) -> dict[str, object]:
        return {
            "evaluator_key": self.evaluator_key,
            "opaque_identifier": self.opaque_identifier,
            "policy": self.policy,
            "M_bit": self.memory_bit,
            "P_bit": self.payload_bit,
            "M_matches_oracle": self.memory_matches_oracle,
            "P_matches_oracle": self.payload_matches_oracle,
            "read_source": self.read_source,
            "readout_value": self.readout_value,
            "action_operand": self.action_operand,
            "Y_action": self.y_action,
            "Y_correct": self.y_correct,
            "Y_status": self.y_status,
            "Y_score_status": self.y_score_status,
            "readout_fidelity": self.readout_fidelity,
            "causal_source_use": self.causal_source_use,
            "R_post": self.resources_post,
            "trace": [e.as_dict() for e in self.trace],
        }


def capability_prehistory_events(task_memory: MemoryRecord, payload: MemoryRecord,
                                  apparatus: Apparatus) -> tuple[TraceEvent, ...]:
    """Trusted variant-B prehistory, including source-specific receipt by D.

    The C production/transfer events are trusted exogenous facts. Each source
    receipt carries the exact record ID and version, and explicitly records the
    payload's physical accessibility (a_P=1) for this matrix.
    """
    events: list[TraceEvent] = []
    for record, source, write_kind, transfer_kind in (
        (task_memory, "M_task", "C_write_event_exogenous", "C_memory_transfer_event_exogenous"),
        (payload, "P_res", "C_residual_payload_write_event_exogenous", "C_residual_payload_transfer_event_exogenous"),
    ):
        if record.creator_id == "C":
            events.append(TraceEvent(write_kind, 0, 0,
                                     (("source", source), ("record_id", record.record_id),
                                      ("version", record.version), ("creator_id", record.creator_id))))
            events.append(TraceEvent(transfer_kind, 0, 0,
                                     (("source", source), ("record_id", record.record_id),
                                      ("version", record.version), ("creator_id", record.creator_id))))
        else:
            events.append(TraceEvent("external_record_provenance_event_exogenous", 0, 0,
                                     (("source", source), ("record_id", record.record_id),
                                      ("version", record.version), ("creator_id", record.creator_id))))
            events.append(TraceEvent("external_record_transfer_event_exogenous", 0, 0,
                                     (("source", source), ("record_id", record.record_id),
                                      ("version", record.version), ("creator_id", record.creator_id))))
        receive_kind = "D_receive_memory_event_exogenous" if source == "M_task" else "D_receive_payload_event_exogenous"
        events.append(TraceEvent(receive_kind, 0, 0,
                                 (("source", source), ("record_id", record.record_id),
                                  ("version", record.version), ("creator_id", record.creator_id),
                                  ("holder", "D"), ("accessible", True))))
    if apparatus.kind == "original" and apparatus.creator_id == "C":
        events.append(TraceEvent("C_produce_event_exogenous", 0, 0,
                                 (("apparatus_id", apparatus.apparatus_id), ("creator_id", apparatus.creator_id))))
        events.append(TraceEvent("C_apparatus_transfer_event_exogenous", 0, 0,
                                 (("apparatus_id", apparatus.apparatus_id), ("creator_id", apparatus.creator_id))))
    elif apparatus.kind == "substitute":
        events.append(TraceEvent("test_fixture_provide_event_exogenous", 0, 0,
                                 (("apparatus_id", apparatus.apparatus_id), ("creator_id", apparatus.creator_id))))
        events.append(TraceEvent("test_fixture_transfer_event_exogenous", 0, 0,
                                 (("apparatus_id", apparatus.apparatus_id), ("creator_id", apparatus.creator_id))))
    else:
        events.append(TraceEvent("apparatus_absence_declared_event", 0, 0,
                                 (("apparatus_present", False),)))
    events.append(TraceEvent("D_receive_event_exogenous", 0, 0,
                             (("holder", "D"), ("apparatus_present", apparatus.kind != "absent"),
                              ("production_and_transfer_simulated", False))))
    events.append(TraceEvent("source_off_event", 0, 0,
                             (("source", "C"), ("new_writes_permitted", False),
                              ("new_transfers_permitted", False))))
    return tuple(events)


def validate_full_causal_chain(events: Iterable[TraceEvent], source: str, task: str) -> bool:
    """Validate identity-preserving provenance→transfer→receipt→source-off→read→action."""
    materialized = tuple(events)
    if source == "M_task":
        provenance_kinds = {"C_write_event_exogenous", "external_record_provenance_event_exogenous"}
        transfer_kinds = {"C_memory_transfer_event_exogenous", "external_record_transfer_event_exogenous"}
        receive_kind = "D_receive_memory_event_exogenous"
    elif source == "P_res":
        provenance_kinds = {"C_residual_payload_write_event_exogenous", "external_record_provenance_event_exogenous"}
        transfer_kinds = {"C_residual_payload_transfer_event_exogenous", "external_record_transfer_event_exogenous"}
        receive_kind = "D_receive_payload_event_exogenous"
    else:
        raise ValueError("full prehistory validation is defined for M_task and P_res")

    def index_where(predicate):
        return next((i for i, event in enumerate(materialized) if predicate(event)), None)

    read_index = index_where(lambda e: e.event_type == "read_event"
                             and dict(e.details).get("source") == source
                             and dict(e.details).get("task") == task)
    if read_index is None:
        return False
    read_details = dict(materialized[read_index].details)
    record_id = read_details.get("record_id")
    version = read_details.get("version")
    creator_id = read_details.get("creator_id")
    if record_id is None or version is None or creator_id is None:
        return False
    matches_record = lambda e: (dict(e.details).get("source") == source
                                and dict(e.details).get("record_id") == record_id
                                and dict(e.details).get("version") == version
                                and dict(e.details).get("creator_id") == creator_id)
    provenance_index = index_where(lambda e: e.event_type in provenance_kinds and matches_record(e))
    transfer_index = index_where(lambda e: e.event_type in transfer_kinds and matches_record(e))
    receive_index = index_where(lambda e: e.event_type == receive_kind and matches_record(e)
                                and dict(e.details).get("holder") == "D"
                                and dict(e.details).get("accessible") is True)
    source_off_index = index_where(lambda e: e.event_type == "source_off_event")
    action_index = index_where(lambda e: e.event_type == "action_event"
                               and dict(e.details).get("task") == task)
    indices = (provenance_index, transfer_index, receive_index, source_off_index,
               read_index, action_index)
    if any(i is None for i in indices):
        return False
    if not (provenance_index < transfer_index < receive_index < source_off_index < read_index < action_index):
        return False
    action_details = dict(materialized[action_index].details)
    return (read_details.get("returned_value") == action_details.get("operand")
            and action_details.get("read_source") == source
            and action_details.get("source_record_id") == record_id
            and action_details.get("source_record_version") == version
            and action_details.get("source_record_creator_id") == creator_id)


def run_capability_cell(evaluator_key: str, policy_name: str, memory_bit: int,
                        payload_bit: int, opaque_identifier: str = "evaluator-only") -> CapabilityResult:
    """Evaluate one policy×task×(M,P) cell; evaluator-only fields stay outside D."""
    tasks = {t.evaluator_key: t for t in evaluator_tasks()}
    if evaluator_key not in tasks:
        raise KeyError(evaluator_key)
    if policy_name not in POLICY_CAPABILITIES:
        raise KeyError(policy_name)
    task = tasks[evaluator_key]
    if memory_bit not in (0, 1) or payload_bit not in (0, 1):
        raise ValueError("memory and payload bits must be binary")

    task_record = MemoryRecord.make(memory_bit, "M_task")
    payload_record = MemoryRecord.make(payload_bit, "P_res")
    events: list[TraceEvent] = list(capability_prehistory_events(task_record, payload_record, Apparatus.a1(2)))
    read_values: dict[str, int] = {}

    def read_memory() -> int:
        read_values["M_task"] = memory_bit
        events.append(TraceEvent("read_event", 1, 1,
                                 (("source", "M_task"), ("task", "Task1"),
                                  ("record_id", task_record.record_id), ("version", task_record.version),
                                  ("creator_id", task_record.creator_id),
                                  ("returned_value", memory_bit))))
        return memory_bit

    def read_payload() -> int:
        read_values["P_res"] = payload_bit
        events.append(TraceEvent("read_event", 1, 1,
                                 (("source", "P_res"), ("task", "Task1"),
                                  ("record_id", payload_record.record_id), ("version", payload_record.version),
                                  ("creator_id", payload_record.creator_id),
                                  ("returned_value", payload_bit))))
        return payload_bit

    readers = {"M_task": read_memory, "P_res": read_payload}
    observation = PolicyObservation(
        task.public_input,
        allowed_sources=POLICY_CAPABILITIES[policy_name],
        readers=readers,
    )
    action, attempted = invoke_policy(policy_name, observation)
    read_attempts = [entry for entry in attempted if entry.startswith("read:")]
    if len(read_attempts) > 1:
        raise RuntimeError("a capability cell permits at most one source read")
    # Only source-read events are expected in the monitor. Any direct service-field
    # attempt or private-field introspection invalidates this policy execution.
    unexpected = [x for x in attempted if not x.startswith("read:")]
    if unexpected:
        raise RuntimeError(f"production policy attempted forbidden access: {unexpected}")
    if len(read_values) > 1:
        raise RuntimeError("a single-source policy read more than one source")

    read_source = next(iter(read_values), None)
    readout = read_values.get(read_source) if read_source is not None else None
    operand = action
    if action is None:
        events.append(TraceEvent("abstain_event", 2, 2, (("task", "Task1"), ("policy", policy_name))))
    else:
        events.append(TraceEvent("action_event", 2, 2,
                                 (("task", "Task1"), ("operand", operand), ("policy", policy_name),
                                  ("read_source", read_source),
                                  ("source_record_id", (task_record.record_id if read_source == "M_task"
                                                         else payload_record.record_id if read_source == "P_res" else None)),
                                  ("source_record_version", (task_record.version if read_source == "M_task"
                                                              else payload_record.version if read_source == "P_res" else None)),
                                  ("source_record_creator_id", (task_record.creator_id if read_source == "M_task"
                                                                 else payload_record.creator_id if read_source == "P_res" else None)))))
    _, correct = evaluate(task.tau, task.public_input, action)
    memory_target, _ = evaluate(task.tau, task.public_input, memory_bit)
    payload_target, _ = evaluate(task.tau, task.public_input, payload_bit)
    if action is None:
        status = Status.ABSTAINED.value
        resources_post = (3, 2, 0, 0)
        fidelity = None
    else:
        # Action execution and oracle correctness are deliberately separate.
        op = apply_operation(ResourceVector(3, 2, 0, 0), name="capability_action",
                             cost=TASK_COST, byproduct=TASK_BYPRODUCT)
        if op.exhausted:
            status = Status.RESOURCE_EXHAUSTED.value
            resources_post = op.resources.as_tuple()
        else:
            status = Status.SUCCESS.value
            resources_post = op.resources.as_tuple()
        fidelity = (readout == operand) if read_source is not None else None
    causal = bool(read_source is not None and readout is not None
                  and validate_full_causal_chain(events, read_source, "Task1"))
    score_status = "NOT_SCORED" if correct is None else ("CORRECT" if correct else "WRONG_ANSWER")
    return CapabilityResult(evaluator_key, opaque_identifier, policy_name, memory_bit, payload_bit,
                            memory_bit == memory_target, payload_bit == payload_target,
                            read_source, readout, operand, action, correct, status, score_status, fidelity,
                            causal, resources_post, tuple(events))


def run_apparatus_class_contrast() -> dict[str, object]:
    """Compare A0/A1/A2 using a public-input probe, never the oracle target as action."""
    from .metrics import point_mass, total_variation
    from .audit import calibrate_a2

    calibration = calibrate_a2()
    apparatuses = {"A0": Apparatus.a0(), "A1": Apparatus.a1(2), "A2": Apparatus.a2(2)}
    case_results: dict[str, object] = {}
    all_class_conditions = True
    for task in evaluator_tasks():
        probe_context = PolicyObservation(task.public_input, allowed_sources=(), readers={})
        probe_action, probe_access = invoke_policy("pi_input", probe_context)
        if probe_access or probe_action not in (0, 1):
            raise RuntimeError("hardware probe policy violated its public-input-only contract")
        target, _ = evaluate(task.tau, task.public_input, probe_action)
        profiles: dict[str, tuple[object, ...]] = {}
        traces: dict[str, list[dict[str, object]]] = {}
        used: dict[str, bool] = {}
        for name, apparatus in apparatuses.items():
            resources = ResourceVector(3, 2, 0, 0)
            events = list(capability_prehistory_events(
                MemoryRecord.make(0, "M_task"), MemoryRecord.make(0, "P_res"), apparatus
            ))
            events.append(TraceEvent("hardware_probe_request_event", 1, 1,
                                     (("policy", "pi_input"), ("operand", probe_action),
                                      ("source", "public_input"))))
            action: Optional[int] = None
            correct: Optional[bool] = None
            if not apparatus.operational or apparatus.health < 1:
                status = Status.APPARATUS_DEGRADED.value
                health_after = apparatus.health
                events.append(TraceEvent("task_failed_event", 2, 2, (("status", status),)))
            else:
                operation = apply_operation(resources, name="Task1_apparatus_probe",
                                            cost=TASK_COST, byproduct=TASK_BYPRODUCT)
                resources = operation.resources
                if operation.exhausted:
                    status = Status.RESOURCE_EXHAUSTED.value
                    health_after = apparatus.health
                    events.append(TraceEvent("task_failed_event", 2, 2, (("status", status),)))
                else:
                    status = Status.SUCCESS.value
                    action = probe_action
                    _, correct = evaluate(task.tau, task.public_input, action)
                    health_after = apparatus.health - 1
                    events.append(TraceEvent("apparatus_use_event", 2, 2,
                                             (("apparatus_id", apparatus.apparatus_id),
                                              ("creator_id", apparatus.creator_id),
                                              ("port_id", apparatus.port_id))))
                    events.append(TraceEvent("action_event", 2, 2,
                                             (("task", "Task1"), ("operand", probe_action),
                                              ("result", action), ("Y_correct", correct),
                                              ("status", status), ("source", "public_input"))))
            used[name] = any(e.event_type == "apparatus_use_event" for e in events)
            profiles[name] = (action, correct, status, resources.as_tuple(), health_after)
            traces[name] = [e.as_dict() for e in events]
        distances = {
            "A1_vs_A0": str(total_variation(point_mass(profiles["A1"]), point_mass(profiles["A0"]))),
            "A2_vs_A0": str(total_variation(point_mass(profiles["A2"]), point_mass(profiles["A0"]))),
            "A1_vs_A2": str(total_variation(point_mass(profiles["A1"]), point_mass(profiles["A2"]))),
        }
        conditions = (
            used["A1"] and used["A2"] and not used["A0"]
            and profiles["A1"][2] == Status.SUCCESS.value
            and profiles["A2"][2] == Status.SUCCESS.value
            and profiles["A0"][2] == Status.APPARATUS_DEGRADED.value
            and distances["A1_vs_A0"] == "1"
            and distances["A2_vs_A0"] == "1"
            and distances["A1_vs_A2"] == "0"
            and calibration["valid"]
        )
        all_class_conditions &= conditions
        case_results[task.evaluator_key] = {
            "Y_star_evaluator_only": target,
            "probe_policy": "pi_input",
            "probe_operand_from_public_input": probe_action,
            "oracle_correctness_scored_but_not_used_as_hardware_gate": True,
            "profiles": {k: list(v) for k, v in profiles.items()},
            "apparatus_used": used,
            "TV_distances": distances,
            "causal_apparatus_use": {name: used[name] for name in used},
            "traces": traces,
            "H_A_class_conditions_pass": conditions,
        }
    return {
        "H_A_class": "PASS" if all_class_conditions else "FAIL_OR_NOT_EVALUABLE",
        "H_A_token": "NOT_CLAIMED",
        "A2_calibration_valid": calibration["valid"],
        "calibration": calibration,
        "cases": case_results,
        "profile_fields": ["Y_action", "Y_correct", "Y_status", "R_post", "health_post"],
        "interpretation": "Functional apparatus-class contrast using a public-input-only action; oracle correctness is scored independently and is not hardwired into the operand. A2 calibration is model-internal, not physical apparatus evidence.",
    }


def capability_matrix() -> list[dict[str, object]]:
    """2 evaluator-only task cases × 5 policies × 4 M×P cells = exactly 40 rows.

    A1 is held fixed in this capability matrix; apparatus contrasts remain separate.
    The evaluator-only tau/key/target are never passed to a policy observation.
    """
    rows: list[dict[str, object]] = []
    for task in evaluator_tasks():
        for policy in ("pi_M", "pi_P", "pi_fixed", "pi_none", "pi_input"):
            for m in (0, 1):
                for p in (0, 1):
                    cell = run_capability_cell(task.evaluator_key, policy, m, p)
                    rows.append(cell.row())
    if len(rows) != 40:
        raise AssertionError(f"expected 40 capability cells, got {len(rows)}")
    return rows


def capability_factorial_contrasts(matrix: Optional[list[dict[str, object]]] = None) -> dict[str, object]:
    """Exact full-profile M/P contrasts for every evaluator case and policy.

    The profile excludes diagnostic source labels and opaque evaluator metadata;
    it contains the factual action, oracle correctness, execution status and
    post-action resource vector. Each cell is deterministic, represented as a
    point mass, and all TV distances are exact.
    """
    from .metrics import point_mass, total_variation

    rows = matrix if matrix is not None else capability_matrix()
    grouped: dict[tuple[str, str], dict[tuple[int, int], dict[str, object]]] = {}
    for row in rows:
        key = (str(row["evaluator_key"]), str(row["policy"]))
        cell = (int(row["M_bit"]), int(row["P_bit"]))
        if cell in grouped.setdefault(key, {}):
            raise ValueError(f"duplicate capability cell {key}/{cell}")
        grouped[key][cell] = row
    if len(grouped) != 10:
        raise ValueError("capability contrasts require 2 evaluator tasks × 5 candidate policies")

    results: dict[str, object] = {}
    for (evaluator_key, policy), cells in sorted(grouped.items()):
        if set(cells) != {(0, 0), (0, 1), (1, 0), (1, 1)}:
            raise ValueError(f"incomplete 2×2 cell matrix for {evaluator_key}/{policy}")

        def profile(m: int, p: int) -> tuple[object, ...]:
            row = cells[(m, p)]
            return (row["Y_action"], row["Y_correct"], row["Y_status"], tuple(row["R_post"]))

        d_m = {str(p): str(total_variation(point_mass(profile(0, p)),
                                            point_mass(profile(1, p)))) for p in (0, 1)}
        d_p = {str(m): str(total_variation(point_mass(profile(m, 0)),
                                            point_mass(profile(m, 1)))) for m in (0, 1)}
        results[f"{evaluator_key}/{policy}"] = {
            "delta_M_by_P": d_m,
            "delta_P_by_M": d_p,
            "profile_fields": ["Y_action", "Y_correct", "Y_status", "R_post"],
            "diagnostic_source_fields_excluded": True,
        }

    expected_patterns = {}
    for key, value in results.items():
        policy = key.split("/", 1)[1]
        expected = {
            "pi_M": ({"0": "1", "1": "1"}, {"0": "0", "1": "0"}),
            "pi_P": ({"0": "0", "1": "0"}, {"0": "1", "1": "1"}),
            "pi_fixed": ({"0": "0", "1": "0"}, {"0": "0", "1": "0"}),
            "pi_none": ({"0": "0", "1": "0"}, {"0": "0", "1": "0"}),
            "pi_input": ({"0": "0", "1": "0"}, {"0": "0", "1": "0"}),
        }[policy]
        expected_patterns[key] = (
            value["delta_M_by_P"] == expected[0] and value["delta_P_by_M"] == expected[1]
        )
    return {
        "method": "exact full-joint-profile TV on deterministic point masses",
        "results": results,
        "source_factor_patterns_match_policy_contract": all(expected_patterns.values()),
        "pattern_checks": expected_patterns,
        "interpretation": "Model-internal policy capability contrasts; not independent evidence for a physical memory mechanism.",
    }


def legacy_policy_baseline() -> list[dict[str, object]]:
    """Separate compatibility baseline; intentionally excluded from the 40-cell library matrix."""
    rows = []
    for task in evaluator_tasks():
        for m in (0, 1):
            for p in (0, 1):
                rows.append(run_capability_cell(task.evaluator_key, "pi_0_legacy", m, p).row())
    return rows



@dataclass(frozen=True, slots=True)
class ScoredBLiteRun:
    """Evaluator-side scores attached after execution; never part of BState."""
    execution: BLiteRun
    evaluator_key: str
    y_task1_target: int
    y_task1_correct: Optional[bool]
    y_task2_target: int
    y_task2_correct: Optional[bool]

    def as_dict(self) -> dict[str, object]:
        result = self.execution.as_dict()
        result.update({
            "evaluator_key": self.evaluator_key,
            "Y_task1_action": self.execution.state_after_repair.task1_action,
            "Y_task1_target": self.y_task1_target,
            "Y_task1_correct": self.y_task1_correct,
            "Y_task2_action": self.execution.executed.y_action,
            "Y_task2_target": self.y_task2_target,
            "Y_task2_correct": self.y_task2_correct,
            "oracle_scoring_layer": "evaluation.py; outside executor state and transition kernel",
        })
        return result


def score_b_lite_run(execution: BLiteRun, evaluator_key: str) -> ScoredBLiteRun:
    """Score already-produced actions against evaluator-only task context."""
    task = evaluator_task(evaluator_key)
    target1, correct1 = evaluate(task.tau, task.public_input,
                                 execution.state_after_repair.task1_action)
    target2, correct2 = evaluate(task.tau, task.public_input,
                                 execution.executed.y_action)
    return ScoredBLiteRun(execution, evaluator_key, target1, correct1, target2, correct2)

