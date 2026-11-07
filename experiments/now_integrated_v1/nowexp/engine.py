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
from .local_instruments import produce, retire_inherited, can_repair, correct, withhold, capable, use


class BranchRequired(Exception):
    def __init__(self, address, options):
        self.address, self.options = address, options


class Engine:
    def __init__(self, config, seed, decisions=None):
        self.config = config.validate()
        self.seed = int(seed)
        self.decisions = decisions
        self.input_content = input_bits(seed, config.forced_content, config.preparation)
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
        self.source_registers = dict(zip(('MA','MB'),self.input_content))
        self.completion_events = []
        self.supply_requests = set()
        for g in range(config.generations):
            name = f"N{g}"
            # Every potential substrate and its location are GIVEN, not generated.
            self.lines[name] = Worldline(2*g, config.receiver_velocity if g else 0)
            self.cells[name] = Cell(name, g,
                fuel=4 if g == 0 else 0,
                address=f"N{g+1}" if g+1 < config.generations and config.address_enabled and config.successor_address_enabled else None,
                contact=config.imported_contacts,
                contact_origin="imported" if config.imported_contacts else "absent",
                contact_material=int(config.imported_contacts),
                unavailable_material=int(not config.imported_contacts))
        if config.initial_seed:
            self.cells["N0"].apparatus.append(Apparatus("seed:A", "preparation", -1, 1).__dict__)
        else:
            self.cells["N0"].unavailable_material += 1
        if config.separate_apparatus:
            root=self.cells['N0'];root.apparatus=[]
            for label,enabled,roles in (
                ('W',config.initial_seed and config.seed_writer,['write','catalyze']),
                ('R',config.initial_seed and config.seed_reader,['read','catalyze','repair','correct'])):
                if enabled:
                    apparatus=Apparatus('seed:'+label,'preparation',-1,1).__dict__
                    apparatus.update(roles=roles,functional_type='writer' if label=='W' else 'reader')
                    root.apparatus.append(apparatus)
                else:root.unavailable_material+=1
            if not config.initial_seed:root.unavailable_material-=1
            for cell in self.cells.values():cell.precursor_capacity=16
        if config.inherited_routes:
            for cell in self.cells.values():cell.address=None
            self.cells['N0'].route_template=[0,1]
            # Local ports are delivered by physical signals on the given substrate.
            radius=4.01 if config.branching else 2.01
            for src in self.cells:
                for dst in self.cells:
                    dx=self.lines[src].x(0)-self.lines[dst].x(0)
                    if src!=dst and 0<dx<=radius:
                        self.schedule(0,src,'beacon_emit',dict(target=dst),src+':beacon:'+dst)
        self.initial_totals = self.totals()
        if config.prepared_records:
            root=self.cells['N0']
            for side,bit in zip(('A','B'),self.input_content):
                root.pay(1,'prepared_record_cost')
                root.memories[side]=memory.write(bit,config.memory,0.,config.bath_modes,config.bath_coupling,config.detuning)
                root.memory_origins[side]='prepared:'+side
        self.schedule(0, "N0", "boot", {}, "boot:N0")
        for side, bit in zip(("A", "B"), self.input_content):
            owner = "M" + side
            self.schedule(0, owner, "source_emit", {"side": side, "bit": bit}, owner+":emit")
            if config.source_repeat:
                self.schedule(4, owner, "source_emit", {"side": side, "bit": bit}, owner+":repeat")
            self.schedule(5 if config.source_repeat else .1, owner, "source_off", {}, owner+":off")

    def schedule(self, t, owner, kind, data, identity, phase=0, parents=()):
        if not math.isfinite(t) or t < self.now - self.config.thresholds["causal_interval_tolerance"]:
            raise ValueError("event in past/nonfinite time")
        if identity in self.events_seen or any(e["id"] == identity for e in self.queue):
            raise ValueError("duplicate event ID")
        self.queue.append(dict(t=float(t), owner=owner, kind=kind, data=copy.deepcopy(data),
                               id=identity, phase=phase, parents=list(parents)))

    def send(self, src, dst, kind, payload, identity, speed=1.0, delay=0.0, parent=None):
        arrival = reception(self.lines[src], self.lines[dst], self.now, speed, delay,
                            self.config.thresholds["causal_interval_tolerance"])
        x0, x1 = self.lines[src].x(self.now), self.lines[dst].x(arrival)
        if speed*(arrival-self.now)+self.config.thresholds["causal_interval_tolerance"] < abs(x1-x0):
            raise ArithmeticError("delivery exceeds its declared carrier speed")
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
            if len(c.pending) > self.config.inbox_slots or len(c.memories) > self.config.record_slots:
                raise ArithmeticError("physical inbox/record bank exceeded")
            if sum(len(v) for v in c.fragments.values())>self.config.fragment_slots:
                raise ArithmeticError('fragment bank exceeded')

    def request_supply(self, cell, event):
        # Reserve receiver capacity before issuing a real message. No instant donor read.
        fuel = min(14, cell.fuel_capacity-cell.fuel-cell.reserved_fuel-cell.unavailable_fuel)
        precursor = min(10 if self.config.separate_apparatus else 4,
                        cell.precursor_capacity-cell.precursor-cell.reserved_precursor-cell.unavailable_material)
        cell.reserved_fuel += fuel
        cell.reserved_precursor += precursor
        self.send(cell.identity, "donor", "supply_request",
                  dict(target=cell.identity, fuel=fuel, precursor=precursor),
                  event["id"]+":request", parent=event["id"])

    def receive_record(self, cell, side, bit, event):
        if side in cell.pending or side in cell.memories:
            return
        if len(cell.pending) >= self.config.inbox_slots:
            cell.failures.append("inbox_capacity:"+side)
            return
        cell.pending[side] = bit
        cell.pending_origins[side] = event["id"]
        cell.pending_at[side] = self.now/self.lines[cell.identity].gamma
        self.schedule(self.lines[cell.identity].after(self.now, self.config.inbox_lifetime),
                      cell.identity, "pending_expire", {"side": side},
                      event["id"]+":expire:"+side, parents=(event["id"],))

    def maybe_write(self, cell, event):
        if not capable(cell, "write"):
            return
        proper = self.now / self.lines[cell.identity].gamma
        for side in ("A", "B"):
            if side not in cell.pending or side in cell.memories:
                continue
            if proper-cell.pending_at[side] > self.config.inbox_lifetime:
                cell.pending.pop(side)
                cell.failures.append("inbox_expired:"+side)
                continue
            if len(cell.memories) >= self.config.record_slots:
                cell.failures.append("record_capacity:"+side)
                continue
            # Classical orthogonal input; spent credit pays loading, not a thermodynamic theorem.
            cost = 2 if self.config.memory == "finite_dark" else 1
            if not cell.pay(cost, "record_load"):
                continue
            bit = cell.pending.pop(side)
            use(cell, "write")
            identity = event["id"]+":write:"+side
            cell.memory_origins[side] = identity
            self.log.append(dict(kind="instrument", id=identity, owner=cell.identity,
                t=self.now, operation="write", parents=sorted(set([event["id"], cell.pending_origins[side]])),
                cost=cost, output="memory:"+side))
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
            mode=cfg.completion_mode;before=self.source_registers[owner]
            if mode!='trace':self.source_alive[owner]=False
            if mode in ('erase','transfer','decay'):
                self.environment_records.append(dict(mode='classical_completion',operation=mode,
                    owner=owner,bit=before,accessible=mode=='transfer'))
                self.source_registers[owner]=0 if mode=='erase' else None
            self.completion_events.append(dict(owner=owner,operation=mode,t=self.now,
                interaction_stopped=not self.source_alive[owner],before=before,
                after=self.source_registers[owner],record_in_full_environment=mode in ('erase','transfer','decay')))
            return
        if kind=='beacon_emit':
            self.send(owner,data['target'],'beacon_arrive',dict(peer=owner),e['id']+':arrive',parent=e['id'])
            return
        if kind == "source_emit":
            if self.source_alive[owner]:
                if cfg.fragmented_records:
                    # Two shares are required; neither incomplete message enters the decoder.
                    mask=int(uniform(self.seed,0,data['side'],'fragment')>=.5)
                    for index,value in enumerate((mask,mask^data['bit'])):
                        if cfg.drop_fragment and index==1:continue
                        fragment=dict(side=data['side'],message=e['id'],index=index,value=value)
                        self.send(owner,'N0','fragment_arrive',fragment,e['id']+':fragment:'+str(index),
                                  delay=cfg.record_delay+index*.25,parent=e['id'])
                        if cfg.duplicate_fragment:
                            self.send(owner,'N0','fragment_arrive',fragment,e['id']+':duplicate:'+str(index),
                                      delay=cfg.record_delay+index*.25+.1,parent=e['id'])
                else:
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
        if kind=='beacon_arrive':
            cell.peer_beacons[data['peer']]=dict(received=self.now,event=e['id'])
        elif kind=='fragment_arrive':
            side=data['side']
            if side in cell.pending or side in cell.memories:return
            fragments=cell.fragments.setdefault(data['message'],{})
            index=str(data['index'])
            if index in fragments:
                if fragments[index]!=data['value']:cell.failures.append('conflicting_fragment')
                return
            if sum(len(v) for v in cell.fragments.values())>=cfg.fragment_slots:
                cell.failures.append('fragment_capacity');return
            fragments[index]=data['value']
            if set(fragments)=={'0','1'}:
                bit=fragments['0']^fragments['1'];cell.fragments.pop(data['message'])
                self.receive_record(cell,side,bit,e);self.maybe_write(cell,e)
        elif kind == "boot":
            self.boot(cell, e)
        elif kind == "pending_expire":
            if data["side"] in cell.pending:
                cell.pending.pop(data["side"])
                cell.failures.append("inbox_expired:"+data["side"])
        elif kind == "supply_arrive":
            packet = self.in_transit.pop(data["packet"])
            cell.reserved_fuel -= data["reserved"]["fuel"]
            cell.reserved_precursor -= data["reserved"]["precursor"]
            cell.fuel += packet["fuel"]
            cell.precursor += packet["precursor"]
            cell.delivery_times.append(dict(kind=kind, coordinate=self.now,
                                           proper=self.now/self.lines[owner].gamma))
            self.maybe_write(cell, e)
        elif kind == "record_arrive":
            # A repeat cannot silently erase/replace an existing physical record.
            self.receive_record(cell, data["side"], data["bit"], e)
            cell.delivery_times.append(dict(kind=kind, side=data["side"], coordinate=self.now,
                                           proper=self.now/self.lines[owner].gamma))
            self.maybe_write(cell, e)
        elif kind == "offspring_arrive":
            packet = self.in_transit.pop(data["packet"])
            cell.apparatus.extend(packet["apparatus"])
            if cfg.inherited_routes:cell.route_template=list(packet.get('route_template',[]))
            for side, bit in packet["records"].items():
                self.receive_record(cell, side, bit, e)
            self.boot(cell, e)
            cell.delivery_times.append(dict(kind=kind, coordinate=self.now,
                                           proper=self.now/self.lines[owner].gamma))
            self.maybe_write(cell, e)
        elif kind == "read":
            if cfg.damage_writer or cfg.damage_reader:
                damaged=[a for a in cell.apparatus if
                    (cfg.damage_writer and a.get('functional_type')=='writer') or
                    (cfg.damage_reader and a.get('functional_type')=='reader')]
                cell.apparatus=[a for a in cell.apparatus if a not in damaged]
                cell.material_waste+=sum(a['material_units'] for a in damaged)
            if cfg.erase_record:
                self.environment_records.extend(copy.deepcopy(list(cell.memories.values())))
                cell.memories.clear()
                cell.pending.clear()
            if cfg.reader_enabled and capable(cell, "read"):
                proper = self.now / self.lines[owner].gamma
                for side in ("A", "B"):
                    if side not in cell.memories or len(cell.decoded) >= cfg.working_slots:
                        continue
                    if cell.fuel < 1:
                        cell.failures.append("fuel:record_read")
                        continue
                    options = [x for x in memory.outcomes(cell.memories[side], proper,
                        cfg.classical_survival, cfg.thresholds["density_trace_tolerance"],
                        cfg.thresholds["psd_negative_tolerance"]) if x[1] > 0]
                    address = f"{cell.generation}:{side}:read"
                    if self.decisions is not None:
                        if len(options) > 1 and address not in self.decisions:
                            raise BranchRequired(address, [(i, x[1]) for i,x in enumerate(options)])
                        chosen = self.decisions.get(address, 0)
                    else:
                        draw, total, chosen = uniform(self.seed, cell.generation, side, "read"), 0., len(options)-1
                        for i, option in enumerate(options):
                            total += option[1]
                            if draw < total:
                                chosen = i
                                break
                    value, _, quality, post = options[chosen]
                    cell.pay(1, "record_read")
                    use(cell, "read")
                    e["parents"] = sorted(set(e["parents"]+[cell.memory_origins[side]]))
                    cell.memories[side] = post
                    cell.last_read_quality[side] = quality
                    if value is not None:
                        cell.decoded[side] = value
        elif kind == "produce":
            produce(cell, cfg.production, cfg)
        elif kind == "retire":
            if cfg.retire_inherited:
                retire_inherited(cell)
        elif kind == "repair":
            if not cfg.repair_contacts:
                if cfg.disabled_resource_policy == "matched":
                    withhold(cell, 1, 1)
            elif cfg.inherited_routes:
                if cfg.damage_route:cell.route_template=[]
                if cell.contact:return
                available=cell.apparatus
                if len(cell.route_template)!=2 or any(type(i)!=int or i<0 or i>=len(available) for i in cell.route_template):
                    cell.failures.append('missing_contact_template');return
                writer,reader=[available[i] for i in cell.route_template]
                if writer not in capable(cell,'write') or reader not in capable(cell,'read'):
                    cell.failures.append('template_ports_incompatible');return
                if cell.precursor<1 or not can_repair(cell,True,cfg) or not cell.pay(1,'contact_repair'):return
                use(cell,'repair');cell.precursor-=1;cell.contact_material+=1
                cell.contact_peers=[writer['identity'],reader['identity']]
                peers=sorted(cell.peer_beacons)
                if peers and not (cfg.branching and cell.generation>0):cell.address=peers[0]
                self.schedule(self.lines[owner].after(self.now,.5),owner,'contact_ready',{},e['id']+':done',parents=(e['id'],))
            elif (not cell.contact and cfg.address_enabled and cfg.contact_address_enabled and cell.precursor >= 1
                  and can_repair(cell, True, cfg) and cell.pay(1, "contact_repair")):
                use(cell, "repair")
                cell.precursor -= 1
                cell.contact_material += 1
                self.schedule(self.lines[owner].after(self.now, .5), owner, "contact_ready", {},
                              e["id"]+":done", parents=(e["id"],))
        elif kind == "contact_ready":
            cell.contact = True
            cell.contact_origin = "local_paid_rule_from_record"
        elif kind == "correct":
            correct(cell, cfg.corrector, cfg)
        elif kind == "transfer":
            if cell.address is None or cell.health < cfg.thresholds["function_health_at_least"] or not cell.contact:
                return
            if cell.decoded != cfg.required_content:
                return
            targets=sorted(cell.peer_beacons)[:2] if cfg.branching and cell.generation==0 else [cell.address]
            for target in targets:
                if not cell.pay(1,'transfer'):break
                moved=[]
                count=2 if cfg.separate_apparatus else 1
                if cfg.transfer_apparatus and len(cell.apparatus)>=2*count:
                    moved=cell.apparatus[-count:];del cell.apparatus[-count:]
                records=dict(cell.decoded)
                if cfg.scramble_child:records['B']^=1
                packet_id=e['id']+':packet'+(':'+target if cfg.branching else '')
                self.in_transit[packet_id]=dict(fuel=0,precursor=0,apparatus=moved,records=records,
                    route_template=list(cell.route_template) if cfg.transmit_route else [])
                self.send(owner,target,'offspring_arrive',dict(packet=packet_id),packet_id,speed=.5,parent=e['id'])
                cell.transmitted=True
                cell.transmitted_to.append(target)
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
        cell = self.cells.get(e["owner"])
        before = None if cell is None else cell.local_view()
        if cell is not None and cell.last_event is not None:
            e["parents"] = sorted(set(e["parents"]+[cell.last_event]))
        self.events_seen.add(e["id"])
        self.dispatch(e)
        self.processed += 1
        self.audit()
        if cell is not None:
            cell.last_event = e["id"]
        self.log.append(dict(kind="event", event=copy.deepcopy(e),
            before=before, local=None if cell is None else cell.local_view(), totals=self.totals()))

    def run(self, stop_after=None):
        while self.queue and (stop_after is None or self.processed < stop_after):
            self.step()
        return self.result()

    def result(self):
        cells = [self.cells[f"N{i}"] for i in range(self.config.generations)]
        profiles = [dict(node=c.identity, active=c.active, function=int(c.health>=self.config.thresholds["function_health_at_least"]),
             health=c.health, transmitted=c.transmitted, decoded=dict(c.decoded),
             own_apparatus=sum(a["made_by"] == c.identity for a in c.apparatus),
             inherited_apparatus=sum(a["made_by"] != c.identity for a in c.apparatus),
             contact=c.contact, contact_origin=c.contact_origin,
             spent_fuel=c.spent_fuel, remaining_fuel=c.fuel, precursor=c.precursor,
             unavailable_fuel=c.unavailable_fuel, unavailable_material=c.unavailable_material,
             material_waste=c.material_waste, costs=dict(c.costs),
             read_quality=copy.deepcopy(c.last_read_quality), failures=list(c.failures),
             delivery_times=copy.deepcopy(c.delivery_times), capability_uses=copy.deepcopy(c.capability_uses),
             decode_slots=self.config.working_slots, inbox_slots=self.config.inbox_slots,
             record_slots=self.config.record_slots, pending_records=len(c.pending), stored_records=len(c.memories)) for c in cells]
        for c,p in zip(cells,profiles):
            p.update(apparatus_types=[a.get('functional_type','shared') for a in c.apparatus],
                     route_template=list(c.route_template),contact_endpoints=list(c.contact_peers),
                     delivered_peers=sorted(c.peer_beacons),fragment_slots_used=sum(len(v) for v in c.fragments.values()),
                     transmitted_to=list(c.transmitted_to),
                     potential_children=([f'N{i}' for i in (1,2)] if c.generation==0 else []) if self.config.branching
                         else ([f'N{c.generation+1}'] if c.generation+1<self.config.generations else []))
        prefix = 0
        for p in profiles:
            if not p["function"]:
                break
            prefix += 1
        child = cells[1] if len(cells)>1 else None
        child_lateness = 0.
        if child is not None and child.started_at is not None:
            arrivals = [d["proper"] for d in child.delivery_times if d["kind"] == "supply_arrive"]
            if arrivals:
                child_lateness = max(0., max(arrivals)-child.started_at/self.lines[child.identity].gamma-self.config.read_wait)
        return dict(profile=profiles, input_content=self.input_content, child_supply_lateness=child_lateness,
                    parent_function=profiles[0]["function"],
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
                    mediator_completion=copy.deepcopy(self.completion_events),
                    source_registers=copy.deepcopy(self.source_registers),
                    energy_balance_status="NOT_IMPLEMENTED: credits are not joules",
                    closure_verdict="FINITE_TRAJECTORY_ONLY")

    def snapshot(self):
        return dict(schema=2, config=asdict(self.config), seed=self.seed, now=self.now,
            decisions=self.decisions, input_content=self.input_content,
            queue=copy.deepcopy(self.queue), events_seen=sorted(self.events_seen),
            sequence=self.sequence, processed=self.processed,
            cells={k:v.to_dict() for k,v in self.cells.items()},
            lines={k:asdict(v) for k,v in self.lines.items()}, donor=dict(self.donor),
            in_transit=copy.deepcopy(self.in_transit), log=copy.deepcopy(self.log),
            environment_records=copy.deepcopy(self.environment_records),
            source_registers=copy.deepcopy(self.source_registers),completion_events=copy.deepcopy(self.completion_events),
            source_alive=dict(self.source_alive), supply_requests=sorted(self.supply_requests),
            initial_totals=dict(self.initial_totals))

    @classmethod
    def restore(cls, data):
        if data["schema"] != 2:
            raise ValueError("unsupported checkpoint")
        obj = cls.__new__(cls)
        obj.config = Config(**data["config"]).validate()
        for k in ("seed","now","sequence","processed","queue","donor","in_transit", "log", "decisions", "input_content",
                  "environment_records","source_alive","initial_totals","source_registers","completion_events"):
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
