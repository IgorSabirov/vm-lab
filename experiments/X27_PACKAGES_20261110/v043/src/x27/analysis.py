"""Exact estimators, factorial contrasts, reachability and H-Q partitioning."""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Callable, Hashable, Iterable, Mapping, Optional, Sequence, TypeVar

from .engine import (
    Task1Probe, run_task1_probe, make_initial_state, advance_stage, estimate_readiness, state_digest
)
from .model import (
    Arm,
    Apparatus,
    Disturbance,
    MemoryRecord,
    ModelConfig,
    RepairRecord,
    ResourceVector,
    Stage,
    State,
    SubstituteCalibration,
    TraceEvent,
)


Profile = Hashable
T = TypeVar("T", bound=Hashable)


def deterministic_law(profile: Profile) -> dict[Profile, Fraction]:
    return {profile: Fraction(1, 1)}


def _exact_probability(value: object, *, label: str) -> Fraction:
    """Convert an integer/rational mass without silently importing float error."""
    if isinstance(value, bool) or not isinstance(value, (int, Fraction)):
        raise TypeError(f"{label} must be int or Fraction; floats and other types are rejected")
    probability = Fraction(value)
    if probability < 0:
        raise ValueError(f"{label} must be non-negative")
    return probability


def _validated_exact_distribution(
    law: Mapping[Profile, object], *, label: str = "distribution"
) -> dict[Profile, Fraction]:
    if not law:
        raise ValueError(f"{label} must not be empty")
    exact = {key: _exact_probability(value, label=f"{label}[{key!r}]") for key, value in law.items()}
    total = sum(exact.values(), Fraction(0, 1))
    if total != 1:
        raise ValueError(f"{label} must be normalized exactly to one (sum={total})")
    return exact


def total_variation(p: Mapping[Profile, object], q: Mapping[Profile, object]) -> Fraction:
    """Exact TV distance; only non-negative int/Fraction probability masses are accepted."""
    p_exact = _validated_exact_distribution(p, label="P")
    q_exact = _validated_exact_distribution(q, label="Q")
    support = set(p_exact) | set(q_exact)
    distance = sum(
        (abs(p_exact.get(y, Fraction(0, 1)) - q_exact.get(y, Fraction(0, 1))) for y in support),
        Fraction(0, 1),
    ) / 2
    if not Fraction(0, 1) <= distance <= Fraction(1, 1):
        raise ArithmeticError(f"TV invariant violated: {distance}")
    return distance


def mixed_difference_norm(
    p11: Mapping[Profile, object],
    p10: Mapping[Profile, object],
    p01: Mapping[Profile, object],
    p00: Mapping[Profile, object],
) -> Fraction:
    """Half L1 norm of four separately validated exact laws."""
    laws = (
        _validated_exact_distribution(p11, label="P11"),
        _validated_exact_distribution(p10, label="P10"),
        _validated_exact_distribution(p01, label="P01"),
        _validated_exact_distribution(p00, label="P00"),
    )
    support = set().union(*(set(law) for law in laws))
    return sum(
        (abs(laws[0].get(y, 0) - laws[1].get(y, 0) - laws[2].get(y, 0) + laws[3].get(y, 0)) for y in support),
        Fraction(0, 1),
    ) / 2


def _profile(probe: Task1Probe) -> tuple[object, ...]:
    p = probe.profile
    return (p.y_function, p.y_status, p.finish_time, p.resources_post.as_tuple())


def _law(probe: Task1Probe) -> dict[Profile, Fraction]:
    return deterministic_law(_profile(probe))


def _has_ordered_read_and_action(events: Sequence[TraceEvent], source: str) -> bool:
    read_indices = [i for i, event in enumerate(events) if event.event_type == "read_event" and dict(event.details).get("source") == source]
    action_indices = [i for i, event in enumerate(events) if event.event_type == "action_event"]
    return bool(read_indices and action_indices and min(read_indices) < min(action_indices))


