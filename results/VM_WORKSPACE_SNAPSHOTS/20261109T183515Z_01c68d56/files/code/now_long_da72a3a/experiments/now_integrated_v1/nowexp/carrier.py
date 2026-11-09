"""Finite causal carriers for the existing NOW dispatcher.

The C2 word rule is the FIG2A_FULL operational rule recorded in R126. Payloads
are an explicit NOW extension: each unique object follows the b half through a
rewrite; a merge combines locations, never objects. No theorem about the
authors' named graphs, reversibility of payloads, or physical energy is assumed.
Prepared orders/CDT use supplied future links and supplied local clocks. Their
integer timestamps are preparation data, never MCMC time or emergent proper time.
"""
import copy
import heapq
import math
import json
from pathlib import Path


def full_step(word, interaction=True):
    """Return new word and old-node -> new-node payload map, without rotation.

    Bit order a1,b1,a2,b2. All payloads at a split follow its B child. The
    directed cyclic boundary is processed exactly like an internal edge.
    """
    word = list(word)
    n = len(word)
    if not n or any(type(s) is not int or not 0 <= s < 16 for s in word):
        raise ValueError('nonempty four-bit word required')
    merge = {i for i in range(n) if n > 1 and (word[i], word[(i+1) % n]) in ((1, 2), (4, 8))} if interaction else set()
    consumed = {(i+1) % n for i in merge}
    expanded, mapping = [], {}
    # If the seam is a merge, start at its left member, not its consumed right.
    start = n-1 if n-1 in merge else 0
    for j in range(n):
        i = (start+j) % n
        if i in consumed:
            continue
        if i in merge:
            mapping[i] = mapping[(i+1) % n] = len(expanded)
            expanded.append(word[i] | word[(i+1) % n])
        elif interaction and word[i] in (3, 12):
            expanded.extend((word[i] & 5, word[i] & 10))
            mapping[i] = len(expanded)-1
        else:
            mapping[i] = len(expanded)
            expanded.append(word[i])
    # Q: preserve edges, import a from successor, retain local b.
    out = [(expanded[(i+1) % len(expanded)] & 5) | (s & 10) for i, s in enumerate(expanded)]
    return out, mapping


def fixture(kind, owners, horizon=512):
    """Deterministic interface fixtures, NOT equilibrium Ising/CDT samples."""
    if kind in ('add_quiet', 'add_growing'):
        word = [0]*len(owners)
        if kind == 'add_quiet':
            word[-1] = 11  # C2 blocker, not the bits-only four-cycle fixture.
        else:
            word[0], word[2] = 1, 2
        return dict(kind='add_c2_full', id=kind, word=word,
                    anchors=dict(zip(owners, range(len(owners)))), horizon=horizon,
                    max_vertices=4096, interaction=True, evidence='conditional_interface_fixture')
    if kind not in ('ising_order', 'cdt_strip'):
        raise ValueError('unknown geometry fixture')
    events, links = [], []
    n = len(owners)
    for t in range(horizon+1):
        for i, owner in enumerate(owners):
            events.append(dict(id=f'{t}:{i}', t=t, owner=owner, tau=t,
                               coordinates=[t, i] if kind == 'ising_order' else None))
            if t:
                links.append([f'{t-1}:{i}', f'{t}:{i}'])
                for j in range(n):
                    connected = abs(i-j) == 1 if kind == 'ising_order' else j == (i+1) % n
                    if connected:
                        links.append([f'{t-1}:{i}', f'{t}:{j}'])
    return dict(kind='prepared_order', id=kind, family=kind, events=events, links=links,
                horizon=horizon, evidence='conditional_interface_fixture',
                measure='one frozen fixture; no equilibrium or j-star estimate',
                clock='given integer local clock',
                source_geometry=('two-dimensional product order u=t+x, v=t-x'
                                 if kind == 'ising_order' else 'unwrapped periodic spatial CDT strip'))


