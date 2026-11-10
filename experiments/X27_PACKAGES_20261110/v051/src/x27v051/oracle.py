"""Independent evaluator for the X27 v0.5.1 hidden-task challenge.

The evaluator receives Q_eval=(tau, public_input). Policies receive only the
public_input and explicitly granted read capabilities. Neither tau nor an
opaque evaluator-case key is part of the executor interface. This is a
software-layer separation, not a cryptographically isolated oracle service.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class OracleTask:
    evaluator_key: str  # evaluator-side join key; never sent to a policy
    tau: str            # evaluator-only task context
    public_input: tuple[tuple[str, int | str], ...]
    version: str


_PUBLIC_INPUT = (
    ("command", "emit_the_supplied_binary_content"),
    ("public_hint", 0),
)

# Task cases intentionally have identical public input but different hidden tau.
_TASKS: Mapping[str, OracleTask] = {
    "eval_case_opaque_A": OracleTask(
        "eval_case_opaque_A", "evaluator_case_A", _PUBLIC_INPUT, "oracle-v1"
    ),
    "eval_case_opaque_B": OracleTask(
        "eval_case_opaque_B", "evaluator_case_B", _PUBLIC_INPUT, "oracle-v1"
    ),
}

# The independent target table is keyed by (tau, p), not by task ID.
_TARGETS: Mapping[tuple[str, tuple[tuple[str, int | str], ...]], int] = {
    ("evaluator_case_A", _PUBLIC_INPUT): 0,
    ("evaluator_case_B", _PUBLIC_INPUT): 1,
}


def evaluator_tasks() -> tuple[OracleTask, ...]:
    """Return evaluator-side metadata; no target is included in these objects."""
    return tuple(_TASKS[k] for k in sorted(_TASKS))


def evaluator_task(evaluator_key: str) -> OracleTask:
    """Resolve an evaluator-side join key to hidden tau and public input."""
    try:
        return _TASKS[evaluator_key]
    except KeyError as exc:
        raise KeyError(f"unknown evaluator task {evaluator_key!r}") from exc


def evaluate(tau: str, public_input: tuple[tuple[str, int | str], ...],
             action: int | None) -> tuple[int, bool | None]:
    """Compute Y*=f_oracle(tau,p) and score the factual action independently."""
    key = (tau, tuple(public_input))
    if key not in _TARGETS:
        raise KeyError("oracle has no target for this (tau, public_input) pair")
    target = _TARGETS[key]
    if action is None:
        return target, None
    if isinstance(action, bool) or action not in (0, 1):
        raise ValueError("action must be 0, 1 or None")
    return target, action == target


def oracle_manifest() -> dict[str, object]:
    """Machine-readable evaluator manifest (not exposed to executor policies)."""
    return {
        "version": "oracle-v1",
        "evaluator_interface": "Q_eval=(tau,p)",
        "executor_interface": "I_D=p",
        "executor_visible_fields": ["public_input"],
        "evaluator_only_fields": ["tau", "evaluator_key", "target"],
        "tasks": [
            {
                "evaluator_key": task.evaluator_key,
                "tau": task.tau,
                "public_input": dict(task.public_input),
                "target": _TARGETS[(task.tau, task.public_input)],
                "version": task.version,
            }
            for task in evaluator_tasks()
        ],
        "claim_boundary": "Independent scoring within this finite software model; not a physical task oracle.",
    }
