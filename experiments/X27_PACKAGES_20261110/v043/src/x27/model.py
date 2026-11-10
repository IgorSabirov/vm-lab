"""Immutable finite-state data structures for X27 U010 v0.4.3.

The model deliberately separates physical state from append-only diagnostic traces.
All values that affect future transitions belong to State; trace metadata does not.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Optional, Tuple


CAPACITY = 3


class Stage(IntEnum):
    INITIALIZE = 0
    READ_TASK1 = 1
    EXECUTE_TASK1 = 2
    RESTORE = 3
    READINESS = 4
    DISTURBANCE_AND_READ_TASK2 = 5
    EXECUTE_TASK2 = 6
    TERMINAL = 7


class Arm(str, Enum):
    R0 = "R0"
    R_EXT = "R_ext"
    R_INT = "R_int"


class Disturbance(str, Enum):
    NONE = "omega_0"
    DELAY = "omega_delay"
    LOSS_E = "omega_loss_E"
    LOSS_M = "omega_loss_M"


class EquipmentKind(str, Enum):
    ABSENT = "absent"
    ORIGINAL = "original"
    SUBSTITUTE = "substitute"


class EquipmentHealth(str, Enum):
    ABSENT = "absent"
    WORKING = "working"
    WORN = "worn"


class OutcomeStatus(str, Enum):
    SUCCESS = "SUCCESS"
    WRONG_ANSWER = "WRONG_ANSWER"
    TIMEOUT = "TIMEOUT"
    ABORTED = "ABORTED"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"
    INTEGRITY_ERROR = "INTEGRITY_ERROR"
    MISSING_READ_EVENT = "MISSING_READ_EVENT"
    APPARATUS_DEGRADED = "APPARATUS_DEGRADED"
    NO_RESTORE_POSSIBLE = "NO_RESTORE_POSSIBLE"
    TASK2_FAILED = "TASK2_FAILED"
    TASK2_SUCCEEDED = "TASK2_SUCCEEDED"
    LOSS_NOT_APPLICABLE = "LOSS_NOT_APPLICABLE"


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    """A valid binary semantic record with an independently checked checksum.

    Checksum convention for this executable reference model: h(s) = 1 - s.
    This is a concrete, explicit choice because the protocol text leaves h open.
    """

    record_id: str
    version: int
    semantic_bit: int
    checksum: int
    creator_id: str = "C"

    def __post_init__(self) -> None:
        if self.semantic_bit not in (0, 1):
            raise ValueError("semantic_bit must be 0 or 1")
        if self.checksum not in (0, 1):
            raise ValueError("checksum must be 0 or 1")
        if self.version < 1:
            raise ValueError("version must be >= 1")

    @classmethod
    def make(
        cls,
        semantic_bit: int,
        *,
        record_id: str = "M_task",
        version: int = 1,
        creator_id: str = "C",
    ) -> "MemoryRecord":
        if semantic_bit not in (0, 1):
            raise ValueError("semantic_bit must be 0 or 1")
        return cls(record_id, version, semantic_bit, 1 - semantic_bit, creator_id)

    @property
    def valid(self) -> bool:
        return self.checksum == 1 - self.semantic_bit

    def corrupted(self) -> "MemoryRecord":
        return MemoryRecord(
            self.record_id,
            self.version,
            self.semantic_bit,
            1 - self.checksum,
            self.creator_id,
        )


@dataclass(frozen=True, slots=True)
class RepairRecord:
    """Two valid production-memory instructions: bit 0 -> r0, bit 1 -> r1."""

    record_id: str
    version: int
    instruction_bit: int
    checksum: int
    creator_id: str = "C"

    def __post_init__(self) -> None:
        if self.instruction_bit not in (0, 1) or self.checksum not in (0, 1):
            raise ValueError("repair record fields must be binary")
        if self.version < 1:
            raise ValueError("version must be >= 1")

    @classmethod
    def make(cls, instruction: str, *, record_id: str = "M_prod") -> "RepairRecord":
        if instruction not in ("r0", "r1"):
            raise ValueError("instruction must be r0 or r1")
        bit = 0 if instruction == "r0" else 1
        return cls(record_id, 1, bit, 1 - bit)

    @property
    def instruction(self) -> str:
        return "r0" if self.instruction_bit == 0 else "r1"

    @property
    def valid(self) -> bool:
        return self.checksum == 1 - self.instruction_bit


@dataclass(frozen=True, slots=True)
class ResourceVector:
    energy: int
    material: int
    waste: int
    unavailable: int

    def __post_init__(self) -> None:
        for name, value in self.as_dict().items():
            if not isinstance(value, int) or value < 0 or value > CAPACITY:
                raise ValueError(f"resource {name} must be an integer in [0, {CAPACITY}]")

    def as_tuple(self) -> Tuple[int, int, int, int]:
        return (self.energy, self.material, self.waste, self.unavailable)

    def as_dict(self) -> dict[str, int]:
        return {
            "E": self.energy,
            "M": self.material,
            "W": self.waste,
            "U": self.unavailable,
        }

    @classmethod
    def zero(cls) -> "ResourceVector":
        return cls(0, 0, 0, 0)


@dataclass(frozen=True, slots=True)
class ResourceOperation:
    name: str
    inflow: ResourceVector = field(default_factory=ResourceVector.zero)
    cost: ResourceVector = field(default_factory=ResourceVector.zero)
    byproduct: ResourceVector = field(default_factory=ResourceVector.zero)


@dataclass(frozen=True, slots=True)
class ResourceApplication:
    resources: ResourceVector
    spill_inflow: ResourceVector
    spill_byproduct: ResourceVector
    exhausted: bool
    events: Tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Apparatus:
    kind: EquipmentKind
    health: EquipmentHealth
    connected: bool
    apparatus_id: Optional[str]
    creator_id: Optional[str]
    generation: int
    resource_batch: Optional[str]
    port_id: Optional[str]
    token_signature: str

    def __post_init__(self) -> None:
        if self.kind == EquipmentKind.ABSENT:
            if self.health != EquipmentHealth.ABSENT or self.connected:
                raise ValueError("absent apparatus must have absent health and be disconnected")
        else:
            if self.health == EquipmentHealth.ABSENT:
                raise ValueError("present apparatus cannot have absent health")
        if self.connected and not self.port_id:
            raise ValueError("connected apparatus requires a port_id")
        if self.generation < 0:
            raise ValueError("generation must be non-negative")

    @classmethod
    def a0(cls) -> "Apparatus":
        return cls(
            EquipmentKind.ABSENT,
            EquipmentHealth.ABSENT,
            False,
            None,
            None,
            0,
            None,
            None,
            "none",
        )

    @classmethod
    def a1(cls, *, health: EquipmentHealth = EquipmentHealth.WORKING) -> "Apparatus":
        return cls(
            EquipmentKind.ORIGINAL,
            health,
            True,
            "apparatus-C-001",
            "C",
            1,
            "batch-C-001",
            "port-main",
            "token-original",
        )

    @classmethod
    def a2(cls, *, health: EquipmentHealth = EquipmentHealth.WORKING) -> "Apparatus":
        return cls(
            EquipmentKind.SUBSTITUTE,
            health,
            True,
            "apparatus-substitute-001",
            "test-fixture",
            1,
            "batch-substitute-001",
            "port-main",
            "token-substitute",
        )

    @property
    def operational(self) -> bool:
        return self.kind != EquipmentKind.ABSENT and self.health == EquipmentHealth.WORKING and self.connected

    def worn(self) -> "Apparatus":
        if self.kind == EquipmentKind.ABSENT:
            return self
        return Apparatus(
            self.kind,
            EquipmentHealth.WORN,
            self.connected,
            self.apparatus_id,
            self.creator_id,
            self.generation,
            self.resource_batch,
            self.port_id,
            self.token_signature,
        )

    def repaired(self) -> "Apparatus":
        if self.kind == EquipmentKind.ABSENT:
            return self
        return Apparatus(
            self.kind,
            EquipmentHealth.WORKING,
            self.connected,
            self.apparatus_id,
            self.creator_id,
            self.generation,
            self.resource_batch,
            self.port_id,
            self.token_signature,
        )


@dataclass(frozen=True, slots=True)
class SubstituteCalibration:
    compatible_ports: bool
    functionally_equivalent: bool
    transition_equivalent: bool
    cost_equivalent: bool
    connected_under_frozen_protocol: bool

    @property
    def valid(self) -> bool:
        return all(
            (
                self.compatible_ports,
                self.functionally_equivalent,
                self.transition_equivalent,
                self.cost_equivalent,
                self.connected_under_frozen_protocol,
            )
        )


@dataclass(frozen=True, slots=True)
class ModelConfig:
    initial_resources: ResourceVector = field(default_factory=lambda: ResourceVector(3, 2, 0, 0))
    task_cost: ResourceVector = field(default_factory=lambda: ResourceVector(1, 0, 0, 0))
    task_byproduct: ResourceVector = field(default_factory=lambda: ResourceVector(0, 0, 1, 0))
    repair_cost: ResourceVector = field(default_factory=lambda: ResourceVector(1, 1, 0, 0))
    repair_r0_byproduct: ResourceVector = field(default_factory=lambda: ResourceVector(0, 0, 1, 0))
    repair_r1_byproduct: ResourceVector = field(default_factory=lambda: ResourceVector(0, 0, 1, 1))
    external_injection: ResourceVector = field(default_factory=lambda: ResourceVector(1, 1, 0, 0))
    max_time: int = 9
    delay_steps: int = 1
    expected_function: Optional[int] = None
    required_token_signature: Optional[str] = None
    default_repair_instruction: str = "r0"

    def __post_init__(self) -> None:
        if self.max_time < 1 or self.delay_steps < 1:
            raise ValueError("max_time and delay_steps must be positive")
        if self.expected_function not in (None, 0, 1):
            raise ValueError("expected_function must be None, 0 or 1")
        if self.default_repair_instruction not in ("r0", "r1"):
            raise ValueError("default_repair_instruction must be r0 or r1")


@dataclass(frozen=True, slots=True)
class State:
    """Complete Markov state for the B-LITE kernel.

    Append-only trace events, immutable provenance labels and the current
    intervention scenario are intentionally not embedded unless they change
    future transitions. Disturbance is passed as a fixed experimental input.
    """

    task_memory: MemoryRecord
    prod_memory: RepairRecord
    residual_payload: MemoryRecord
    payload_accessible: bool
    apparatus: Apparatus
    resources: ResourceVector
    stage: int = int(Stage.INITIALIZE)
    time: int = 0
    source_off: bool = False
    task1_operand: Optional[int] = None
    task1_read_source: Optional[str] = None
    task1_function: Optional[int] = None
    task1_status: Optional[str] = None
    task2_operand: Optional[int] = None
    task2_read_source: Optional[str] = None
    task2_function: Optional[int] = None
    task2_status: Optional[str] = None
    repair_instruction: Optional[str] = None
    internal_restore_used: bool = False
    external_donor_used: bool = False

    def __post_init__(self) -> None:
        if self.stage < 0 or self.stage > int(Stage.TERMINAL):
            raise ValueError("stage must be in [0, 7]")
        if self.time < 0:
            raise ValueError("time must be non-negative")
        for name, value in (
            ("task1_operand", self.task1_operand),
            ("task1_function", self.task1_function),
            ("task2_operand", self.task2_operand),
            ("task2_function", self.task2_function),
        ):
            if value not in (None, 0, 1):
                raise ValueError(f"{name} must be None, 0 or 1")

    @property
    def terminal(self) -> bool:
        return self.stage == int(Stage.TERMINAL)


@dataclass(frozen=True, slots=True)
class TraceEvent:
    event_type: str
    stage: int
    time: int
    details: Tuple[Tuple[str, str | int | bool | None], ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "event_type": self.event_type,
            "stage": self.stage,
            "time": self.time,
            "details": dict(self.details),
        }


def make_memory_pair() -> tuple[MemoryRecord, MemoryRecord]:
    """Return m and valid Tm; they differ in one semantic bit."""
    return (
        MemoryRecord.make(0, record_id="M_task:m"),
        MemoryRecord.make(1, record_id="M_task:Tm"),
    )
