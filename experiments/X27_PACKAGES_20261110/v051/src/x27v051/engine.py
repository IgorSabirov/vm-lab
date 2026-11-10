"""X27 v0.5.1 capability, repair, dose and readiness engines."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, fields, is_dataclass, replace
from enum import Enum
from hashlib import sha256
import json
from typing import Any, Iterable, Optional

from .model import (
    Apparatus, Arm, BState, DELAY_STEPS, Disturbance, Health, INITIAL_MATERIAL,
    MAX_TIME, MemoryRecord, RepairRecord, ResourceVector, Stage, Status, TraceEvent, emit,
    REQUIRED_STRESS,
)
from .resources import (
    EXTERNAL_INJECTION, REPAIR_BYPRODUCT, REPAIR_COST, TASK_BYPRODUCT, TASK_COST,
    apply_loss, apply_operation,
)


def _canonical(value: Any) -> Any:
    if isinstance(value, Enum):
        return {"enum": type(value).__name__, "value": value.value}
    if is_dataclass(value) and not isinstance(value, type):
        return {"dataclass": type(value).__name__,
                "fields": {f.name: _canonical(getattr(value, f.name)) for f in fields(value)}}
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in sorted(value.items(), key=lambda x: str(x[0]))}
    if isinstance(value, (tuple, list)):
        return [_canonical(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported state value {type(value).__name__}")


def state_digest(state: BState) -> str:
    payload = json.dumps(_canonical(state), sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def validate_read_before_action(events: Iterable[TraceEvent], source: str, task: str) -> str:
    """Return a source- and task-specific causal-read verdict from an event trace."""
    materialized = tuple(events)
    read_index = next((i for i, event in enumerate(materialized)
                       if event.event_type == "read_event"
                       and dict(event.details).get("source") == source
                       and dict(event.details).get("task") == task), None)
    action_index = next((i for i, event in enumerate(materialized)
                         if event.event_type == "action_event"
                         and dict(event.details).get("task") == task), None)
    if read_index is None:
        return Status.MISSING_READ_EVENT.value
    if action_index is None:
        return "NO_ACTION_EVENT"
    if read_index >= action_index:
        return "READ_NOT_BEFORE_ACTION"
    return "CAUSAL_READ_VALID"


def validate_causal_record_chain(events: Iterable[TraceEvent], source: str, task: str,
                                 record: MemoryRecord | RepairRecord) -> bool:
    """Require one provenance identity from exogenous receipt through read to action.

    This is stronger than a source/time check: record_id, version and creator_id
    must match at provenance, transfer, receipt, read and action boundaries.
    """
    materialized = tuple(events)
    if source == "M_task":
        if task not in ("Task1", "Task2"):
            raise ValueError("M_task chain task must be Task1 or Task2")
        provenance_kinds = {"C_write_event_exogenous", "external_record_provenance_event_exogenous"}
        transfer_kinds = {"C_memory_transfer_event_exogenous", "external_record_transfer_event_exogenous"}
        receive_kind = "D_receive_memory_event_exogenous"
        action_kind, action_field = "action_event", "operand"
    elif source == "M_prod":
        if task != "repair":
            raise ValueError("M_prod chain task must be repair")
        provenance_kinds = {"C_prod_instruction_write_event_exogenous", "external_prod_instruction_event_exogenous"}
        transfer_kinds = {"C_prod_instruction_transfer_event_exogenous", "external_prod_instruction_transfer_event_exogenous"}
        receive_kind = "D_receive_prod_memory_event_exogenous"
        action_kind, action_field = "repair_action_event", "instruction"
    else:
        raise ValueError("record-chain validation supports M_task and M_prod")

    expected = {"source": source, "record_id": record.record_id,
                "version": record.version, "creator_id": record.creator_id}

    def idx(predicate):
        return next((i for i, event in enumerate(materialized) if predicate(event)), None)

    def matches(event):
        details = dict(event.details)
        return all(details.get(key) == value for key, value in expected.items())

    provenance_i = idx(lambda e: e.event_type in provenance_kinds and matches(e))
    transfer_i = idx(lambda e: e.event_type in transfer_kinds and matches(e))
    receive_i = idx(lambda e: e.event_type == receive_kind and matches(e)
                    and dict(e.details).get("holder") == "D"
                    and dict(e.details).get("accessible") is True)
    source_off_i = idx(lambda e: e.event_type == "source_off_event"
                       and dict(e.details).get("new_writes_permitted") is False
                       and dict(e.details).get("new_transfers_permitted") is False)
    read_i = idx(lambda e: e.event_type == "read_event" and matches(e)
                 and dict(e.details).get("task") == task)
    action_i = idx(lambda e: e.event_type == action_kind
                   and dict(e.details).get("task", "repair" if task == "repair" else None) == task)
    indices = (provenance_i, transfer_i, receive_i, source_off_i, read_i, action_i)
    if any(i is None for i in indices):
        return False
    if not (provenance_i < transfer_i < receive_i < source_off_i < read_i < action_i):
        return False
    read_details = dict(materialized[read_i].details)
    action_details = dict(materialized[action_i].details)
    return (read_details.get("returned_value") == action_details.get(action_field)
            and action_details.get("read_source") == source
            and action_details.get("source_record_id") == record.record_id
            and action_details.get("source_record_version") == record.version
            and action_details.get("source_record_creator_id") == record.creator_id)


@dataclass(frozen=True, slots=True)
class Task2Result:
    disturbance: str
    load: int
    success: bool
    status: str
    finish_time: int
    health_before: int
    health_after: int
    resources_final: tuple[int, int, int, int]
    gates: tuple[tuple[str, bool], ...]
    events: tuple[TraceEvent, ...]
    ledger: tuple[dict[str, object], ...]
    y_action: Optional[int] = None

    def as_dict(self) -> dict[str, object]:
        return {
            "disturbance": self.disturbance, "load": self.load, "success": self.success,
            "status": self.status, "finish_time": self.finish_time,
            "health_before": self.health_before, "health_after": self.health_after,
            "resources_final": self.resources_final, "gates": dict(self.gates),
            "Y_action": self.y_action,
            "events": [e.as_dict() for e in self.events], "ledger": list(self.ledger),
        }


def simulate_task2(snapshot: BState, disturbance: str, load: int = 1,
                   max_time: int = MAX_TIME) -> Task2Result:
    """Pure Task-2 simulation from a post-repair stage-4 snapshot."""
    if snapshot.stage != int(Stage.READINESS):
        raise ValueError("Task-2 simulator requires a stage-4 snapshot")
    if load not in (1, 2):
        raise ValueError("Task-2 load must be 1 or 2")
    if disturbance not in ("omega_0",) + REQUIRED_STRESS:
        raise ValueError(f"unknown disturbance {disturbance}")
    state = deepcopy(snapshot)
    events: list[TraceEvent] = []
    ledger: list[dict[str, object]] = []
    action_result: Optional[int] = None
    # Stage 5: disturbance occurs before Task-2 read.
    state = replace(state, stage=int(Stage.DISTURBANCE_AND_READ_TASK2), time=5)
    read_time = 5
    if disturbance == "omega_delay":
        events.append(TraceEvent("delay_start_event", 5, 5, (("steps", DELAY_STEPS),)))
        read_time += DELAY_STEPS
        events.append(TraceEvent("delay_end_event", 5, read_time, (("steps", DELAY_STEPS),)))
        state = replace(state, time=read_time)
    elif disturbance in ("omega_loss_E", "omega_loss_M"):
        comp = "E" if disturbance.endswith("E") else "M"
        after, applicable, log = apply_loss(state.resources, comp)
        events.append(TraceEvent("resource_loss_event", 5, 5, tuple(sorted(log.items()))))
        state = replace(state, resources=after)
    # Task-2 read is distinct from the M_prod repair read.
    if state.task_memory.valid:
        read_value = state.task_memory.semantic_bit
        events.append(TraceEvent("read_event", 5, read_time,
                                 (("source", "M_task"), ("task", "Task2"),
                                  ("record_id", state.task_memory.record_id),
                                  ("version", state.task_memory.version),
                                  ("creator_id", state.task_memory.creator_id),
                                  ("returned_value", read_value))))
        state = replace(state, task2_read=read_value, task2_operand=read_value)
        g_memory = True
    else:
        events.append(TraceEvent("integrity_error_event", 5, read_time,
                                 (("source", "M_task"), ("task", "Task2"))))
        g_memory = False
        state = replace(state, task2_read=None, task2_operand=None)
    # Stage 6: an action takes one tick after read.
    action_time = read_time + 1
    state = replace(state, stage=int(Stage.EXECUTE_TASK2), time=action_time)
    health_before = state.apparatus.health
    g_health = state.apparatus.operational and health_before >= load
    g_resource = state.resources.energy >= TASK_COST[0]
    g_time = action_time + 1 <= max_time
    gates = (("G_memory", g_memory), ("G_health", g_health),
             ("G_resource", g_resource), ("G_time", g_time))
    if not g_memory:
        status = Status.INTEGRITY_ERROR.value
    elif not g_health:
        status = Status.APPARATUS_DEGRADED.value
    elif not g_resource:
        status = Status.RESOURCE_EXHAUSTED.value
    elif not g_time:
        status = Status.TIMEOUT.value
    else:
        op = apply_operation(state.resources, name="Task2", cost=TASK_COST, byproduct=TASK_BYPRODUCT)
        ledger.append(op.as_dict())
        if op.exhausted:
            status = Status.RESOURCE_EXHAUSTED.value
            g_resource = False
            gates = (("G_memory", g_memory), ("G_health", g_health),
                     ("G_resource", False), ("G_time", g_time))
            state = replace(state, resources=op.resources)
        else:
            status = Status.SUCCESS.value
            state = replace(state, resources=op.resources,
                              apparatus=state.apparatus.with_health(health_before - 1))
            action_result = state.task2_operand
            events.append(TraceEvent("action_event", 6, action_time,
                                     (("task", "Task2"), ("operand", state.task2_operand),
                                      ("result", action_result), ("status", status),
                                      ("read_source", "M_task"),
                                      ("source_record_id", state.task_memory.record_id),
                                      ("source_record_version", state.task_memory.version),
                                      ("source_record_creator_id", state.task_memory.creator_id))))
    if status != Status.SUCCESS.value:
        events.append(TraceEvent("task2_failed_event", 6, action_time,
                                 (("status", status), ("gates", tuple(gates)))))
    finish = action_time + 1
    state = replace(state, stage=int(Stage.TERMINAL), time=finish, task2_status=status)
    events.append(TraceEvent("terminal_event", 7, finish, (("status", status),)))
    return Task2Result(disturbance, load, status == Status.SUCCESS.value, status, finish,
                       health_before, state.apparatus.health, state.resources.as_tuple(),
                       tuple(gates), tuple(events), tuple(ledger), action_result)


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    v_nom: bool
    v_rob: bool
    nominal: Task2Result
    stress: tuple[Task2Result, ...]
    digest_before: str
    digest_after: str
    purity_pass: bool
    order_independent: bool
    required_stress: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {"V_nom": self.v_nom, "V_rob": self.v_rob,
                "nominal": self.nominal.as_dict(),
                "stress": [s.as_dict() for s in self.stress],
                "digest_before": self.digest_before, "digest_after": self.digest_after,
                "purity_pass": self.purity_pass, "order_independent": self.order_independent,
                "required_stress": self.required_stress}


def estimate_readiness(snapshot: BState, stress_scenarios: Iterable[str] = REQUIRED_STRESS,
                       load: int = 1, max_time: int = MAX_TIME) -> ReadinessReport:
    scenarios = tuple(stress_scenarios)
    if not scenarios:
        raise ValueError("stress scenario set cannot be empty")
    if len(scenarios) != len(set(scenarios)):
        raise ValueError("stress scenario set cannot contain duplicates")
    if set(scenarios) != set(REQUIRED_STRESS):
        raise ValueError(f"stress scenario set must equal {REQUIRED_STRESS}")
    before = state_digest(snapshot)
    nominal = simulate_task2(deepcopy(snapshot), "omega_0", load, max_time)
    forward = tuple(simulate_task2(deepcopy(snapshot), w, load, max_time) for w in scenarios)
    reverse = tuple(simulate_task2(deepcopy(snapshot), w, load, max_time) for w in reversed(scenarios))
    forward_map = {r.disturbance: (r.success, r.status, r.finish_time, r.resources_final, r.health_after) for r in forward}
    reverse_map = {r.disturbance: (r.success, r.status, r.finish_time, r.resources_final, r.health_after) for r in reverse}
    after = state_digest(snapshot)
    purity = before == after
    order_independent = forward_map == reverse_map
    return ReadinessReport(nominal.success, all(r.success for r in forward), nominal,
                           forward, before, after, purity, order_independent, scenarios)


@dataclass(frozen=True, slots=True)
class BLiteRun:
    arm: str
    dose_energy: int
    repair_instruction: Optional[str]
    causal_prod_read: bool
    load: int
    state_after_repair: BState
    executed: Task2Result
    readiness: Optional[ReadinessReport]
    events: tuple[TraceEvent, ...]
    ledger: tuple[dict[str, object], ...]
    repair_health_gain: int

    @property
    def task2_reached(self) -> bool:
        # A Task-2 read or integrity check at stage 5 is the first evidence
        # that the Task-2 phase was entered. A repair failure is not a Task-2 failure.
        return any(e.stage == int(Stage.DISTURBANCE_AND_READ_TASK2)
                   and e.event_type in ("read_event", "integrity_error_event",
                                        "delay_start_event", "resource_loss_event")
                   for e in self.executed.events)

    @property
    def pre_task2_terminal_cause(self) -> Optional[str]:
        return None if self.task2_reached else self.executed.status

    def as_dict(self) -> dict[str, object]:
        reached = self.task2_reached
        return {"arm": self.arm, "dose_energy": self.dose_energy,
                "repair_instruction": self.repair_instruction,
                "causal_prod_read": self.causal_prod_read, "load": self.load,
                "Y_task1_action": self.state_after_repair.task1_action,
                "Y_task2_action": self.executed.y_action if reached else None,
                "health_after_repair": self.state_after_repair.apparatus.health,
                "repair_health_gain": self.repair_health_gain,
                "Y_task2": self.executed.success if reached else None,
                "Y_status2": self.executed.status if reached else "NOT_REACHED",
                "pre_task2_terminal_cause": self.pre_task2_terminal_cause,
                "task2_reached": reached,
                "T_finish2": self.executed.finish_time if reached else None,
                "R_post2": self.executed.resources_final if reached else None,
                "R_at_terminal_before_task2": self.executed.resources_final if not reached else None,
                "V_nom": self.readiness.v_nom if self.readiness else None,
                "V_rob": self.readiness.v_rob if self.readiness else None,
                "readiness": self.readiness.as_dict() if self.readiness else None,
                "events": [e.as_dict() for e in self.events],
                "ledger": list(self.ledger)}


def _initial_b_state(dose_energy: int, task_memory: Optional[MemoryRecord] = None,
                     prod_memory: Optional[RepairRecord] = None) -> BState:
    return BState(
        task_memory=task_memory or MemoryRecord.make(0, "M_task"),
        prod_memory=prod_memory or RepairRecord.make("r0"),
        apparatus=Apparatus.a1(2),
        resources=ResourceVector(dose_energy, INITIAL_MATERIAL, 0, 0),
    )


def trusted_prehistory_events(memory: MemoryRecord, prod_memory: RepairRecord,
                              apparatus: Apparatus) -> tuple[TraceEvent, ...]:
    """Record object-specific variant-B prehistory as trusted exogenous facts."""
    events: list[TraceEvent] = []
    for record, source, write_kind, transfer_kind, receive_kind, external_write, external_transfer in (
        (memory, "M_task", "C_write_event_exogenous", "C_memory_transfer_event_exogenous",
         "D_receive_memory_event_exogenous", "external_record_provenance_event_exogenous",
         "external_record_transfer_event_exogenous"),
        (prod_memory, "M_prod", "C_prod_instruction_write_event_exogenous",
         "C_prod_instruction_transfer_event_exogenous", "D_receive_prod_memory_event_exogenous",
         "external_prod_instruction_event_exogenous", "external_prod_instruction_transfer_event_exogenous"),
    ):
        common = (("source", source), ("record_id", record.record_id),
                  ("version", record.version), ("creator_id", record.creator_id))
        if record.creator_id == "C":
            events.append(TraceEvent(write_kind, 0, 0, common))
            events.append(TraceEvent(transfer_kind, 0, 0, common))
        else:
            events.append(TraceEvent(external_write, 0, 0, common))
            events.append(TraceEvent(external_transfer, 0, 0, common))
        events.append(TraceEvent(receive_kind, 0, 0,
                                 common + (("holder", "D"), ("accessible", True))))

    if apparatus.kind == "original" and apparatus.creator_id == "C":
        events.extend((
            TraceEvent("C_produce_event_exogenous", 0, 0,
                       (("apparatus_id", apparatus.apparatus_id), ("creator_id", apparatus.creator_id))),
            TraceEvent("C_apparatus_transfer_event_exogenous", 0, 0,
                       (("apparatus_id", apparatus.apparatus_id), ("creator_id", apparatus.creator_id))),
        ))
        provenance = "C_PRODUCED_AND_TRANSFERRED"
    elif apparatus.kind == "substitute":
        events.extend((
            TraceEvent("test_fixture_provide_event_exogenous", 0, 0,
                       (("apparatus_id", apparatus.apparatus_id), ("creator_id", apparatus.creator_id))),
            TraceEvent("test_fixture_transfer_event_exogenous", 0, 0,
                       (("apparatus_id", apparatus.apparatus_id), ("creator_id", apparatus.creator_id))),
        ))
        provenance = "TEST_FIXTURE"
    elif apparatus.kind == "absent":
        events.append(TraceEvent("apparatus_absence_declared_event", 0, 0,
                                 (("apparatus_present", False),)))
        provenance = "ABSENT"
    else:
        events.append(TraceEvent("apparatus_provenance_event_exogenous", 0, 0,
                                 (("apparatus_id", apparatus.apparatus_id), ("creator_id", apparatus.creator_id))))
        provenance = "OTHER_ORIGIN"
    events.append(TraceEvent("D_receive_event_exogenous", 0, 0,
                             (("holder", "D"), ("production_and_transfer_simulated", False),
                              ("apparatus_present", apparatus.kind != "absent"),
                              ("apparatus_provenance", provenance), ("source_off", True))))
    events.append(TraceEvent("source_off_event", 0, 0,
                             (("source", "C"), ("new_writes_permitted", False),
                              ("new_transfers_permitted", False))))
    return tuple(events)


def run_b_lite(arm: str = "R_int", dose_energy: int = 3, *,
               causal_prod_read: bool = False,
               load: int = 1, disturbance: str = "omega_0", compute_readiness: bool = True,
               task_memory: Optional[MemoryRecord] = None,
               prod_memory: Optional[RepairRecord] = None) -> BLiteRun:
    if arm not in ("R0", "R_ext", "R_int"):
        raise ValueError("arm must be R0, R_ext or R_int")
    if dose_energy not in (1, 2, 3, 4):
        raise ValueError("dose_energy must be in {1,2,3,4}")
    if causal_prod_read and arm != "R_int":
        raise ValueError("causal M_prod repair is defined only for the R_int arm")
    if load not in (1, 2):
        raise ValueError("load must be 1 or 2")
    if disturbance not in ("omega_0",) + REQUIRED_STRESS:
        raise ValueError(f"unknown disturbance {disturbance}")
    state = _initial_b_state(dose_energy, task_memory, prod_memory)
    events: list[TraceEvent] = list(trusted_prehistory_events(
        state.task_memory, state.prod_memory, state.apparatus
    ))
    ledger: list[dict[str, object]] = []
    state = replace(state, stage=int(Stage.READ_TASK1), time=1, source_off=True)
    if not state.task_memory.valid:
        events.append(TraceEvent("integrity_error_event", 1, 1, (("source", "M_task"), ("task", "Task1"))))
        bad = replace(state, stage=int(Stage.TERMINAL), time=3,
                        task1_status=Status.INTEGRITY_ERROR.value)
        failed = Task2Result(disturbance, load, False, Status.INTEGRITY_ERROR.value, 3, 2, 2,
                             bad.resources.as_tuple(), (("G_memory", False),), tuple(events), tuple(ledger))
        return BLiteRun(arm, dose_energy, None, causal_prod_read, load, bad, failed, None,
                        tuple(events), tuple(ledger), 0)
    read_bit = state.task_memory.semantic_bit
    events.append(TraceEvent("read_event", 1, 1,
                             (("source", "M_task"), ("task", "Task1"),
                              ("record_id", state.task_memory.record_id),
                              ("version", state.task_memory.version),
                              ("creator_id", state.task_memory.creator_id),
                              ("returned_value", read_bit))))
    state = replace(state, task1_read=read_bit, task1_operand=read_bit,
                      stage=int(Stage.EXECUTE_TASK1), time=2)
    if not state.apparatus.operational or state.apparatus.health < 1:
        t1_status = Status.APPARATUS_DEGRADED.value
    else:
        op1 = apply_operation(state.resources, name="Task1", cost=TASK_COST, byproduct=TASK_BYPRODUCT)
        ledger.append(op1.as_dict())
        if op1.exhausted:
            t1_status = Status.RESOURCE_EXHAUSTED.value
            state = replace(state, resources=op1.resources)
        else:
            t1_status = Status.SUCCESS.value
            state = replace(state, resources=op1.resources,
                              apparatus=state.apparatus.with_health(state.apparatus.health - 1))
            state = replace(state, task1_action=read_bit)
            events.append(TraceEvent("action_event", 2, 2,
                                     (("task", "Task1"), ("operand", read_bit),
                                      ("result", read_bit), ("status", t1_status),
                                      ("read_source", "M_task"),
                                      ("source_record_id", state.task_memory.record_id),
                                      ("source_record_version", state.task_memory.version),
                                      ("source_record_creator_id", state.task_memory.creator_id))))
    state = replace(state, task1_status=t1_status,
                      stage=int(Stage.RESTORE), time=3)
    if t1_status != Status.SUCCESS.value:
        terminal = replace(state, stage=int(Stage.TERMINAL))
        failed = Task2Result(disturbance, load, False, t1_status, 3,
                             state.apparatus.health, state.apparatus.health,
                             state.resources.as_tuple(), (("G_task1", False),), tuple(events), tuple(ledger))
        return BLiteRun(arm, dose_energy, None, causal_prod_read, load, terminal, failed, None,
                        tuple(events), tuple(ledger), 0)

    health_before_repair = state.apparatus.health
    chosen = None
    if arm == "R0":
        events.append(TraceEvent("restore_disabled_event", 3, 3, ()))
    else:
        if arm == "R_ext":
            inject = apply_operation(state.resources, name="external_injection", inflow=EXTERNAL_INJECTION)
            ledger.append(inject.as_dict())
            state = replace(state, resources=inject.resources, external_donor_used=True)
            events.append(TraceEvent("external_injection_event", 3, 3,
                                     (("inflow", EXTERNAL_INJECTION), ("spill", inject.spill_inflow))))
            chosen = "r0"
        elif causal_prod_read:
            if not state.prod_memory.valid:
                events.append(TraceEvent("integrity_error_event", 3, 3, (("source", "M_prod"), ("task", "repair"))))
                # Task 2 was not reached; preserve task2_status=None.
                terminal = replace(state, stage=int(Stage.TERMINAL))
                failed = Task2Result(disturbance, load, False, Status.INTEGRITY_ERROR.value, 3,
                                     state.apparatus.health, state.apparatus.health,
                                     state.resources.as_tuple(), (("G_prod_memory", False),), tuple(events), tuple(ledger))
                return BLiteRun(arm, dose_energy, None, causal_prod_read, load, terminal, failed, None,
                                tuple(events), tuple(ledger), 0)
            chosen = state.prod_memory.instruction
            events.append(TraceEvent("read_event", 3, 3,
                                     (("source", "M_prod"), ("task", "repair"),
                                      ("record_id", state.prod_memory.record_id),
                                      ("version", state.prod_memory.version),
                                      ("creator_id", state.prod_memory.creator_id),
                                      ("returned_value", chosen))))
        else:
            chosen = "r0"  # R1 is fixed by specification; caller cannot select r1 outside R2.
        repair = apply_operation(state.resources, name=f"Repair_{chosen}",
                                 cost=REPAIR_COST, byproduct=REPAIR_BYPRODUCT)
        ledger.append(repair.as_dict())
        if repair.exhausted:
            # Repair failed before the Task-2 phase; do not write a Task-2 status.
            state = replace(state, resources=repair.resources)
            terminal = replace(state, stage=int(Stage.TERMINAL))
            failed = Task2Result(disturbance, load, False, Status.RESOURCE_EXHAUSTED.value, 3,
                                 state.apparatus.health, state.apparatus.health,
                                 state.resources.as_tuple(), (("G_repair_resource", False),), tuple(events), tuple(ledger))
            return BLiteRun(arm, dose_energy, chosen, causal_prod_read, load, terminal, failed, None,
                            tuple(events), tuple(ledger), 0)
        target_health = 1 if chosen == "r0" else 2
        state = replace(state, resources=repair.resources,
                          apparatus=state.apparatus.with_health(target_health),
                          repair_instruction=chosen, internal_restore_used=arm == "R_int")
        events.append(TraceEvent("repair_action_event", 3, 3,
                                 (("task", "repair"), ("instruction", chosen),
                                  ("health_before", health_before_repair),
                                  ("health_after", target_health), ("resource_cost", REPAIR_COST),
                                  ("read_source", "M_prod" if causal_prod_read else None),
                                  ("source_record_id", state.prod_memory.record_id if causal_prod_read else None),
                                  ("source_record_version", state.prod_memory.version if causal_prod_read else None),
                                  ("source_record_creator_id", state.prod_memory.creator_id if causal_prod_read else None))))
    repair_gain = state.apparatus.health - health_before_repair
    state = replace(state, stage=int(Stage.READINESS), time=4)
    readiness = estimate_readiness(state, load=load) if compute_readiness else None
    if readiness is not None and (not readiness.purity_pass or not readiness.order_independent):
        raise RuntimeError("readiness estimator purity or order-independence failure")
    executed = simulate_task2(state, disturbance, load)
    events.extend(executed.events)
    return BLiteRun(arm, dose_energy, chosen, causal_prod_read, load, state, executed,
                    readiness, tuple(events), tuple(ledger) + executed.ledger, repair_gain)


def run_dose_sweep() -> dict[str, object]:
    """Exact dose sweep; pre-readiness termination is recorded as unready.

    A trajectory that cannot complete repair has no stage-4 snapshot and thus
    no V_ready estimator call. It is reported as structurally unready, with
    Task 2 explicitly marked NOT_REACHED rather than TASK2_FAILED.
    """
    rows = []
    for energy in (1, 2, 3, 4):
        run = run_b_lite("R_int", energy, load=1)
        task2_attempted = run.task2_reached
        if run.readiness is None:
            predicted_nominal = False
            predicted_robust = False
            readiness_status = "READINESS_NOT_REACHED_PRE_REPAIR_TERMINAL"
            robust_by_scenario: dict[str, object] = {}
            prediction_matches_execution = None
        else:
            predicted_nominal = run.readiness.v_nom
            predicted_robust = run.readiness.v_rob
            readiness_status = "EVALUATED_FROM_STAGE4_SNAPSHOT"
            robust_by_scenario = {
                r.disturbance: {"predicted_success": r.success, "status": r.status}
                for r in run.readiness.stress
            }
            prediction_matches_execution = (predicted_nominal == run.executed.success) if task2_attempted else None
        rows.append({"E_initial": energy,
                     "V_nom": predicted_nominal,
                     "V_rob": predicted_robust,
                     "Y_task2_attempted": task2_attempted,
                     "Y_task2_executed": run.executed.success if task2_attempted else None,
                     "Y_task2_status": run.executed.status if task2_attempted else "NOT_REACHED",
                     "pre_task2_terminal_cause": run.pre_task2_terminal_cause,
                     "nominal": predicted_nominal,
                     "readiness_status": readiness_status,
                     "prediction_matches_execution": prediction_matches_execution,
                     "robust": predicted_robust,
                     "robust_by_scenario": robust_by_scenario,
                     "R_final_nominal": run.executed.resources_final,
                     "health_after_repair": run.state_after_repair.apparatus.health,
                     "repair_health_gain": run.repair_health_gain})
    nominal_threshold = next((r["E_initial"] for r in rows if r["V_nom"]), None)
    robust_threshold = next((r["E_initial"] for r in rows if r["V_rob"]), None)
    mono_nom = all((not rows[i]["V_nom"]) or rows[i + 1]["V_nom"] for i in range(len(rows) - 1))
    mono_rob = all((not rows[i]["V_rob"]) or rows[i + 1]["V_rob"] for i in range(len(rows) - 1))
    evaluated_rows = [r for r in rows if r["prediction_matches_execution"] is not None]
    prediction_consistency = bool(evaluated_rows) and all(r["prediction_matches_execution"] for r in evaluated_rows)
    pre_readiness_rows = [r for r in rows if r["readiness_status"] == "READINESS_NOT_REACHED_PRE_REPAIR_TERMINAL"]
    pre_readiness_failures = bool(pre_readiness_rows) and all(
        r["pre_task2_terminal_cause"] == Status.RESOURCE_EXHAUSTED.value
        and not r["Y_task2_attempted"] and not r["V_nom"] and not r["V_rob"]
        for r in pre_readiness_rows
    )
    return {"capacity": (4, 3, 3, 3), "dose_grid": (1, 2, 3, 4),
            "rows": rows, "E_star_nominal": nominal_threshold,
            "E_star_robust": robust_threshold,
            "nominality_monotone": mono_nom, "robustness_monotone": mono_rob,
            "readiness_execution_consistent_on_evaluable_cells": prediction_consistency,
            "pre_readiness_failures_classified": pre_readiness_failures,
            "pre_readiness_failure_count": len(pre_readiness_rows),
            "status": "PASS" if mono_nom and mono_rob and prediction_consistency and pre_readiness_failures
            and nominal_threshold is not None and robust_threshold is not None
            else "MONOTONICITY_NOT_SUPPORTED_OR_NO_THRESHOLD_OR_PREDICTION_MISMATCH"}


def functional_repair_contrast() -> dict[str, object]:
    results: dict[str, dict[str, object]] = {}
    for load in (1, 2):
        r0 = run_b_lite("R_int", 3, causal_prod_read=True,
                        prod_memory=RepairRecord.make("r0"), load=load)
        r1 = run_b_lite("R_int", 3, causal_prod_read=True,
                        prod_memory=RepairRecord.make("r1"), load=load)
        func0 = (r0.executed.success, r0.executed.status, r0.executed.y_action)
        func1 = (r1.executed.success, r1.executed.status, r1.executed.y_action)
        # This is a declared evaluator-visible post-task state profile, not the
        # entire hidden Markov state (which also contains records/provenance).
        state0 = (func0, r0.executed.health_after, r0.executed.finish_time, r0.executed.resources_final)
        state1 = (func1, r1.executed.health_after, r1.executed.finish_time, r1.executed.resources_final)
        from .metrics import point_mass, total_variation
        tv_func = total_variation(point_mass(func0), point_mass(func1))
        tv_state = total_variation(point_mass(state0), point_mass(state1))
        def trace_valid(run, expected):
            record = run.state_after_repair.prod_memory
            return (record.instruction == expected
                    and validate_causal_record_chain(run.events, "M_prod", "repair", record))
        results[f"load_{load}"] = {
            "r0": r0.as_dict(), "r1": r1.as_dict(),
            "TV_func": str(tv_func), "TV_state_profile": str(tv_state),
            "state_profile_fields": ["Y_task2_exec", "Y_status2", "Y_action", "health_after", "finish_time", "resources_final"],
            "causal_read_r0": trace_valid(r0, "r0"),
            "causal_read_r1": trace_valid(r1, "r1"),
            "TV_func_fields": ["Y_task2_exec", "Y_status2", "Y_action"],
        }
    return {"results": results,
            "R2_PASS": results["load_2"]["TV_func"] == "1" and
                       results["load_2"]["causal_read_r0"] and results["load_2"]["causal_read_r1"],
            "R2_NULL_CONTROL_PASS": results["load_1"]["TV_func"] == "0",
            "TV_state_profile_load1_is_not_R2_criterion": results["load_1"]["TV_state_profile"] == "1"}
