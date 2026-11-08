#!/usr/bin/env python3
"""ADD_BACKEND_SMOKE_V1

Standalone, standard-library-only reconstruction of the local graph operations
in Arrighi–Dowek–Durbec, arXiv:2306.07121v2, for a finite cyclic graph.

IMPORTANT SCOPE:
- This is an independent implementation reconstructed from the paper's text,
  equations and Fig. 7; it is not the authors' source code.
- It is an algebra/interface smoke test, not a reproduction of the paper's
  asymptotic proofs or a physical model of NOW.
- The optional repair object is an organizational overlay and is NOT part of
  the ADD reversible dynamics.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import random
import statistics
import sys
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Named graph objects (names are essential for exact reversibility).
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Name:
    tag: str
    x: object = None
    y: object = None


def base_name(i: object) -> Name:
    return Name("base", i, None)


def proj_left(n: Name) -> Name:
    return n.x if n.tag == "merge" else Name("left", n, None)


def proj_right(n: Name) -> Name:
    return n.y if n.tag == "merge" else Name("right", n, None)


def merge_name(x: Name, y: Name) -> Name:
    # The defining cancellation law (u.l) vee (u.r) = u.
    if x.tag == "left" and y.tag == "right" and x.x == y.x:
        return x.x
    return Name("merge", x, y)


@dataclass(frozen=True)
class Port:
    node: Name
    port: str  # "a" or "b"


def edge(p: Port, q: Port) -> Tuple[Port, Port]:
    """Canonical orientation: b-port endpoint first, a-port endpoint second."""
    if p.port == q.port:
        raise ValueError(f"an edge must join an a port to a b port: {p}, {q}")
    return (p, q) if p.port == "b" else (q, p)


@dataclass
class Graph:
    # State order is (a1, b1, a2, b2); C1 uses a2=b2=0.
    states: Dict[Name, Tuple[int, int, int, int]]
    edges: List[Tuple[Port, Port]]


def ring_graph(states: Sequence[Tuple[int, int, int, int]]) -> Graph:
    if not states:
        raise ValueError("a cyclic graph must have at least one vertex")
    names = [base_name(i) for i in range(len(states))]
    es = [edge(Port(names[i], "b"), Port(names[(i + 1) % len(names)], "a"))
          for i in range(len(names))]
    g = Graph(dict(zip(names, states)), es)
    validate_graph(g)
    return g


def edge_key(e: Tuple[Port, Port]) -> frozenset:
    return frozenset(e)


def validate_graph(g: Graph) -> None:
    if not g.states:
        raise ValueError("empty graph is not in the finite cyclic state space")
    expected = {Port(n, p) for n in g.states for p in ("a", "b")}
    seen = []
    if len(g.edges) != len(g.states):
        raise ValueError("a finite 2-port cycle must have |E|=|V|")
    for s in g.states.values():
        if len(s) != 4 or any(x not in (0, 1) for x in s):
            raise ValueError(f"invalid C2 node state: {s}")
    for e in g.edges:
        if len(e) != 2 or {e[0].port, e[1].port} != {"a", "b"}:
            raise ValueError(f"invalid edge: {e}")
        if e[0].port != "b" or e[1].port != "a":
            raise ValueError(f"edge is not in canonical b->a orientation: {e}")
        for p in e:
            if p.node not in g.states:
                raise ValueError(f"edge references absent node: {p.node}")
            seen.append(p)
    if len(seen) != len(expected) or len(set(seen)) != len(seen) or set(seen) != expected:
        raise ValueError("every a/b port must occur in exactly one edge")

    # Connectedness: this smoke is for one circular component, not a disjoint union.
    adj = {n: set() for n in g.states}
    for x, y in g.edges:
        adj[x.node].add(y.node)
        adj[y.node].add(x.node)
    start = next(iter(g.states))
    visited = {start}
    stack = [start]
    while stack:
        u = stack.pop()
        for v in adj[u]:
            if v not in visited:
                visited.add(v)
                stack.append(v)
    if visited != set(g.states):
        raise ValueError("graph has more than one connected component")


def mate_map(g: Graph) -> Dict[Port, Port]:
    out: Dict[Port, Port] = {}
    for x, y in g.edges:
        out[x] = y
        out[y] = x
    return out


def edge_from_port(g: Graph, p: Port) -> Tuple[Port, Port]:
    m = mate_map(g)
    if p not in m:
        raise ValueError(f"unmatched port: {p}")
    return edge(p, m[p])


def directed_edge_nodes(e: Tuple[Port, Port]) -> Tuple[Name, Name]:
    if e[0].port == "b" and e[1].port == "a":
        return e[0].node, e[1].node
    raise ValueError(f"edge must be canonical b->a: {e}")


def graph_equal(g: Graph, h: Graph) -> bool:
    return (g.states == h.states and
            {edge_key(e) for e in g.edges} == {edge_key(e) for e in h.edges})


def particle_counts(g: Graph) -> Tuple[int, int, int, int]:
    return tuple(sum(s[i] for s in g.states.values()) for i in range(4))  # type: ignore


def particle_total(g: Graph) -> int:
    return sum(particle_counts(g))


# ---------------------------------------------------------------------------
# Reversible half-shift sqrt(tau) and exact inverse.
# ---------------------------------------------------------------------------

def sqrt_tau(g: Graph) -> Graph:
    validate_graph(g)
    new_name_by_edge: Dict[Tuple[Name, Name], Name] = {}
    for e in g.edges:
        u, v = directed_edge_nodes(e)
        new_name_by_edge[(u, v)] = merge_name(proj_right(u), proj_left(v))

    new_states: Dict[Name, Tuple[int, int, int, int]] = {}
    for e in g.edges:
        u, v = directed_edge_nodes(e)
        w = new_name_by_edge[(u, v)]
        su, sv = g.states[u], g.states[v]
        new_states[w] = (su[0], sv[1], su[2], sv[3])

    new_edges = []
    for u in g.states:
        u_out, x = directed_edge_nodes(edge_from_port(g, Port(u, "b")))
        y, u_in = directed_edge_nodes(edge_from_port(g, Port(u, "a")))
        if u_out != u or u_in != u:
            raise AssertionError("cycle incidence reconstruction failed")
        no = new_name_by_edge[(u, x)]
        ni = new_name_by_edge[(y, u)]
        new_edges.append(edge(Port(no, "b"), Port(ni, "a")))

    out = Graph(new_states, new_edges)
    validate_graph(out)
    return out


def sqrt_tau_inverse(g: Graph) -> Graph:
    """Algebraic inverse of sqrt_tau, retaining exact named-vertex identities."""
    validate_graph(g)
    original_name_by_edge: Dict[Tuple[Name, Name], Name] = {}
    for e in g.edges:
        w, z = directed_edge_nodes(e)
        # If w=u.r vee x.l and z=y.r vee u.l, recover u.
        original_name_by_edge[(w, z)] = merge_name(proj_right(z), proj_left(w))

    new_states: Dict[Name, Tuple[int, int, int, int]] = {}
    for (w, z), u in original_name_by_edge.items():
        sw, sz = g.states[w], g.states[z]
        new_states[u] = (sw[0], sz[1], sw[2], sz[3])

    new_edges = []
    for w in g.states:
        _, z = directed_edge_nodes(edge_from_port(g, Port(w, "b")))
        y, _ = directed_edge_nodes(edge_from_port(g, Port(w, "a")))
        tail = original_name_by_edge[(w, z)]
        head = original_name_by_edge[(y, w)]
        new_edges.append(edge(Port(tail, "b"), Port(head, "a")))

    out = Graph(new_states, new_edges)
    validate_graph(out)
    return out


def port_time_flip(g: Graph) -> Graph:
    """T0 for sqrt(tau): swap a<->b and corresponding internal bits."""
    states = {n: (s[1], s[0], s[3], s[2]) for n, s in g.states.items()}
    edges = []
    for e in g.edges:
        x = Port(e[0].node, "a" if e[0].port == "b" else "b")
        y = Port(e[1].node, "a" if e[1].port == "b" else "b")
        edges.append(edge(x, y))
    out = Graph(states, edges)
    validate_graph(out)
    return out


# ---------------------------------------------------------------------------
# Involutive local collision/split step I2, from the two mirrored Fig. 7 rules.
# This is built as one simultaneous boundary-port rewrite; that matters when
# two redexes sit at adjacent vertices and share an old edge.
# ---------------------------------------------------------------------------

def I2(g: Graph) -> Graph:
    validate_graph(g)
    splits: Dict[Name, int] = {}
    for n, s in g.states.items():
        if s == (1, 1, 0, 0):
            splits[n] = 1
        elif s == (0, 0, 1, 1):
            splits[n] = 2

    merges: List[Tuple[Name, Name, int]] = []
    for e in g.edges:
        u, v = directed_edge_nodes(e)
        su, sv = g.states[u], g.states[v]
        if su == (1, 0, 0, 0) and sv == (0, 1, 0, 0):
            merges.append((u, v, 1))
        elif su == (0, 0, 1, 0) and sv == (0, 0, 0, 1):
            # Mirrored channel-2 pattern; the recovered parent order is v vee u.
            merges.append((u, v, 2))

    used = set(splits)
    merge_parent: Dict[Tuple[Name, Name, int], Name] = {}
    for u, v, channel in merges:
        if u in used or v in used:
            raise ValueError("overlapping I2 rewrite patterns; state is not admissible")
        used.update((u, v))
        parent = merge_name(u, v) if channel == 1 else merge_name(v, u)
        merge_parent[(u, v, channel)] = parent

    new_states = {n: s for n, s in g.states.items() if n not in used}
    boundary_map: Dict[Port, Port] = {}
    internal_edges: List[Tuple[Port, Port]] = []

    # Vertex splits.
    for n, channel in splits.items():
        nl, nr = proj_left(n), proj_right(n)
        if nl in new_states or nr in new_states or nl == nr:
            raise ValueError("I2 split would collide with an existing named vertex")
        if channel == 1:
            new_states[nl] = (1, 0, 0, 0)  # a1 particle on left child
            new_states[nr] = (0, 1, 0, 0)  # b1 particle on right child
            boundary_map[Port(n, "a")] = Port(nl, "a")
            boundary_map[Port(n, "b")] = Port(nr, "b")
            internal_edges.append(edge(Port(nl, "b"), Port(nr, "a")))
        else:
            # Mirror of channel 1 under R: old a goes to right, old b to left.
            new_states[nl] = (0, 0, 0, 1)  # b2 particle on left child
            new_states[nr] = (0, 0, 1, 0)  # a2 particle on right child
            boundary_map[Port(n, "a")] = Port(nr, "a")
            boundary_map[Port(n, "b")] = Port(nl, "b")
            internal_edges.append(edge(Port(nr, "b"), Port(nl, "a")))

    # Vertex merges.
    merge_edge_keys = set()
    for (u, v, channel), parent in merge_parent.items():
        new_states[parent] = (1, 1, 0, 0) if channel == 1 else (0, 0, 1, 1)
        boundary_map[Port(u, "a")] = Port(parent, "a")
        boundary_map[Port(v, "b")] = Port(parent, "b")
        merge_edge_keys.add(frozenset((Port(u, "b"), Port(v, "a"))))

    # Unchanged vertices keep their port identities.
    for n in g.states:
        if n not in used:
            boundary_map[Port(n, "a")] = Port(n, "a")
            boundary_map[Port(n, "b")] = Port(n, "b")

    # Apply all boundary substitutions simultaneously, then add split edges.
    new_edges = []
    for old_e in g.edges:
        if frozenset(old_e) in merge_edge_keys:
            continue
        try:
            new_edges.append(edge(boundary_map[old_e[0]], boundary_map[old_e[1]]))
        except KeyError as exc:
            raise AssertionError(f"unmapped boundary port in I2: {exc}") from exc
    new_edges.extend(internal_edges)

    out = Graph(new_states, new_edges)
    validate_graph(out)
    return out


def R_c2(g: Graph) -> Graph:
    """R: a1<->b2, a2<->b1, plus exchange of port labels a<->b."""
    states = {n: (s[3], s[2], s[1], s[0]) for n, s in g.states.items()}
    edges = []
    for e in g.edges:
        x = Port(e[0].node, "a" if e[0].port == "b" else "b")
        y = Port(e[1].node, "a" if e[1].port == "b" else "b")
        edges.append(edge(x, y))
    out = Graph(states, edges)
    validate_graph(out)
    return out


def f_main(g: Graph) -> Graph:
    # C1 restriction: second channel is empty and remains empty.
    if any(s[2] or s[3] for s in g.states.values()):
        raise ValueError("f_main is defined here only on the C1 subspace")
    return sqrt_tau(I2(g))


def f_main_inverse(g: Graph) -> Graph:
    if any(s[2] or s[3] for s in g.states.values()):
        raise ValueError("f_main_inverse is defined here only on the C1 subspace")
    return I2(sqrt_tau_inverse(g))


def f_sym(g: Graph) -> Graph:
    return sqrt_tau(I2(g))


def f_sym_inverse(g: Graph) -> Graph:
    return I2(sqrt_tau_inverse(g))


def T_sym(g: Graph) -> Graph:
    return I2(R_c2(g))


# ---------------------------------------------------------------------------
# Observables: count entropy, occupancy density, local motifs and graph paths.
# ---------------------------------------------------------------------------

def log_binomial(n: int, k: int) -> float:
    if not (0 <= k <= n):
        raise ValueError(f"invalid binomial arguments n={n}, k={k}")
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def entropy_c1(g: Graph) -> float:
    if any(s[2] or s[3] for s in g.states.values()):
        raise ValueError("C1 entropy requested for a C2 state")
    L = len(g.states)
    p = particle_total(g)
    return log_binomial(2 * L, p)


def entropy_c2_total_slots(g: Graph) -> float:
    """Coarse-grain by L and total p: log binomial(4L,p), not thermodynamic S."""
    L = len(g.states)
    p = particle_total(g)
    return log_binomial(4 * L, p)


def entropy_c2_species_resolved(g: Graph) -> float:
    """Alternative coarse-graining: preserve the four per-channel bit counts."""
    L = len(g.states)
    counts = particle_counts(g)
    return sum(log_binomial(L, p_i) for p_i in counts)


def graph_neighbors(g: Graph) -> Dict[Name, set]:
    adj = {n: set() for n in g.states}
    for x, y in g.edges:
        adj[x.node].add(y.node)
        adj[y.node].add(x.node)
    return adj


def graph_distance(g: Graph, source: Name, target: Name) -> Optional[int]:
    """Undirected spatial graph distance; deliberately NOT a causal-time predicate."""
    if source not in g.states or target not in g.states:
        return None
    if source == target:
        return 0
    adj = graph_neighbors(g)
    queue = [(source, 0)]
    seen = {source}
    for node, d in queue:
        for nxt in adj[node]:
            if nxt == target:
                return d + 1
            if nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, d + 1))
    return None


def radius_window(g: Graph, center: Name, radius: int) -> set:
    if radius < 0:
        raise ValueError("radius must be nonnegative")
    adj = graph_neighbors(g)
    dist = {center: 0}
    queue = [center]
    for node in queue:
        if dist[node] == radius:
            continue
        for nxt in adj[node]:
            if nxt not in dist:
                dist[nxt] = dist[node] + 1
                queue.append(nxt)
    return set(dist)


def local_observables(g: Graph, radius: int = 2) -> dict:
    L = len(g.states)
    p = particle_total(g)
    counts = particle_counts(g)
    windows = [radius_window(g, n, radius) for n in g.states]
    local_particle_density = statistics.mean(
        sum(sum(g.states[x]) for x in w) / len(w) for w in windows
    )
    local_slot_fraction = statistics.mean(
        sum(sum(g.states[x]) for x in w) / (4 * len(w)) for w in windows
    )

    split_motifs = sum(1 for s in g.states.values() if s in ((1, 1, 0, 0), (0, 0, 1, 1)))
    merge_motifs = 0
    for e in g.edges:
        u, v = directed_edge_nodes(e)
        su, sv = g.states[u], g.states[v]
        if ((su == (1, 0, 0, 0) and sv == (0, 1, 0, 0)) or
            (su == (0, 0, 1, 0) and sv == (0, 0, 0, 1))):
            merge_motifs += 1

    return {
        "L": L,
        "p_total": p,
        "p_by_bit": list(counts),
        "particle_density_per_vertex": p / L,
        "slot_occupancy_fraction": p / (4 * L),
        "mean_radius_window_particle_density": local_particle_density,
        "mean_radius_window_slot_fraction": local_slot_fraction,
        "active_split_patterns": split_motifs,
        "active_merge_patterns": merge_motifs,
        "active_local_rewrite_patterns": split_motifs + merge_motifs,
        "S_C2_total_slots": entropy_c2_total_slots(g),
        "S_C2_species_resolved": entropy_c2_species_resolved(g),
        "spatial_graph_connected": True,
        "causal_reachability": "NOT_DEFINED_BY_SPATIAL_GRAPH_ALONE",
    }


# ---------------------------------------------------------------------------
# Organizational overlay: local repair is not part of ADD's reversible law.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RepairEvent:
    event_id: str
    initiator: Name
    endpoints: Tuple[Name, Name]
    parent_event_ids: Tuple[str, ...]
    start_tick: int
    delay: int
    cost: float


def schedule_local_repair(g: Graph, event: RepairEvent, local_resource: float) -> dict:
    if event.initiator not in event.endpoints:
        raise ValueError("repair must be initiated by one of the local endpoints")
    if len(set(event.endpoints)) != 2:
        raise ValueError("repair must identify two distinct endpoints")
    if any(n not in g.states for n in event.endpoints):
        raise ValueError("repair endpoints must exist in the local graph")
    if graph_distance(g, event.endpoints[0], event.endpoints[1]) != 1:
        raise ValueError("repair endpoints must share a direct local channel")
    if not event.parent_event_ids:
        raise ValueError("repair needs at least one causal parent event")
    if event.start_tick < 0 or event.delay < 1:
        raise ValueError("repair requires nonnegative start and strictly positive delay")
    if event.cost <= 0 or local_resource < event.cost:
        raise ValueError("repair requires positive cost covered by local resource")
    return {
        "event_id": event.event_id,
        "initiator": repr(event.initiator),
        "endpoints": [repr(x) for x in event.endpoints],
        "parent_event_ids": list(event.parent_event_ids),
        "start_tick": event.start_tick,
        "completion_tick": event.start_tick + event.delay,
        "cost": event.cost,
        "local_resource_before": local_resource,
        "local_resource_after": local_resource - event.cost,
        "mutates_ADD_state": False,
        "status": "SCHEDULED_LOCAL_OVERLAY_EVENT",
    }


def create_carrier_from_waste(*_args, **_kwargs):
    raise NotImplementedError(
        "waste is not a free carrier; an explicit recycling mechanism and balance are required"
    )


def path_log_ratio(p_forward: Optional[float], p_reverse: Optional[float],
                   reverse_protocol_defined: bool) -> Optional[float]:
    """Return log(P_F/P_R); None means the reverse experiment is undefined."""
    if not reverse_protocol_defined or p_forward is None or p_reverse is None:
        return None
    if not (0.0 <= p_forward <= 1.0 and 0.0 <= p_reverse <= 1.0):
        raise ValueError("path probabilities must be in [0,1]")
    if p_forward == 0.0 and p_reverse == 0.0:
        return None  # the paired path is absent on both sides
    if p_reverse == 0.0:
        return math.inf  # valid, defined reverse ensemble has zero support here
    if p_forward == 0.0:
        return -math.inf
    return math.log(p_forward / p_reverse)


# ---------------------------------------------------------------------------
# Smoke tests.
# ---------------------------------------------------------------------------

def test_exhaustive_c1() -> dict:
    tested = 0
    for states in itertools.product(((0, 0, 0, 0), (1, 0, 0, 0),
                                     (0, 1, 0, 0), (1, 1, 0, 0)), repeat=3):
        g = ring_graph(states)
        if not graph_equal(f_main_inverse(f_main(g)), g):
            raise AssertionError(f"C1 main reversibility failed at {states}")
        before = particle_counts(g)
        if particle_counts(f_main(g)) != before:
            raise AssertionError("C1 particle conservation failed")
        tested += 1
    return {"status": "PASS", "states": tested, "ring_vertices": 3}


def test_exhaustive_c2() -> dict:
    tested = 0
    for states in itertools.product(itertools.product((0, 1), repeat=4), repeat=3):
        g = ring_graph(states)
        before = particle_counts(g)
        i2 = I2(g)
        if not graph_equal(I2(i2), g):
            raise AssertionError(f"I2 involution failed at {states}")
        r = R_c2(g)
        if not graph_equal(R_c2(r), g):
            raise AssertionError(f"R involution failed at {states}")
        if not graph_equal(I2(r), R_c2(i2)):
            raise AssertionError(f"I2R=RI2 failed at {states}")
        shifted = sqrt_tau(g)
        if not graph_equal(sqrt_tau_inverse(shifted), g):
            raise AssertionError(f"sqrt(tau) inverse failed at {states}")
        if not graph_equal(R_c2(sqrt_tau(R_c2(g))), sqrt_tau_inverse(g)):
            raise AssertionError(f"R sqrt(tau) R = sqrt(tau)^-1 failed at {states}")
        t = T_sym(g)
        if not graph_equal(T_sym(t), g):
            raise AssertionError(f"T^2=Id failed at {states}")
        if not graph_equal(T_sym(f_sym(T_sym(g))), f_sym_inverse(g)):
            raise AssertionError(f"T f_sym T = f_sym^-1 failed at {states}")
        if not graph_equal(f_sym_inverse(f_sym(g)), g):
            raise AssertionError(f"f_sym inverse composition failed at {states}")
        if particle_counts(i2) != before:
            raise AssertionError("I2 did not conserve bitwise particle counts")
        if particle_counts(shifted) != before:
            raise AssertionError("sqrt(tau) did not conserve bitwise particle counts")
        if particle_counts(f_sym(g)) != before:
            raise AssertionError("f_sym did not conserve bitwise particle counts")
        tested += 1
    return {
        "status": "PASS",
        "states": tested,
        "ring_vertices": 3,
        "checks": ["I2^2=Id", "R^2=Id", "I2R=RI2",
                   "sqrt(tau)^-1 sqrt(tau)=Id", "R sqrt(tau) R=sqrt(tau)^-1",
                   "T^2=Id", "T f_sym T=f_sym^-1", "four bit-counts conserved"],
    }


def find_main_not_time_symmetric_witness() -> dict:
    # Main C1 is reversible, but the paper says it is not time-symmetric.
    for states in itertools.product(((0, 0, 0, 0), (1, 0, 0, 0),
                                     (0, 1, 0, 0), (1, 1, 0, 0)), repeat=3):
        g = ring_graph(states)
        # In C1, T0 is the port time flip; compare T0 f T0 with f^-1.
        lhs = port_time_flip(f_main(port_time_flip(g)))
        rhs = f_main_inverse(g)
        if not graph_equal(lhs, rhs):
            return {"status": "PASS", "counterexample_found": True,
                    "initial_states": [list(x) for x in states],
                    "meaning": "finite witness that this C1 implementation is not time-symmetric"}
    return {"status": "UNRESOLVED", "counterexample_found": False}


def test_repair_and_reverse_contract() -> dict:
    g = ring_graph([(0, 0, 0, 0)] * 4)
    n0, n1 = list(g.states)[:2]
    ev = RepairEvent("repair-1", n0, (n0, n1), ("damage-0",), 4, 2, 3.0)
    successful = schedule_local_repair(g, ev, local_resource=5.0)
    if successful["completion_tick"] != 6 or successful["local_resource_after"] != 2.0:
        raise AssertionError("repair timing/resource accounting failed")

    rejected = {}
    try:
        schedule_local_repair(g, RepairEvent("remote", list(g.states)[2], (n0, n1),
                                              ("damage-0",), 4, 2, 1.0), 5.0)
    except ValueError:
        rejected["remote_initiator"] = True
    try:
        schedule_local_repair(g, RepairEvent("instant", n0, (n0, n1),
                                              ("damage-0",), 4, 0, 1.0), 5.0)
    except ValueError:
        rejected["zero_delay"] = True
    try:
        schedule_local_repair(g, RepairEvent("unfunded", n0, (n0, n1),
                                              ("damage-0",), 4, 2, 6.0), 5.0)
    except ValueError:
        rejected["insufficient_local_resource"] = True
    try:
        schedule_local_repair(g, RepairEvent("nonlocal", n0, (n0, list(g.states)[2]),
                                              ("damage-0",), 4, 2, 1.0), 5.0)
    except ValueError:
        rejected["nonadjacent_endpoints"] = True
    try:
        schedule_local_repair(g, RepairEvent("free", n0, (n0, n1),
                                              ("damage-0",), 4, 2, 0.0), 5.0)
    except ValueError:
        rejected["zero_cost"] = True
    if len(rejected) != 5:
        raise AssertionError(f"repair negative controls incomplete: {rejected}")

    if path_log_ratio(0.2, None, reverse_protocol_defined=False) is not None:
        raise AssertionError("undefined reverse protocol must return undefined A")
    if path_log_ratio(0.2, 0.2, reverse_protocol_defined=True) != 0.0:
        raise AssertionError("paired exact preparation should give A=0")
    if not math.isinf(path_log_ratio(0.2, 0.0, reverse_protocol_defined=True) or 0.0):
        raise AssertionError("valid zero reverse support must be distinct from undefined")
    try:
        create_carrier_from_waste("waste")
    except NotImplementedError:
        waste_guard = True
    else:
        waste_guard = False
    if not waste_guard:
        raise AssertionError("waste-to-carrier must not be implicit")
    return {
        "status": "PASS",
        "repair_overlay": successful,
        "negative_controls": rejected,
        "reverse_protocol_undefined": "A_UNDEFINED (None), not infinity",
        "matched_forward_reverse_probability": "A=0",
        "valid_zero_reverse_support": "infinity only when reverse ensemble is defined",
        "waste_to_carrier": "BLOCKED without explicit recycling mechanism",
    }


def sample_trajectory(seed: int = 20261104, initial_vertices: int = 12,
                      steps: int = 24, bit_probability: float = 0.50,
                      radius: int = 2) -> dict:
    rng = random.Random(seed)
    states = [tuple(int(rng.random() < bit_probability) for _ in range(4))
              for _ in range(initial_vertices)]
    g = ring_graph(states)
    rows = []
    for t in range(steps + 1):
        obs = local_observables(g, radius=radius)
        rows.append({"t": t, **obs})
        if t < steps:
            before = particle_counts(g)
            g = f_sym(g)
            if particle_counts(g) != before:
                raise AssertionError("particle counts changed along sample trajectory")
    return {
        "seed": seed,
        "initial_vertices": initial_vertices,
        "steps": steps,
        "bit_probability": bit_probability,
        "window_radius": radius,
        "rows": rows,
        "interpretation": (
            "one finite trajectory of the reconstructed F2 rule; numerical illustration only, "
            "not evidence for the paper's asymptotic Theta(n) statement"
        ),
    }


def sample_ensemble(seed_start: int = 20261100, count: int = 8,
                    initial_vertices: int = 12, steps: int = 24,
                    bit_probability: float = 0.50) -> dict:
    """Small seeded ensemble; descriptive calibration, not an asymptotic test."""
    runs = []
    exemplar = None
    for seed in range(seed_start, seed_start + count):
        tr = sample_trajectory(seed=seed, initial_vertices=initial_vertices,
                               steps=steps, bit_probability=bit_probability)
        rows = tr["rows"]
        first, last = rows[0], rows[-1]
        runs.append({
            "seed": seed,
            "L_initial": first["L"],
            "L_final": last["L"],
            "delta_L": last["L"] - first["L"],
            "p_total": first["p_total"],
            "S_initial": first["S_C2_total_slots"],
            "S_final": last["S_C2_total_slots"],
            "local_density_initial": first["mean_radius_window_particle_density"],
            "local_density_final": last["mean_radius_window_particle_density"],
            "active_patterns_initial": first["active_local_rewrite_patterns"],
            "active_patterns_final": last["active_local_rewrite_patterns"],
        })
        if seed == 20261104:
            exemplar = tr
    deltas = [r["delta_L"] for r in runs]
    s_deltas = [r["S_final"] - r["S_initial"] for r in runs]
    rho_ratios = [
        (r["local_density_final"] / r["local_density_initial"]
         if r["local_density_initial"] > 0 else None) for r in runs
    ]
    valid_rho_ratios = [x for x in rho_ratios if x is not None]
    return {
        "seed_start": seed_start,
        "sample_count": count,
        "initial_vertices": initial_vertices,
        "steps": steps,
        "bit_probability": bit_probability,
        "trajectories_with_L_growth": sum(d > 0 for d in deltas),
        "median_delta_L": statistics.median(deltas),
        "min_L_final": min(r["L_final"] for r in runs),
        "max_L_final": max(r["L_final"] for r in runs),
        "median_delta_S_C2_total_slots": statistics.median(s_deltas),
        "median_local_density_ratio_final_over_initial": (
            statistics.median(valid_rho_ratios) if valid_rho_ratios else None
        ),
        "runs": runs,
        "exemplar_seed_20261104": exemplar,
        "interpretation": (
            "small finite seed ensemble from this independent reconstruction; "
            "not a genericity proof, not a Theta(n) estimate, and not a reproduction "
            "of the authors' numerical setup"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", default=None, help="optional path for JSON results")
    parser.add_argument("--skip-growth", action="store_true", help="skip illustrative trajectory")
    args = parser.parse_args()

    results = {
        "artifact": "ADD_BACKEND_SMOKE_V1",
        "implementation_status": "INDEPENDENT_RECONSTRUCTION_FROM_PAPER_TEXT_AND_FIGURE_7",
        "not_author_code": True,
        "not_NOW_integration": True,
        "tests": {
            "C1_reversibility_and_conservation": test_exhaustive_c1(),
            "C2_full_exhaustive_symmetry": test_exhaustive_c2(),
            "main_C1_not_time_symmetric": find_main_not_time_symmetric_witness(),
            "repair_reverse_resource_contract": test_repair_and_reverse_contract(),
        },
        "growth_demo": None if args.skip_growth else sample_ensemble(),
        "important_scope_limits": [
            "the spatial ring graph alone does not define a causal event order or delivery event",
            "the repair object is an external organizational overlay, not an ADD rule",
            "no thermodynamic energy/heat balance is defined",
        "organizational viability is not computed: no record-reader-writer apparatus is embedded",
        "no global topology rewrite operation is exposed",
            "waste recycling and carrier creation are not implemented",
            "C2 entropy is an explicit coarse-graining choice, not a unique thermodynamic entropy",
            "no asymptotic theorem is inferred from the finite sample trajectory",
        ],
    }
    rendered = json.dumps(results, ensure_ascii=False, indent=2)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            f.write(rendered + "\n")
    print(rendered)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FATAL: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
