"""Pure transition engine for X27-A and X27-B-LITE.

The executable model is deterministic. Every transition returns a new immutable
State plus diagnostic TraceEvents; it never mutates an input state or journal.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from hashlib import sha256
import json
from typing import Callable, Iterable, Mapping, Optional

from .model import (
    Arm,
    Apparatus,
    Disturbance,
    EquipmentHealth,
    EquipmentKind,
    MemoryRecord,
    ModelConfig,
    OutcomeStatus,
    RepairRecord,
    ResourceApplication,
    ResourceOperation,
    ResourceVector,
    Stage,
    State,
    TraceEvent,
)


@dataclass(frozen=True, slots=True)
class StepOutcome:
    state: State
    events: tuple[TraceEvent, ...]


@dataclass(frozen=True, slots=True)
class Task1Profile:
    y_function: Optional[int]
    y_status: str
    finish_time: int
    resources_post: ResourceVector

    def as_dict(self) -> dict[str, object]:
        return {
            "Y_function": self.y_function,
            "Y_status": self.y_status,
            "T_finish": self.finish_time,
            "R_post1": self.resources_post.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class Task1Probe:
    profile: Task1Profile
    events: tuple[TraceEvent, ...]
    apparatus_after: Apparatus
    read_source: Optional[str]
    used_apparatus: bool


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    disturbance: str
    success: bool
    status: str
    finish_time: int
    resources_final: ResourceVector
    state_final: State
    events: tuple[TraceEvent, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "disturbance": self.disturbance,
            "success": self.success,
            "status": self.status,
            "finish_time": self.finish_time,
            "resources_final": self.resources_final.as_dict(),
            "events": [event.as_dict() for event in self.events],
        }


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    v_nom: bool
    v_rob: bool
    scenarios: tuple[ScenarioResult, ...]
    state_hash_before: str
    state_hash_after: str
    purity_pass: bool
    order_independent: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "V_nom": self.v_nom,
            "V_rob": self.v_rob,
            "scenario_results": [result.as_dict() for result in self.scenarios],
            "state_hash_before": self.state_hash_before,
            "state_hash_after": self.state_hash_after,
            "purity_pass": self.purity_pass,
            "order_independent": self.order_independent,
        }


@dataclass(frozen=True, slots=True)
class RunResult:
    arm: str
    applied_disturbance: str
    state_final: State
    readiness: ReadinessReport
    events: tuple[TraceEvent, ...]

    @property
    def task2_success(self) -> bool:
        return self.state_final.task2_status == OutcomeStatus.SUCCESS.value

    def as_dict(self) -> dict[str, object]:
        return {
            "arm": self.arm,
            "applied_disturbance": self.applied_disturbance,
            "Y_task2": self.task2_success,
            "Y_status2": self.state_final.task2_status,
            "T_finish2": self.state_final.time,
            "R_post2": self.state_final.resources.as_dict(),
            "V_nom": self.readiness.v_nom,
            "V_rob": self.readiness.v_rob,
            "internal_restore_used": self.state_final.internal_restore_used,
            "external_donor_used": self.state_final.external_donor_used,
            "readiness": self.readiness.as_dict(),
            "events": [event.as_dict() for event in self.events],
        }


def _vec(values: tuple[int, int, int, int]) -> ResourceVector:
    return ResourceVector(*values)


def _capped_add(base: ResourceVector, addition: ResourceVector) -> tuple[ResourceVector, ResourceVector]:
    raw = tuple(a + b for a, b in zip(base.as_tuple(), addition.as_tuple()))
    kept = tuple(min(3, x) for x in raw)
    spill = tuple(max(0, x - 3) for x in raw)
    return _vec(kept), _vec(spill)


def apply_resource_operation(resources: ResourceVector, operation: ResourceOperation) -> ResourceApplication:
    """Apply inflow -> spill check -> atomic cost -> byproduct -> spill check.

    An inflow is a committed event before the operation's cost is checked. If the
    cost cannot be paid, the post-inflow state remains, no cost is deducted and
    no byproduct is created. Callers use a separate injection operation when
    external supply is an independent event, as it is in R_ext.
    """
    after_inflow, spill_in = _capped_add(resources, operation.inflow)
    after_inflow_tuple = after_inflow.as_tuple()
    cost_tuple = operation.cost.as_tuple()
    if any(have < need for have, need in zip(after_inflow_tuple, cost_tuple)):
        return ResourceApplication(
            resources=after_inflow,
            spill_inflow=spill_in,
            spill_byproduct=ResourceVector.zero(),
            exhausted=True,
            events=("INFLOW_APPLIED", "RESOURCE_EXHAUSTED"),
        )

    after_cost = _vec(tuple(have - need for have, need in zip(after_inflow_tuple, cost_tuple)))
    after_byproduct, spill_byproduct = _capped_add(after_cost, operation.byproduct)
    event_names = ["INFLOW_APPLIED", "COST_DEDUCTED", "BYPRODUCT_ADDED"]
    if any(spill_in.as_tuple()):
        event_names.append("SPILL_INFLOW")
    if any(spill_byproduct.as_tuple()):
        event_names.append("SPILL_BYPRODUCT")
    return ResourceApplication(
        resources=after_byproduct,
        spill_inflow=spill_in,
        spill_byproduct=spill_byproduct,
        exhausted=False,
        events=tuple(event_names),
    )


def apply_resource_loss(resources: ResourceVector, component: str) -> tuple[ResourceVector, bool]:
    """Remove one unit when present; otherwise return LOSS_NOT_APPLICABLE."""
    indices = {"E": 0, "M": 1}
    if component not in indices:
        raise ValueError("component must be E or M")
    values = list(resources.as_tuple())
    index = indices[component]
    if values[index] == 0:
        return resources, False
    values[index] -= 1
    return _vec(tuple(values)), True


def _event(event_type: str, state: State, **details: object) -> TraceEvent:
    safe_details = tuple(sorted((key, value) for key, value in details.items()))
    return TraceEvent(event_type, state.stage, state.time, safe_details)  # type: ignore[arg-type]


def _event_at(event_type: str, state: State, event_time: int, **details: object) -> TraceEvent:
    """Create an event with an explicit event time inside a multi-tick stage."""
    if event_time < state.time:
        raise ValueError("event_time cannot precede the current state time")
    safe_details = tuple(sorted((key, value) for key, value in details.items()))
    return TraceEvent(event_type, state.stage, event_time, safe_details)  # type: ignore[arg-type]


def _canonical_value(value: object) -> object:
    """Recursively serialize every transition-state field without omissions."""
    if isinstance(value, Enum):
        return {"__enum__": f"{type(value).__module__}.{type(value).__qualname__}", "value": value.value}
    if is_dataclass(value) and not isinstance(value, type):
        return {
            "__dataclass__": f"{type(value).__module__}.{type(value).__qualname__}",
            "fields": {field.name: _canonical_value(getattr(value, field.name)) for field in fields(value)},
        }
    if isinstance(value, tuple):
        return [_canonical_value(item) for item in value]
    if isinstance(value, list):
        return [_canonical_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _canonical_value(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported value in canonical state serialization: {type(value).__name__}")


def canonical_state_payload(state: State) -> dict[str, object]:
    """Canonical recursive serialization of all state dataclasses and fields.

    This deliberately includes nested provenance labels, identifiers and versions
    because they are part of the X27 state identity used by purity and partition
    fingerprints. Trace journals remain outside State and are not hashed here.
    """
    payload = _canonical_value(state)
    if not isinstance(payload, dict):  # defensive contract for the serializer
        raise TypeError("canonical State serialization must produce an object")
    return payload


def state_digest(state: State) -> str:
    payload = json.dumps(canonical_state_payload(state), sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def make_initial_state(
    *,
    task_memory: Optional[MemoryRecord] = None,
    prod_memory: Optional[RepairRecord] = None,
    residual_payload: Optional[MemoryRecord] = None,
    payload_accessible: bool = True,
    apparatus: Optional[Apparatus] = None,
    resources: Optional[ResourceVector] = None,
) -> State:
    m, tm = (MemoryRecord.make(0), MemoryRecord.make(1))
    return State(
        task_memory=task_memory or m,
        prod_memory=prod_memory or RepairRecord.make("r0"),
        residual_payload=residual_payload or m,
        payload_accessible=payload_accessible,
        apparatus=apparatus or Apparatus.a1(),
        resources=resources or ResourceVector(3, 2, 0, 0),
    )


def _resource_operation_details(
    before: ResourceVector,
    operation: ResourceOperation,
    result: ResourceApplication,
) -> dict[str, str | int | bool]:
    """Flat, lossless event fields for an auditable per-operation resource ledger."""
    fields: dict[str, str | int | bool] = {
        "operation": operation.name,
        "operation_status": "RESOURCE_EXHAUSTED" if result.exhausted else "APPLIED",
    }
    labels = ("E", "M", "W", "U")
    vectors = {
        "before": before,
        "inflow": operation.inflow,
        "cost": operation.cost,
        "byproduct": operation.byproduct,
        "after": result.resources,
        "spill_inflow": result.spill_inflow,
        "spill_byproduct": result.spill_byproduct,
    }
    for prefix, vector in vectors.items():
        for label, value in zip(labels, vector.as_tuple()):
            fields[f"{prefix}_{label}"] = value
    return fields


def _resource_event_set(
    events: list[TraceEvent],
    state: State,
    result: ResourceApplication,
    operation: ResourceOperation,
) -> None:
    events.append(
        _event(
            "resource_operation_event",
            state,
            **_resource_operation_details(state.resources, operation, result),
        )
    )
    if any(result.spill_inflow.as_tuple()):
        events.append(
            _event(
                "overflow_event",
                state,
                operation=operation.name,
                spill_energy=result.spill_inflow.energy,
                spill_material=result.spill_inflow.material,
                spill_waste=result.spill_inflow.waste,
                spill_unavailable=result.spill_inflow.unavailable,
                phase="inflow",
            )
        )
    if any(result.spill_byproduct.as_tuple()):
        events.append(
            _event(
                "overflow_event",
                state,
                operation=operation.name,
                spill_energy=result.spill_byproduct.energy,
                spill_material=result.spill_byproduct.material,
                spill_waste=result.spill_byproduct.waste,
                spill_unavailable=result.spill_byproduct.unavailable,
                phase="byproduct",
            )
        )

def _apply_task_action(state: State, *, task_number: int, config: ModelConfig) -> tuple[State, list[TraceEvent]]:
    events: list[TraceEvent] = []
    operand = state.task1_operand if task_number == 1 else state.task2_operand
    source = state.task1_read_source if task_number == 1 else state.task2_read_source
    existing_status = state.task1_status if task_number == 1 else state.task2_status
    if existing_status == OutcomeStatus.INTEGRITY_ERROR.value:
        status = OutcomeStatus.INTEGRITY_ERROR.value
        events.append(_event("task_action_rejected", state, task=task_number, status=status, reason="main_memory_checksum_mismatch"))
        if task_number == 1:
            return replace(state, task1_status=status), events
        return replace(state, task2_status=status), events

    if operand is None or source != "M_task":
        status = OutcomeStatus.MISSING_READ_EVENT.value
        events.append(_event("task_action_rejected", state, task=task_number, status=status, reason="missing_main_memory_read"))
        if task_number == 1:
            return replace(state, task1_status=status), events
        return replace(state, task2_status=status), events

    if not state.apparatus.operational:
        status = OutcomeStatus.APPARATUS_DEGRADED.value
        events.append(_event("task_action_rejected", state, task=task_number, status=status, reason="apparatus_not_operational"))
        if task_number == 1:
            return replace(state, task1_status=status), events
        return replace(state, task2_status=status), events

    if config.required_token_signature is not None and state.apparatus.token_signature != config.required_token_signature:
        status = OutcomeStatus.APPARATUS_DEGRADED.value
        events.append(_event("task_action_rejected", state, task=task_number, status=status, reason="token_signature_mismatch"))
        if task_number == 1:
            return replace(state, task1_status=status), events
        return replace(state, task2_status=status), events

    op = ResourceOperation(
        name=f"TASK_{task_number}",
        cost=config.task_cost,
        byproduct=config.task_byproduct,
    )
    applied = apply_resource_operation(state.resources, op)
    _resource_event_set(events, state, applied, op)
    if applied.exhausted:
        status = OutcomeStatus.RESOURCE_EXHAUSTED.value
        events.append(_event("task_action_rejected", state, task=task_number, status=status))
        if task_number == 1:
            return replace(state, resources=applied.resources, task1_status=status), events
        return replace(state, resources=applied.resources, task2_status=status), events

    events.append(
        _event(
            "apparatus_use_event",
            state,
            apparatus_id=state.apparatus.apparatus_id,
            creator_id=state.apparatus.creator_id,
            generation=state.apparatus.generation,
            resource_batch=state.apparatus.resource_batch,
            port_id=state.apparatus.port_id,
            task=task_number,
            action_operand=operand,
        )
    )
    events.append(_event("action_event", state, task=task_number, action_operand=operand))
    if task_number == 1:
        return replace(
            state,
            resources=applied.resources,
            apparatus=state.apparatus.worn(),
            task1_function=operand,
            task1_status=OutcomeStatus.SUCCESS.value,
        ), events
    return replace(
        state,
        resources=applied.resources,
        task2_function=operand,
        task2_status=OutcomeStatus.SUCCESS.value,
    ), events


def _repair_stage(
    state: State, arm: Arm, config: ModelConfig, *, causal_prod_read: bool
) -> tuple[State, list[TraceEvent]]:
    events: list[TraceEvent] = []
    if arm == Arm.R0:
        events.append(_event("restore_disabled", state, arm=arm.value))
        return state, events

    if arm == Arm.R_EXT:
        injection = ResourceOperation(name="EXTERNAL_INJECTION", inflow=config.external_injection)
        injected = apply_resource_operation(state.resources, injection)
        _resource_event_set(events, state, injected, injection)
        state = replace(state, resources=injected.resources, external_donor_used=True)
        events.append(_event("external_injection_event", state, amount=config.external_injection.as_tuple()))

    if state.apparatus.kind == EquipmentKind.ABSENT:
        events.append(_event("restore_rejected", state, status=OutcomeStatus.NO_RESTORE_POSSIBLE.value, reason="apparatus_absent"))
        return state, events

    if causal_prod_read:
        if not state.prod_memory.valid:
            events.append(_event("integrity_error", state, source="M_prod", record_id=state.prod_memory.record_id))
            return state, events
        instruction = state.prod_memory.instruction
        events.append(
            _event(
                "read_event",
                state,
                source="M_prod",
                record_id=state.prod_memory.record_id,
                version=state.prod_memory.version,
                returned_value=instruction,
            )
        )
    else:
        # R1 is independently testable with a fixed, predeclared protocol.
        # This branch intentionally does not read M_prod and cannot support R2.
        instruction = config.default_repair_instruction
    byproduct = config.repair_r0_byproduct if instruction == "r0" else config.repair_r1_byproduct
    op = ResourceOperation(name=f"REPAIR_{instruction}", cost=config.repair_cost, byproduct=byproduct)
    applied = apply_resource_operation(state.resources, op)
    _resource_event_set(events, state, applied, op)
    state = replace(state, resources=applied.resources, repair_instruction=instruction)
    if applied.exhausted:
        events.append(_event("repair_action_rejected", state, instruction=instruction, status=OutcomeStatus.RESOURCE_EXHAUSTED.value))
        return state, events

    events.append(_event("repair_action", state, instruction=instruction, read_source=("M_prod" if causal_prod_read else "frozen_protocol")))
    events.append(
        _event(
            "apparatus_repaired_event",
            state,
            apparatus_id=state.apparatus.apparatus_id,
            port_id=state.apparatus.port_id,
            instruction=instruction,
        )
    )
    return replace(
        state,
        apparatus=state.apparatus.repaired(),
        internal_restore_used=(arm == Arm.R_INT),
        external_donor_used=(arm == Arm.R_EXT),
    ), events


def advance_stage(
    state: State,
    *,
    arm: Arm = Arm.R_INT,
    disturbance: Disturbance = Disturbance.NONE,
    config: ModelConfig = ModelConfig(),
    causal_prod_read: bool = True,
    module: str = "B-LITE",
) -> StepOutcome:
    """Advance exactly one stage. Inputs are immutable; all changes are returned."""
    if state.terminal:
        return StepOutcome(state, ())

    events: list[TraceEvent] = []
    stage = Stage(state.stage)

    if stage == Stage.INITIALIZE:
        new_state = replace(state, stage=int(Stage.READ_TASK1), time=state.time + 1, source_off=True)
        events.append(_event("source_off_event", state, source="C", source_off=True, boundary="D_autonomous_start"))

    elif stage == Stage.READ_TASK1:
        if not state.source_off:
            events.append(_event("run_invalid", state, reason="source_not_off_before_read"))
            new_state = replace(state, stage=int(Stage.EXECUTE_TASK1), time=state.time + 1, task1_status="RUN_INVALID_SOURCE_ON")
        elif not state.task_memory.valid:
            events.append(_event("integrity_error", state, source="M_task", task=1, record_id=state.task_memory.record_id))
            new_state = replace(
                state,
                stage=int(Stage.EXECUTE_TASK1),
                time=state.time + 1,
                task1_read_source=None,
                task1_status=OutcomeStatus.INTEGRITY_ERROR.value,
            )
        else:
            events.append(
                _event(
                    "read_event",
                    state,
                    source="M_task",
                    task=1,
                    record_id=state.task_memory.record_id,
                    version=state.task_memory.version,
                    returned_value=state.task_memory.semantic_bit,
                )
            )
            events.append(_event("action_operand_bound", state, task=1, operand=state.task_memory.semantic_bit))
            new_state = replace(
                state,
                stage=int(Stage.EXECUTE_TASK1),
                time=state.time + 1,
                task1_operand=state.task_memory.semantic_bit,
                task1_read_source="M_task",
            )

    elif stage == Stage.EXECUTE_TASK1:
        acted, action_events = _apply_task_action(state, task_number=1, config=config)
        events.extend(action_events)
        target_stage = Stage.TERMINAL if module == "A" else Stage.RESTORE
        new_state = replace(acted, stage=int(target_stage), time=state.time + 1)

    elif stage == Stage.RESTORE:
        restored, restore_events = _repair_stage(state, arm, config, causal_prod_read=causal_prod_read)
        events.extend(restore_events)
        new_state = replace(restored, stage=int(Stage.READINESS), time=state.time + 1)

    elif stage == Stage.READINESS:
        new_state = replace(state, stage=int(Stage.DISTURBANCE_AND_READ_TASK2), time=state.time + 1)
        events.append(_event("readiness_checkpoint", state, time_before_task2=state.time))

    elif stage == Stage.DISTURBANCE_AND_READ_TASK2:
        resources = state.resources
        delay = 0
        if disturbance == Disturbance.DELAY:
            delay = config.delay_steps
            events.append(_event("disturbance_event", state, disturbance=disturbance.value, delay_steps=delay))
            events.append(_event_at("delay_start_event", state, state.time, delay_steps=delay))
            events.append(_event_at("delay_end_event", state, state.time + delay, delay_steps=delay))
        elif disturbance in (Disturbance.LOSS_E, Disturbance.LOSS_M):
            component = "E" if disturbance == Disturbance.LOSS_E else "M"
            resources_before_loss = resources
            resources, applied = apply_resource_loss(resources, component)
            before_values = dict(zip(("E", "M", "W", "U"), resources_before_loss.as_tuple()))
            after_values = dict(zip(("E", "M", "W", "U"), resources.as_tuple()))
            events.append(_event("disturbance_event", state, disturbance=disturbance.value, component=component, applied=applied))
            events.append(
                _event(
                    "resource_loss_event",
                    state,
                    component=component,
                    applied=applied,
                    amount=(1 if applied else 0),
                    **{f"before_{key}": value for key, value in before_values.items()},
                    **{f"after_{key}": value for key, value in after_values.items()},
                )
            )
            if not applied:
                events.append(_event("loss_not_applicable", state, component=component))
        if state.time + 1 + delay > config.max_time:
            new_state = replace(
                state,
                stage=int(Stage.TERMINAL),
                time=state.time + 1 + delay,
                resources=resources,
                task2_status=OutcomeStatus.TIMEOUT.value,
            )
            events.append(_event_at("timeout_event", state, state.time + 1 + delay, task=2, max_time=config.max_time, phase="delay_or_read_deadline"))
        elif not state.task_memory.valid:
            new_state = replace(
                state,
                stage=int(Stage.EXECUTE_TASK2),
                time=state.time + 1 + delay,
                resources=resources,
                task2_status=OutcomeStatus.INTEGRITY_ERROR.value,
            )
            events.append(_event_at("integrity_error", state, state.time + delay, source="M_task", task=2, record_id=state.task_memory.record_id))
        else:
            read_time = state.time + delay
            events.append(
                _event_at(
                    "read_event",
                    state,
                    read_time,
                    source="M_task",
                    task=2,
                    record_id=state.task_memory.record_id,
                    version=state.task_memory.version,
                    returned_value=state.task_memory.semantic_bit,
                )
            )
            events.append(_event_at("action_operand_bound", state, read_time, task=2, operand=state.task_memory.semantic_bit))
            new_state = replace(
                state,
                stage=int(Stage.EXECUTE_TASK2),
                time=state.time + 1 + delay,
                resources=resources,
                task2_operand=state.task_memory.semantic_bit,
                task2_read_source="M_task",
                task2_status=None,
            )

    elif stage == Stage.EXECUTE_TASK2:
        if state.time + 1 > config.max_time:
            new_state = replace(
                state,
                stage=int(Stage.TERMINAL),
                time=state.time + 1,
                task2_status=OutcomeStatus.TIMEOUT.value,
            )
            events.append(_event("timeout_event", new_state, task=2, max_time=config.max_time, phase="execution"))
            events.append(_event("task2_terminal_event", new_state, status=OutcomeStatus.TIMEOUT.value))
        elif state.task2_status in (OutcomeStatus.INTEGRITY_ERROR.value, OutcomeStatus.TIMEOUT.value):
            new_state = replace(state, stage=int(Stage.TERMINAL), time=state.time + 1)
            events.append(_event("task2_terminal_event", new_state, status=state.task2_status))
        else:
            acted, action_events = _apply_task_action(state, task_number=2, config=config)
            events.extend(action_events)
            status = acted.task2_status
            new_state = replace(acted, stage=int(Stage.TERMINAL), time=state.time + 1, task2_status=status)
            events.append(_event("task2_terminal_event", new_state, status=status))

    else:  # defensive: all stage values are enumerated above
        raise RuntimeError(f"unhandled stage: {state.stage}")

    return StepOutcome(new_state, tuple(events))


def simulate_task2_from_snapshot(
    snapshot: State,
    disturbance: Disturbance,
    *,
    arm: Arm = Arm.R_INT,
    config: ModelConfig = ModelConfig(),
    causal_prod_read: bool = True,
) -> ScenarioResult:
    """Evaluate Task 2 from an immutable post-repair snapshot (stage 4)."""
    if snapshot.stage != int(Stage.READINESS):
        raise ValueError("readiness snapshot must be at stage 4")
    state = deepcopy(snapshot)
    events: list[TraceEvent] = []
    while not state.terminal:
        step = advance_stage(state, arm=arm, disturbance=disturbance, config=config, causal_prod_read=causal_prod_read)
        state = step.state
        events.extend(step.events)
    success = state.task2_status == OutcomeStatus.SUCCESS.value
    return ScenarioResult(
        disturbance=disturbance.value,
        success=success,
        status=state.task2_status or OutcomeStatus.ABORTED.value,
        finish_time=state.time,
        resources_final=state.resources,
        state_final=state,
        events=tuple(events),
    )


def estimate_readiness(
    snapshot: State,
    *,
    arm: Arm = Arm.R_INT,
    config: ModelConfig = ModelConfig(),
    causal_prod_read: bool = True,
    stress_scenarios: Iterable[Disturbance] = (
        Disturbance.DELAY,
        Disturbance.LOSS_E,
        Disturbance.LOSS_M,
    ),
) -> ReadinessReport:
    """Pure readiness estimator; every scenario starts from the same snapshot.

    No shared mutable state or short-circuit evaluation is used. All declared
    scenarios are computed before V_rob is aggregated.
    """
    scenario_list = tuple(stress_scenarios)
    required_scenarios = {Disturbance.DELAY, Disturbance.LOSS_E, Disturbance.LOSS_M}
    if not scenario_list:
        raise ValueError("stress_scenarios must not be empty; robust readiness is not evaluable without stress cases")
    if any(not isinstance(item, Disturbance) for item in scenario_list):
        raise TypeError("stress_scenarios must contain Disturbance enum values")
    if len(set(scenario_list)) != len(scenario_list):
        raise ValueError("stress_scenarios must not contain duplicates")
    if set(scenario_list) != required_scenarios:
        missing = sorted(item.value for item in required_scenarios - set(scenario_list))
        extra = sorted(item.value for item in set(scenario_list) - required_scenarios)
        raise ValueError(f"stress_scenarios must equal the protocol set; missing={missing}, extra={extra}")

    before = state_digest(snapshot)
    frozen_snapshot = deepcopy(snapshot)
    nominal = simulate_task2_from_snapshot(frozen_snapshot, Disturbance.NONE, arm=arm, config=config, causal_prod_read=causal_prod_read)
    stress_results = tuple(
        simulate_task2_from_snapshot(deepcopy(frozen_snapshot), scenario, arm=arm, config=config, causal_prod_read=causal_prod_read)
        for scenario in scenario_list
    )
    after = state_digest(snapshot)

    # Repeat in reverse order as an explicit order-independence check.
    reverse_results = tuple(
        simulate_task2_from_snapshot(deepcopy(frozen_snapshot), scenario, arm=arm, config=config, causal_prod_read=causal_prod_read)
        for scenario in reversed(scenario_list)
    )
    forward_by_name = {result.disturbance: result.as_dict() for result in stress_results}
    reverse_by_name = {result.disturbance: result.as_dict() for result in reverse_results}
    order_independent = forward_by_name == reverse_by_name
    purity_pass = before == after
    all_results = (nominal,) + stress_results
    return ReadinessReport(
        v_nom=nominal.success,
        v_rob=all(result.success for result in stress_results),
        scenarios=all_results,
        state_hash_before=before,
        state_hash_after=after,
        purity_pass=purity_pass,
        order_independent=order_independent,
    )


def run_b_lite(
    *,
    arm: Arm,
    disturbance: Disturbance = Disturbance.NONE,
    task_memory: Optional[MemoryRecord] = None,
    prod_memory: Optional[RepairRecord] = None,
    residual_payload: Optional[MemoryRecord] = None,
    apparatus: Optional[Apparatus] = None,
    config: ModelConfig = ModelConfig(),
    causal_prod_read: bool = False,
) -> RunResult:
    """Run one B-LITE arm; Task 2 reuses the original M_task record."""
    state = make_initial_state(
        task_memory=task_memory,
        prod_memory=prod_memory,
        residual_payload=residual_payload,
        apparatus=apparatus,
        resources=config.initial_resources,
    )
    trace: list[TraceEvent] = list(
        trusted_prehistory_events(
            memory=state.task_memory,
            prod_memory=state.prod_memory,
            apparatus=state.apparatus,
            residual_payload=state.residual_payload,
        )
    )
    while state.stage < int(Stage.READINESS):
        step = advance_stage(state, arm=arm, disturbance=Disturbance.NONE, config=config, causal_prod_read=causal_prod_read)
        state = step.state
        trace.extend(step.events)

    readiness = estimate_readiness(state, arm=arm, config=config, causal_prod_read=causal_prod_read)
    while not state.terminal:
        step = advance_stage(state, arm=arm, disturbance=disturbance, config=config, causal_prod_read=causal_prod_read)
        state = step.state
        trace.extend(step.events)

    return RunResult(arm.value, disturbance.value, state, readiness, tuple(trace))


def run_task1_probe(
    *,
    task_memory: MemoryRecord,
    residual_payload: MemoryRecord,
    apparatus: Apparatus,
    payload_accessible: bool = True,
    read_source: str = "M_task",
    config: ModelConfig = ModelConfig(),
) -> Task1Probe:
    """Run the X27-A Task-1 probe under a declared read source.

    read_source='P_res' is used only for the bypass positive control. Main
    factorial cells use read_source='M_task' while payload remains accessible.
    """
    if read_source not in ("M_task", "P_res", "none"):
        raise ValueError("read_source must be M_task, P_res or none")
    resources = config.initial_resources
    events: list[TraceEvent] = list(
        trusted_prehistory_events(
            memory=task_memory,
            prod_memory=None,
            apparatus=apparatus,
            residual_payload=residual_payload,
        )
    )
    events.append(TraceEvent("source_off_event", 0, 0, (("source", "C"), ("source_off", True))))
    t = 1  # source_off / D autonomous boundary
    operand: Optional[int] = None
    source_used: Optional[str] = None
    integrity_error = False

    if read_source == "M_task":
        if task_memory.valid:
            operand = task_memory.semantic_bit
            source_used = "M_task"
            events.append(TraceEvent("read_event", 1, t, (("source", "M_task"), ("returned_value", operand))))
        else:
            integrity_error = True
            events.append(TraceEvent("integrity_error", 1, t, (("source", "M_task"),)))
    elif read_source == "P_res":
        if payload_accessible and residual_payload.valid:
            operand = residual_payload.semantic_bit
            source_used = "P_res"
            events.append(TraceEvent("read_event", 1, t, (("source", "P_res"), ("returned_value", operand))))
        else:
            events.append(TraceEvent("payload_unavailable", 1, t, ()))
    else:
        events.append(TraceEvent("read_skipped", 1, t, ()))

    t += 1
    used_apparatus = False
    function: Optional[int] = None
    if operand is None:
        status = (
            OutcomeStatus.INTEGRITY_ERROR.value
            if integrity_error
            else OutcomeStatus.MISSING_READ_EVENT.value
        )
    elif not apparatus.operational:
        status = OutcomeStatus.APPARATUS_DEGRADED.value
    elif config.required_token_signature is not None and apparatus.token_signature != config.required_token_signature:
        status = OutcomeStatus.APPARATUS_DEGRADED.value
    else:
        op = ResourceOperation("TASK_1", cost=config.task_cost, byproduct=config.task_byproduct)
        applied = apply_resource_operation(resources, op)
        resource_details = _resource_operation_details(resources, op, applied)
        events.append(TraceEvent("resource_operation_event", 2, t, tuple(sorted(resource_details.items()))))
        for name in ("spill_inflow", "spill_byproduct"):
            spill = getattr(applied, name)
            if any(spill.as_tuple()):
                events.append(
                    TraceEvent(
                        "overflow_event",
                        2,
                        t,
                        (("operation", op.name), ("spill", spill.as_tuple())),
                    )
                )
        resources = applied.resources
        if applied.exhausted:
            status = OutcomeStatus.RESOURCE_EXHAUSTED.value
        else:
            status = OutcomeStatus.SUCCESS.value
            function = operand
            used_apparatus = True
            events.append(
                TraceEvent(
                    "apparatus_use_event",
                    2,
                    t,
                    (
                        ("apparatus_id", apparatus.apparatus_id),
                        ("creator_id", apparatus.creator_id),
                        ("generation", apparatus.generation),
                        ("resource_batch", apparatus.resource_batch),
                        ("port_id", apparatus.port_id),
                        ("action_operand", operand),
                    ),
                )
            )
            events.append(TraceEvent("action_event", 2, t, (("action_operand", operand),)))
    worn = apparatus.worn() if used_apparatus else apparatus
    profile = Task1Profile(function, status, t + 1, resources)
    return Task1Probe(profile, tuple(events), worn, source_used, used_apparatus)


def trusted_prehistory_events(
    *,
    memory: MemoryRecord,
    prod_memory: Optional[RepairRecord],
    apparatus: Apparatus,
    residual_payload: Optional[MemoryRecord] = None,
) -> tuple[TraceEvent, ...]:
    """Record variant-B provenance as trusted exogenous prehistory, not a claim
    that this experiment simulated C's production or transfer costs.
    """
    events: list[TraceEvent] = []
    if memory.creator_id == "C":
        events.extend((
            TraceEvent("C_write_event_exogenous", -5, -5, (("record_id", memory.record_id), ("creator_id", memory.creator_id))),
            TraceEvent("C_memory_transfer_event_exogenous", -2, -2, (("record_id", memory.record_id), ("creator_id", memory.creator_id))),
        ))
    else:
        events.extend((
            TraceEvent("memory_provenance_declared_event_exogenous", -5, -5, (("record_id", memory.record_id), ("creator_id", memory.creator_id))),
            TraceEvent("external_memory_transfer_event_exogenous", -2, -2, (("record_id", memory.record_id), ("creator_id", memory.creator_id))),
        ))
    if residual_payload is not None:
        if residual_payload.creator_id == "C":
            events.append(
                TraceEvent("C_payload_write_event_exogenous", -4, -4, (("record_id", residual_payload.record_id), ("creator_id", residual_payload.creator_id)))
            )
            events.append(
                TraceEvent("C_payload_transfer_event_exogenous", -2, -2, (("record_id", residual_payload.record_id), ("creator_id", residual_payload.creator_id)))
            )
        else:
            events.append(
                TraceEvent("external_payload_provenance_event_exogenous", -4, -4, (("record_id", residual_payload.record_id), ("creator_id", residual_payload.creator_id)))
            )
    if prod_memory is not None:
        prod_event_type = (
            "C_prod_instruction_write_event_exogenous"
            if prod_memory.creator_id == "C"
            else "external_prod_instruction_event_exogenous"
        )
        events.append(
            TraceEvent(prod_event_type, -4, -4, (("record_id", prod_memory.record_id), ("creator_id", prod_memory.creator_id)))
        )

    if apparatus.kind == EquipmentKind.ORIGINAL and apparatus.creator_id == "C":
        events.append(
            TraceEvent("C_produce_event_exogenous", -4, -4, (("apparatus_id", apparatus.apparatus_id), ("creator_id", apparatus.creator_id)))
        )
        events.append(
            TraceEvent("C_apparatus_transfer_event_exogenous", -2, -2, (("apparatus_id", apparatus.apparatus_id), ("creator_id", apparatus.creator_id)))
        )
        apparatus_provenance = "C_PRODUCED_AND_TRANSFERRED"
    elif apparatus.kind == EquipmentKind.SUBSTITUTE:
        events.append(
            TraceEvent("test_fixture_provide_event_exogenous", -4, -4, (("apparatus_id", apparatus.apparatus_id), ("creator_id", apparatus.creator_id)))
        )
        events.append(
            TraceEvent("test_fixture_transfer_event_exogenous", -2, -2, (("apparatus_id", apparatus.apparatus_id), ("creator_id", apparatus.creator_id)))
        )
        apparatus_provenance = "TEST_FIXTURE"
    elif apparatus.kind == EquipmentKind.ABSENT:
        events.append(TraceEvent("apparatus_absence_declared_event", -2, -2, (("apparatus_present", False),)))
        apparatus_provenance = "ABSENT"
    else:
        events.append(
            TraceEvent("apparatus_provenance_event_exogenous", -4, -4, (("apparatus_id", apparatus.apparatus_id), ("creator_id", apparatus.creator_id)))
        )
        apparatus_provenance = "OTHER_ORIGIN"

    events.append(
        TraceEvent(
            "D_receive_event_exogenous",
            -1,
            -1,
            (
                ("holder", "D"),
                ("production_and_transfer_simulated", False),
                ("apparatus_present", apparatus.kind != EquipmentKind.ABSENT),
                ("apparatus_provenance", apparatus_provenance),
            ),
        )
    )
    return tuple(events)
