"""Independent controls for the ring, the Sol bundle and the two Bianchi channels."""
import json
from collections import Counter
from itertools import product
from math import gcd

import mpmath as mp
import sympy as sp


def ideal_count(word):
    active = [i for i, bit in enumerate(word) if bit]
    total = 0
    for bits in product([False, True], repeat=len(active)):
        chosen = {i for i, flag in zip(active, bits) if flag}
        edges = sum((i + 1) % len(word) in chosen for i in chosen)
        total += 2 ** edges
    return total


def ring(word, phase):
    size = len(word)
    shift = sp.zeros(size)
    for i in range(size - 1):
        shift[i, i + 1] = 1
    shift[size - 1, 0] = phase
    projector = sp.diag(*word)
    difference = projector * (shift - sp.eye(size)) * projector
    return sp.eye(size) + difference * difference.H


def ring_and_sol():
    A = sp.Matrix([[2, 1], [1, 1]])
    P = sp.Matrix([[1, -1], [0, 1]])
    energy = sp.symbols('E')
    transfer = sp.Matrix([[3 - energy, -1], [1, 0]])
    assert A * P == P * transfer.subs(energy, 0)
    counts = Counter()
    for size in range(3, 9):
        for word in product([0, 1], repeat=size):
            target = ideal_count(word)
            for phase in (1, sp.I, -1, (3 + 4*sp.I)/5):
                observed = ring(word, phase).det(method='domain-ge')
                correction = 2 * sp.re(phase) if all(word) else 0
                assert sp.simplify(observed - target + correction) == 0
                counts['dense_determinants'] += 1
            counts['words'] += 1

    for size in range(3, 13):
        for phase in (1, sp.I, -1):
            polynomial = ring([1]*size, phase).charpoly(energy).as_expr()
            expected = sp.trace(transfer**size) - 2 * sp.re(phase)
            assert sp.expand((-1)**size * polynomial - expected) == 0
            counts['whole_polynomial_checks'] += 1

    signs = {}
    for sign in (1, -1):
        matrix = A**6 - sign * sp.eye(2)
        first = gcd(*[int(x) for x in matrix])
        signs[str(sign)] = [first, abs(int(matrix.det())) // first]
    assert signs == {'1': [8, 40], '-1': [18, 18]}
    n = 6
    ell = 2*mp.log(mp.phi)
    base_modes = {str(t): str(+(2*mp.pi/ell)**2/(1+4*t)) for t in (0, 1, 5)}
    return {
        **counts, 'full_six': {label: int(ring([1]*n, z).det())
                              for label, z in [('periodic', 1), ('quarter', sp.I), ('antiperiodic', -1)]},
        'six_ideals': ideal_count([1]*6), 'six_smith_factors': signs,
        'Sol_base_mode_k1_at_b0_1': base_modes,
    }


def form_counts(cutoff, second):
    """Coefficients in a Euclidean square, used only on t >= 1 after reflection."""
    counts = Counter()
    for x, y in product(range(-cutoff, cutoff+1), repeat=2):
        norm = 2*x*x + 2*x*y + 3*y*y if second else x*x + 5*y*y
        if norm:
            counts[norm] += 1
    return counts


def lattice_pair(w, cutoff):
    counts = [form_counts(cutoff, second) for second in (False, True)]
    def integral_coeff(s, a):
        return mp.gammainc(s, a, mp.inf) / a**s

    # Each form has determinant 5. After rescaling, a quarter-turn identifies
    # the lattice with its dual; splitting the Mellin integral at 1 gives both terms.
    weights = {}
    for n in set(counts[0]) | set(counts[1]):
        a = mp.pi*n/mp.sqrt(5)
        weights[n] = integral_coeff(w, a) + integral_coeff(1-w, a)
    constant = 1/(w-1) - 1/w
    return [(constant + mp.fsum(m*weights[n] for n, m in row.items()))/2 for row in counts]


def lattice_channels(w, cutoff):
    lo, hi = lattice_pair(w-1, cutoff), lattice_pair(w, cutoff)
    return [(lo[0]+s*lo[1])/(hi[0]+s*hi[1]) for s in (1, -1)]


def dirichlet_channels(w):
    # Independent reference: Dirichlet characters and gamma factor.
    c5, c4 = [0,1,-1,-1,1], [0,1,0,-1]
    c20 = [c5[i % 5]*c4[i % 4] for i in range(20)]
    def completed(s):
        factor = (mp.sqrt(5)/mp.pi)**s * mp.gamma(s)
        return (factor*mp.zeta(s)*mp.dirichlet(s,c20),
                factor*mp.dirichlet(s,c5)*mp.dirichlet(s,c4))
    return [num/den for num, den in zip(completed(w-1), completed(w))]


def invariant_lattices(limit):
    # Column HNF [[a,b],[0,d]], 0 <= b < a. Test both column images in the lattice.
    total = accepted = 0
    for n in range(1, limit+1):
        count = 0
        for d in sp.divisors(n):
            a = n//d
            for b in range(a):
                total += 1
                if a % d or b % d:
                    continue
                if (a - b*(a//d)) % a == 0 and (b + d - b*(b//d)) % a == 0:
                    count += 1
        coefficient = sum((0,1,-1,-1,1)[k%5] for k in sp.divisors(n))
        assert count == coefficient
        accepted += count
    return {'max_index': limit, 'tested': total, 'invariant': accepted}


def channels():
    w = mp.mpc(1, 2)
    coarse, fine = (lattice_channels(w, n) for n in (5, 8))
    reference = dirichlet_channels(w)
    result = {}
    for name, x, y, z in zip(('symmetric','antisymmetric'), coarse, fine, reference):
        assert abs(y-z) < mp.mpf('1e-35')
        assert abs(x-y) < mp.mpf('1e-18')
        result[name] = {
            'real': mp.nstr(y.real, 30), 'imag': mp.nstr(y.imag, 30),
            'phase_radians': mp.nstr(mp.arg(y), 30),
            'refinement_change': mp.nstr(abs(x-y), 6),
            'dirichlet_residual': mp.nstr(abs(y-z), 6),
        }
    assert abs(fine[0] - fine[1]) > mp.mpf('.1')
    return result


if __name__ == '__main__':
    mp.mp.dps = 50
    print(json.dumps({'R141_HNF': invariant_lattices(500), 'ring_and_sol': ring_and_sol(), 'bianchi_w_1_plus_2i': channels()}, indent=2))
