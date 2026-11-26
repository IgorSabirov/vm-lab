"""Independent finite checks for the R150 audit. Python 3, NumPy and SymPy.
Run: OPENBLAS_NUM_THREADS=1 python replay.py > results.json
Reference: the published R150 Floquet word engine in the parent directory.
"""
import collections
import itertools
import json
import math
import sys
from pathlib import Path

import numpy as np
import sympy as sp

BITS = (1, 2, 4, 8)
EPS = (1, -1)


def canonical(word):
    return min(word[i:] + word[:i] for i in range(len(word)))


def word_from_positions(k, size):
    word = [0] * size
    for site, bit in zip((0, *k), BITS):
        word[site] |= bit
    return tuple(word)


def coordinates(word):
    pos = [next(i for i, x in enumerate(word) if x & bit) for bit in BITS]
    return tuple((x - pos[0]) % len(word) for x in pos[1:])


def rewrite(word, signs=EPS):
    """Emit one replacement per site in cyclic order, skipping consumed ends.
    The emitted starting site is immaterial on the rotation quotient.
    """
    a = (1, 2) if signs[0] == 1 else (2, 1)
    b = (4, 8) if signs[1] == 1 else (8, 4)
    joins = {a: 3, b: 12}
    splits = {3: a, 12: b}
    n = len(word)
    result = []
    for i, x in enumerate(word):
        pair = (x, word[(i + 1) % n])
        previous = (word[(i - 1) % n], x)
        if previous in joins:
            continue
        if pair in joins:
            result.append(joins[pair])
        else:
            result.extend(splits.get(x, (x,)))
    return tuple(result)


def shift(w):
    return tuple((w[i] & 10) | (w[(i + 1) % len(w)] & 5) for i in range(len(w)))


def reverse_channels(w):
    return tuple(sum(b for a, b in zip(BITS, reversed(BITS)) if x & a) for x in w)


def step(w, signs=EPS):
    return shift(rewrite(w, signs))


def restrict_map(words, signs=EPS):
    words = set(words)
    images = {w: canonical(step(w, signs)) for w in words}
    keep = set(words)
    while True:
        new = {w for w in keep if images[w] in keep}
        if new == keep:
            break
        keep = new
    f = {w: images[w] for w in keep}
    assert set(f.values()) == keep
    return f


def four_words(size):
    return [canonical(word_from_positions(k, size)) for k in itertools.product(range(size), repeat=3)]


def orbits(f):
    remaining = set(f)
    cycles = []
    while remaining:
        start = min(remaining)
        w = start
        c = []
        while w in remaining:
            remaining.remove(w)
            c.append(w)
            w = f[w]
        assert w == start
        cycles.append(c)
    return cycles


def layer(w):
    t, u, x = coordinates(w)
    return u, (x - t) % len(w)


def active(w):
    u, v = layer(w)
    return bool(u and v and (u - v) % len(w) == 1)


def mass(w):
    n = len(w)
    s = sum(layer(w)) % n
    return s if s <= (n - 1) // 2 else s - n


def chi(w):
    return sum(int((x & 5) == 5) - int((x & 10) == 10) for x in w)


def interaction_count(w):
    splits = sum(x in (3, 12) for x in w)
    joins = sum((x, w[(i + 1) % len(w)]) in ((1, 2), (8, 4)) for i, x in enumerate(w))
    return splits, joins


def square_permutation(f, states):
    indices = {w: i for i, w in enumerate(states)}
    a = sp.zeros(len(states))
    for i, w in enumerate(states):
        a[indices[f[w]], i] = 1
    return a


