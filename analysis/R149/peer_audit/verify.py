"""Exact finite checks for R149. Run from any directory with Python 3 and SymPy."""
import json
import sys
from collections import Counter
from itertools import product, groupby
from math import prod
from pathlib import Path

import sympy as sp

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "analysis/R141_R148_MODEL/code"))
from r130_reference import forward, named, word


def step_counts(states, channels):
    pairs = list(zip(states, states[1:] + states[:1]))
    splits = states.count(3)
    merges = pairs.count((1, 2))
    if channels == 2:
        splits += states.count(12)
        merges += pairs.count((8, 4))
    return splits, merges


def path(codes, steps, eps=(1,)):
    state = named(codes)
    lengths = [len(state)]
    events = []
    for _ in range(steps):
        split, merge = step_counts(word(state), len(eps))
        state = forward(state, eps)
        assert len(state) == lengths[-1] + split - merge
        lengths.append(len(state))
        events.append([split, merge])
    return lengths, events


def rotate(s, d):
    return s[d:] + s[:d]


def pattern_counts(w, offsets):
    return Counter(tuple(w[(i + j) % len(w)] for j in offsets) for i in range(len(w)))


def runs(w):
    v = rotate(w, w.index('0'))
    return sorted(len(list(g)) for b, g in groupby(v) if b == '1')


def mask_matrix(w):
    n = len(w)
    mask = sp.diag(*map(int, w))
    shift = sp.zeros(n)
    for i in range(n):
        shift[i, (i + 1) % n] = 1
    b = mask * (shift - sp.eye(n)) * mask
    return b * b.T


def pair_audit(words, order, steps, first, predicted_z, final_lengths):
    x, y = words
    n = len(x)
    assert n == len(y) and y not in {rotate(v,i) for v in (x,x[::-1]) for i in range(n)}
    for ds in product(range(n), repeat=order - 1):
        assert pattern_counts(x, (0, *ds)) == pattern_counts(y, (0, *ds))
    matrices = [mask_matrix(w) for w in words]
    determinants = [int((sp.eye(n) + k).det()) for k in matrices]
    assert determinants == predicted_z
    paths = [path([int(v) + 1 for v in w], steps) for w in words]
    lengths = [p[0] for p in paths]
    assert next(i for i in range(steps + 1) if lengths[0][i] != lengths[1][i]) == first
    assert [s[-1] for s in lengths] == final_lengths
    profiles = [runs(w) for w in words]
    assert determinants == [prod(int(sp.fibonacci(2*l+1)) for l in r) for r in profiles]
    return dict(words=words, active_runs=profiles, determinant=determinants,
                matched_order=order, matched_components=n**(order-1)*2**order,
                lengths=lengths, events_split_merge=[p[1] for p in paths], first_difference=first)


def geometry():
    small = ['000010001011', '000001010011']
    original = ['111111221212222222112121', '111112111121222221222212']
    base = [''.join(str(int(x)-1) for x in w) for w in original]
    lifted = [''.join(x+'0' for x in w) for w in base]
    result = dict(n12=pair_audit(small, 2, 2, 2, [20,20], [12,11]),
                  n24=pair_audit(base, 3, 2, 2, [24400,24208], [23,24]),
                  n48=pair_audit(lifted, 3, 8, 8, [4096,4096], [92,93]))
    result['n12']['ones_autocorrelation'] = [pattern_counts(small[0],(0,d))[('1','1')] for d in range(12)]
    result['n12']['triple_111_offsets_023'] = [pattern_counts(w,(0,2,3))[tuple('111')] for w in small]
    assert result['n12']['triple_111_offsets_023'] == [1,0]
    assert mask_matrix(small[0]).charpoly().all_coeffs() == mask_matrix(small[1]).charpoly().all_coeffs()
    for w in lifted:
        assert mask_matrix(w) == sp.diag(*map(int,w))
    result['n48']['pattern_1010_offsets_0246'] = [pattern_counts(w,(0,2,4,6))[tuple('1010')] for w in lifted]
    assert result['n48']['pattern_1010_offsets_0246'] == [2,1]
    return result


def means():
    words = ['010111', '011011']
    orbits = [sorted({rotate(w,d) for d in range(6)}) for w in words]
    def average(mats):
        return sum(mats, sp.zeros(6))/len(mats)
    matrices = [[mask_matrix(v) for v in o] for o in orbits]
    avgs = [average(a) for a in matrices]
    assert avgs[0] == avgs[1]
    value = (sp.eye(6) + avgs[0]).det()
    readings = [[(sp.eye(6) + k).det() for k in a] for a in matrices]
    assert readings == [[26]*6, [25]*3] and value == sp.Rational(39200,729)
    layer = sp.Rational(sum(map(sum, readings)),9)
    equal_orbits = sp.Rational(sum(a[0] for a in readings),2)
    assert layer == sp.Rational(77,3) and equal_orbits == sp.Rational(51,2)
    return dict(orbit_sizes=list(map(len,orbits)), orbit_readings=[26,25],
                uniform_labelled=str(layer), equal_orbits=str(equal_orbits), determinant_of_mean=str(value))


