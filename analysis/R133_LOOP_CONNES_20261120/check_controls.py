"""Verify the already specified scalar controls. No ADD-orbit or Dirac test."""
from itertools import combinations
import json

import mpmath as mp
import sympy as sp


I = sp.eye(2)
T = [sp.I * sigma / 2 for sigma in (
    sp.Matrix([[0, 1], [1, 0]]), sp.Matrix([[0, -sp.I], [sp.I, 0]]),
    sp.diag(1, -1))]
t = sp.Symbol("t", real=True)


def insertion(links, slot, gen):
    # Two-jet of right multiplication by exp(t gen), including scaled generators.
    result = I
    for index, link in enumerate(links):
        result = result * link
        if index == slot:
            result = result * (I + t * gen + t**2 * (gen * gen) / 2)
    return result


def derivative(probe, links, slot, gen, order):
    return sp.expand(probe(insertion(links, slot, gen))).coeff(t, order) * sp.factorial(order)


def casimirs(probe, links):
    return [-sum(derivative(probe, links, slot, gen, 2) for gen in T)
            for slot in range(len(links))]


def operator_controls():
    # Noncentral unit quaternions, exactly in SU(2).
    a = (I + 2 * sum(T, sp.zeros(2))) / 2
    b = (3 * I + 8 * T[0]) / 5
    c = (4 * I + 6 * T[1]) / 5
    assert all((g.H * g - I).applyfunc(sp.expand).is_zero_matrix and sp.expand(g.det()) == 1 for g in (a, b, c))
    probes = [lambda g: g.trace()/2, lambda g: (g.trace()/2)**2 + g[0, 0],
              lambda g: (g.trace()/2)**3]
    for f in probes:
        for gen in T:
            assert derivative(f, [a,b], 0, gen, 1) == derivative(f, [a*b], 0, b.H*gen*b, 1)
            assert derivative(f, [a,b], 1, gen, 1) == derivative(f, [a*b], 0, gen, 1)
        fine = casimirs(f, [a,b])
        single = casimirs(f, [a*b])[0]
        assert fine == [single, single]
        left, right, rest = casimirs(f, [a,b,c])
        coarse = sum(casimirs(f, [a*b,c]))
        assert (left + right)/2 + rest == coarse
    chi = probes[0]
    coarse = sum(casimirs(chi, [a*b,c]))
    naive = sum(casimirs(chi, [a,b,c]))
    assert naive/coarse == sp.Rational(3,2)
    assert sum(casimirs(chi, [a,b,c,a]))/2 == sum(casimirs(chi, [a*b,c*a]))
    probe = lambda g: g[0,1]
    link = 2*T[0]
    measured = derivative(probe, [I,link], 0, T[2], 1)
    proposed = derivative(probe, [link], 0, T[2], 1)  # Ad_I is identity
    assert (measured, proposed) == (-sp.S.Half, sp.S.Half)
    return {"mixed_naive_over_coarse_character": str(naive/coarse),
            "first_slot_true_vs_peer_nonclass": [str(measured), str(proposed)]}


def entropy(scaled, p):
    # Z[k] and B[k] sum the Boltzmann weight and (beta E) times that weight.
    z = [mp.mpf(1)] + [mp.mpf(0)] * p
    moment = [mp.mpf(0)] * (p+1)
    for u in scaled:
        weight = mp.exp(-u)
        for k in range(p, 0, -1):
            moment[k] += weight * (moment[k-1] + u*z[k-1])
            z[k] += weight*z[k-1]
    return mp.log(z[p]) + moment[p]/z[p]


def thermal_controls():
    mp.mp.dps = 40
    values = []
    for length, p, beta in [(4,3,8), (5,3,8), (100,2,mp.mpf(100)/8), (800,2,100)]:
        modes = [beta*2*mp.sin(mp.pi*k/length) for k in range(length) for _ in range(2)]
        s = entropy(modes, p)
        if length in (4, 5):
            energies = [sum(u) for u in combinations(modes, p)]
            z = sum(mp.exp(-u) for u in energies)
            assert abs(s-mp.log(z)-sum(u*mp.exp(-u) for u in energies)/z) < mp.mpf('1e-35')
        values.append(s)
    modes = [0, 0] + [mp.pi*k/4 for k in range(1,401) for _ in range(4)]
    values.append(entropy(modes, 2))
    expected = (1.41285634202, 1.40919968436, 4.50191999924, 4.49182348162, 4.49166701497)
    assert all(abs(s-e) < mp.mpf('6e-12') for s,e in zip(values,expected))
    return dict(zip(("L4", "L5", "L100", "L800", "limit_K400"),
                    (mp.nstr(s, 14) for s in values)))


if __name__ == "__main__":
    print(json.dumps({"scope": "known_controls_only", "operators": operator_controls(),
                      "entropy_nats": thermal_controls()}, indent=2))
