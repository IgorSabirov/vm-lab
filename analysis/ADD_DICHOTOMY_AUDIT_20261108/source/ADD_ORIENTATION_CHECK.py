#!/usr/bin/env python3
"""Orientation/dichotomy audit for the reconstructed ADD C2 ring backend.

Imports add_backend_smoke_v1.py from the same directory. This checks the
explicit half-shift construction and exhaustively tests the E0 -> no-merge
property on rings L=2,3,4. It is an audit of the reconstruction, not author code.
"""
from __future__ import annotations
import itertools
import json
import add_backend_smoke_v1 as m

SPLITS = ((1, 1, 0, 0), (0, 0, 1, 1))
MERGES = (
    ((1, 0, 0, 0), (0, 1, 0, 0)),
    ((0, 0, 1, 0), (0, 0, 0, 1)),
)


def motifs(g):
    split = [n for n, s in g.states.items() if s in SPLITS]
    merge = []
    for e in g.edges:
        u, v = m.directed_edge_nodes(e)
        if (g.states[u], g.states[v]) in MERGES:
            merge.append((u, v))
    return split, merge


def canonical_cycle_word(g):
    """Canonical cyclic word of vertex states along the directed cycle."""
    start = next(iter(g.states))
    order = []
    cur = start
    for _ in range(len(g.states)):
        order.append(g.states[cur])
        _, nxt = m.directed_edge_nodes(m.edge_from_port(g, m.Port(cur, "b")))
        cur = nxt
    rotations = [tuple(order[i:] + order[:i]) for i in range(len(order))]
    return min(rotations)


def run():
    # Disputed L=3 counterexample from the review.
    x0 = m.ring_graph([
        (1, 0, 0, 0),
        (0, 0, 0, 0),
        (0, 1, 0, 0),
    ])
    x1_pre = m.I2(x0)
    x1 = m.sqrt_tau(x1_pre)
    x0_split, x0_merge = motifs(x0)
    x1_split, x1_merge = motifs(x1)
    order = {n: i for i, n in enumerate(x1.states)}
    directed_edges = sorted(
        (order[u], order[v]) for u, v in (m.directed_edge_nodes(e) for e in x1.edges)
    )

    # Exhaust all states in E0 at each small cycle size.
    exhaustive = []
    for L in (2, 3, 4):
        e0 = bad_merge = active = quiet = 0
        for config in itertools.product(itertools.product((0, 1), repeat=4), repeat=L):
            g = m.ring_graph(config)
            s0, r0 = motifs(g)
            if s0 or r0:
                continue
            e0 += 1
            h = m.sqrt_tau(g)
            s1, r1 = motifs(h)
            bad_merge += bool(r1)
            if s1:
                active += 1
            else:
                quiet += 1
        exhaustive.append({
            "L": L,
            "E0_count": e0,
            "active_after_half_shift": active,
            "quiet_after_half_shift": quiet,
            "merge_after_half_shift_violations": bad_merge,
            "pass": bad_merge == 0 and active + quiet == e0,
        })

    # The stronger no-later-merge induction is checked on all E0 states at L=3.
    no_later_merge_bad = 0
    for config in itertools.product(itertools.product((0, 1), repeat=4), repeat=3):
        g = m.ring_graph(config)
        s0, r0 = motifs(g)
        if s0 or r0:
            continue
        for _ in range(4):
            g = m.f_sym(g)
            if motifs(g)[1]:
                no_later_merge_bad += 1
                break

    # On every E0 state at L=3, check the full-orbit structural induction:
    # no merges, split count never decreases, and each split contributes one
    # new vertex on the next f_sym step. Quiet states return after two steps
    # up to directed-cycle isomorphism.
    orbit_transitions = 0
    merge_orbit_violations = 0
    split_persistence_violations = 0
    size_increment_violations = 0
    quiet_period2_violations = 0
    quiet_initial_count = 0
    for config in itertools.product(itertools.product((0, 1), repeat=4), repeat=3):
        g = m.ring_graph(config)
        if any(motifs(g)):
            continue
        x0_word = canonical_cycle_word(g)
        x1 = m.f_sym(g)
        if len(motifs(x1)[0]) == 0:
            quiet_initial_count += 1
            x2 = m.f_sym(x1)
            if canonical_cycle_word(x2) != x0_word:
                quiet_period2_violations += 1
        cur = g
        for _ in range(7):
            split_before, merge_before = motifs(cur)
            nxt = m.f_sym(cur)
            split_after, merge_after = motifs(nxt)
            merge_orbit_violations += bool(merge_after)
            split_persistence_violations += (len(split_after) < len(split_before))
            size_increment_violations += (len(nxt.states) - len(cur.states) != len(split_before))
            cur = nxt
            orbit_transitions += 1

    # A non-E0 counterexample: merges can continue; no universal monotonicity.
    non_e0 = m.ring_graph([
        (1, 0, 0, 0),
        (0, 1, 0, 0),
        (0, 0, 0, 0),
    ])
    non_e0_trace = [{"t": 0, "L": len(non_e0.states), "motifs": list(map(len, motifs(non_e0)))}]
    for t in range(1, 5):
        non_e0 = m.f_sym(non_e0)
        non_e0_trace.append({"t": t, "L": len(non_e0.states), "motifs": list(map(len, motifs(non_e0)))})

    return {
        "status": "PASS" if (
            not x0_split and not x0_merge and m.graph_equal(x0, x1_pre)
            and len(x1.states) == 3 and not x1_merge
            and directed_edges == [(0, 2), (1, 0), (2, 1)]
            and all(row["pass"] for row in exhaustive)
            and no_later_merge_bad == 0
            and merge_orbit_violations == 0
            and split_persistence_violations == 0
            and size_increment_violations == 0
            and quiet_period2_violations == 0
        ) else "FAIL",
        "scope": "reconstructed C2 rules on one oriented two-port cycle; not author source code",
        "counterexample": {
            "initial_states": [[1,0,0,0],[0,0,0,0],[0,1,0,0]],
            "I2_is_identity": m.graph_equal(x0, x1_pre),
            "L_after_sqrt_tau": len(x1.states),
            "initial_split_merge_counts": [len(x0_split), len(x0_merge)],
            "after_half_shift_split_merge_counts": [len(x1_split), len(x1_merge)],
            "new_directed_edges_by_index": directed_edges,
            "orientation": "w_i -> w_(i-1)",
        },
        "E0_exhaustive": exhaustive,
        "E0_no_merge_through_four_f2_steps_at_L3": {
            "violations": no_later_merge_bad,
            "pass": no_later_merge_bad == 0,
        },
        "E0_full_orbit_checks_at_L3": {
            "transitions_checked": orbit_transitions,
            "quiet_initial_states": quiet_initial_count,
            "merge_violations": merge_orbit_violations,
            "split_persistence_violations": split_persistence_violations,
            "size_increment_not_equal_split_count": size_increment_violations,
            "quiet_period2_isomorphism_violations": quiet_period2_violations,
            "pass": not any((merge_orbit_violations, split_persistence_violations,
                              size_increment_violations, quiet_period2_violations)),
        },
        "non_E0_counterexample": {
            "initial_states": [[1,0,0,0],[0,1,0,0],[0,0,0,0]],
            "trace": non_e0_trace,
            "meaning": "outside E0, a merge motif may persist and further alter L; no global monotonicity follows",
        },
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
