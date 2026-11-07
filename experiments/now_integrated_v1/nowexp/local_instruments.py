"""Candidate paid reaction rules. Rules themselves are imported, not derived."""
from .state import Apparatus


def produce(cell, enabled):
    # Two precursors become two material apparatuses; catalyst survives this event.
    if not enabled:
        withhold(cell, 2, 2)
        return []
    if not cell.apparatus or cell.decoded != {"A": 1, "B": 1}:
        return []
    if cell.precursor < 2 or cell.fuel < 2:
        cell.failures.append("production_budget")
        return []
    cell.pay(2, "apparatus_production")
    cell.precursor -= 2
    made = [Apparatus(f"{cell.identity}:new:{j}", cell.identity,
                      cell.generation, cell.decoded["A"]).__dict__ for j in range(2)]
    cell.apparatus.extend(made)
    return made


def retire_inherited(cell):
    old = [a for a in cell.apparatus if a["generation"] < cell.generation]
    cell.apparatus = [a for a in cell.apparatus if a["generation"] >= cell.generation]
    cell.material_waste += sum(a["material_units"] for a in old)
    return [a["identity"] for a in old]


def can_repair(cell, enabled):
    return (enabled and bool(cell.apparatus)
            and cell.decoded.get("A") == 1 and cell.decoded.get("B") == 1)


def withhold(cell, fuel, precursor):
    """Disabled-mechanism credits are not reassigned to another mechanism."""
    f, p = min(fuel, cell.fuel), min(precursor, cell.precursor)
    cell.fuel -= f
    cell.precursor -= p
    cell.unavailable_fuel += f
    cell.unavailable_material += p


def correct(cell, enabled):
    if (enabled and cell.apparatus and cell.contact
            and cell.decoded == {"A": 1, "B": 1}
            and cell.pay(2, "functional_correction")):
        cell.health = min(10, cell.health + 2)
        return True
    return False
