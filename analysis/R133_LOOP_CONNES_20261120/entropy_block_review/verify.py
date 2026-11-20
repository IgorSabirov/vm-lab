"""Local algebra, named block endpoints and equilibrium entropies for the R133 review."""
import json
from pathlib import Path
from runpy import run_path

import mpmath as mp
import sympy as sp
from sympy.combinatorics.free_groups import free_group

HERE = Path(__file__).resolve().parent
engine = run_path(str(HERE.parents[1] / "ADD_NEIGHBOR_SYNTHESIS_20261117/verify.py"))
frame = run_path(str(HERE.parent / "frame_review/check_review.py"))
eps = (1, -1)


def label_checks():
    states = engine["named"](range(16))
    reversal = engine["word"](engine["r2"](states))
    low_only = engine["word"](engine["swap_bits"](states))
    assert set(low_only) == set(range(4))
    extended = tuple((s & 12) | low_only[s] for s in range(16))

    def dimensions(permutation):
        assert set(permutation) == set(range(16))
        assert all(permutation[t] == s for s, t in enumerate(permutation))
        fixed = sum(t == s for s, t in enumerate(permutation))
        pairs = (16 - fixed) // 2
        return [fixed + 4*pairs, fixed + pairs]

    assert dimensions(reversal) == [28, 10] and dimensions(extended) == [24, 12]
    return {"r2_algebra_and_commutant": dimensions(reversal),
            "low_swap_preserve_high_algebra_and_commutant": dimensions(extended),
            "engine_swap_bits_distinct_outputs_on_16": len(set(low_only))}


def term_size(term):
    if term[0] == "atom":
        return 1
    return 1 + sum(term_size(child) for child in term[1:])


def block_checks():
    left, right, join = (engine[k] for k in ("left", "right", "join"))
    initial = engine["named"]((1, 2, 12))
    a, b, c = (name for name, label in initial)
    _, x, y, z, h = free_group("x,y,z,h")
    start = tuple((name, label, link) for (name, label), link in zip(initial, (x, y, z)))

    def from_name(state, name):
        k = next(i for i, row in enumerate(state) if row[0] == name)
        return state[k:] + state[:k]

    def merge(state):
        first, second, *rest = from_name(state, a)
        assert second[0] == b
        return ((join(a, b), 3, first[2]*second[2]), *rest)

    def split(state):
        first, *rest = from_name(state, c)
        return ((left(c), 8, h), (right(c), 4, h**-1 * first[2]), *rest)

    def strip(state):
        return tuple((name, label) for name, label, link in state)

    target = ((join(a, b), 3, x*y), (left(c), 8, h), (right(c), 4, h**-1*z))
    for offset in range(len(start)):
        rotated = start[offset:] + start[:offset]
        for path in (split(merge(rotated)), merge(split(rotated))):
            assert from_name(path, join(a, b)) == target
    assert target[0][2]*target[1][2]*target[2][2] == x*y*z
    interact = lambda state: engine["interact"](state, eps)
    both = interact(initial)
    assert engine["equal"](both, strip(target))
    assert engine["equal"](engine["transport"](strip(target), 2), engine["forward"](initial, eps))
    assert engine["equal"](interact(both), initial)

    # Show representatives starting at A or at the newly joined vertex.
    def labels_from(state, name):
        return list(engine["word"](from_name(state, name)))

    paths = {"two_full_passes": labels_from(interact(both), a),
             "only_merge_then_full": labels_from(interact(strip(merge(start))), a),
             "only_split_then_full": labels_from(interact(strip(split(start))), join(a,b))}
    assert list(paths.values()) == [[1, 2, 12], [1, 2, 8, 4], [3, 12]]
    state = initial
    sizes = []
    for n in range(1, 25):
        state = engine["forward"](state, eps)
        name = next(u for u, s in state if s == 12)
        sizes.append(term_size(name))
        assert sizes[-1] == 2*n + 5
    return {"declared_endpoint": [[s, str(link)] for _, s, link in target],
            "cyclic_starts_checked": 3, "full_pass_controls": paths,
            "name_sizes_steps_1_3_24": [sizes[i] for i in (0, 2, 23)]}


def frame_checks():
    I, T = frame["I"], frame["T"]
    a, b = (3*I + 8*T[0])/5, (4*I + 6*T[1])/5
    before = sp.expand((T[2]*a*b)[0,1])
    inside = sp.expand((a*T[2]*b)[0,1])
    assert sp.expand((a*b * (b.H*T[2]*b))[0,1]) == inside
    assert before == -sp.Rational(8,25) + sp.I*9/50
    assert inside == sp.Rational(8,25) + sp.I*9/50
    return {"matrix_identities": frame["path_checks"](), "two_link_g12": list(map(str, (before, inside)))}


def fock(length, beta):
    terms = []
    for k in range(length):
        x = 2*beta*mp.sinpi(mp.mpf(k)/length)
        q = mp.exp(-x)
        terms.append(mp.log1p(q) + x*q/(1+q))
    return 2*mp.fsum(terms)


def entropy_checks():
    with mp.workdps(60):
        for beta in (mp.mpf("0.1"), 1, 4, 8, 32):
            values = [fock(length, beta) for length in range(1, 81)]
            assert all(a < b for a, b in zip(values, values[1:]))
        increments = [fock(n+1,32)-fock(n,32) for n in (2,3)]
        p3 = []
        for length in (4,5):
            energies = [16*mp.sinpi(mp.mpf(k)/length) for k in range(length) for _ in range(2)]
            p3.append(frame["control"]["entropy"](energies, 3))
        assert p3[1] < p3[0] and fock(5,8) > fock(4,8)
        return {"dps": 60, "adjacent_pairs_in_grid": 395,
                "fock_beta1_L7_L8": [mp.nstr(fock(n,1),16) for n in (7,8)],
                "fock_beta32_deltas_L2_L3": [mp.nstr(v,12) for v in increments],
                "fock_beta8_L4_L5": [mp.nstr(fock(n,8),15) for n in (4,5)],
                "fixed_p3_beta8_L4_L5": [mp.nstr(v,15) for v in p3]}


if __name__ == "__main__":
    print(json.dumps({"labels": label_checks(), "blocks": block_checks(),
                      "frames": frame_checks(), "entropy_nats": entropy_checks()}, indent=2))