def run_x27a_matrix(*, config: ModelConfig = ModelConfig()) -> dict[str, object]:
    """Run the required 2x2 memory/payload matrix with a physically accessible payload."""
    m0, m1 = MemoryRecord.make(0, record_id="M0"), MemoryRecord.make(1, record_id="M1")
    p0, p1 = MemoryRecord.make(0, record_id="P0"), MemoryRecord.make(1, record_id="P1")
    memories = (m0, m1)
    payloads = (p0, p1)
    cells: dict[str, Task1Probe] = {}
    for i, memory in enumerate(memories):
        for j, payload in enumerate(payloads):
            cells[f"{i}{j}"] = run_task1_probe(
                task_memory=memory,
                residual_payload=payload,
                apparatus=Apparatus.a1(),
                payload_accessible=True,
                read_source="M_task",
                config=config,
            )

    laws = {key: _law(value) for key, value in cells.items()}
    delta_m = {
        "P0": total_variation(laws["00"], laws["10"]),
        "P1": total_variation(laws["01"], laws["11"]),
    }
    delta_p = {
        "M0": total_variation(laws["00"], laws["01"]),
        "M1": total_variation(laws["10"], laws["11"]),
    }

    functional = {}
    causal = {}
    for i, memory in enumerate(memories):
        for j, _payload in enumerate(payloads):
            key = f"{i}{j}"
            probe = cells[key]
            functional[key] = probe.profile.y_function == memory.semantic_bit
            causal[key] = _has_ordered_read_and_action(probe.events, "M_task")
    h_m_pass = all(functional.values()) and all(causal.values()) and all(v == 1 for v in delta_m.values())

    payload_reads = {
        key: any(
            event.event_type == "read_event" and dict(event.details).get("source") == "P_res"
            for event in probe.events
        )
        for key, probe in cells.items()
    }
    h_p_pass = all(v == 0 for v in delta_p.values()) and not any(payload_reads.values())

    serialised_cells = {
        key: {
            "profile": {
                "Y_function": probe.profile.y_function,
                "Y_status": probe.profile.y_status,
                "T_finish": probe.profile.finish_time,
                "R_post1": probe.profile.resources_post.as_dict(),
            },
            "read_source": probe.read_source,
            "read_before_action": _has_ordered_read_and_action(probe.events, "M_task"),
            "payload_read": payload_reads[key],
            "events": [event.as_dict() for event in probe.events],
        }
        for key, probe in cells.items()
    }
    return {
        "module": "X27-A",
        "a_payload": 1,
        "cells": serialised_cells,
        "delta_M": {key: float(value) for key, value in delta_m.items()},
        "delta_P": {key: float(value) for key, value in delta_p.items()},
        "functional_following": functional,
        "causal_main_memory_trace": causal,
        "H_M": "PASS" if h_m_pass else "FAIL",
        "H_P": "PASS" if h_p_pass else "FAIL",
    }


def run_payload_bypass_positive_control(*, config: ModelConfig = ModelConfig()) -> dict[str, object]:
    m0 = MemoryRecord.make(0, record_id="M0")
    p1 = MemoryRecord.make(1, record_id="P1")
    probe = run_task1_probe(
        task_memory=m0,
        residual_payload=p1,
        apparatus=Apparatus.a1(),
        payload_accessible=True,
        read_source="P_res",
        config=config,
    )
    bypass = any(
        event.event_type == "read_event" and dict(event.details).get("source") == "P_res"
        for event in probe.events
    )
    return {
        "control": "PC2_PAYLOAD_BYPASS",
        "payload_read_detected": bypass,
        "H_P": "FAIL" if bypass else "PASS",
        "Y_function": probe.profile.y_function,
        "events": [event.as_dict() for event in probe.events],
    }


