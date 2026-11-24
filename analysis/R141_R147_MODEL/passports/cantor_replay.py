"""Finite witnesses for the Cantor passport. Run from anywhere in vm-lab."""
from collections import Counter
from fractions import Fraction
from itertools import product
import json
import math
from pathlib import Path
import runpy


IDENTITY = (1, 0, 0, 1)
A = (2, 1, 1, 1)
PHI = (1 + math.sqrt(5)) / 2


def multiply(x, y, modulus=None):
    a, b, c, d = x
    e, f, g, h = y
    result = (a*e+b*g, a*f+b*h, c*e+d*g, c*f+d*h)
    return result if modulus is None else tuple(value % modulus for value in result)


def power(exponent, modulus=None):
    result, base = IDENTITY, A
    while exponent:
        if exponent % 2:
            result = multiply(result, base, modulus)
        base = multiply(base, base, modulus)
        exponent //= 2
    return result


def fib(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a+b
    return a


def languages():
    word = '0'
    for _ in range(17):
        word = ''.join('01' if char == '0' else '0' for char in word)
    counts = []
    for n in range(1, 17):
        blocks = {word[j:j+n] for j in range(len(word)-n+1)}
        golden = {''.join(bits) for bits in product('01', repeat=n) if '11' not in ''.join(bits)}
        assert blocks <= golden and len(blocks) == n+1
        assert len(golden) == fib(n+2)
        counts.append([n, len(golden), len(blocks)])
    assert '000' not in word
    return counts


def geometric_gaps(depth):
    # The cylinders labelled 0 and 10 are copies of [0,3/4] at scales 1/3 and 1/9.
    scale = Fraction(5, 12)
    hist = Counter()
    def visit(left, right, length):
        if length > depth:
            return
        width = right-left
        cut_left = left + width/3
        cut_right = right - width/9
        hist[cut_right-cut_left] += 1
        visit(left, cut_left, length+1)
        visit(cut_right, right, length+2)
    visit(Fraction(0), Fraction(3,4), 0)
    for n in range(depth+1):
        assert hist[scale/3**n] == fib(n+1)
    return {'max_scale_index': depth, 'gaps_counted': sum(hist.values()),
            'hausdorff_dimension_ternary': math.log(PHI)/math.log(3)}


def lattice_contains(matrix, vector):
    a, b, c, d = matrix
    x, y = vector
    determinant = a*d-b*c
    return (d*x-b*y) % determinant == 0 and (a*y-c*x) % determinant == 0


def ideal_matrix(n, sign=1):
    a, b, c, d = power(n)
    return a-sign, b, c, d-sign


def projects(m, n, sign):
    a, b, c, d = ideal_matrix(m, sign)
    return all(lattice_contains(ideal_matrix(n, sign), col) for col in ((a,c), (b,d)))


def tower():
    tested = 0
    for n in range(1, 51):
        quotient = ideal_matrix(n)
        # In the field basis (phi,1), one is the second coordinate vector.
        for d in range(1, n+1):
            _, b, _, e = power(d)
            assert lattice_contains(quotient, (b,e-1)) == (d == n)
        for m in range(n, 51, n):
            assert projects(m, n, 1)
            tested += 1
    assert not projects(12, 6, -1) and projects(18, 6, -1)
    orders = {}
    for q in range(2, 65):
        x, order = A, 1
        while tuple(v%q for v in x) != IDENTITY:
            x, order = multiply(x, A, q), order+1
        assert all(v % q == 0 for v in ideal_matrix(order))
        orders[q] = order
    congruence_orders = []
    for r in range(1, 13):
        mod = 3**r
        order = 4*3**(r-1)
        assert power(order, mod) == IDENTITY
        for p in (2,3):
            if order % p == 0:
                assert power(order//p, mod) != IDENTITY
        congruence_orders.append([r, order])
    return {'unit_orbit_exact_periods_verified': [1,50], 'cover_projection_checks':tested,
            'signed_projections_12_to_6_and_18_to_6':[False,True],
            'cofinality_moduli_checked':[2,64], 'orders_selected':{q:orders[q] for q in (4,5,20)},
            'mod_3_power_orders':congruence_orders}


def measures():
    starts = lambda a,b: a == 1 and b == 2
    count = sum(starts(a,b) for a,b in product(range(4),repeat=2))
    # Number of admissible labelled cycles with position zero occupied, divided by all cycles.
    cycle_rows = []
    for n in (4,6,10,16):
        cycles = [bits for bits in product((0,1),repeat=n)
                  if all(not (bits[i] and bits[(i+1)%n]) for i in range(n))]
        density = Fraction(sum(bits[0] for bits in cycles),len(cycles))
        cycle_rows.append([n,str(density)])
    return {'uniform_R130_site_pair':str(Fraction(count,16)),
            'uniform_allowed_cycle_site':cycle_rows, 'max_entropy_limit':1/(PHI**2+1)}


def fibonacci_operator():
    source = Path(__file__).resolve().parents[2]/'R142_MAGIC_NUMBERS'/'fibonacci.py'
    rows = runpy.run_path(str(source))['audit']()
    return [{'n':r['size'], 'filled_bands':r['B'],
             'gap_at_contrast_1':round(float(r['gap_contrast_1']),9),
             'gap_at_contrast_0_below_1e_minus_12':bool(abs(r['gap_contrast_0'])<1e-12)} for r in rows]


if __name__ == '__main__':
    print(json.dumps({'language_counts_n_golden_fibonacci':languages(), 'golden_string':geometric_gaps(16),
                      'arithmetic_and_geometric_towers':tower(), 'measures':measures(),
                      'R142_original_operator':fibonacci_operator()},indent=2))
