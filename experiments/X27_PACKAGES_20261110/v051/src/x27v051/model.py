"""Immutable finite model primitives for X27 v0.5.1."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Optional, Tuple

CAPACITY: Tuple[int, int, int, int] = (4, 3, 3, 3)
INITIAL_MATERIAL = 2
MAX_TIME = 9
DELAY_STEPS = 1
REQUIRED_STRESS = ("omega_delay", "omega_loss_E", "omega_loss_M")


class Stage(IntEnum):
    INITIALIZE = 0
    READ_TASK1 = 1
    EXECUTE_TASK1 = 2
    RESTORE = 3
    READINESS = 4
    DISTURBANCE_AND_READ_TASK2 = 5
    EXECUTE_TASK2 = 6
    TERMINAL = 7


class Health(IntEnum):
    NON_OPERATIONAL = 0
    MINIMUM = 1
    RESERVE = 2


class Arm(str, Enum):
    R0 = "R0"
    R_EXT = "R_ext"
    R_INT = "R_int"


class Disturbance(str, Enum):
    NONE = "omega_0"
    DELAY = "omega_delay"
    LOSS_E = "omega_loss_E"
    LOSS_M = "omega_loss_M"


class Status(str, Enum):
    SUCCESS = "SUCCESS"
    WRONG_ANSWER = "WRONG_ANSWER"
    ABSTAINED = "ABSTAINED"
    INTEGRITY_ERROR = "INTEGRITY_ERROR"
    MISSING_READ_EVENT = "MISSING_READ_EVENT"
    APPARATUS_DEGRADED = "APPARATUS_DEGRADED"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"
    TIMEOUT = "TIMEOUT"
    REPAIR_FAILED = "REPAIR_FAILED"
    TASK2_FAILED = "TASK2_FAILED"


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    record_id: str
    version: int
    semantic_bit: int
    checksum: int
    creator_id: str = "C"

    def __post_init__(self) -> None:
        if isinstance(self.semantic_bit, bool) or not isinstance(self.semantic_bit, int) or self.semantic_bit not in (0, 1):
            raise ValueError("semantic_bit must be integer 0 or 1")
        if isinstance(self.checksum, bool) or not isinstance(self.checksum, int) or self.checksum not in (0, 1):
            raise ValueError("checksum must be integer 0 or 1")
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise ValueError("version must be a positive integer")
        if not isinstance(self.record_id, str) or not self.record_id:
            raise ValueError("record_id must be a non-empty string")
        if not isinstance(self.creator_id, str) or not self.creator_id:
            raise ValueError("creator_id must be a non-empty string")

    @classmethod
    def make(cls, bit: int, record_id: str, creator_id: str = "C") -> "MemoryRecord":
        return cls(record_id, 1, bit, 1 - bit, creator_id)

    @property
    def valid(self) -> bool:
        return self.checksum == 1 - self.semantic_bit


@dataclass(frozen=True, slots=True)
class RepairRecord:
    record_id: str
    version: int
    instruction: str
    checksum: int
    creator_id: str = "C"

    def __post_init__(self) -> None:
        if self.instruction not in ("r0", "r1"):
            raise ValueError("repair instruction must be r0 or r1")
        if isinstance(self.checksum, bool) or not isinstance(self.checksum, int) or self.checksum not in (0, 1):
            raise ValueError("checksum must be integer 0 or 1")
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise ValueError("version must be a positive integer")
        if not isinstance(self.record_id, str) or not self.record_id:
            raise ValueError("record_id must be a non-empty string")
        if not isinstance(self.creator_id, str) or not self.creator_id:
            raise ValueError("creator_id must be a non-empty string")

    @classmethod
    def make(cls, instruction: str, creator_id: str = "C") -> "RepairRecord":
        bit = 0 if instruction == "r0" else 1
        return cls("M_prod", 1, instruction, 1 - bit, creator_id)

    @property
    def valid(self) -> bool:
        bit = 0 if self.instruction == "r0" else 1
        return self.checksum == 1 - bit


@dataclass(frozen=True, slots=True)
class ResourceVector:
    energy: int
    material: int
    waste: int
    unavailable: int

    def __post_init__(self) -> None:
        vals = self.as_tuple()
        for i, v in enumerate(vals):
            if isinstance(v, bool) or not isinstance(v, int):
                raise TypeError("resource components must be integers")
            if v < 0 or v > CAPACITY[i]:
                raise ValueError(f"resource component {i} must be in [0,{CAPACITY[i]}]")

    def as_tuple(self) -> Tuple[int, int, int, int]:
        return (self.energy, self.material, self.waste, self.unavailable)

    def as_dict(self) -> dict[str, int]:
        return dict(zip(("E", "M", "W", "U"), self.as_tuple()))

    @classmethod
    def from_tuple(cls, values: Tuple[int, int, int, int]) -> "ResourceVector":
        return cls(*values)


@dataclass(frozen=True, slots=True)
class Apparatus:
    kind: str
    health: int
    connected: bool
    port_id: Optional[str]
    apparatus_id: str
    creator_id: str
    token_signature: str

    def __post_init__(self) -> None:
        if self.kind not in ("original", "substitute", "absent"):
            raise ValueError("unknown apparatus kind")
        if isinstance(self.health, bool) or not isinstance(self.health, int) or self.health not in (0, 1, 2):
            raise ValueError("health must be integer 0, 1 or 2")
        if not isinstance(self.connected, bool):
            raise TypeError("connected must be bool")
        if self.kind == "absent":
            if self.health != 0 or self.connected or self.port_id is not None:
                raise ValueError("absent apparatus must have health=0 and be disconnected")
        elif self.port_id is None and self.connected:
            raise ValueError("connected apparatus requires a port")

    @classmethod
    def a0(cls) -> "Apparatus":
        return cls("absent", 0, False, None, "none", "none", "none")

    @classmethod
    def a1(cls, health: int = 2) -> "Apparatus":
        return cls("original", health, True, "port-main", "apparatus-C-001", "C", "token-original")

    @classmethod
    def a2(cls, health: int = 2) -> "Apparatus":
        return cls("substitute", health, True, "port-main", "apparatus-substitute-001", "test-fixture", "token-substitute")

    @property
    def operational(self) -> bool:
        return self.kind != "absent" and self.connected and self.health >= 1

    def with_health(self, health: int) -> "Apparatus":
        return Apparatus(self.kind, health, self.connected, self.port_id, self.apparatus_id,
                         self.creator_id, self.token_signature)


@dataclass(frozen=True, slots=True)
class TraceEvent:
    event_type: str
    stage: int
    time: int
    details: Tuple[Tuple[str, object], ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {"event_type": self.event_type, "stage": self.stage, "time": self.time,
                "details": dict(self.details)}


@dataclass(frozen=True, slots=True)
class BState:
    """Complete decision state for B-LITE; trace remains diagnostic side data."""
    task_memory: MemoryRecord
    prod_memory: RepairRecord
    apparatus: Apparatus
    resources: ResourceVector
    stage: int = int(Stage.INITIALIZE)
    time: int = 0
    source_off: bool = False
    task1_read: Optional[int] = None
    task1_operand: Optional[int] = None
    task1_action: Optional[int] = None
    task1_status: Optional[str] = None
    task2_read: Optional[int] = None
    task2_operand: Optional[int] = None
    task2_status: Optional[str] = None
    repair_instruction: Optional[str] = None
    internal_restore_used: bool = False
    external_donor_used: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.stage, bool) or not isinstance(self.stage, int) or not 0 <= self.stage <= 7:
            raise ValueError("stage must be integer in [0,7]")
        if isinstance(self.time, bool) or not isinstance(self.time, int) or self.time < 0:
            raise ValueError("time must be a nonnegative integer")
        if not isinstance(self.source_off, bool) or not isinstance(self.internal_restore_used, bool) or not isinstance(self.external_donor_used, bool):
            raise TypeError("state flags must be bool")
        for name in ("task1_read", "task1_operand", "task1_action", "task2_read", "task2_operand"):
            v = getattr(self, name)
            if v is not None and (isinstance(v, bool) or not isinstance(v, int) or v not in (0, 1)):
                raise ValueError(f"{name} must be None or integer 0 or 1")


def emit(event_type: str, state: BState, **details: object) -> TraceEvent:
    return TraceEvent(event_type, state.stage, state.time, tuple(sorted(details.items())))
