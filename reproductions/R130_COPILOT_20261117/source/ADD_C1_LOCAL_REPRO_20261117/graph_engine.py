"""Independent explicit graph implementation with string name terms.

Edges connect a b-port (first endpoint) to an a-port (second endpoint).
Uses graph incidence and simultaneous boundary rewrites, never a ring scan.
"""
from dataclasses import dataclass
from functools import lru_cache


@lru_cache(None)
def pair_parts(name):
    if not name.startswith('('):
        return None
    depth = 0
    for i in range(1, len(name)-1):
        c = name[i]
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
        elif c == ',' and depth == 0:
            return name[1:i], name[i+1:-1]
    raise ValueError('malformed join name')


def project(name, side):
    pair = pair_parts(name)
    return pair[side == 'R'] if pair else side+name


def combine(a, b):
    if a.startswith('L') and b == 'R'+a[1:]:
        return a[1:]
    return '('+a+','+b+')'


@lru_cache(None)
def support(name):
    p = pair_parts(name)
    if p:
        return support(p[0])+support(p[1])
    i = 0
    while i < len(name) and name[i] in 'LR':
        i += 1
    atom = name[i:]
    if not atom.startswith('u') or not atom[1:].isdigit():
        raise ValueError('malformed atomic name')
    return ((atom, name[:i][::-1]),)


@dataclass
class Graph:
    states: dict
    edges: tuple


def make(w):
    return Graph({'u'+str(i): s for i, s in enumerate(w)},
                 tuple(('u'+str(i), 'u'+str((i+1) % len(w))) for i in range(len(w))))


def normalize(name):
    parts = pair_parts(name)
    if parts:
        return combine(normalize(parts[0]), normalize(parts[1]))
    if name.startswith(('L', 'R')):
        return project(normalize(name[1:]), name[0])
    return name


def validate(g):
    if not g.states or len(g.edges) != len(g.states):
        raise ValueError('empty graph or incorrect edge count')
    if any(type(s) is not int or s not in range(4) for s in g.states.values()):
        raise ValueError('invalid C1 state')
    outgoing, incoming = {}, {}
    for u, v in g.edges:
        if u not in g.states or v not in g.states or u in outgoing or v in incoming:
            raise ValueError('invalid incidence or reused port')
        outgoing[u], incoming[v] = v, u
    if outgoing.keys() != g.states.keys() or incoming.keys() != g.states.keys():
        raise ValueError('unused port')
    seen, u = set(), next(iter(g.states))
    while u not in seen:
        seen.add(u)
        u = outgoing[u]
    if seen != g.states.keys():
        raise ValueError('disconnected cycles')
    # Per-atom prefix trie proves disjointness of all finite descendant cones.
    tries = {}
    for name in g.states:
        if normalize(name) != name:
            raise ValueError('non-normal name')
        for atom, path in support(name):
            node = tries.setdefault(atom, {})
            for bit in path:
                if '$' in node:
                    raise ValueError('A1 ancestor overlap')
                node = node.setdefault(bit, {})
            if node:
                raise ValueError('A1 descendant overlap')
            node['$'] = True
    return True


def snapshot(g):
    return {'states': sorted([n, s] for n, s in g.states.items()),
            'edges_b_to_a': sorted([u, v] for u, v in g.edges)}


def q(g, version='A', inverse=False):
    out = {}
    mid = {}
    for u, v in g.edges:
        if version == 'A':
            name = combine(project(u, 'R'), project(v, 'L'))
            aa, bb = (u, v) if inverse else (v, u)
        elif version == 'P_ring':
            name = (combine(project(v, 'R'), project(u, 'L')) if inverse
                    else combine(project(u, 'R'), project(v, 'L')))
            aa, bb = u, v
        else:
            raise ValueError('no total operator for P_raw')
        mid[u, v] = name
        out[name] = (g.states[aa] & 1) + (g.states[bb] & 2)
    incoming = {v: u for u, v in g.edges}
    outgoing = {u: v for u, v in g.edges}
    es = []
    for vertex in g.states:
        before = mid[incoming[vertex], vertex]
        after = mid[vertex, outgoing[vertex]]
        es.append((before, after) if version == 'A' else (after, before))
    return Graph(out, tuple(es))


def flip(g):
    return Graph({n: (2*(s % 2)+s//2) for n, s in g.states.items()}, g.edges)


def interact(g):
    # Identify all disjoint rewrites from the input, then connect their boundaries.
    merges = [(u, v) for u, v in g.edges if u != v and g.states[u] == 1 and g.states[v] == 2]
    split = {n for n, s in g.states.items() if s == 3}
    used = set(split)
    for u, v in merges:
        if u in used or v in used:
            raise ValueError('overlapping rewrites')
        used.update((u, v))
    out = {n: s for n, s in g.states.items() if n not in used}
    portmap = {(n, p): (n, p) for n in out for p in ('a', 'b')}
    internal = []
    removed = set(merges)
    for n in split:
        nl, nr = project(n, 'L'), project(n, 'R')
        out[nl], out[nr] = 1, 2
        portmap[n, 'a'], portmap[n, 'b'] = (nl, 'a'), (nr, 'b')
        internal.append((nl, nr))
    for u, v in merges:
        name = combine(u, v)
        out[name] = 3
        portmap[u, 'a'], portmap[v, 'b'] = (name, 'a'), (name, 'b')
    es = list(internal)
    for u, v in g.edges:
        if (u, v) in removed:
            continue
        a, b = portmap[u, 'b'], portmap[v, 'a']
        if a[1] != 'b' or b[1] != 'a':
            raise ValueError('boundary port changed orientation')
        es.append((a[0], b[0]))
    return Graph(out, tuple(es))


def forward(g, version='A'):
    return q(interact(g), version)


def backward(g, version='A'):
    return interact(q(g, version, True))


def printed_shape(g):
    vertices = set()
    for u, v in g.edges:
        vertices.add(combine(project(u, 'R'), project(v, 'L')))
    es = set()
    for u in g.states:
        for x in g.states:
            for y in g.states:
                es.add((combine(project(u, 'R'), project(x, 'L')),
                        combine(project(y, 'R'), project(u, 'L'))))
    return {'vertices': sorted(vertices), 'edges_b_to_a': sorted(map(list, es)),
            'bits_status': 'UNBOUND_X_IN_PRINTED_CLAUSE'}