def run_apparatus_factorial(
    *,
    calibration: SubstituteCalibration,
    config: ModelConfig = ModelConfig(),
) -> dict[str, object]:
    memory = MemoryRecord.make(0, record_id="M0")
    payload = MemoryRecord.make(0, record_id="P0")
    apparatuses = {"A0": Apparatus.a0(), "A1": Apparatus.a1(), "A2": Apparatus.a2()}
    probes = {
        name: run_task1_probe(
            task_memory=memory,
            residual_payload=payload,
            apparatus=apparatus,
            payload_accessible=True,
            read_source="M_task",
            config=config,
        )
        for name, apparatus in apparatuses.items()
    }
    q = {name: probe.profile.y_status == "SUCCESS" and probe.used_apparatus for name, probe in probes.items()}
    laws = {name: _law(probe) for name, probe in probes.items()}
    tv_distances = {
        "A1_vs_A0": float(total_variation(laws["A1"], laws["A0"])),
        "A2_vs_A0": float(total_variation(laws["A2"], laws["A0"])),
        "A1_vs_A2": float(total_variation(laws["A1"], laws["A2"])),
    }
    trace_use = {
        name: any(event.event_type == "apparatus_use_event" for event in probe.events)
        for name, probe in probes.items()
    }
    class_pass = (
        q["A1"] and q["A2"] and not q["A0"] and calibration.valid
        and trace_use["A1"] and trace_use["A2"] and not trace_use["A0"]
        and tv_distances["A1_vs_A0"] > 0 and tv_distances["A2_vs_A0"] > 0
    )

    # Token dependence is tested in both directions. Original-A1 necessity is
    # reported separately from the symmetric token-specificity control.
    token_directions: dict[str, object] = {
        "original_required": "NOT_RUN",
        "substitute_required": "NOT_RUN",
    }
    symmetric_token_specificity = "NOT_CLAIMED"
    original_a1_necessity = "NOT_CLAIMED"
    token_verdict = "NOT_CLAIMED"
    token_tv = None
    if config.required_token_signature is not None:
        if not calibration.valid:
            token_verdict = "NOT_EVALUABLE_UNCALIBRATED_SUBSTITUTE"
            token_tv = None
            symmetric_token_specificity = "NOT_EVALUABLE_UNCALIBRATED_SUBSTITUTE"
            token_directions = {
                "original_required": "NOT_EVALUABLE_UNCALIBRATED_SUBSTITUTE",
                "substitute_required": "NOT_EVALUABLE_UNCALIBRATED_SUBSTITUTE",
            }
        else:
            directional_results: dict[str, dict[str, object]] = {}
            for direction, required, accepted_name in (
                ("original_required", "token-original", "A1"),
                ("substitute_required", "token-substitute", "A2"),
            ):
                directional_config = replace(config, required_token_signature=required)
                directional_probes = {
                    name: run_task1_probe(
                        task_memory=memory,
                        residual_payload=payload,
                        apparatus=apparatuses[name],
                        config=directional_config,
                    )
                    for name in ("A1", "A2")
                }
                accepted = directional_probes[accepted_name].used_apparatus
                rejected = directional_probes["A2" if accepted_name == "A1" else "A1"].used_apparatus
                passed = accepted and not rejected
                directional_results[direction] = {
                    "required_signature": required,
                    "accepted_apparatus": accepted_name,
                    "A1_used": directional_probes["A1"].used_apparatus,
                    "A2_used": directional_probes["A2"].used_apparatus,
                    "status": "PASS" if passed else "NO_TOKEN_SPECIFICITY_DETECTED",
                }
            token_directions = directional_results
            symmetric_token_specificity = (
                "PASS"
                if all(row["status"] == "PASS" for row in directional_results.values())
                else "FAIL"
            )
            active_required = config.required_token_signature
            active_original = directional_results["original_required"]
            active_substitute = directional_results["substitute_required"]
            active_row = (
                active_original if active_required == "token-original"
                else active_substitute if active_required == "token-substitute"
                else None
            )
            token_verdict = active_row["status"] if active_row is not None else "NO_TOKEN_SPECIFICITY_DETECTED"
            token_tv = float(total_variation(_law(probes["A1"]), _law(probes["A2"])))
            original_a1_necessity = (
                "PASS" if active_original["A1_used"] and not active_original["A2_used"] else "FAIL"
            )

    return {
        "q_A": q,
        "A2_calibration_valid": calibration.valid,
        "H_A_class": "PASS" if class_pass else "FAIL_OR_NOT_EVALUABLE",
        "H_A_token": token_verdict,
        "H_A_token_TV": token_tv,
        "H_A_token_directions": token_directions,
        "H_A_token_symmetric_specificity": symmetric_token_specificity,
        "H_A1_necessity_under_original_token": original_a1_necessity,
        "TV_distances": tv_distances,
        "profiles": {name: probe.profile.as_dict() for name, probe in probes.items()},
        "apparatus_use": {name: probe.used_apparatus for name, probe in probes.items()},
        "apparatus_use_trace": trace_use,
        "traces": {name: [event.as_dict() for event in probe.events] for name, probe in probes.items()},
    }