class Carrier:
    def __init__(self, spec, owners):
        self.spec = copy.deepcopy(spec)
        if 'prepared_id' in spec:
            bank = json.loads((Path(__file__).resolve().parents[1]/'preregistration/PREPARED_GEOMETRIES.json').read_text())
            self.spec = copy.deepcopy(bank['geometries'][spec['prepared_id']])
            self.spec['ensemble'] = copy.deepcopy(spec.get('ensemble'))
        if 'fixture' in spec:
            self.spec = fixture(spec['fixture'], owners, spec.get('horizon', 512))
            if 'interaction' in spec:
                self.spec['interaction'] = spec['interaction']
        self.beacon_pairs = {tuple(pair) for pair in self.spec.get('beacon_pairs', [(owners[i+1], owners[i]) for i in range(3, len(owners)-1)])}
        if any(len(pair) != 2 or any(o not in owners for o in pair) for pair in self.beacon_pairs):
            raise ValueError('beacon pair has unknown physical owner')
        self.kind = self.spec['kind']
        self.pending, self.trace = {}, []
        self.tick = 0
        self.tick_queued = False
        self.blocked = []
        self.horizon = self.spec['horizon']
        if type(self.horizon) is not int or not 1 <= self.horizon <= 4096:
            raise ValueError('finite geometry horizon required')
        if self.kind == 'add_c2_full':
            self.word = list(self.spec['word'])
            full_step(self.word, False)  # validate input only; no trajectory
            self.anchors = dict(self.spec['anchors'])
            if set(self.anchors) != set(owners) or any(type(i) is not int or not 0 <= i < len(self.word) for i in self.anchors.values()):
                raise ValueError('one valid anchor for every physical owner required')
            if not len(self.word) <= self.spec['max_vertices'] <= 4096:
                raise ValueError('finite carrier cap required')
            self.initial_particles = self.particles()
        elif self.kind == 'prepared_order':
            self.events = {e['id']: e for e in self.spec['events']}
            if len(self.events) != len(self.spec['events']) or len(self.events) > 65536:
                raise ValueError('duplicate events or oversized prepared geometry')
            self.next = {v: [] for v in self.events}
            self.worldlines = {o: [] for o in owners}
            for v, e in self.events.items():
                if (type(e['t']) is not int or not 0 <= e['t'] <= self.horizon
                        or e['owner'] not in self.worldlines or e.get('tau') != e['t']):
                    raise ValueError('this adapter requires declared unit local clocks and owned events')
                self.worldlines[e['owner']].append(v)
            for a, b in self.spec['links']:
                if a not in self.events or b not in self.events or self.events[a]['t'] >= self.events[b]['t']:
                    raise ValueError('link outside graph or not strictly future directed')
                self.next[a].append(b)
            for owner, line in self.worldlines.items():
                line.sort(key=lambda v: self.events[v]['t'])
                if [self.events[v]['t'] for v in line] != list(range(self.horizon+1)):
                    raise ValueError('complete bounded owner clock chain required: '+owner)
                if any(b not in self.next[a] for a, b in zip(line, line[1:])):
                    raise ValueError('owner worldline is not a causal chain')
        else:
            raise ValueError('unsupported geometry; C3/D tables are not silently substituted')

    def clock(self, t):
        t = math.ceil(t-1e-12)
        if not 0 <= t <= self.horizon:
            raise ValueError('declared geometry horizon exceeded; no clamping')
        return t

    def particles(self):
        return [sum((s >> b) & 1 for s in self.word) for b in range(4)]

    def advance(self, t):
        if self.kind != 'add_c2_full':
            return
        stop = self.clock(t)
        while self.tick < stop:
            word, mapping = full_step(self.word, self.spec.get('interaction', True))
            if len(word) > self.spec['max_vertices']:
                raise RuntimeError('carrier cap reached; trajectory is not completed')
            self.anchors = {k: mapping[v] for k, v in self.anchors.items()}
            for packet in self.pending.values():
                packet['node'] = mapping[packet['node']]
            self.word = word
            self.tick += 1
            if self.particles() != self.initial_particles:
                raise ArithmeticError('C2 particle imbalance')

    def path(self, src, dst, sent, speed):
        """Canonical route in GIVEN causal graph; not a learned local route.

        Material packets have one movement per two clock ticks, with explicit
        waiting edges. This is a discrete latency rule, not a derived metric.
        """
        begin = self.worldlines[src][self.clock(sent)]
        heap = [(self.events[begin]['t'], begin, self.events[begin]['t'], (begin,))]
        visited = set()
        period = math.ceil(1/speed)
        while heap:
            t, node, ready, path = heapq.heappop(heap)
            key = (node, ready)
            if key in visited:
                continue
            visited.add(key)
            if self.events[node]['owner'] == dst:
                return list(path)
            for nxt in sorted(self.next[node]):
                movement = self.events[node]['owner'] != self.events[nxt]['owner']
                if movement and t < ready:
                    continue
                nt = self.events[nxt]['t']
                nr = nt+period-1 if movement else max(ready, nt)
                heapq.heappush(heap, (nt, nxt, nr, path+(nxt,)))
        return None

    def send(self, engine, src, dst, kind, payload, identity, speed, delay, parent):
        if identity in self.pending or not 0 < speed <= 1 or delay < 0:
            raise ValueError('duplicate or invalid physical packet')
        packet = dict(src=src, dst=dst, kind=kind, payload=copy.deepcopy(payload),
                      id=identity, parent=parent, sent=engine.now, ready=self.clock(engine.now+delay),
                      period=math.ceil(1/speed))
        if self.kind == 'add_c2_full':
            self.advance(engine.now)
            packet['node'] = self.anchors[src]
            self.pending[identity] = packet
            self.queue_tick(engine)
        else:
            route = self.path(src, dst, engine.now+delay, speed)
            if route is None:
                self.blocked.append(dict(id=identity, reason='no_future_route', packet=packet))
                return
            packet.update(route=route, cursor=0)
            self.pending[identity] = packet
            # Route includes the source wait; actual ownership remains unique.
            engine.schedule(self.events[route[0]]['t'], '@carrier', 'carrier_hop',
                            dict(packet=identity), identity+':hop:0', phase=-10)

    def queue_tick(self, engine):
        if self.pending and not self.tick_queued:
            if self.tick >= self.horizon:
                raise RuntimeError('undelivered packets at finite carrier horizon')
            engine.schedule(max(self.tick+1, math.floor(engine.now)+1), '@carrier', 'carrier_tick', {},
                            'carrier:tick:'+str(max(self.tick+1, math.floor(engine.now)+1)), phase=-10)
            self.tick_queued = True

    def deliver(self, engine, identity):
        p = self.pending.pop(identity)
        engine.log.append(dict(kind='causal_channel', id=identity, src=p['src'], dst=p['dst'],
                               sent=p['sent'], received=engine.now, geometry=self.spec['id'],
                               clock='given geometry ticks', route=p.get('route')))
        engine.schedule(engine.now, p['dst'], p['kind'], p['payload'], identity,
                        parents=() if p['parent'] is None else (p['parent'],))

    def dispatch(self, engine, event):
        if event['kind'] == 'carrier_tick':
            self.tick_queued = False
            self.advance(engine.now)
            for identity in sorted(list(self.pending)):
                p = self.pending[identity]
                if engine.now < p['ready']:
                    continue
                if p['node'] != self.anchors[p['dst']]:
                    p['node'] = (p['node']+1) % len(self.word)
                    p['ready'] = engine.now+p['period']
                self.trace.append(dict(t=engine.now, packet=identity, node=p['node'], vertices=len(self.word)))
                if p['node'] == self.anchors[p['dst']]:
                    self.deliver(engine, identity)
            self.queue_tick(engine)
        elif event['kind'] == 'carrier_hop':
            identity = event['data']['packet']
            p = self.pending[identity]
            v = p['route'][p['cursor']]
            self.trace.append(dict(t=engine.now, packet=identity, event=v))
            if p['cursor'] == len(p['route'])-1:
                self.deliver(engine, identity)
            else:
                p['cursor'] += 1
                nxt = p['route'][p['cursor']]
                engine.schedule(self.events[nxt]['t'], '@carrier', 'carrier_hop', dict(packet=identity),
                                identity+':hop:'+str(p['cursor']), phase=-10)
        else:
            raise ValueError('unknown carrier event')

    def snapshot(self):
        return copy.deepcopy(dict(spec=self.spec, pending=self.pending, trace=self.trace,
                                  tick=self.tick, tick_queued=self.tick_queued, blocked=self.blocked,
                                  word=getattr(self, 'word', None), anchors=getattr(self, 'anchors', None)))

    @classmethod
    def restore(cls, data, owners):
        obj = cls(data['spec'], owners)
        for key in ('pending', 'trace', 'tick', 'tick_queued', 'blocked'):
            setattr(obj, key, copy.deepcopy(data[key]))
        if obj.kind == 'add_c2_full':
            obj.word, obj.anchors = copy.deepcopy(data['word']), dict(data['anchors'])
            if obj.particles() != obj.initial_particles:
                raise ValueError('corrupt carrier checkpoint')
        return obj

    def report(self):
        return dict(id=self.spec['id'], kind=self.kind, evidence=self.spec.get('evidence', 'supplied_geometry'),
                    clock='given unit local clock', pending=len(self.pending), blocked=len(self.blocked),
                    vertices=len(self.word) if self.kind == 'add_c2_full' else len(self.events),
                    particle_counts=self.particles() if self.kind == 'add_c2_full' else None,
                    payload_rule='unique object follows b half; no cloning',
                    physical_reverse='NOT_IMPLEMENTED', equilibrium_measure='NOT_ESTABLISHED')
