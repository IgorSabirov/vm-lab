"""Component-wise finite resource ledger with atomic costs and explicit spill."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Tuple
from .model import CAPACITY, ResourceVector

ZERO = (0, 0, 0, 0)
TASK_COST = (1, 0, 0, 0)
TASK_BYPRODUCT = (0, 0, 1, 0)
REPAIR_COST = (1, 1, 0, 0)
REPAIR_BYPRODUCT = (0, 0, 1, 0)
EXTERNAL_INJECTION = (1, 1, 0, 0)


@dataclass(frozen=True, slots=True)
class ResourceOperationResult:
    resources: ResourceVector
    spill_inflow: Tuple[int, int, int, int]
    spill_byproduct: Tuple[int, int, int, int]
    exhausted: bool
    ledger: Tuple[Tuple[str, object], ...]

    def as_dict(self) -> dict[str, object]:
        return {"resources": self.resources.as_dict(), "spill_inflow": self.spill_inflow,
                "spill_byproduct": self.spill_byproduct, "exhausted": self.exhausted,
                "ledger": dict(self.ledger)}


def _check_vector(v: Iterable[int], name: str) -> Tuple[int, int, int, int]:
    xs = tuple(v)
    if len(xs) != 4:
        raise ValueError(f"{name} must have four components")
    for x in xs:
        if isinstance(x, bool) or not isinstance(x, int) or x < 0:
            raise ValueError(f"{name} components must be nonnegative integers")
    return xs  # type: ignore[return-value]


def _cap(raw: Tuple[int, ...]) -> tuple[Tuple[int, int, int, int], Tuple[int, int, int, int]]:
    kept = tuple(min(CAPACITY[i], raw[i]) for i in range(4))
    spill = tuple(max(0, raw[i] - CAPACITY[i]) for i in range(4))
    return kept, spill  # type: ignore[return-value]


def apply_operation(resources: ResourceVector, *, name: str,
                    inflow: Iterable[int] = ZERO,
                    cost: Iterable[int] = ZERO,
                    byproduct: Iterable[int] = ZERO) -> ResourceOperationResult:
    """Apply inflow→spill→atomic cost→deduct→byproduct→spill. Pure function."""
    inf = _check_vector(inflow, "inflow")
    cst = _check_vector(cost, "cost")
    byp = _check_vector(byproduct, "byproduct")
    before = resources.as_tuple()
    raw_in = tuple(before[i] + inf[i] for i in range(4))
    after_in, spill_in = _cap(raw_in)
    if any(after_in[i] < cst[i] for i in range(4)):
        rv = ResourceVector.from_tuple(after_in)
        return ResourceOperationResult(
            rv, spill_in, (0, 0, 0, 0), True,
            (("name", name), ("before", before), ("inflow", inf),
             ("after_inflow", after_in), ("cost", cst), ("cost_deducted", False),
             ("byproduct", byp), ("after", after_in), ("spill_inflow", spill_in),
             ("spill_byproduct", (0, 0, 0, 0)), ("status", "RESOURCE_EXHAUSTED")))
    after_cost = tuple(after_in[i] - cst[i] for i in range(4))
    raw_by = tuple(after_cost[i] + byp[i] for i in range(4))
    after_by, spill_by = _cap(raw_by)
    rv = ResourceVector.from_tuple(after_by)
    return ResourceOperationResult(
        rv, spill_in, spill_by, False,
        (("name", name), ("before", before), ("inflow", inf),
         ("after_inflow", after_in), ("cost", cst), ("cost_deducted", True),
         ("after_cost", after_cost), ("byproduct", byp), ("after", after_by),
         ("spill_inflow", spill_in), ("spill_byproduct", spill_by), ("status", "APPLIED")))


def apply_loss(resources: ResourceVector, component: str) -> tuple[ResourceVector, bool, dict[str, object]]:
    idx = {"E": 0, "M": 1}.get(component)
    if idx is None:
        raise ValueError("loss component must be E or M")
    before = resources.as_tuple()
    vals = list(before)
    applicable = vals[idx] > 0
    if applicable:
        vals[idx] -= 1
    after = tuple(vals)
    return ResourceVector.from_tuple(after), applicable, {
        "component": component, "before": before, "after": after,
        "applicable": applicable,
        "status": "LOSS_APPLIED" if applicable else "LOSS_NOT_APPLICABLE",
    }


def saturation_probe() -> dict[str, object]:
    start = ResourceVector(4, 2, 0, 0)
    result = apply_operation(start, name="capacity_probe", inflow=(1, 1, 0, 0))
    return {"kept": result.resources.as_tuple(), "spill_inflow": result.spill_inflow,
            "expected_kept": (4, 3, 0, 0), "expected_spill": (1, 0, 0, 0),
            "pass": result.resources.as_tuple() == (4, 3, 0, 0) and result.spill_inflow == (1, 0, 0, 0)}