def parity(null_basis, t):
    if not null_basis:
        return [0, 0]
    k = sp.Matrix.hstack(*null_basis)
    r = k.gauss_jordan_solve(t * k)[0]
    tr = int(r.trace())
    return [(k.cols + tr) // 2, (k.cols - tr) // 2]


def core_checks(size):
    words = four_words(size)
    f = restrict_map(words)
    t = {w: canonical(rewrite(reverse_channels(w))) for w in f}
    assert all(t[t[w]] == w and t[f[t[f[w]]]] == w for w in f)
    assert set(f) == {w for w in words if 0 in layer(w) or active(w)}
    cycles = orbits(f)
    strength = collections.Counter()
    for c in cycles:
        local = [interaction_count(w) for w in c]
        assert all(a == b for a, b in local)
        rate = sp.Rational(sum(a > 0 for a, b in local), len(c))
        assert all(bool(rate) == active(w) for w in c)
        strength[str(rate)] += len(c)
        assert all(chi(w) == chi(c[0]) and mass(w) == mass(c[0]) for w in c)
        for w in c:
            if active(w):
                j, u, x = coordinates(w)
                assert coordinates(shift(w))[0] == (j + 1) % size
                assert coordinates(rewrite(w))[0] == ({0: 1, 1: 0}.get(j, j))
                assert layer(rewrite(w)) == layer(shift(w)) == layer(w)
    counts = dict(sorted(collections.Counter(map(len, cycles)).items()))
    # Count eigenvalues from closed cyclic blocks. Ranks for selected sizes
    # are independently certified below by rational/exact matrix identities.
    result = dict(size=size, carrier=len(f), cycles=counts, activity=strength,
                  trace_T=sum(t[w] == w for w in f), trace_FT=sum(f[t[w]] == w for w in f),
                  dim_iD=sum(1 + int(len(c)%2 == 0) for c in cycles),
                  even_half_turn_mass_odd_violations=sum(mass(t[w]) != -mass(w) for w in f))
    # i(zeta-zeta^-1) is an algebraic integer. A rational target must
    # be integral. For +/-1 on a cyclic block the period is a multiple of 12.
    def rational_zeros(c, offset):
        if offset.q != 1:
            return 0
        if offset == 0:
            return 1 + int(len(c) % 2 == 0)
        if abs(offset) == 1:
            return 2 * int(len(c) % 12 == 0)
        raise AssertionError('unexpected offset')
    result['combined_zeros'] = sum(rational_zeros(c, sp.Rational(chi(c[0])) +
                                sp.Rational(mass(c[0]),size**2)) for c in cycles)
    result['chi_zeros'] = sum(rational_zeros(c, sp.Rational(chi(c[0]))) for c in cycles)
    assert result['combined_zeros'] == (4 if size%2 else 2)
    if size == 7:
        for label, test in [('full', lambda w: True), ('active', active), ('self', lambda w: layer(w) == (4, 3))]:
            seq = sorted(w for w in f if test(w))
            F, T = (square_permutation(p, seq) for p in (f, t))
            FT = F*T
            h = sp.I * (F - F.T)
            assert FT**2 == sp.eye(len(seq)) and FT*h*FT == -h
            def measured(matrix):
                ns = matrix.nullspace()
                return dict(ker=len(ns), parity=parity(ns, T))
            # Solve small orbit blocks and reassemble full zero-mode basis in the original space.
            def block_measure(offset, grading=T):
                col = []
                index = {w: i for i, w in enumerate(seq)}
                for c in cycles:
                    if c[0] not in index:
                        continue
                    rows = [index[w] for w in c]
                    block = h.extract(rows, rows) + sp.eye(len(rows))*offset(c[0])
                    for v in block.nullspace():
                        big = sp.zeros(len(seq), 1)
                        for j, i in enumerate(rows):
                            big[i] = v[j]
                        col.append(big)
                return dict(ker=len(col), parity=parity(col, grading))
            entry = {'states':len(seq), 'trT':int(T.trace()),'trFT':int(FT.trace()),
                     'bare':block_measure(lambda w:0), 'chi':block_measure(chi),
                     'combined':block_measure(lambda w:chi(w) + sp.Rational(mass(w), size**2))}
            if label == 'self':
                for name, g in [('F0', F-sp.eye(7)), ('Fpi', F+sp.eye(7))]:
                    entry[name] = measured(g)
                entry['bare_with_FT'] = block_measure(lambda w:0, FT)
                entry['D_singular_sq_poly'] = str(sp.factor((h*h).charpoly().as_expr()))
            result[label] = entry
    return result


def returns():
    size = 7
    words = set(four_words(size))
    f = restrict_map(words)
    hist = collections.Counter()
    for initial in words - f.keys():
        w = initial
        left = False
        for j in range(1, 65):
            w = step(w)
            if len(w) != size:
                left = True
            elif left:
                hist[j] += 1
                break
    w = word_from_positions((0, 1, 2), 7)
    initial = canonical(w)
    trace = [list(coordinates(w))]
    lens = [7]
    for j in range(7):
        w = step(w)
        lens.append(len(w))
        trace.append(list(coordinates(w)))
    assert canonical(w) == initial and 7 not in lens[1:-1]
    return dict(excluded=len(words)-len(f), horizon=64, first_return_to_length=dict(sorted(hist.items())),
                returned=sum(hist.values()), example_lengths=lens, example_coordinates=trace)


def sector_words(n, populations):
    choices = [list(itertools.combinations(range(n), count)) for count in populations]
    words = set()
    for positions in itertools.product(*choices):
        w = [0]*n
        for p, bit in zip(positions, BITS):
            for j in p:
                w[j] |= bit
        words.add(canonical(tuple(w)))
    return words


def alternative_rules():
    populations = {}
    for pop in [(1,1,1,1), (2,1,1,2), (2,2,2,2)]:
        s = sector_words(5, pop)
        f = restrict_map(s)
        t = {w:canonical(rewrite(reverse_channels(w))) for w in f}
        assert all(t.get(t[w]) == w and t[f[t[f[w]]]] == w for w in f)
        c = orbits(f)
        populations[str(pop)] = [len(s), len(f), sum(t[w] == w for w in f),
                                  sum(1 + int(len(p)%2 == 0) for p in c)]
    signs = {}
    for eps in itertools.product((1,-1), repeat=2):
        f = restrict_map(four_words(7), eps)
        signs[str(eps)] = dict(sorted(collections.Counter(map(len,orbits(f))).items()))
    return dict(populations_L5=populations, orientations_L7=signs)


def local_obstruction():
    n = 15
    states = [word_from_positions((1, u, u), n) for u in (5,11)]
    assert canonical(rewrite(reverse_channels(states[0]))) == canonical(states[1])
    assert all(canonical(step(w)) == canonical(w) for w in states)
    matches = []
    for r in range(1, n + 1):
        hs = [collections.Counter((w+w)[i:i+r] for i in range(n)) for w in states]
        if hs[0] == hs[1]:
            matches.append(r)
    return dict(size=n, positions=[[1,5,5],[1,11,11]], mass=list(map(mass,states)), identical_window_lengths=matches)


def other_operators():
    n = 7
    q, i = sp.zeros(n), sp.eye(n)
    i.row_swap(0,1)
    for j in range(n):
        q[(j+1)%n,j] = 1
    F=q*i
    z,x=sp.symbols('z x')
    w=q*((sp.eye(n)+i)/2 + z*(sp.eye(n)-i)/2)
    p=x**7 + (z-1)*(x**6+x)/2-z
    assert sp.expand(w.charpoly(x).as_expr()-p)==0
    result = {'W_minus_i':[len((w.subs(z,-sp.I)-sp.eye(n)).nullspace()),
                            len((w.subs(z,-sp.I)+sp.eye(n)).nullspace())],
              'W_det':str(sp.factor(w.det())), 'W_at_zero_phase':str(sp.factor(p.subs(x,1))),
              'W_pi_polynomial':str(sp.factor(p.subs(x,-1))), 'W_unitarity_error_sample':abs(abs(.3+.954j)**2-1)}
    edges=[(0,2),(2,3),(3,4),(4,5),(5,6),(6,0)]
    for name, links in [('without_loop',edges),('with_loop',edges+[(1,1)]),('cut',edges[:-1])]:
        b=sp.zeros(n,len(links))
        for col,(left,right) in enumerate(links):
            b[left,col]-=1
            b[right,col]+=1
        result[name] = [n-b.rank(),len(links)-b.rank()]
    m=sp.zeros(7)
    for row,pos,neg in [(1,2,7),(2,3,1),(3,4,2),(3,7,6),(4,5,3),(6,3,5),(7,1,3)]:
        m[row-1,pos-1]+=1
        m[row-1,neg-1]-=1
    result['KS_poly'] = str(sp.factor((m.T*m).charpoly(x).as_expr()))
    result['D_poly'] = str(sp.factor((-(F-F.T)**2).charpoly(x).as_expr()))
    # On L=7, all active layers are identical before adding the five constant potentials.
    g=sp.sqrt(3)
    t=sp.eye(7)
    t.row_swap(2,6)
    t.row_swap(3,5)
    rot=sp.eye(7)
    rot[0:2,0:2]=sp.Matrix([[4,-3],[3,4]])/5
    j=F*t
    deformed=rot*j*rot.T*t
    assert deformed.T*deformed==sp.eye(7) and t*deformed*t==deformed.T
    result['T_preserving_deformation']=[len((deformed-sign*sp.eye(7)).nullspace()) for sign in (1,-1)]
    result['old_fixed_state_preserved'] = deformed[:,1]==sp.eye(7)[:,1]
    # Direct full unitary phase kick, with no charged cycles dropped.
    f7=restrict_map(four_words(7))
    seq=sorted(f7)
    ff=np.array(square_permutation(f7,seq)).astype(complex)
    tt=np.array(square_permutation({a:canonical(rewrite(reverse_channels(a))) for a in f7},seq)).astype(complex)
    unit=np.diag([(-1j)**chi(a) for a in seq]) @ ff
    assert np.allclose(tt@unit@tt,unit.conj().T)
    counted={}
    for sign in (1,-1):
        _,s,vh=np.linalg.svd(unit-sign*np.eye(len(seq)))
        k=vh[s<1e-10].conj().T
        vals=np.linalg.eigvalsh(k.conj().T@tt@k)
        counted[str(sign)]=[int((vals>0.5).sum()),int((vals<-.5).sum())]
    result['U_pi2_full_parities_direct']=counted
    values=[-3,-2,0,2,3]
    for name,mu in [('resonance',g/3),('beyond',sp.Rational(3,5))]:
        ev=[sp.simplify(base+mu*offset) for offset in values for base in [0,0,0,g,g,-g,-g]]
        nz=[abs(float(a)) for a in ev if a!=0]
        result[name]=dict(nulls=ev.count(0),gap_to_nonzero=min(nz),min_abs=float(min(map(abs,ev))))
    # abs(min spectrum) includes the symmetry-required zero. Gap to other
    # states at a crossing is zero if the original three alone are exempted.
    return result


def masses():
    m=np.array([.51099895069,105.6583755,1776.93])
    err=np.array([.00000000016,.0000023,.09])
    a=np.sqrt(m)
    gradient=1/a.sum()**2-m.sum()/(a*a.sum()**3)
    q=m.sum()/a.sum()**2
    sigma=np.linalg.norm(gradient*err)
    b,c=a[:2]
    tau=(2*(b+c)+math.sqrt(3*(b*b+4*b*c+c*c)))**2
    e,mu=(1+math.sqrt(2)*math.cos(2/9+t) for t in (2*math.pi/3,-2*math.pi/3))
    return dict(Q=q,sigma=sigma,Q_standardized=(q-2/3)/sigma,tau=tau,
                fixed_ratio=(mu/e)**2,ratio_standardized=((mu/e)**2-206.7682827)/.0000046)


def compare_published_rule():
    """Cross-check the independent cyclic rewrite against the committed port rule."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from word_rule import F_word, T_word

    count = 0
    for size in range(2, 15):
        for word in four_words(size):
            assert canonical(step(word)) == canonical(F_word(word))
            assert canonical(rewrite(reverse_channels(word))) == canonical(T_word(word))
            count += 1
    return dict(tested_inputs=count, lengths=[2, 14])


if __name__ == '__main__':
    report = dict(cores=[core_checks(n) for n in range(2, 16)], returns=returns(),
                  controls=alternative_rules(), locality=local_obstruction(),
                  operators=other_operators(), masses=masses(),
                  compared_published_F_T=compare_published_rule())
    print(json.dumps(report, indent=2, ensure_ascii=False))