def run_memory_apparatus_interaction(*, config: ModelConfig = ModelConfig()) -> dict[str, object]:
    m0, m1 = MemoryRecord.make(0, record_id="M0"), MemoryRecord.make(1, record_id="M1")
    p = MemoryRecord.make(0, record_id="P0")
    probes: dict[tuple[int, str], Task1Probe] = {}
    for bit, memory in ((0, m0), (1, m1)):
        for a_name, apparatus in (("A0", Apparatus.a0()), ("A1", Apparatus.a1())):
            probes[(bit, a_name)] = run_task1_probe(
                task_memory=memory,
                residual_payload=p,
                apparatus=apparatus,
                config=config,
            )
    magnitude = mixed_difference_norm(
        _law(probes[(1, "A1")]),
        _law(probes[(1, "A0")]),
        _law(probes[(0, "A1")]),
        _law(probes[(0, "A0")]),
    )
    return {"mixed_difference_TV_norm": float(magnitude), "H_MA": "PASS" if magnitude > 0 else "NO_INTERACTION_DETECTED"}


@dataclass(frozen=True, slots=True)
class HQNode:
    state: State
    interventions_left: int
    arm_context: Arm = Arm.R_INT
    disturbance_context: Disturbance = Disturbance.NONE
    readiness_signature: Optional[tuple[bool, bool]] = None


def _apparatus_options() -> dict[str, Apparatus]:
    return {"A0": Apparatus.a0(), "A1": Apparatus.a1(), "A2": Apparatus.a2()}


def hq_actions(node: HQNode, *, module: str) -> tuple[str, ...]:
    state = node.state
    if state.terminal:
        return ("continue",)
    actions = ["continue"]
    if node.interventions_left <= 0:
        return tuple(actions)
    equipment_stages = (int(Stage.INITIALIZE),) if module == "A" else (int(Stage.INITIALIZE), int(Stage.RESTORE))
    memory_stages = (int(Stage.READ_TASK1),) if module == "A" else (int(Stage.READ_TASK1), int(Stage.DISTURBANCE_AND_READ_TASK2))
    if state.stage in equipment_stages:
        actions.extend(("do(A=A0)", "do(A=A1)", "do(A=A2)"))
    if state.stage in memory_stages:
        actions.extend(("do(M_task=m)", "do(M_task=Tm)", "do(P_res=m)", "do(P_res=Tm)"))
    if module == "B-LITE" and state.stage == int(Stage.RESTORE):
        actions.extend(("do(M_prod=r0)", "do(M_prod=r1)"))
    return tuple(actions)


def apply_hq_action(
    node: HQNode,
    action: str,
    *,
    module: str,
    config: ModelConfig = ModelConfig(),
) -> HQNode:
    state = node.state
    if action == "continue":
        arm = node.arm_context if module == "B-LITE" else Arm.R0
        readiness_signature = node.readiness_signature
        if module == "B-LITE" and state.stage == int(Stage.READINESS):
            # This legacy H-Q graph evaluates a causal M_prod-read context (R2-like).
            readiness = estimate_readiness(state, arm=arm, config=config, causal_prod_read=True)
            readiness_signature = (readiness.v_nom, readiness.v_rob)
        next_state = advance_stage(
            state, arm=arm, disturbance=node.disturbance_context, config=config,
            causal_prod_read=(module == "B-LITE"), module=module
        ).state
        return HQNode(
            next_state, node.interventions_left, node.arm_context, node.disturbance_context, readiness_signature
        )
    if node.interventions_left <= 0:
        raise ValueError("intervention budget exhausted")

    updates: dict[str, object] = {}
    if action == "do(A=A0)":
        updates["apparatus"] = Apparatus.a0()
    elif action == "do(A=A1)":
        updates["apparatus"] = Apparatus.a1()
    elif action == "do(A=A2)":
        updates["apparatus"] = Apparatus.a2()
    elif action == "do(M_task=m)":
        updates["task_memory"] = MemoryRecord.make(0, record_id="M_task:intervened_m")
    elif action == "do(M_task=Tm)":
        updates["task_memory"] = MemoryRecord.make(1, record_id="M_task:intervened_Tm")
    elif action == "do(P_res=m)":
        updates["residual_payload"] = MemoryRecord.make(0, record_id="P_res:intervened_m")
        updates["payload_accessible"] = True
    elif action == "do(P_res=Tm)":
        updates["residual_payload"] = MemoryRecord.make(1, record_id="P_res:intervened_Tm")
        updates["payload_accessible"] = True
    elif action == "do(M_prod=r0)" and module == "B-LITE":
        updates["prod_memory"] = RepairRecord.make("r0", record_id="M_prod:intervened_r0")
    elif action == "do(M_prod=r1)" and module == "B-LITE":
        updates["prod_memory"] = RepairRecord.make("r1", record_id="M_prod:intervened_r1")
    else:
        raise ValueError(f"invalid H-Q action for {module} at stage {state.stage}: {action}")
    return HQNode(
        replace(state, **updates),
        node.interventions_left - 1,
        node.arm_context,
        node.disturbance_context,
        node.readiness_signature,
    )


