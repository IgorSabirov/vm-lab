"""Candidate paid reaction rules. Rules themselves are imported, not derived."""
from .state import Apparatus


def capable(cell, role):
    # Imported operational type law; no claim to derive function from chemistry.
    return [a for a in cell.apparatus if a["template"] == 1 and role not in a.get("disabled_roles", ())]


def use(cell, role):
    available = capable(cell, role)
    if available:
        cell.capability_uses.append(dict(role=role, apparatus=available[0]["identity"],
                                       origin=available[0]["made_by"]))
    return bool(available)


def produce(cell, enabled, cfg):
    # Two precursors become two material apparatuses; catalyst survives this event.
    if not enabled:
        if cfg.disabled_resource_policy == "matched":
            withhold(cell, 2, 2)
        return []
    if not capable(cell, "catalyze") or cell.decoded != cfg.required_content:
        return []
    if cell.precursor < 2 or cell.fuel < 2:
        cell.failures.append("production_budget")
        return []
    cell.pay(2, "apparatus_production")
    use(cell, "catalyze")
    cell.precursor -= 2
    made = [Apparatus(f"{cell.identity}:new:{j}", cell.identity,
                      cell.generation, cfg.produced_template).__dict__ for j in range(2)]
    for apparatus in made:
        apparatus["disabled_roles"] = list(cfg.produced_disabled_roles)
    cell.apparatus.extend(made)
    return made


def retire_inherited(cell):
    old = [a for a in cell.apparatus if a["generation"] < cell.generation]
    cell.apparatus = [a for a in cell.apparatus if a["generation"] >= cell.generation]
    cell.material_waste += sum(a["material_units"] for a in old)
    return [a["identity"] for a in old]


def can_repair(cell, enabled, cfg):
    return enabled and bool(capable(cell, "repair")) and cell.decoded == cfg.required_content


def withhold(cell, fuel, precursor):
    """Disabled-mechanism credits are not reassigned to another mechanism."""
    f, p = min(fuel, cell.fuel), min(precursor, cell.precursor)
    cell.fuel -= f
    cell.precursor -= p
    cell.unavailable_fuel += f
    cell.unavailable_material += p


def correct(cell, enabled, cfg):
    if not enabled and cfg.disabled_resource_policy == "matched":
        withhold(cell, 2, 0)
    if (enabled and capable(cell, "correct") and cell.contact
            and cell.decoded == cfg.required_content
            and cell.pay(2, "functional_correction")):
        use(cell, "correct")
        cell.health = min(10, cell.health + 2)
        return True
    return False
