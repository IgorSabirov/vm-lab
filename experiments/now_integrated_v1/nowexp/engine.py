"""Finite local-instrument engine. Candidate rules; not executed by its author yet.

All controller functions operate on one Cell. The dispatcher routes physical
messages and audits totals, but never supplies remote state to a controller.
Transport is reliable and finite-speed in this first implementation. General
leases/cancellation, arbitrary losses and fragmentation are outside its claims.
"""
from dataclasses import asdict
import copy
import hashlib
import json
import math

from .state import Cell, Config, Apparatus
from .kinematics import Worldline, reception
from .randomness import uniform, input_bits
from . import memory
from .local_instruments import produce, retire_inherited, can_repair, correct, withhold


class Engine:
    def __init__(self, config, seed):
        self.config = config.validate()
        self.seed = int(seed)
        self.now = 0.0
        self.queue = []
        self.events_seen = set()
        self.sequence = 0
        self.processed = 0
        self.cells = {}
        self.lines = {"donor": Worldline(-2), "MA": Worldline(-1), "MB": Worldline(1)}
        self.donor = {"fuel": config.donor_fuel, "precursor": config.donor_precursor}
        self.in_transit = {}
        self.log = []
        self.environment_records = []
        self.source_alive = {"MA": True, "MB": True}
        self.supply_requests = set()
        for g in range(config.generations):
            name = f"N{g}"
            # Every potential substrate and its location are GIVEN, not generated.
            self.lines[name] = Worldline(2*g, config.receiver_velocity if g else 0)
            self.cells[name] = Cell(name, g,
                fuel=4 if g == 0 else 0,
                address=f"N{g+1}" if g+1 < config.generations and config.address_enabled else None,
                contact=config.imported_contacts,
                contact_origin="imported" if config.imported_contacts else "absent",
                contact_material=int(config.imported_contacts),
                unavailable_material=int(not config.imported_contacts))
        if config.initial_seed:
            self.cells["N0"].apparatus.append(Apparatus("seed:A", "preparation", -1, 1).__dict__)
        else:
            self.cells["N0"].unavailable_material += 1
        self.initial_totals = self.totals()
        self.schedule(0, "N0", "boot", {}, "boot:N0")
        for side, bit in zip(("A", "B"), input_bits(seed, config.forced_content, config.preparation)):
            owner = "M" + side
            self.schedule(0, owner, "source_emit", {"side": side, "bit": bit}, owner+":emit")
            if config.source_repeat:
                self.schedule(4, owner, "source_emit", {"side": side, "bit": bit}, owner+":repeat")
            self.schedule(5 if config.source_repeat else .1, owner, "source_off", {}, owner+":off")

    def schedule(self, t, owner, kind, data, identity, phase=0, parents=()):
        if not math.isfinite(t) or t < self.now - 1e-10:
            raise ValueError("event in past/nonfinite time")
        if identity in self.events_seen or any(e["id"] == identity for e in self.queue):
            raise ValueError("duplicate event ID")
        self.queue.append(dict(t=float(t), owner=owner, kind=kind, data=copy.deepcopy(data),
                               id=identity, phase=phase, parents=list(parents)))

    def send(self, src, dst, kind, payload, identity, speed=1.0, delay=0.0, parent=None):
        arrival = reception(self.lines[src], self.lines[dst], self.now, speed, delay)
        x0, x1 = self.lines[src].x(self.now), self.lines[dst].x(arrival)
        if arrival-self.now+1e-10 < abs(x1-x0):
            raise ArithmeticError("superluminal delivery")
        self.log.append(dict(kind="channel", id=identity, src=src, dst=dst,
                             sent=self.now, received=arrival, x0=x0, x1=x1, speed=speed))
        self.schedule(arrival, dst, kind, payload, identity, parents=(() if parent is None else (parent,)))

    def totals(self):
        fuel = self.donor["fuel"]
        material = self.donor["precursor"]
        for c in self.cells.values():
            fuel += c.fuel + c.spent_fuel + c.unavailable_fuel
            material += c.precursor + c.material_waste + c.unavailable_material + c.contact_material
            material += sum(a["material_units"] for a in c.apparatus)
        for p in self.in_transit.values():
            fuel += p.get("fuel", 0)
            material += p.get("precursor", 0) + sum(a["material_units"] for a in p.get("apparatus", []))
        return {"fuel_credits": fuel, "material_units": material}

    def audit(self):
        if self.totals() != self.initial_totals:
            raise ArithmeticError("whole-system token/material imbalance")
        if min(self.donor.values()) < 0:
            raise ArithmeticError("negative donor")
        for c in self.cells.values():
            if min(c.fuel, c.precursor, c.reserved_fuel, c.reserved_precursor) < 0:
                raise ArithmeticError("negative local stock")
            if c.fuel+c.reserved_fuel+c.unavailable_fuel > c.fuel_capacity or c.precursor+c.reserved_precursor+c.unavailable_material > c.precursor_capacity:
                raise ArithmeticError("receiver capacity exceeded")
            if len(c.decoded) > self.config.working_slots:
                raise ArithmeticError("working memory exceeded")

    def request_supply(self, cell, event):
        # Reserve receiver capacity before issuing a real message. No instant donor read.
        fuel = min(14, cell.fuel_capacity-cell.fuel-cell.reserved_fuel-cell.unavailable_fuel)
        precursor = min(4, cell.precursor_capacity-cell.precursor-cell.reserved_precursor-cell.unavailable_material)
        cell.reserved_fuel += fuel
        cell.reserved_precursor += precursor
        self.send(cell.identity, "donor", "supply_request",
                  dict(target=cell.identity, fuel=fuel, precursor=precursor),
                  event["id"]+":request", parent=event["id"])

    def maybe_write(self, cell):
        if not cell.apparatus:
            return
        proper = self.now / self.lines[cell.identity].gamma
        for side in ("A", "B"):
            if side not in cell.pending or side in cell.memories:
                continue
            # Classical orthogonal input; spent credit pays loading, not a thermodynamic theorem.
            cost = 2 if self.config.memory == "finite_dark" else 1
            if not cell.pay(cost, "record_load"):
                continue
            bit = cell.pending.pop(side)
            cell.memories[side] = memory.write(bit, self.config.memory, proper,
                self.config.bath_modes, self.config.bath_coupling, self.config.detuning)

    def boot(self, cell, event):
        if cell.active:
            return
        cell.active, cell.started_at = True, self.now
        self.request_supply(cell, event)
        for offset, kind in [(0,"read"),(1,"produce"),(2,"retire"),
                             (3,"repair"),(4,"correct"),(5,"transfer")]:
            t = self.lines[cell.identity].after(self.now, self.config.read_wait+offset)
            self.schedule(t, cell.identity, kind, {}, cell.identity+":"+kind, phase=1,
                          parents=(event["id"],))

    def dispatch(self, e):
        kind, owner, data = e["kind"], e["owner"], e["data"]
        cfg = self.config
        if kind == "source_off":
            self.source_alive[owner] = False
            return
        if kind == "source_emit":
            if self.source_alive[owner]:
                self.send(owner, "N0", "record_arrive", data, e["id"]+":delivery",
                          delay=cfg.record_delay, parent=e["id"])
            return
        if kind == "supply_request":
            if e["id"] in self.supply_requests:
                raise ValueError("duplicate supply request")
            self.supply_requests.add(e["id"])
            # Same-recipient ties have a declared canonical local order in pop_event.
            issued = {k: min(self.donor[k], data[k]) for k in ("fuel", "precursor")}
            for k in issued:
                self.donor[k] -= issued[k]
            packet_id = e["id"]+":cargo"
            self.in_transit[packet_id] = dict(issued, apparatus=[])
            self.send("donor", data["target"], "supply_arrive",
                      dict(packet=packet_id, reserved={k:data[k] for k in issued}),
                      packet_id, speed=.5, delay=cfg.supply_delay, parent=e["id"])
            return
        cell = self.cells[owner]
        if kind == "boot":
            self.boot(cell, e)
        elif kind == "supply_arrive":
            packet = self.in_transit.pop(data["packet"])
            cell.reserved_fuel -= data["reserved"]["fuel"]
            cell.reserved_precursor -= data["reserved"]["precursor"]
            cell.fuel += packet["fuel"]
            cell.precursor += packet["precursor"]
            self.maybe_write(cell)
        elif kind == "record_arrive":
            # A repeat cannot silently erase/replace an existing physical record.
            if data["side"] not in cell.memories and data["side"] not in cell.pending:
                cell.pending[data["side"]] = data["bit"]
            self.maybe_write(cell)
        elif kind == "offspring_arrive":
            packet = self.in_transit.pop(data["packet"])
            cell.apparatus.extend(packet["apparatus"])
            cell.pending.update(packet["records"])
            self.boot(cell, e)
            self.maybe_write(cell)
        elif kind == "read":
            if cfg.erase_record:
                self.environment_records.extend(copy.deepcopy(list(cell.memories.values())))
                cell.memories.clear()
                cell.pending.clear()
            if cfg.reader_enabled and cell.apparatus:
                proper = self.now / self.lines[owner].gamma
                for side in ("A", "B"):
                    if side not in cell.memories or len(cell.decoded) >= cfg.working_slots:
                        continue
                    if not cell.pay(1, "record_read"):
                        continue
                    value, quality, post = memory.read(cell.memories[side], proper,
                        uniform(self.seed, cell.generation, side, "read"), cfg.classical_survival)
                    cell.memories[side] = post
                    cell.last_read_quality[side] = quality
                    if value is not None:
                        cell.decoded[side] = value
        elif kind == "produce":
            produce(cell, cfg.production)
        elif kind == "retire":
            if cfg.retire_inherited:
                retire_inherited(cell)
        elif kind == "repair":
            if not cfg.repair_contacts:
                withhold(cell, 1, 1)
            elif (not cell.contact and cfg.address_enabled and cell.precursor >= 1
                  and can_repair(cell, True) and cell.pay(1, "contact_repair")):
                cell.precursor -= 1
                cell.contact_material += 1
                self.schedule(self.lines[owner].after(self.now, .5), owner, "contact_ready", {},
                              e["id"]+":done", parents=(e["id"],))
        elif kind == "contact_ready":
            cell.contact = True
            cell.contact_origin = "local_paid_rule_from_record"
        elif kind == "correct":
            correct(cell, cfg.corrector)
        elif kind == "transfer":
            if cell.address is None or cell.health < 8 or not cell.contact:
                return
            if cell.decoded != {"A":1,"B":1} or not cell.pay(1, "transfer"):
                return
            moved = []
            if cfg.transfer_apparatus and len(cell.apparatus) >= 2:
                moved.append(cell.apparatus.pop())
            records = dict(cell.decoded)
            if cfg.scramble_child:
                records["B"] ^= 1
            packet_id = e["id"]+":packet"
            self.in_transit[packet_id] = dict(fuel=0, precursor=0, apparatus=moved, records=records)
            self.send(owner, cell.address, "offspring_arrive", dict(packet=packet_id),
                      packet_id, speed=.5, parent=e["id"])
            cell.transmitted = True
        else:
            raise ValueError("unknown local instrument: "+kind)

    def pop_event(self):
        earliest = min(e["t"] for e in self.queue)
        # Reverse only owners at exactly the same coordinate time. Local order is invariant.
        owners = sorted({e["owner"] for e in self.queue if e["t"] == earliest},
                        reverse=self.config.scheduler_reverse)
        candidates = [e for e in self.queue if e["t"] == earliest and e["owner"] == owners[0]]
        event = min(candidates, key=lambda e:(e["phase"], e["id"]))
        self.queue.remove(event)
        return event

    def step(self):
        if self.processed >= self.config.max_events:
            raise RuntimeError("declared event limit reached")
        e = self.pop_event()
        self.now = e["t"]
        self.events_seen.add(e["id"])
        self.dispatch(e)
        self.processed += 1
        self.audit()
        cell = self.cells.get(e["owner"])
        self.log.append(dict(kind="event", event=copy.deepcopy(e),
            local=None if cell is None else cell.local_view(), totals=self.totals()))

    def run(self, stop_after=None):
        while self.queue and (stop_after is None or self.processed < stop_after):
            self.step()
        return self.result()

    def result(self):
        cells = [self.cells[f"N{i}"] for i in range(self.config.generations)]
        profiles = [dict(node=c.identity, active=c.active, function=int(c.health>=8),
             health=c.health, transmitted=c.transmitted, decoded=dict(c.decoded),
             own_apparatus=sum(a["made_by"] == c.identity for a in c.apparatus),
             inherited_apparatus=sum(a["made_by"] != c.identity for a in c.apparatus),
             contact=c.contact, contact_origin=c.contact_origin,
             spent_fuel=c.spent_fuel, remaining_fuel=c.fuel, precursor=c.precursor,
             unavailable_fuel=c.unavailable_fuel, unavailable_material=c.unavailable_material,
             material_waste=c.material_waste, costs=dict(c.costs),
             read_quality=copy.deepcopy(c.last_read_quality), failures=list(c.failures)) for c in cells]
        prefix = 0
        for p in profiles:
            if not p["function"]:
                break
            prefix += 1
        return dict(profile=profiles, parent_function=profiles[0]["function"],
                    child_function=profiles[1]["function"] if len(profiles)>1 else None,
                    final_function=profiles[-1]["function"],
                    consecutive_functional=prefix,
                    mean_health=sum(p["health"] for p in profiles)/len(profiles),
                    total_spent_fuel=sum(p["spent_fuel"] for p in profiles),
                    all_functional=all(p["function"] for p in profiles),
                    finished=not self.queue, pending_events=len(self.queue),
                    material_and_credit_balance=self.totals(), initial_totals=self.initial_totals,
                    events=self.processed, model_time=self.now,
                    external_injections=0, geometric_substrate="given",
                    energy_balance_status="NOT_IMPLEMENTED: credits are not joules",
                    closure_verdict="FINITE_TRAJECTORY_ONLY")

    def snapshot(self):
        return dict(schema=1, config=asdict(self.config), seed=self.seed, now=self.now,
            queue=copy.deepcopy(self.queue), events_seen=sorted(self.events_seen),
            sequence=self.sequence, processed=self.processed,
            cells={k:v.to_dict() for k,v in self.cells.items()},
            lines={k:asdict(v) for k,v in self.lines.items()}, donor=dict(self.donor),
            in_transit=copy.deepcopy(self.in_transit), log=copy.deepcopy(self.log),
            environment_records=copy.deepcopy(self.environment_records),
            source_alive=dict(self.source_alive), supply_requests=sorted(self.supply_requests),
            initial_totals=dict(self.initial_totals))

    @classmethod
    def restore(cls, data):
        if data["schema"] != 1:
            raise ValueError("unsupported checkpoint")
        obj = cls.__new__(cls)
        obj.config = Config(**data["config"]).validate()
        for k in ("seed","now","sequence","processed","queue","donor","in_transit", "log",
                  "environment_records","source_alive","initial_totals"):
            setattr(obj, k, copy.deepcopy(data[k]))
        obj.cells = {k:Cell(**v) for k,v in data["cells"].items()}
        obj.lines = {k:Worldline(**v) for k,v in data["lines"].items()}
        obj.events_seen = set(data["events_seen"])
        obj.supply_requests = set(data["supply_requests"])
        obj.audit()
        return obj


def canonical_hash(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()
