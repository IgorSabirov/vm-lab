"""Exact independent controls for the integrated R141–R148 atlas. Print JSON."""
from collections import Counter
from fractions import Fraction
from itertools import product
from math import gcd, prod
import json

import sympy as sp
from sympy.matrices.normalforms import smith_normal_form


def probabilities(weights, length, cyclic=False):
    """Exact binary cylinder weights with mark (0,1), independent input letters."""
    total = sum(weights)
    masses = Counter()
    count = length if cyclic else length + 1
    for word in product(range(len(weights)), repeat=count):
        mask = ''.join(str(int((word[i], word[(i+1) % count]) == (0, 1)))
                       for i in range(length))
        masses[mask] += prod(weights[j] for j in word)
    return {word: Fraction(weight, total**count) for word, weight in masses.items()}


def moment_model(length, density, cyclic):
    """Recover all atom masses from inclusion moments by Boolean Möbius inversion."""
    moments = []
    for bits in product(range(2), repeat=length):
        adjacent = any(a and b for a, b in zip(bits, bits[1:]))
        if cyclic and bits[-1] and bits[0]:
            adjacent = True
        moments.append(Fraction(0) if adjacent else density**sum(bits))
    for shift in range(length):
        bit = 1 << shift
        for i in range(1 << length):
            if not i & bit:
                moments[i] -= moments[i | bit]
    return {format(i, '0%db' % length): v for i, v in enumerate(moments) if v}


def marked_laws():
    rows = []
    for cyclic in (False, True):
        for n in range(3 if cyclic else 1, 8):
            four = probabilities([1, 1, 1, 1], n, cyclic)
            three = probabilities([1, 1, 2], n, cyclic)
            target = moment_model(n, Fraction(1, 16), cyclic)
            assert four == three == target
            rows.append([cyclic, n, len(four), str(sum(four.values()))])
    fibers = {w: int(p * 4096) for w, p in probabilities([1]*4, 6, True).items()}
    return {'comparisons': rows, 'six_ring_fibres': dict(sorted(fibers.items())),
            'two_age_laws_same_density': '1/16'}


def integral_form_controls():
    Q = sp.symbols('q')
    B = sp.Matrix([[Q-1, 1], [Q-2, 1]])
    T = sp.Matrix([[Q, -1], [1, 0]])
    gl = sp.Matrix([[1, 0], [1, -1]])
    assert gl * B == T * gl and gl.det() == -1
    x, y, z = sp.symbols('x y z')
    sy = sp.Matrix([[x, y], [y, z]])
    generic = sp.Matrix([[-2*(Q-2), Q-2], [Q-2, 2]])
    assert (B.T*generic*B-generic).applyfunc(sp.expand) == sp.zeros(2)
    assert sp.expand(generic.det()) == 4-Q**2
    rows = {}
    for q, D, order3 in [(3, -5, 4), (4, -3, 6)]:
        b = B.subs(Q,q)
        form = generic.subs(Q,q) / gcd(q-2,2)
        nullity = len(sp.linear_eq_to_matrix(list(b.T*sy*b-sy), [x,y,z])[0].nullspace())
        assert nullity == 1 and form.det() == D
        # Check orders by modular powering, removing every prime factor.
        orders = []
        for r in range(1,13):
            m = 3**r
            k = order3 * 3**(r-1)
            def power_mod(exp):
                a = b
                result = sp.eye(2)
                while exp:
                    if exp % 2:
                        result = (result*a) % m
                    a = (a*a) % m
                    exp //= 2
                return result
            assert power_mod(k) == sp.eye(2)
            assert all(power_mod(k//p) != sp.eye(2) for p in sp.factorint(k))
            orders.append(k)
        # reduced positive primitive binary forms, discriminants of imaginary fields
        disc = -20 if q == 3 else -3
        reduced = []
        for a in range(1, int((abs(disc)/3)**0.5)+1):
            for bcoef in range(-a, a+1):
                c, rem = divmod(bcoef*bcoef-disc, 4*a)
                if rem or c < a or gcd(gcd(a,bcoef),c) != 1:
                    continue
                if bcoef < 0 and (abs(bcoef) == a or a == c):
                    continue
                reduced.append([a,bcoef,c])
        rows[q] = {'S':form.tolist(), 'det_Q':D, 'reduced_forms':reduced, 'ord_3r':orders}
    assert len(rows[3]['reduced_forms']) == 2 and len(rows[4]['reduced_forms']) == 1
    return rows


def phase_smith():
    E = sp.symbols('E')
    checks = 0
    examples = {}
    for q in (3,4,5):
        for n in range(3,9):
            for phase in (1, -1, sp.I):
                shift = sp.zeros(n)
                for j in range(n-1):
                    shift[j,j+1] = 1
                shift[n-1,0] = phase
                h = q*sp.eye(n)-shift-shift.H
                # characteristic polynomial of the full n x n matrix in independent arithmetic
                got = (-1)**n * h.charpoly(E).as_expr()
                v0,v1 = 2, q-E
                for j in range(2,n+1):
                    v0,v1 = v1,sp.expand((q-E)*v1-v0)
                assert sp.expand(got-v1+phase+sp.conjugate(phase)) == 0
                if n == 6 and q in (3,4):
                    row = {'det':int(h.det())}
                    if phase in (1,-1):
                        sn = smith_normal_form(h, domain=sp.ZZ)
                        row['Smith_nonunit'] = [abs(int(v)) for v in sn.diagonal() if abs(v)!=1]
                    examples[str((q,n,str(phase)))] = row
                checks += 1
    return {'polynomials':checks,'examples':examples}


def same_trace():
    b3 = sp.Matrix([[2,1],[1,1]])
    b7 = sp.Matrix([[6,1],[5,1]])
    reps = [(1,0),(0,1),(1,1),(1,2)]
    def lines(a):
        return [v for v in reps if sp.Matrix.hstack(sp.Matrix(v),a*sp.Matrix(v)).det()%3==0]
    assert b7.charpoly().as_expr() == (b3**2).charpoly().as_expr()
    assert len(lines(b7))==1 and len(lines(b3**2))==4
    return {'B7':lines(b7), 'B3_squared':lines(b3**2), 'common_trace':7}


if __name__ == '__main__':
    report = {'weighted_mask_laws':marked_laws(), 'integral_forms':integral_form_controls(),
              'phase_and_smith':phase_smith(), 'same_trace_different_lattice':same_trace()}
    print(json.dumps(report,ensure_ascii=False,indent=2,default=lambda v:int(v)))
