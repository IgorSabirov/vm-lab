"""Exact finite intervention-family and predictive partition utilities.

The sequence generator freezes a complete *stage schedule*: every stage from
0 through 6 has one explicit ``continue`` transition, while at most two
stage-local interventions are inserted before that stage's continue. Model
partition results remain pending until a concrete state-transition adapter is
independently reviewed; the generic refinement algorithm is not reported as a
full X27 H-Q result.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Callable, Hashable, Iterable, Mapping, Sequence, TypeVar

S = TypeVar("S", bound=Hashable)


@dataclass(frozen=True, slots=True)
class Intervention:
    stage: int
    operator: str
    value: str

    def label(self) -> str:
        return f"stage{self.stage}:{self.operator}={self.value}"

    @property
    def controlled_variable(self) -> str:
        return {
            "do(M_task)": "M_task",
            "do(P_res)": "P_res",
            "do(A)": "A",
            "do(M_prod)": "M_prod",
        }[self.operator]


def intervention_alphabet(module: str) -> tuple[Intervention, ...]:
    if module not in ("A", "B-LITE"):
        raise ValueError("module must be A or B-LITE")
    controls: list[Intervention] = []
    for stage in (1, 5):
        for bit in (0, 1):
            controls.append(Intervention(stage, "do(M_task)", str(bit)))
            controls.append(Intervention(stage, "do(P_res)", str(bit)))
    for stage in (0, 3):
        for apparatus in ("A0", "A1", "A2"):
            controls.append(Intervention(stage, "do(A)", apparatus))
    if module == "B-LITE":
        for repair in ("r0", "r1"):
            controls.append(Intervention(3, "do(M_prod)", repair))
    return tuple(sorted(controls, key=lambda a: (a.stage, a.operator, a.value)))


def _compatible_pair(a: Intervention, b: Intervention) -> bool:
    """Two same-stage controls may co-occur only on distinct variables."""
    if b.stage < a.stage:
        return False
    if a.stage == b.stage and a.controlled_variable == b.controlled_variable:
        return False
    return True


def generate_intervention_sequences(module: str, max_depth: int = 2) -> dict[str, object]:
    """Enumerate all stage-local intervention schedules of depth at most two.

    Every schedule explicitly includes ``continue@stage_k`` for k=0..6.
    Interventions at a stage are applied before its continue. Controls are never
    queued from an earlier stage. Conflicting same-stage interventions on the
    same variable (e.g. A0 followed by A1 at stage 3) are excluded.
    """
    if max_depth != 2:
        raise ValueError("v0.5.1 freezes intervention depth at two")
    alphabet = intervention_alphabet(module)

    selections: list[tuple[Intervention, ...]] = [()]
    selections.extend((a,) for a in alphabet)
    for a, b in combinations(alphabet, 2):
        if _compatible_pair(a, b):
            selections.append((a, b))

    schedules: list[list[str]] = []
    for selected in selections:
        canonical = tuple(sorted(selected, key=lambda a: (a.stage, a.operator, a.value)))
        tokens: list[str] = []
        for stage in range(7):
            tokens.extend(item.label() for item in canonical if item.stage == stage)
            tokens.append(f"continue@stage{stage}")
        schedules.append(tokens)

    unique = {tuple(schedule): schedule for schedule in schedules}
    ordered = [unique[key] for key in sorted(unique)]
    return {
        "module": module,
        "alphabet": [a.label() for a in alphabet],
        "continue_semantics": "continue@stage_k advances from stage k to k+1 without changing other variables; exactly once at each stage 0..6 in every complete schedule",
        "intervention_order": "stage-local interventions occur before continue at that stage; within one stage canonical operator/value order is used",
        "same_stage_conflicts": "at most one intervention per controlled variable per stage; interventions on distinct variables may co-occur",
        "depth_limit": 2,
        "queued_commands": False,
        "sequence_count": len(ordered),
        "sequences": ordered,
    }


def exact_partition(states: Iterable[S], actions: Sequence[str],
                    transition: Callable[[S, str], tuple[str, Hashable]],
                    observation: Callable[[S], Hashable]) -> dict[str, object]:
    """Strong deterministic future-output equivalence by partition refinement.

    ``transition(state, action)`` returns ``("state", next_state)`` or
    ``("output", output_leaf)``. Every state must support every action in the
    supplied (already stage-scoped) action alphabet. Terminal outputs are leaves,
    never partition members.
    """
    domain = tuple(states)
    if len(set(domain)) != len(domain):
        raise ValueError("states must be unique")
    if not domain:
        raise ValueError("partition domain cannot be empty")
    if not actions:
        raise ValueError("action alphabet cannot be empty")
    index = set(domain)
    obs = {state: observation(state) for state in domain}

    def assign(signatures: Mapping[S, Hashable]) -> dict[S, int]:
        unique_signatures = sorted(set(signatures.values()), key=repr)
        colors = {signature: i for i, signature in enumerate(unique_signatures)}
        return {state: colors[signatures[state]] for state in domain}

    colors = assign(obs)
    rounds = 0
    while True:
        signatures: dict[S, Hashable] = {}
        for state in domain:
            future = []
            for action in actions:
                kind, target = transition(state, action)
                if kind == "state":
                    if target not in index:
                        raise ValueError("transition reached a state outside the declared finite domain")
                    future.append((action, "class", colors[target]))
                elif kind == "output":
                    future.append((action, "output", target))
                else:
                    raise ValueError("transition kind must be 'state' or 'output'")
            signatures[state] = (obs[state], tuple(future))
        refined = assign(signatures)
        rounds += 1
        same_partition = all(
            (colors[a] == colors[b]) == (refined[a] == refined[b])
            for a in domain for b in domain
        )
        colors = refined
        if same_partition:
            break
        if rounds > len(domain) + 1:
            raise RuntimeError("partition refinement failed to stabilize")

    groups: dict[int, list[Hashable]] = {}
    for state, color in colors.items():
        groups.setdefault(color, []).append(state)
    return {
        "state_count": len(domain),
        "action_alphabet": list(actions),
        "rounds": rounds,
        "class_count": len(groups),
        "classes": [[repr(state) for state in members]
                    for _, members in sorted(groups.items())],
        "scope": "exact deterministic future-output equivalence for this finite domain, observable and action alphabet",
    }


def hq_observable_contract() -> dict[str, object]:
    return {
        "O_D": ["public_input", "only explicitly granted read capability calls"],
        "O_eval": ["Y_action", "Y_correct", "Y_status", "T_finish", "R_final", "health_final", "V_nom", "V_rob"],
        "J_trace": ["read events", "action events", "repair events", "resource ledger", "apparatus provenance", "donor events"],
        "J_trace_role": "diagnostic only unless a field is explicitly promoted into O_D or O_eval in a later frozen delta",
        "equivalences": ["H-Q-task", "H-Q-control", "H-Q-R1", "H-Q-R2"],
        "decision_domain": [1, 2, 5, 6],
        "control_domain_additional_stages": [0, 3],
        "terminal_states": "output leaves, never partition members",
        "interpretation": "future-output equivalence for frozen observations and finite intervention family; not full causal-trace equivalence",
        "status": "SPECIFIED_ALGORITHM_AND_SEQUENCE_FAMILY_AVAILABLE_FULL_KERNEL_ADAPTER_PENDING",
    }