def bit_tests():
    eps = (1,-1)
    after = {s: len(forward(named(s),eps)) for s in product(range(16), repeat=3)}
    histogram = Counter()
    for (left, s, right), length in after.items():
        for bit in [1,2,4,8]:
            histogram[after[left,s^bit,right] - length] += 1
    assert histogram == {-2:64,-1:2176,0:11904,1:2176,2:64}
    def length(a,b):
        return after[a,b,0]
    adjacent = Counter(length(a^i,b^j)-length(a^i,b)-length(a,b^j)+length(a,b)
                       for a,b in product(range(16),repeat=2) for i,j in product([1,2,4,8],repeat=2))
    assert adjacent == {-1:64,0:3968,1:64}
    # Individual particles and the vacuum have constant length; track the four arms.
    trials = 0
    for n in range(3,25):
        for channel, (a,b) in enumerate([(1,2),(4,8)], start=1):
            single = [0]*n
            single[0] = a
            for x in ([0]*n,single,[b]+[0]*(n-1)):
                assert path(x,n,eps)[0] == [n]*(n+1)
            for r in range(n):
                s = [0]*n
                s[r] |= a
                s[0] |= b
                if channel == 1:
                    first, sign = (1,-1) if r == n-1 else (r+1,1)
                else:
                    first, sign = (1,1) if r == 0 else (r,-1)
                assert path(s,first,eps)[0] == [n]*first + [n+sign]
                trials += 1
    regimes = {}
    for codes in [(0,2,12),(1,2,12),(0,3,12),(0,2,13)]:
        lengths,events = path(codes,8,eps)
        regimes[str(codes)] = dict(lengths=lengths, events=events)
    assert regimes['(0, 2, 12)']['lengths'] == list(range(3,12))
    assert regimes['(1, 2, 12)']['events'] == [[1,1]]*8
    assert regimes['(0, 3, 12)']['lengths'] == [3]+list(range(5,13))
    assert regimes['(0, 2, 13)']['events'] == [[0,0]]*8
    return dict(single_flip=dict(sorted(histogram.items())), adjacent_mixed=dict(sorted(adjacent.items())),
                first_event_trials=trials, common_background_regimes=regimes)


def su3():
    variable = sp.symbols('x')
    trace, trace_bar = sp.symbols('T Tbar')
    polynomial = variable**3-trace*variable**2+trace_bar*variable-1
    delta = sp.discriminant(polynomial,variable)
    omega = (-1+sp.sqrt(3)*sp.I)/2
    roots = [1,omega,sp.conjugate(omega)]
    result = {}
    for key, eigs, expected in [('regular',[1,sp.I,-sp.I],2),('double',[-1,-1,1],4),('central',[1,1,1],8)]:
        T = sum(eigs)
        D = [sp.simplify(prod(322-z*l-sp.conjugate(z*l) for l in eigs).expand(complex=True)) for z in roots]
        M = sum(D)/3
        Y = sp.simplify(sum(sp.conjugate(z)*d for z,d in zip(roots,D))/3)
        assert sp.simplify(Y+103360*T+sp.conjugate(T)**2) == 0
        rotated = D[1:] + D[:1]
        rotated_mode = sum(sp.conjugate(z)*d for z,d in zip(roots,rotated))/3
        assert sp.simplify(rotated_mode-omega*Y) == 0
        disc = int(delta.subs({trace:T,trace_bar:sp.conjugate(T)}))
        dim = 2 if disc else (8 if abs(T)==3 else 4)
        H = sp.diag(*eigs)
        # Kernel of the commutator on all 3x3 matrices, with one traceless constraint.
        comm = sp.kronecker_product(H,sp.eye(3)) - sp.kronecker_product(sp.eye(3),H.T)
        assert dim == expected == 9-comm.rank()-1
        result[key] = dict(T=int(T), delta=disc, dim=dim, readings=list(map(int,D)), mean=int(M), Y=int(Y))
    assert result['regular']['mean'] == result['double']['mean']
    assert result['regular']['Y'] != result['double']['Y']
    return result


def passive_control():
    # Reversible two-bit system. q governs the action; m is an archived bit.
    def observed(m,q,rounds=4):
        actions=[]
        for _ in range(rounds):
            actions.append(q)
            q=1-q
        return actions
    states = list(product(range(2), repeat=2))
    for m,q in states:
        assert observed(m,q) == observed(1-m,q) != observed(m,1-q)
    return dict(states=len(states), horizon=4, length_of_state_cycle=2,
                change_archive_changes_actions=0, change_controller_changes_actions=4)


if __name__ == '__main__':
    output = dict(geometry=geometry(), preparations=means(), bits=bit_tests(), su3=su3(),
                  passive_memory_control=passive_control())
    print(json.dumps(output,indent=2,ensure_ascii=False))