def hq_observation(node: HQNode) -> tuple[object, ...]:
    state = node.state
    if state.terminal:
        return (
            "terminal",
            node.readiness_signature,
            state.task1_status,
            state.task1_function,
            state.task2_status,
            state.task2_function,
            state.time,
            state.resources.as_tuple(),
        )
    # Decision stage is observable; latent memory/provenance/resource state is
    # not promoted to an observation merely to force a nontrivial partition.
    return ("stage", state.stage, node.readiness_signature)


def build_hq_graph(
    *,
    module: str = "B-LITE",
    config: ModelConfig = ModelConfig(),
    max_interventions: int = 2,
    max_nodes: int = 350_000,
    contexts: Optional[Sequence[tuple[Arm, Disturbance]]] = None,
) -> tuple[set[HQNode], dict[tuple[HQNode, str], HQNode]]:
    """Enumerate exact controlled reachability for the finite intervention family."""
    if module not in ("A", "B-LITE"):
        raise ValueError("module must be A or B-LITE")
    m0, m1 = MemoryRecord.make(0), MemoryRecord.make(1)
    p0, p1 = MemoryRecord.make(0, record_id="P0"), MemoryRecord.make(1, record_id="P1")
    r0, r1 = RepairRecord.make("r0"), RepairRecord.make("r1")
    apps = _apparatus_options()
    if contexts is None:
        contexts = ((Arm.R_INT, Disturbance.NONE),) if module == "B-LITE" else ((Arm.R0, Disturbance.NONE),)
    initial_nodes = {
        HQNode(
            make_initial_state(
                task_memory=m,
                prod_memory=r,
                residual_payload=p,
                apparatus=a,
                resources=config.initial_resources,
            ),
            max_interventions,
            arm_context=arm_context,
            disturbance_context=disturbance_context,
        )
        for m in (m0, m1)
        for p in (p0, p1)
        for r in ((r0, r1) if module == "B-LITE" else (r0,))
        for a in (apps["A1"],)
        for arm_context, disturbance_context in contexts
    }
    seen: set[HQNode] = set(initial_nodes)
    transitions: dict[tuple[HQNode, str], HQNode] = {}
    queue = deque(initial_nodes)
    while queue:
        node = queue.popleft()
        for action in hq_actions(node, module=module):
            target = apply_hq_action(node, action, module=module, config=config)
            transitions[(node, action)] = target
            if target not in seen:
                seen.add(target)
                if len(seen) > max_nodes:
                    raise RuntimeError(f"reachable closure exceeded configured limit {max_nodes}")
                queue.append(target)
    return seen, transitions


def partition_refinement(
    states: set[T],
    actions: Callable[[T], Sequence[str]],
    transition: Callable[[T, str], T | Hashable | Mapping[T | Hashable, Fraction]],
    observation: Callable[[T], Hashable],
    *,
    terminal_output_key: Optional[Callable[[Hashable], Hashable]] = None,
) -> tuple[tuple[T, ...], ...]:
    """Coarsest exact controlled-bisimulation partition of nonterminal states.

    A transition may end at an external terminal-output token. Such tokens are
    compared by ``terminal_output_key`` and are never admitted to the partition
    domain. This implements the distinction between decision states and
    terminal outcomes explicitly.
    """
    by_observation: dict[Hashable, list[T]] = defaultdict(list)
    for state in states:
        by_observation[observation(state)].append(state)
    blocks: list[tuple[T, ...]] = [tuple(group) for group in by_observation.values()]

    def target_signature(target: Hashable, block_id: Mapping[T, int]) -> Hashable:
        if target in block_id:
            return ("block", block_id[target])
        if terminal_output_key is not None:
            return ("terminal_output", terminal_output_key(target))
        raise ValueError("transition target lies outside supplied state set")

    while True:
        block_id = {state: index for index, block in enumerate(blocks) for state in block}
        refined: dict[Hashable, list[T]] = defaultdict(list)
        for state in states:
            action_signature = []
            available = tuple(actions(state))
            for action in available:
                target_or_law = transition(state, action)
                if isinstance(target_or_law, Mapping):
                    law = _validated_exact_distribution(target_or_law, label="transition law")
                    target_mass: dict[Hashable, Fraction] = defaultdict(Fraction)
                    for target, probability in law.items():
                        target_mass[target_signature(target, block_id)] += probability
                    action_signature.append((action, tuple(sorted(target_mass.items(), key=repr))))
                else:
                    target = target_or_law
                    action_signature.append((action, ((target_signature(target, block_id), Fraction(1, 1)),)))
            signature = (observation(state), available, tuple(action_signature))
            refined[signature].append(state)
        new_blocks = [tuple(group) for group in refined.values()]
        old_equivalence = {frozenset(block) for block in blocks}
        new_equivalence = {frozenset(block) for block in new_blocks}
        blocks = new_blocks
        if old_equivalence == new_equivalence:
            return tuple(blocks)


