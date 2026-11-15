"""Exact finite checks accompanying the general algebra in REPORT.md.

Local budget forecast: <30 s; ceiling 600 s. No BBN integrations.
Names implement Definition 8 reductions, so dual-grid indexing is not discarded.
"""
import hashlib
import itertools
import json
import time
from fractions import Fraction
from pathlib import Path


def split(u, side):
    return u[1 if side == 'l' else 2] if u[0] == 'join' else ('split', u, side)


def join(u, v):
    if u[0] == v[0] == 'split' and u[1] == v[1] and (u[2], v[2]) == ('l', 'r'):
        return u[1]
    return ('join', u, v)


def graph(bits):
    return [(('atom', i), a, b) for i, (a, b) in enumerate(bits)]


def canonical(g):
    return (frozenset(g), frozenset((g[i][0], g[(i+1) % len(g)][0]) for i in range(len(g))))


def T(g):
    return [(u, b, a) for u, a, b in g]


def Q(g, printed=False):
    out = []
    for i, (u, a, b) in enumerate(g):
        v, aa, bb = g[(i+1) % len(g)]
        out.append((join(split(u, 'r'), split(v, 'l')), a if printed else aa, bb if printed else b))
    return out


def tau(g, inverse=False):
    d = -1 if inverse else 1
    return [(u, g[(i+d) % len(g)][1], g[(i-d) % len(g)][2]) for i, (u, a, b) in enumerate(g)]


def I(g):
    # The n=1 rule only. Rotate the list if a merger crosses its storage boundary.
    if g[-1][1:] == (1, 0) and g[0][1:] == (0, 1):
        g = g[-1:] + g[:-1]
    out, i = [], 0
    while i < len(g):
        u, a, b = g[i]
        if (a, b) == (1, 1):
            out.extend([(split(u, 'l'), 1, 0), (split(u, 'r'), 0, 1)])
        elif (a, b) == (1, 0) and i+1 < len(g) and g[i+1][1:] == (0, 1):
            out.append((join(u, g[i+1][0]), 1, 1))
            i += 1
        else:
            out.append(g[i])
        i += 1
    return out


def main():
    started = time.perf_counter()
    cases = 0
    for n, length in [(1, 3), (1, 4), (1, 5), (2, 3)]:
        alphabet = list(itertools.product(range(2**n), repeat=2))
        for bits in itertools.product(alphabet, repeat=length):
            x = graph(bits)
            checks = [
                (Q(Q(x)), tau(x)),
                (Q(Q(x, True), True), tau(x, True)),
                (Q(Q(x, True)), x),
                (Q(Q(x), True), x),
                (T(Q(T(x), True)), Q(x)),
                (T(Q(T(x))), Q(x, True)),
            ]
            for lhs, rhs in checks:
                assert canonical(lhs) == canonical(rhs), (n, length, bits)
            if n == 1:
                assert canonical(I(I(x))) == canonical(x), bits
            cases += 1

    x = graph([(1, 1), (0, 0), (0, 0), (0, 0)])
    tft = T(Q(I(T(x))))
    finverse = I(Q(x, True))
    assert (len(tft), len(finverse)) == (5, 4)
    assert canonical(tft) != canonical(finverse)
    y = graph([(1, 0), (0, 1), (0, 0), (0, 0)])
    macro_next = [len(Q(I(y))), len(Q(I(T(y))))]
    assert macro_next == [3, 4]

    def mm(a, b):
        return [[sum(x*y for x, y in zip(row, col)) for col in zip(*b)] for row in a]
    L, S, P = [[-1, 0], [1, 0]], [[0, 1], [1, 0]], [[1, 1]]
    assert mm(P, S) == P and mm(P, L) == [[0, 0]]
    sls, minus_l = mm(mm(S, L), S), [[-x for x in row] for row in L]
    assert sls != minus_l
    kappas = []
    for w in [Fraction(1, 2), Fraction(9, 10)]:
        a, b = w, 1-w
        kappas.append(str(2*a*b/(a*a+b*b)))
    assert kappas == ['1', '9/41']
    result = {
        'status': 'PASS_WITH_EXPLICIT_COUNTEREXAMPLES',
        'semantics': 'Corrected edges supplied by user; named cyclic graph; figure-consistent tau; n bits encoded by integers.',
        'finite_cases': cases,
        'six_half_shift_identities_per_case': True,
        'I_involution_n1_cases': 1344,
        'general_proof': 'REPORT.md#named-half-steps',
        'full_dynamics_counterexample': {'input_ab': ['11', '00', '00', '00'], 'TFT_vertex_count': len(tft), 'F_inverse_vertex_count': len(finverse)},
        'same_initial_vertex_and_particle_counts_different_next_size': {'input_ab': ['10', '01', '00', '00'], 'F_X_and_F_TX_sizes': macro_next},
        'sum_invariance_not_time_reversal': {'P': P, 'L_lambda_1': L, 'swap': S, 'SLS': sls, 'minus_L': minus_l},
        'kappa_counterexample': kappas,
        'budget': {'forecast_seconds_upper': 30, 'ceiling_seconds': 600, 'actual_seconds': time.perf_counter()-started, 'environment': 'local', 'vm_jobs': 0, 'bbn_integrations': 0},
        'code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    Path(__file__).with_name('CHECKS.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
