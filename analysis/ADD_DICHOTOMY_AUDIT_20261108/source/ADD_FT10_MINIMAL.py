#!/usr/bin/env python3
"""ADD_FT10_MINIMAL — assembled 2026-11-08, NOT EXECUTED.

Minimal R126 prerequisite, not a new NOW experiment or an attested ADD law.
Usage after review: python ADD_FT10_MINIMAL.py --run-minimal --json-out ft10.json
No external dependencies, imports of project files, downloads or VM access.

Provenance:
  IgorSabirov/vm-lab @ 107cca83c6369734c3d434e756a32377c249d89d
  analysis/FOUR_CANDIDATE_INTEGRATION_20261108/evidence/add_reconstruction/
  add_backend_smoke_v1.py, Git blob 16139da045cd14ea591b6f4938f598a2af49fb03
The graph/name/transport/I2 functions below are preserved from that source.
New code below them supplies only explicit layouts, A1 validation and a
bounded diagnostic harness. NO mirror/parity fix has been silently applied.

Primary specification: https://arxiv.org/html/2306.07121v2
Definition 4, Fig. 2, Definitions 8–9 in Appendix A.

Unresolved source-conformance issue:
  The literal incidence reading of Definition 4 is recorded separately from
  the independent full-edge, port-following tau reference. Matching the former
  is not certification of the latter. Report both; never repair a mismatch by
  ring isomorphism, index reversal or changing the reading on alternate ticks.
  Fig. 2 named fixture has NOT been transcribed, so its gate stays NOT_VERIFIED.

Internal tuples in inherited core are (a1,b1,a2,b2), NOT (a1,a2,b1,b2).
C1 inputs below have two bits; the adapter explicitly pads channel 2 with zero.
Name terms are a separate structure, already present in the inherited source.
I2's C1 restriction is checked here; the full C2 mirrored I2 table is outside
this minimal test. C3/D, growth, ensembles and NOW integration are excluded.

Inherited source description:
ADD_BACKEND_SMOKE_V1

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
# FT-10 harness. No functions in this section execute on import.
# ---------------------------------------------------------------------------

ASSEMBLY = {
    "artifact": "ADD_FT10_MINIMAL",
    "parent": "R126 / existing NOW_INTEGRATED_CONTINUATION_V1 prerequisite",
    "base_commit": "107cca83c6369734c3d434e756a32377c249d89d",
    "prepared_status": "ASSEMBLED_NOT_EXECUTED_NOT_ATTESTED",
    "core_layout": ["a1", "b1", "a2", "b2"],
    "C1_layout": ["a1", "b1"],
    "C2_external_layout": ["a1", "a2", "b1", "b2"],
    "scope": "two three-vertex C1 fixtures; one C2 transport fixture; finite name-law cases",
    "mirror_equals_Def4": "NOT_PROVEN",
    "ADD_source_conformance": "NOT_ATTESTED",
    "NOW_integration": "BLOCKED",
    "figure_2_named_fixture": "NOT_TRANSCRIBED_NOT_VERIFIED",
    "limits": {"max_vertices": 8, "max_name_nodes": 1000, "max_half_steps": 2},
}


def c1_state(a1: int, b1: int) -> tuple:
    if a1 not in (0, 1) or b1 not in (0, 1):
        raise ValueError("C1 consists of exactly two binary bits")
    return (a1, b1, 0, 0)


def c2_state(a1: int, a2: int, b1: int, b2: int) -> tuple:
    if any(x not in (0, 1) for x in (a1, a2, b1, b2)):
        raise ValueError("C2 consists of four binary bits")
    return (a1, b1, a2, b2)


def project(name: Name, word: str) -> Name:
    for letter in word:
        if letter not in "lr":
            raise ValueError("name projection alphabet is l,r")
        name = proj_left(name) if letter == "l" else proj_right(name)
    return name


def leaf_addresses(name: Name, suffix: str = "") -> list:
    """Expand a finite name into its root/path cylinders, respecting projections.

    Two cylinders overlap iff their roots agree and one path prefixes the other.
    Checking every pair, including pairs within one name, checks disjointness
    of descendant cones (A1) for these finite constructor-normalized terms.
    The suffix is a projection of the CURRENT name, not its underlying root.
    """
    if name.tag == "base":
        return [(name.x, suffix)]
    if name.tag in ("left", "right"):
        return leaf_addresses(name.x, ("l" if name.tag == "left" else "r") + suffix)
    if name.tag == "merge":
        if suffix:
            child = name.x if suffix[0] == "l" else name.y
            return leaf_addresses(child, suffix[1:])
        return leaf_addresses(name.x) + leaf_addresses(name.y)
    raise ValueError("unknown name constructor")


def name_size(name: Name) -> int:
    if name.tag == "base":
        return 1
    if name.tag in ("left", "right"):
        return 1 + name_size(name.x)
    return 1 + name_size(name.x) + name_size(name.y)


def validate_A1(g: Graph) -> None:
    leaves = []
    for owner in g.states:
        for root, path in leaf_addresses(owner):
            for old_owner, old_root, old_path in leaves:
                if root == old_root and (path.startswith(old_path) or old_path.startswith(path)):
                    raise ValueError("A1 descendant cones intersect: "
                                     + repr((old_owner, owner, old_path, path)))
            leaves.append((owner, root, path))


def validate_minimal(g: Graph) -> None:
    if len(g.states) > ASSEMBLY["limits"]["max_vertices"]:
        raise ValueError("minimal graph size cap exceeded")
    if sum(name_size(n) for n in g.states) > ASSEMBLY["limits"]["max_name_nodes"]:
        raise ValueError("minimal name-term cap exceeded")
    validate_graph(g)
    validate_A1(g)


def name_text(n: Name) -> str:
    if n.tag == "base":
        return str(n.x)
    if n.tag in ("left", "right"):
        return "(" + name_text(n.x) + ")." + ("l" if n.tag == "left" else "r")
    return "(" + name_text(n.x) + " vee " + name_text(n.y) + ")"


def snapshot(g: Graph) -> dict:
    validate_minimal(g)
    return {
        "states_a1_b1_a2_b2": {name_text(n): list(s) for n, s in g.states.items()},
        "edges_b_to_a": sorted([[name_text(e[0].node), name_text(e[1].node)]
                                  for e in g.edges]),
        "particle_counts": list(particle_counts(g)),
    }


def def4_literal_reference(g: Graph) -> Graph:
    """Separate direct incidence evaluator; NOT an independently attested law.

    Construct w_(u,v)=u.r vee v.l. For each old vertex connect the new vertex
    of its b-incident edge at port b to that of its a-incident edge at port a.
    Preserve this literal reading so a conflict with Fig. 2/tau remains visible.
    Does not call sqrt_tau, directed_edge_nodes, edge_from_port or mate_map.
    """
    validate_minimal(g)
    incidence = {}
    out_states = {}
    for p, q in g.edges:
        b, a = (p, q) if p.port == "b" else (q, p)
        w = merge_name(proj_right(b.node), proj_left(a.node))
        if w in out_states:
            raise ValueError("new vertex name collision")
        sb, sa = g.states[b.node], g.states[a.node]
        out_states[w] = (sb[0], sa[1], sb[2], sa[3])
        incidence[(b.node, "b")] = w
        incidence[(a.node, "a")] = w
    out_edges = [(Port(incidence[(u, "b")], "b"),
                  Port(incidence[(u, "a")], "a")) for u in g.states]
    out = Graph(out_states, out_edges)
    validate_minimal(out)
    return out


def tau_port_reference(g: Graph) -> Graph:
    """Independent full transport: follow occupied port once; keep names/edges.

    This encodes the prose 'moves all particles along their corresponding port'.
    It shares no transport table or coordinate map with sqrt_tau. If the named
    comparison fails, do not substitute a ring isomorphism or a parity rule.
    """
    validate_minimal(g)
    slots = {n: [0, 0, 0, 0] for n in g.states}
    for source, s in g.states.items():
        for channel in (0, 1):
            for offset, port in ((0, "a"), (1, "b")):
                i = 2 * channel + offset
                ends = [q if p == Port(source, port) else p
                        for p, q in g.edges
                        if p == Port(source, port) or q == Port(source, port)]
                if len(ends) != 1:
                    raise ValueError("reference requires one edge per port")
                slots[ends[0].node][i] = s[i]
    out = Graph({n: tuple(s) for n, s in slots.items()}, list(g.edges))
    validate_minimal(out)
    return out


def tagged_locations(g: Graph, channel: int = 1) -> dict:
    """Unique a/b particle identities are read from distinct occupied slots."""
    a_index, b_index = 2 * (channel - 1), 2 * (channel - 1) + 1
    return {tag: [{"name": name_text(n), "port": port}
                  for n, s in g.states.items() if s[index]]
            for tag, port, index in (("A", "a", a_index), ("B", "b", b_index))}


def name_contract() -> dict:
    u, v = base_name("u"), base_name("v")
    cases = (u, proj_left(u), merge_name(u, v),
             merge_name(proj_right(u), proj_left(v)))
    laws = {
        "merge_left_projection": all(proj_left(merge_name(x, v)) == x for x in cases),
        "merge_right_projection": all(proj_right(merge_name(u, x)) == x for x in cases),
        "empty_projection": all(project(x, "") == x for x in cases),
        "child_merge_cancellation": all(merge_name(proj_left(x), proj_right(x)) == x
                                        for x in cases),
        "ordered_merge": merge_name(u, v) != merge_name(v, u),
    }
    # Both cross-vertex collisions and internal self-overlap must be rejected.
    invalid = ((u, proj_left(u)),
               (merge_name(u, v), merge_name(v, base_name("w"))),
               (merge_name(u, u),))
    rejected = []
    for names in invalid:
        try:
            validate_A1(Graph({n: c1_state(0, 0) for n in names}, []))
        except ValueError:
            rejected.append(True)
        else:
            rejected.append(False)
    laws["A1_negative_controls"] = all(rejected)
    validate_A1(Graph({proj_left(u): c1_state(0, 0),
                      proj_right(u): c1_state(0, 0), v: c1_state(0, 0)}, []))
    return {"status": "PASS" if all(laws.values()) else "FAIL",
            "finite_cases_only": True, "laws": laws}


def transport_contract(g: Graph, channel: int = 1) -> dict:
    validate_minimal(g)
    first = sqrt_tau(g)
    second = sqrt_tau(first)
    literal = def4_literal_reference(g)
    expected = tau_port_reference(g)
    stages = (g, first, second)
    for stage in stages:
        validate_minimal(stage)
    checks = {
        "first_equals_literal_Def4_reading": graph_equal(first, literal),
        "second_equals_literal_Def4_reading": graph_equal(second, def4_literal_reference(first)),
        "sqrt_inverse_exact_names": graph_equal(sqrt_tau_inverse(first), g),
        "bit_counts": all(particle_counts(x) == particle_counts(g) for x in stages),
        "two_halves_equal_port_tau_exact_names": graph_equal(second, expected),
        "tagged_worldlines_equal_port_tau": tagged_locations(second, channel)
                                              == tagged_locations(expected, channel),
    }
    return {"status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks,
            "trace": [snapshot(x) for x in stages],
            "worldlines": [tagged_locations(x, channel) for x in stages],
            "independent_tau": snapshot(expected),
            "independent_tau_tags": tagged_locations(expected, channel),
            "scope": "literal Definition 4 reading and port tau are separate constraints"}


def minimal_run() -> dict:
    # A double occupancy supplies the two oppositely oriented tagged particles.
    # I followed immediately by I is an operator-level split/remerge test;
    # it is NOT described as an orbit of the composed sqrt_tau I law.
    initial = ring_graph([c1_state(1, 1), c1_state(0, 0), c1_state(0, 0)])
    split = I2(initial)
    remerged = I2(split)
    for g in (initial, split, remerged):
        validate_minimal(g)
    parent = base_name(0)
    split_checks = {
        "left_child_state": split.states.get(proj_left(parent)) == c1_state(1, 0),
        "right_child_state": split.states.get(proj_right(parent)) == c1_state(0, 1),
        "internal_b_to_a_edge": frozenset((Port(proj_left(parent), "b"),
                                           Port(proj_right(parent), "a")))
                                   in {frozenset(e) for e in split.edges},
        "I_squared_exact_names_edges_states": graph_equal(remerged, initial),
        "particle_counts": particle_counts(initial) == particle_counts(split),
    }
    # Separate pre-existing adjacent names must merge in the declared order.
    adjacent = ring_graph([c1_state(1, 0), c1_state(0, 1), c1_state(0, 0)])
    merged = I2(adjacent)
    validate_minimal(merged)
    split_checks["unrelated_name_merge"] = merged.states.get(
        merge_name(base_name(0), base_name(1))) == c1_state(1, 1)
    split_checks["unrelated_name_merge_inverse"] = graph_equal(I2(merged), adjacent)
    tests = {
        "FT10A_layouts": {"status": "PASS" if (
            c1_state(1, 0) == (1, 0, 0, 0) and
            c2_state(1, 1, 0, 0) == (1, 0, 1, 0)) else "FAIL"},
        "FT10B_name_algebra": name_contract(),
        "FT10C_C1_split_merge": {
            "status": "PASS" if all(split_checks.values()) else "FAIL",
            "checks": split_checks,
            "trace_I_then_I": [snapshot(g) for g in (initial, split, remerged)],
            "trace_unrelated_merge": [snapshot(adjacent), snapshot(merged)],
            "scope": "I2 restricted to C1, not full mirrored C2 table"},
        "FT10D_C1_on_initial": transport_contract(initial),
        "FT10D_C1_after_split": transport_contract(split),
        "FT10D_C2_transport": transport_contract(ring_graph([
            c2_state(0, 1, 0, 0), c2_state(0, 0, 0, 1),
            c2_state(0, 0, 0, 0)]), channel=2),
    }
    return {"assembly": ASSEMBLY, "executed": True,
            "status": "PASS_FINITE_CONSTRAINTS_ONLY" if all(
                x["status"] == "PASS" for x in tests.values()) else "FAIL",
            "source_conformance": "NOT_ATTESTED",
            "NOW_integration": "BLOCKED", "tests": tests,
            "not_checked": ["Fig.2 exact named fixture", "full C2 I2 table",
                            "C3/D", "mirror reading equivalence", "general proof"]}


def main_minimal() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-minimal", action="store_true",
                        help="explicitly execute the bounded FT10 diagnostics")
    parser.add_argument("--json-out", help="write a report, only with --run-minimal")
    args = parser.parse_args()
    if not args.run_minimal:
        if args.json_out:
            parser.error("--json-out requires --run-minimal")
        print(json.dumps(ASSEMBLY, ensure_ascii=False, indent=2))
        return 0
    try:
        result = minimal_run()
    except Exception as exc:
        result = {"assembly": ASSEMBLY, "executed": True, "status": "ERROR",
                  "error": {"type": type(exc).__name__, "message": str(exc)},
                  "source_conformance": "NOT_ATTESTED", "NOW_integration": "BLOCKED"}
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as output:
            output.write(rendered + "\n")
    print(rendered)
    return 0 if result["status"] == "PASS_FINITE_CONSTRAINTS_ONLY" else 1


if __name__ == "__main__":
    raise SystemExit(main_minimal())