def hq_partition(*, module: str = "B-LITE", config: ModelConfig = ModelConfig(), max_nodes: int = 350_000) -> dict[str, object]:
    """Compute future equivalence on decision states; terminals are output leaves.

    Nondecision, nonterminal stages remain in the refinement graph as exact
    operational intermediates. The reported equivalence classes are projected
    onto the preregistered decision region sigma in {1,2,5,6} only.
    """
    states, transitions = build_hq_graph(module=module, config=config, max_nodes=max_nodes)
    terminal_nodes = {node for node in states if node.state.terminal}
    operational_states = states - terminal_nodes
    decision_stages = {1, 2, 5, 6}

    def terminal_leaf(node: HQNode) -> tuple[str, Hashable]:
        if not node.state.terminal:
            raise ValueError("terminal leaf requested for a nonterminal node")
        return ("terminal_output", hq_observation(node))

    def nonterminal_transition(node: HQNode, action: str) -> HQNode | Hashable:
        target = transitions[(node, action)]
        return terminal_leaf(target) if target.state.terminal else target

    blocks = partition_refinement(
        operational_states,
        lambda node: hq_actions(node, module=module),
        nonterminal_transition,
        hq_observation,
        terminal_output_key=lambda token: token,
    )

    def node_id(node: HQNode) -> str:
        payload = {
            "state_sha256": state_digest(node.state),
            "interventions_left": node.interventions_left,
            "arm_context": node.arm_context.value,
            "disturbance_context": node.disturbance_context.value,
            "readiness_signature": node.readiness_signature,
        }
        import hashlib, json
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    decision_nodes = sum(1 for node in operational_states if node.state.stage in decision_stages)
    decision_rows = []
    helper_class_count = 0
    for block in blocks:
        members = [node for node in block if node.state.stage in decision_stages]
        if not members:
            helper_class_count += 1
            continue
        member_ids = sorted(node_id(node) for node in members)
        decision_rows.append({"members": member_ids, "size": len(member_ids)})
    decision_rows.sort(key=lambda row: row["members"][0] if row["members"] else "")
    for index, row in enumerate(decision_rows):
        row["class_id"] = f"HQD{index:04d}"

    terminal_outputs = sorted({repr(hq_observation(node)) for node in terminal_nodes})
    return {
        "module": module,
        "partition_scope": "decision-state projection on stages {1,2,5,6}; helper stages retained internally; terminal states are output leaves",
        "result_status": "LEGACY_REPRODUCTION_ONLY_NOT_TRANSFERABLE" if module == "B-LITE" else "SCOPED_DECISION_OUTPUT_EQUIVALENCE",
        "publishable_as_frozen_HQ_result": False,
        "O_D": ["stage", "readiness_signature when B-LITE"],
        "O_eval": ["terminal_marker", "readiness_signature", "task1_status", "task1_function", "task2_status", "task2_function", "finish_time", "resources"],
        "J_trace": "diagnostic event journal; excluded from partition observation",
        "observable_nonterminal": ["stage", "readiness_signature when B-LITE"],
        "observable_terminal": ["terminal_marker", "readiness_signature", "task1_status", "task1_function", "task2_status", "task2_function", "finish_time", "resources"],
        "trace_journal_in_observable": False,
        "full_causal_trace_equivalence": False,
        "context_label": "LEGACY_R2_LIKE_CAUSAL_M_PROD_READ" if module == "B-LITE" else "A_MODULE_NO_M_PROD",
        "causal_prod_read_on_continue": module == "B-LITE",
        "M_prod_interventions_allowed": module == "B-LITE",
        "R1_context_included": False if module == "B-LITE" else None,
        "R2_like_context_included": True if module == "B-LITE" else None,
        "transferable_to_R1": False if module == "B-LITE" else None,
        "reachable_augmented_nodes": len(states),
        "reachable_physical_states": len({node.state for node in states}),
        "operational_nonterminal_nodes": len(operational_states),
        "decision_nodes": decision_nodes,
        "predictive_classes": len(decision_rows),
        "nondecision_helper_classes": helper_class_count,
        "terminal_nodes_recorded": len(terminal_nodes),
        "terminal_output_classes": len(terminal_outputs),
        "terminal_states_in_partition_domain": False,
        "decision_region_stages": sorted(decision_stages),
        "intervention_depth_limit": 2,
        "includes_readiness_outputs": module == "B-LITE",
        "partition_classes": decision_rows,
        "terminal_outputs": terminal_outputs,
        "status": "COMPUTED_EXACTLY",
    }


