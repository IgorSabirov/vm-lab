"""Policy library with explicit, source-scoped read capabilities.

Policies receive only public input plus the capability methods granted for the
current cell. They never receive evaluator keys, oracle targets, task records,
resource state or trace objects. This is an accidental-access boundary, not an
OS sandbox for hostile Python.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Callable, Optional

_ACTIVE_ACCESS_LOG: ContextVar[Optional[list[str]]] = ContextVar("x27_policy_access_log", default=None)
_FORBIDDEN_FIELDS = frozenset({
    "oracle", "target", "y_star", "expected", "task_id", "task_case_id", "evaluator_key",
    "tau", "opaque_id", "opaque_identifier", "evaluator_case", "task_context",
    "record_id", "creator_id", "state", "resources", "apparatus",
    "task_memory", "residual_payload", "prod_memory", "trace", "journal", "secret",
    "oracle_target", "oracle_table", "answer_key",
})


class PolicyAccessViolation(AttributeError):
    """Raised when a policy asks for an undeclared source or hidden field."""


_PUBLIC_INPUT_KEYS = frozenset({"command", "public_hint"})
_FORBIDDEN_INPUT_KEYS = frozenset({
    "task_id", "task_case_id", "evaluator_key", "opaque_id", "opaque_identifier",
    "tau", "target", "oracle_target", "y_star", "evaluator_case", "task_context",
})


class PolicyObservation:
    """Narrow executor context with explicit M/P read capabilities.

    Only ``public_input`` is a readable data field. M/P values live behind
    stage-local reader callbacks; a policy can invoke only capabilities granted
    to that policy. Private implementation attributes are not accessible through
    normal attribute lookup. A malicious in-process Python extension still needs
    OS-level isolation, which this package does not claim to provide.
    """

    __slots__ = ("public_input", "_allowed_sources", "_readers")

    def __init__(self, public_input: tuple[tuple[str, int | str], ...], *,
                 allowed_sources: tuple[str, ...] = (),
                 readers: Optional[dict[str, Callable[[], int]]] = None) -> None:
        frozen_input = tuple(public_input)
        keys = [key for key, _ in frozen_input]
        if len(keys) != len(set(keys)):
            raise ValueError("public_input contains duplicate field names")
        forbidden = set(keys) & _FORBIDDEN_INPUT_KEYS
        if forbidden:
            raise ValueError(f"evaluator-only fields cannot enter public_input: {sorted(forbidden)}")
        unknown_input = set(keys) - _PUBLIC_INPUT_KEYS
        if unknown_input:
            raise ValueError(f"public_input contains undeclared fields: {sorted(unknown_input)}")
        input_map = dict(frozen_input)
        if "command" not in input_map or input_map["command"] != "emit_the_supplied_binary_content":
            raise ValueError("public_input command does not match the frozen task interface")
        if input_map.get("public_hint") not in (0, 1) or isinstance(input_map.get("public_hint"), bool):
            raise ValueError("public_hint must be a binary integer")
        object.__setattr__(self, "public_input", frozen_input)
        object.__setattr__(self, "_allowed_sources", frozenset(allowed_sources))
        object.__setattr__(self, "_readers", dict(readers or {}))
        unknown = set(allowed_sources) - {"M_task", "P_res"}
        if unknown:
            raise ValueError(f"unknown read capabilities: {sorted(unknown)}")
        if set(allowed_sources) - set(readers or {}):
            raise ValueError("every granted read capability requires a reader")

    def __getattribute__(self, name: str) -> object:
        if name.startswith("_") and name not in {"__class__"}:
            log = _ACTIVE_ACCESS_LOG.get()
            if log is not None:
                log.append(name)
            raise PolicyAccessViolation(f"private policy context field blocked: {name}")
        if name in _FORBIDDEN_FIELDS:
            log = _ACTIVE_ACCESS_LOG.get()
            if log is not None:
                log.append(name)
            raise PolicyAccessViolation(f"policy attempted forbidden field access: {name}")
        return object.__getattribute__(self, name)

    def __getattr__(self, name: str) -> object:
        log = _ACTIVE_ACCESS_LOG.get()
        if log is not None:
            log.append(name)
        raise PolicyAccessViolation(f"unknown or forbidden policy field: {name}")

    def _read(self, source: str) -> int:
        log = _ACTIVE_ACCESS_LOG.get()
        if log is not None:
            log.append(f"read:{source}")
        allowed = object.__getattribute__(self, "_allowed_sources")
        readers = object.__getattribute__(self, "_readers")
        if source not in allowed:
            if log is not None:
                log.append(f"blocked_read:{source}")
            raise PolicyAccessViolation(f"read capability not granted: {source}")
        return readers[source]()

    def read_task_memory(self) -> int:
        return object.__getattribute__(self, "_read")("M_task")

    def read_residual_payload(self) -> int:
        return object.__getattribute__(self, "_read")("P_res")


Policy = Callable[[PolicyObservation], int | None]


def pi_M(obs: PolicyObservation) -> int:
    """Read M_task through its explicit capability."""
    return obs.read_task_memory()


def pi_P(obs: PolicyObservation) -> int:
    """Read residual payload through its explicit capability."""
    return obs.read_residual_payload()


def pi_fixed(obs: PolicyObservation) -> int:
    """Predeclared fixed output; does not inspect input or memory."""
    return 0


def pi_none(obs: PolicyObservation) -> None:
    """Abstain and perform no read."""
    return None


def pi_0_legacy(obs: PolicyObservation) -> int:
    """Compatibility baseline corresponding to the v0.4.x M_task readout."""
    return obs.read_task_memory()


def pi_input(obs: PolicyObservation) -> int:
    """Use public input only; this challenge has a constant public hint."""
    fields = dict(obs.public_input)
    value = fields.get("public_hint")
    if value not in (0, 1):
        raise ValueError("public_hint must be binary")
    return int(value)


POLICIES: dict[str, Policy] = {
    "pi_M": pi_M,
    "pi_0_legacy": pi_0_legacy,
    "pi_P": pi_P,
    "pi_fixed": pi_fixed,
    "pi_none": pi_none,
    "pi_input": pi_input,
}

POLICY_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "pi_M": ("M_task",),
    "pi_0_legacy": ("M_task",),
    "pi_P": ("P_res",),
    "pi_fixed": (),
    "pi_none": (),
    "pi_input": (),
}


def invoke_candidate(policy: Policy, observation: PolicyObservation) -> tuple[int | None, tuple[str, ...], bool]:
    """Invoke a candidate under a scoped dynamic access monitor."""
    access_log: list[str] = []
    token = _ACTIVE_ACCESS_LOG.set(access_log)
    blocked = False
    value: int | None = None
    try:
        value = policy(observation)
    except PolicyAccessViolation:
        blocked = True
    finally:
        _ACTIVE_ACCESS_LOG.reset(token)
    if not blocked and value not in (None, 0, 1):
        raise ValueError("policy must emit 0, 1 or None")
    return value, tuple(access_log), blocked


def invoke_policy(policy_name: str, observation: PolicyObservation) -> tuple[int | None, tuple[str, ...]]:
    if policy_name not in POLICIES:
        raise KeyError(policy_name)
    value, accessed, blocked = invoke_candidate(POLICIES[policy_name], observation)
    if blocked:
        raise PolicyAccessViolation(f"policy access blocked: {accessed}")
    return value, accessed


def rogue_oracle_policy(obs: PolicyObservation) -> int:
    """Adversarial NC16 fixture; not included in the production library."""
    return int(getattr(obs, "oracle"))


def rogue_identifier_policy(obs: PolicyObservation) -> int:
    """Adversarial NC16 fixture; not included in the production library."""
    return int(getattr(obs, "task_id"))


def rogue_opaque_identifier_policy(obs: PolicyObservation) -> int:
    """Adversarial NC15/NC16 fixture; opaque IDs must never reach the policy."""
    return int(getattr(obs, "opaque_identifier"))


def rogue_unauthorized_payload_policy(obs: PolicyObservation) -> int:
    """A memory-only policy attempting to read payload; must be blocked."""
    return int(obs.read_residual_payload())
