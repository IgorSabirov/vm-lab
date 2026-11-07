"""Candidate paid reaction rules. Rules themselves are imported, not derived."""
from .state import Apparatus


def capable(cell, role):
    # Imported operational type law; no claim to derive function from chemistry.
    return [a for a in cell.apparatus if a["template"] == 1 and role not in a.get("disabled_roles", ())
            and ('roles' not in a or role in a['roles'])]


def use(cell, role):
    available = capable(cell, role)
    if available:
        cell.capability_uses.append(dict(role=role, apparatus=available[0]["identity"],
                                       origin=available[0]["made_by"]))
    return bool(available)


def produce(cell, enabled, cfg):
    # Two precursors become two material apparatuses; catalyst survives this event.
    count=(6 if cfg.branching and cell.identity=='N0' else 4) if cfg.separate_apparatus else 2
    if not enabled:
        if cfg.disabled_resource_policy == "matched":
            withhold(cell, count, count)
        return []
    if not capable(cell, "catalyze") or cell.decoded != cfg.required_content:
        return []
    if cell.precursor < count or cell.fuel < count:
        cell.failures.append("production_budget")
        return []
    cell.pay(count, "apparatus_production")
    use(cell, "catalyze")
    cell.precursor -= count
    made = [Apparatus(f"{cell.identity}:new:{j}", cell.identity,
                      cell.generation, cfg.produced_template).__dict__ for j in range(count)]
    for apparatus in made:
        apparatus["disabled_roles"] = list(cfg.produced_disabled_roles)
    if cfg.separate_apparatus:
        for j,apparatus in enumerate(made):
            apparatus['roles']=['write','catalyze'] if j%2==0 else ['read','catalyze','repair','correct']
            apparatus['functional_type']='writer' if j%2==0 else 'reader'
        if cfg.production_semantics!='pair_rule':
            from .typed_reactions import reaction
            from collections import Counter
            q=Counter(1 if a.get('functional_type')=='reader' else 2 if a.get('functional_type')=='writer' else 0 for a in cell.apparatus)
            for apparatus in made:
                chosen=cell.reactor_state if cfg.production_semantics=='A' or q[cell.reactor_state]>0 else min(k for k,n in q.items() if n>0)
                step=reaction(cell.reactor_state,q,cfg.production_semantics,chosen)
                if step is None:raise ArithmeticError('paid typed production has no input access')
                cell.reactor_state=step['state_type'];q=Counter(step['access'])
                kind=step['added_type']
                apparatus['functional_type']={0:'inert',1:'reader',2:'writer'}[kind]
                apparatus['roles']={0:[],1:['read','catalyze','repair','correct'],2:['write','catalyze']}[kind]
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