def g0_report(*, module: str, config: ModelConfig = ModelConfig(), limit: int = 350_000) -> dict[str, object]:
    contexts = (
        tuple((arm, disturbance) for arm in (Arm.R0, Arm.R_EXT, Arm.R_INT) for disturbance in (Disturbance.NONE, Disturbance.DELAY, Disturbance.LOSS_E, Disturbance.LOSS_M))
        if module == "B-LITE"
        else ((Arm.R0, Disturbance.NONE),)
    )
    states, transitions = build_hq_graph(module=module, config=config, max_nodes=limit, contexts=contexts)
    physical_states = {node.state for node in states}
    state_hashes = sorted({state_digest(state) for state in physical_states})
    import hashlib
    closure_digest = hashlib.sha256("\n".join(state_hashes).encode("utf-8")).hexdigest()
    return {
        "module": module,
        "reachable_augmented_nodes": len(states),
        "reachable_count": len(physical_states),
        "limit": limit,
        "status": "PASS" if len(physical_states) <= limit else "FAIL",
        "intervention_depth_limit": 2,
        "contexts_included": [f"{arm.value}/{disturbance.value}" for arm, disturbance in contexts],
        "intervention_transition_count": len(transitions),
        "reachable_state_hash_count": len(state_hashes),
        "reachable_state_hashes_embedded": False,
        "closure_digest_input": "sorted unique state SHA256 hex strings joined by LF, UTF-8 encoded",
        "closure_digest_sha256": closure_digest,
        "kernel": "deterministic_reference_kernel",
    }


def hq_synthetic_controls() -> dict[str, object]:
    """Small exact witnesses for PC8/PC9 and the partition-refinement routine."""
    @dataclass(frozen=True)
    class Tiny:
        stage: int
        hidden: int
        output: int = -1

    states = {Tiny(0, h) for h in (0, 1)} | {Tiny(1, h, h) for h in (0, 1)}
    def acts(s: Tiny) -> tuple[str, ...]:
        return ("continue",) if s.stage == 0 else ("continue",)
    def trans(s: Tiny, _action: str) -> Tiny:
        return Tiny(1, s.hidden, s.hidden) if s.stage == 0 else s
    def obs(s: Tiny) -> tuple[int, int]:
        return (s.stage, s.output if s.stage == 1 else -1)
    blocks = partition_refinement(states, acts, trans, obs)
    hidden_distinguished = next(len(b) for b in blocks if all(s.stage == 0 for s in b)) == 1

    # Aggregable witness: hidden label does not affect transition or observation.
    ag_states = {Tiny(0, h) for h in (0, 1)} | {Tiny(1, h, 0) for h in (0, 1)}
    def ag_trans(s: Tiny, _action: str) -> Tiny:
        return Tiny(1, s.hidden, 0) if s.stage == 0 else s
    ag_blocks = partition_refinement(ag_states, acts, ag_trans, obs)
    ag_same_class = any(sum(1 for s in b if s.stage == 0) == 2 for b in ag_blocks)
    return {
        "PC8_nonaggregability_detected": hidden_distinguished,
        "PC9_aggregability_confirmed": ag_same_class,
        "PC8_classes": len(blocks),
        "PC9_classes": len(ag_blocks),
    }
