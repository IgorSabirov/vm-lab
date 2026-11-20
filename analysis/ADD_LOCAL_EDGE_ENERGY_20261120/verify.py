#!/usr/bin/env python3
"""Exact symbolic test of a directed local ADD edge-energy ansatz.

A ring word w has directed edges e_i=(w_i,w_{i+1}) in b->a order.
E(w)=sum_i eps[e_i] + sum_i eta[e_{i-1},e_i,e_{i+1}].
The eta term reads three consecutive directed edges (four consecutive
vertex labels). Coefficients remain symbolic: ADD supplies no measured
energy labels with which to fit them.
"""
from collections import Counter, defaultdict
from itertools import product
import json

A = "111111221212222222112121"
B = "111112111121222221222212"
TRI_A = "120"
TRI_B = "102"


def edges(word):
    w = tuple(map(int, word))
    return tuple((w[i], w[(i + 1) % len(w)]) for i in range(len(w)))


def feature_counts(word):
    e = edges(word)
    edge_counts = Counter(e)
    eta_counts = Counter((e[i - 1], e[i], e[(i + 1) % len(e)])
                         for i in range(len(e)))
    return edge_counts, eta_counts


def delta_counts(a, b):
    ea, ha = feature_counts(a)
    eb, hb = feature_counts(b)
    de = {k: ea[k] - eb[k] for k in sorted(set(ea) | set(eb)) if ea[k] != eb[k]}
    dh = {k: ha[k] - hb[k] for k in sorted(set(ha) | set(hb)) if ha[k] != hb[k]}
    return de, dh


def all_three_point_counts(word):
    w = tuple(map(int, word)); n = len(w)
    out = {}
    for d in range(n):
        for e in range(n):
            c = Counter((w[i], w[(i + d) % n], w[(i + d + e) % n])
                        for i in range(n))
            out[(d, e)] = tuple((x, c[x]) for x in product(range(3), repeat=3) if c[x])
    return out


def pair_key(word):
    w = tuple(map(int, word)); n = len(w)
    return tuple(tuple(sum((w[i], w[(i + d) % n]) == (a, b) for i in range(n))
                       for a in (1, 2) for b in (1, 2)) for d in range(n))


def n2121(word):
    w = tuple(map(int, word)); n = len(w)
    return sum(tuple(w[(i + j) % n] for j in range(4)) == (2, 1, 2, 1)
               for i in range(n))


def rotations_and_reflections(word):
    w = tuple(map(int, word)); n = len(w); r = w[::-1]
    return {w[i:] + w[:i] for i in range(n)} | {r[i:] + r[:i] for i in range(n)}


def generate_heldout_pair():
    """First lexicographic half-complement pair with equal pair data,
    differing N2121, and not in the dihedral orbit of the R131 pair.
    """
    groups = defaultdict(list)
    for half in product((1, 2), repeat=12):
        w = half + tuple(3 - x for x in half)
        groups[pair_key(w)].append(w)
    known_orbit = rotations_and_reflections(A) | rotations_and_reflections(B)
    for vals in groups.values():
        by_count = defaultdict(list)
        for w in vals:
            by_count[n2121(w)].append(w)
        if len(by_count) < 2:
            continue
        lo, hi = min(by_count), max(by_count)
        a = next((w for w in by_count[lo] if w not in known_orbit), None)
        b = next((w for w in by_count[hi] if w not in known_orbit), None)
        if a is not None and b is not None:
            return ''.join(map(str, a)), ''.join(map(str, b)), len(vals)
    raise RuntimeError('no held-out pair found')


def fmt_edge(e):
    return ''.join(map(str, e))


def fmt_eta(t):
    return '(' + ','.join(fmt_edge(e) for e in t) + ')'


def symbolic_delta(a, b):
    de, dh = delta_counts(a, b)
    terms = [f"({v:+d})*eps[{fmt_edge(k)}]" for k, v in de.items()]
    terms += [f"({v:+d})*eta[{fmt_eta(k)}]" for k, v in dh.items()]
    return ' + '.join(terms) if terms else '0'


def main():
    H1, H2, n_group = generate_heldout_pair()
    pairs = {
        'R131_vs_R132': (A, B),
        'three_node': (TRI_A, TRI_B),
        'heldout_24': (H1, H2),
    }
    result = {
        'status': 'PASS_SYMBOLIC_LOCAL_SEPARABILITY_NOT_PHYSICAL_ENERGY',
        'rule': 'E=sum_i eps[(s_i,s_i+1)] + sum_i eta[(e_i-1,e_i,e_i+1)]',
        'edge_type': 'ordered directed pair (s_i,s_i+1), ring orientation b->a',
        'eta_support': 'three consecutive directed edges = four consecutive vertex labels',
        'calibration_words': ['0', '12', '3'],
        'calibration_roles': ['inert/no-op state', 'merge redex 1->2', 'split parent state 3'],
        'calibration_warning': 'No independent energy labels exist; three words define calibration cases but cannot determine numeric eps/eta. Coefficients remain symbolic.',
        'pairs': {},
    }
    for name, (a, b) in pairs.items():
        de, dh = delta_counts(a, b)
        result['pairs'][name] = {
            'A': a, 'B': b,
            'edge_delta': {fmt_edge(k): v for k, v in de.items()},
            'eta_delta': {fmt_eta(k): v for k, v in dh.items()},
            'delta_E': symbolic_delta(a, b),
            'edge_counts_equal': not de,
            'eta_feature_vectors_differ': bool(dh),
            'all_three_point_counts_equal': all_three_point_counts(a) == all_three_point_counts(b),
            'N2121': [n2121(a), n2121(b)],
        }
    assert result['pairs']['R131_vs_R132']['edge_counts_equal']
    assert result['pairs']['R131_vs_R132']['all_three_point_counts_equal']
    assert result['pairs']['heldout_24']['edge_counts_equal']
    assert result['pairs']['heldout_24']['all_three_point_counts_equal']
    assert result['pairs']['three_node']['eta_feature_vectors_differ']
    assert result['pairs']['three_node']['delta_E'] != '0'
    assert H1 not in (rotations_and_reflections(A) | rotations_and_reflections(B))
    assert H2 not in (rotations_and_reflections(A) | rotations_and_reflections(B))
    result['heldout_generation'] = {
        'method': 'lexicographic enumeration of 12-bit halves h in {1,2}^12; form h||(3-h); group by all directed pair correlations; choose first group with differing N2121 outside R131/R132 dihedral orbits',
        'group_size': n_group,
        'not_dihedrally_equivalent_to_R131_pair': True,
    }
    result['interpretation'] = {
        'R131_R132': 'All directed edge counts cancel; only four-vertex local eta features distinguish. Any coefficient vector outside one exact hyperplane separates them.',
        'three_node': 'The same oriented local rule can distinguish; orientation-blind/reversal-symmetric coefficients may force equality and must be tested separately.',
        'heldout': 'The same frozen local feature family separates a new 24-node pair with identical all-shift three-point counts.',
        'physical_gate': 'NOT_PASSED: no independent energy labels, microscopic X degrees of freedom, coefficient derivation, kinetic law, or relaxation time.',
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
