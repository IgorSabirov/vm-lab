"""Paid XOR task and post-damage restoration in the existing NOW cells.

The controller uses decoded local bits only. The original source is consulted
only by the final observer. The result overwrites the existing B record slot.
"""
import copy
from . import memory
from .local_instruments import capable, produce, use


def ready(cell, cfg):
    return (set(cell.decoded) == {'A', 'B'} and all(type(x) is int and x in (0, 1) for x in cell.decoded.values())) if cfg.task_probe else cell.decoded == cfg.required_content


def schedule(engine, cell, event):
    if not engine.config.task_probe:
        return
    engine.schedule(engine.after(cell.identity, engine.now, engine.config.read_wait+8),
                    cell.identity, 'task_damage', {}, cell.identity+':task:damage', parents=(event['id'],))


def dispatch(engine, e):
    cfg, cell = engine.config, engine.cells[e['owner']]
    kind, owner = e['kind'], e['owner']
    if kind == 'task_damage':
        role = cfg.task_damage
        if role in ('writer', 'reader'):
            removed = [a for a in cell.apparatus if a.get('functional_type') == role]
            cell.apparatus = [a for a in cell.apparatus if a not in removed]
            cell.material_waste += sum(a['material_units'] for a in removed)
        elif role == 'contact':
            cell.material_waste += cell.contact_material
            cell.contact_material, cell.contact, cell.contact_peers = 0, False, []
        cell.task_state = dict(damage=role, mode=cfg.restoration_mode, status='DAMAGED', output=None,
                               original_record_slots=len(cell.memories), reserve_fuel=0, reserve_material=0)
        # All three K branches request the same replenishment at the same time.
        engine.request_supply(cell, e)
        for offset, op in ((0, 'task_restore'), (2, 'task_read'), (3, 'task_write')):
            engine.schedule(engine.after(owner, engine.now, cfg.read_wait+offset), owner, op, {},
                            owner+':'+op, parents=(e['id'],))
    elif kind == 'task_restore':
        # Reserve is fixed in advance. Never copy the realized cost from K=ON.
        fuel, material = min(5, cell.fuel), min(5, cell.precursor)
        cell.fuel -= fuel
        cell.precursor -= material
        cell.task_state.update(reserve_fuel=fuel, reserve_material=material,
                               full_reserve=(fuel == 5 and material == 5))
        ordinary_fuel, ordinary_material = cell.fuel, cell.precursor
        cell.fuel, cell.precursor = fuel, material
        if cfg.restoration_mode == 'on':
            produce(cell, cfg.production, cfg)
            # The same local contact instrument; no global target bit is given.
            engine.dispatch(dict(e, kind='repair', data=dict(task_restore=True)))
        elif cfg.restoration_mode == 'sham':
            cell.pay(cell.fuel, 'task_sham')
            cell.material_waste += cell.precursor
            cell.precursor = 0
        # Unused reserve is physically unavailable to the task in every branch.
        cell.unavailable_fuel += cell.fuel
        cell.unavailable_material += cell.precursor
        cell.fuel, cell.precursor = ordinary_fuel, ordinary_material
        cell.task_state['status'] = 'RESTORATION_ATTEMPTED'
    elif kind == 'task_read':
        cell.decoded.clear()  # A cached pre-damage answer is not a new read.
        engine.dispatch(dict(e, kind='read', data=dict(cycle=100)))
    elif kind == 'task_write':
        state = cell.task_state
        if not (ready(cell, cfg) and capable(cell, 'write') and cell.contact and 'B' in cell.memories):
            state['status'] = 'TASK_UNAVAILABLE'
            return
        # Identity/NOT-A both cost one credit; both retain the original target.
        if cell.fuel < 2:
            state['status'] = 'TASK_FUEL_SHORTFALL'
            return
        cell.pay(1, 'task_content_gate')
        a, b = cell.decoded['A'], cell.decoded['B']
        if cfg.task_content_intervention == 'flip_A':
            a ^= 1
        output = a ^ b
        cell.pay(1, 'task_write')
        use(cell, 'write')
        # A finite environment register carries the overwritten physical state;
        # it is part of the snapshot and never available to the controller.
        engine.environment_records.append(dict(mode='task_overwrite', owner=owner,
                                               old_record=copy.deepcopy(cell.memories['B'])))
        cell.memories['B'] = memory.write(output, cfg.memory, engine.proper(owner, engine.now),
                                          cfg.bath_modes, cfg.bath_coupling, cfg.detuning)
        cell.memory_origins['B'] = e['id']
        state.update(status='TASK_WRITTEN', output=output, output_slot='B', overwrite=True,
                     record_slots_after=len(cell.memories))
    else:
        raise ValueError('unknown task instrument')


def observe(cell, original):
    out = copy.deepcopy(cell.task_state)
    target = original[0] ^ original[1]
    out.update(target=target, success=int(out.get('status') == 'TASK_WRITTEN' and out.get('output') == target),
               observer_only_target=True)
    return out
