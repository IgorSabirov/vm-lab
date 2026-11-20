"""Exact finite bimodule checks and a separate numerical Fock/entropy control."""
from functools import cache
from itertools import combinations_with_replacement, product
from math import exp, log, log1p, pi, sin

import numpy as np
from scipy.integrate import quad

DIMS = (1, 1, 1, 1, 2, 2, 2, 2, 2, 2)


def minimum_dimension():
    """Weighted edge cover of summands, with self-pairs allowed by order zero."""
    full = (1 << len(DIMS)) - 1
    edges = []
    for i, j in combinations_with_replacement(range(len(DIMS)), 2):
        cost = DIMS[i] * DIMS[j] * (1 if i == j else 2)
        edges.append(((1 << i) | (1 << j), cost))

    @cache
    def minimum(covered):
        if covered == full:
            return 0
        missing = full ^ covered
        first = missing & -missing
        return min(cost + minimum(covered | mask) for mask, cost in edges if mask & first)

    return minimum(0)


def comm(a, b):
    return a @ b - b @ a


def witness():
    # H_ij = Hom(C^d_j,C^d_i). J exchanges H_ij and H_ji by adjunction.
    # Two pairs share scalar block 0, two share 1. Assign opposite grades
    # to the first two blocks with right index 0, enabling a nonzero D.
    pairs = [(4, 0), (5, 0), (6, 1), (7, 1), (8, 2), (9, 3)]
    blocks = [(i, j, sign) for (i, j), sign in zip(pairs, (1, -1, 1, 1, 1, 1))]
    opposite = [(j, i, -sign) for i, j, sign in blocks]
    blocks.extend(opposite)
    basis = [(i, j, s, t) for i, j, _ in blocks for s in range(DIMS[i]) for t in range(DIMS[j])]
    index = {v: k for k, v in enumerate(basis)}
    n = len(basis)
    zero = np.zeros((n, n), dtype=int)
    flip = zero.copy()   # J = flip followed by complex conjugation
    for k, (i, j, s, t) in enumerate(basis):
        flip[index[j, i, t, s], k] = 1
    gamma = np.diag([sign for i, j, sign in blocks for _ in range(DIMS[i] * DIMS[j])])

    left = []
    for i, dim in enumerate(DIMS):
        for s, t in product(range(dim), repeat=2):
            unit = zero.copy()
            for k, (a, b, u, v) in enumerate(basis):
                if a == i and u == t:
                    unit[index[a, b, s, v], k] = 1
            assert np.any(unit)
            left.append(unit)
    # For real matrix units J L(b*) J^-1 = flip L(b)^T flip.
    right = [flip @ b.T @ flip for b in left]
    link = zero.copy()
    for s in range(2):
        link[index[5, 0, s, 0], index[4, 0, s, 0]] = 1
    link = link + link.T
    D = link + flip @ link @ flip
    identity = np.eye(n, dtype=int)
    assert len(left) == 28 and n == 24
    assert np.array_equal(flip @ flip, identity) and np.array_equal(gamma @ gamma, identity)
    assert not np.any(flip @ gamma + gamma @ flip)
    assert np.array_equal(D.T, D) and not np.any(comm(flip, D)) and not np.any(D @ gamma + gamma @ D)
    assert all(not np.any(comm(gamma, a)) for a in left)
    assert any(np.any(comm(D, a)) for a in left)
    for a, b in product(left, right):
        assert not np.any(comm(a, b)) and not np.any(comm(comm(D, a), b))
    return n, len(left) * len(right), int(np.count_nonzero(D))


def h(x):
    x = abs(x)
    t = exp(-x)
    return log1p(t) + x * t / (1 + t)


def entropy_control():
    def spectrum(length):
        return [sign * 2 * sin(pi * k / length) for k in range(length) for sign in (1, -1)]

    levels = spectrum(6)
    energies = [0.]
    for level in levels:
        energies += [energy + level for energy in energies]
    weights = np.exp(-np.array(energies))
    probabilities = weights / weights.sum()
    entropy = -float(probabilities @ np.log(probabilities))
    assert len(energies) == 4096 and abs(entropy - sum(map(h, levels))) < 1e-12
    density = 2 * quad(lambda x: h(2 * sin(pi*x)), 0, 1, epsabs=1e-13)[0]
    s8 = sum(map(h, spectrum(8)))
    return entropy, density, s8 / 8 - density


if __name__ == '__main__':
    minimum = minimum_dimension()
    assert minimum == 24
    print("minimum complex dimension for faithful order zero =", minimum)
    print("dimension, pairs of matrix units, nonzero entries of D =", witness())
    print("Fock entropy C6, limiting density at beta=1, S8/8 minus limit =", entropy_control())
