"""Finite controls for the review. Run from any directory with NumPy/SciPy/SymPy."""
from importlib.util import module_from_spec, spec_from_file_location
from itertools import combinations, product
from math import comb, log, pi
from pathlib import Path
import json

import numpy as np


ANALYSIS = Path(__file__).resolve().parents[2]
spec = spec_from_file_location("r132", ANALYSIS/"R132_ADD_YM_CCM_20261119/verify.py")
r132 = module_from_spec(spec)
spec.loader.exec_module(r132)
engine, engine_sha = r132.load_engine()
I = np.eye(2, dtype=complex)
split = {3: (1, 2), 12: (8, 4)}
merge = {pair: s for s, pair in split.items()}


def su2(rng):
    q = rng.normal(size=4)
    a, b, c, d = q / np.linalg.norm(q)
    return np.array([[a+1j*b, c+1j*d], [-c+1j*d, a-1j*b]])


def wilson(links):
    U = I
    for link in links:
        U = U @ link
    return U.trace().real / 2


def spectral_wilson(links):
    n = len(links)
    T = np.zeros((2*n, 2*n), dtype=complex)
    for i, g in enumerate(links):
        j = (i+1) % n
        T[2*i:2*i+2, 2*j:2*j+2] = g
    d = T - np.eye(2*n)
    spectrum = np.linalg.eigvalsh(d.conj().T @ d)
    # Eigenvalues of the vertex Laplacian only. T_n(cos t) = cos(nt).
    return np.cos(n*np.arccos(np.clip(1-spectrum/2, -1, 1))).mean()


def lifted_step(x, links, rng):
    n = len(x)
    starts = {i for i in range(n) if n > 1 and
              (x[i][1], x[(i+1)%n][1]) in merge}
    ends = {(i+1)%n for i in starts}
    i = next(i for i in range(n) if i not in ends)
    consumed = 0
    y, midlinks = [], []
    while consumed < n:
        name, label = x[i]
        step = 1
        if i in starts:
            j = (i+1)%n
            y.append((engine.join(name,x[j][0]),merge[(label,x[j][1])]))
            midlinks.append(links[i] @ links[j])
            step = 2
        elif label in split:
            a, b = split[label]
            y.extend(((engine.left(name),a),(engine.right(name),b)))
            h = su2(rng)
            midlinks.extend((h, h.conj().T @ links[i]))
        else:
            y.append((name,label))
            midlinks.append(links[i])
        i = (i+step)%n
        consumed += step
    assert engine.equal(tuple(y),engine.interact(x,(1,-1)))
    # Put a new Q vertex on each old link. Multiplication compares adjacent midpoints.
    left = [su2(rng) for _ in midlinks]
    right = [a.conj().T @ g for a,g in zip(left,midlinks)]
    newlinks = [b @ left[(i+1)%len(left)] for i,b in enumerate(right)]
    out = engine.transport(tuple(y),2)
    assert engine.equal(out,engine.forward(x,(1,-1)))
    return out, newlinks


def loop_checks():
    rng = np.random.default_rng(20261120)
    words = list(w for n in (1,2,3) for w in product(range(16),repeat=n))
    longer = set()
    while len(longer)<64:
        longer.add(tuple(map(int,rng.integers(16,size=int(rng.integers(4,13))))))
    errors = []
    for w in words+sorted(longer):
        x = engine.named(w)
        links = [su2(rng) for _ in w]
        expected = wilson(links)
        residual = [abs(spectral_wilson(links)-expected)]
        for _ in range(2):
            x,links = lifted_step(x,links,rng)
            residual.extend([abs(wilson(links)-expected),abs(spectral_wilson(links)-expected)])
        errors.append(max(residual))
    X = 1j*np.array([[0,1],[1,0]])
    Y = np.array([[0,1],[-1,0]])
    Z = 1j*np.diag([1,-1])
    order = [spectral_wilson(edges) for edges in ([X,Y,Z],[X,Z,Y])]
    assert np.allclose(order,[1,-1]) and max(errors)<1e-11
    # Fixed external and internal matter orientations; a,b and ac,c^-1 b have the same product.
    spinor = np.array([1,0])
    def observable(a,psi):
        return abs(spinor.conj() @ a @ psi)**2
    matter = [observable(I,spinor),observable(X,spinor),observable(X,X.conj().T@spinor)]
    assert np.allclose(matter,[1,0,1])
    return dict(exhaustive=len(words),longer=len(longer),steps_per_word=2,
                tolerance=1e-11,all_below_tolerance=True,order_control=[1,-1],matter=matter)


def casimir_control():
    pauli = (np.array([[0,1],[1,0]]),np.array([[0,-1j],[1j,0]]),np.diag([1,-1]))
    def rot(t,axis):
        return np.cos(t/2)*I+1j*np.sin(t/2)*axis
    a,b=rot(np.pi/3,pauli[2]),rot(np.pi/2,pauli[0])
    value=wilson([a,b])
    delta=0.0005
    coarse=fine=0.
    for axis in pauli:
        plus,minus=rot(delta,axis),rot(-delta,axis)
        first=(2*value-wilson([plus@a,b])-wilson([minus@a,b]))/(delta**2)
        second=(2*value-wilson([a,plus@b])-wilson([a,minus@b]))/(delta**2)
        coarse+=first
        fine+=first+second
    assert np.allclose([coarse/value,fine/value],[0.75,1.5],rtol=1e-6)
    return [0.75,1.5]


def entropy_energy(bes,p):
    z, u = np.zeros(p+1), np.zeros(p+1)
    z[0] = 1
    for x in bes:
        w = np.exp(-x)
        u[1:] += w*(u[:-1]+x*z[:-1])
        z[1:] += w*z[:-1]
    return log(z[p])+u[p]/z[p]


def entropy_checks():
    def energies(l):
        return np.tile(2*np.sin(pi*np.arange(l)/l),2)
    p, beta = 3, 8
    w = (3,1,0,0)
    successor = engine.forward(engine.named(w),(1,))
    assert len(successor)==5 and sum(s.bit_count() for _,s in successor)==p
    ent = []
    for l in (4,5):
        es=energies(l)
        val=entropy_energy(beta*es,p)
        x=np.array([beta*sum(c) for c in combinations(es,p)])
        z=np.exp(x.min()-x)
        prob=z/z.sum()
        assert np.isclose(val,-prob@np.log(prob))
        ent.append(val)
    assert ent[0]>ent[1]
    x=8
    vals=[entropy_energy(l*energies(l)/x,2) for l in (100,200,400,800)]
    continuum=entropy_energy(np.r_[0.,0.,np.repeat(2*pi*np.arange(1,151)/x,4)],2)
    assert abs(vals[-1]-continuum)<0.0003
    return dict(word=w,lengths=[4,5],beta=beta,p=p,canonical=ent,
                uniform=[log(comb(2*l,p)) for l in (4,5)],
                fixed_ratio_8_p2=vals,limit_p2=continuum)


def grading_checks():
    results = []
    for l in (2,3,5):
        D = r132.graph_operators(l)
        g = np.diag([1]*l+[-1]*l)
        zero = np.zeros_like(g)
        unit = np.eye(2*l,dtype=int)
        swap = np.block([[zero,unit],[unit,zero]])   # J = swap composed with conjugation
        DD = np.block([[D,zero],[zero,D]])
        gg = np.block([[g,zero],[zero,-g]])
        assert np.array_equal(swap@swap,np.eye(4*l))
        assert np.array_equal(swap@gg,-gg@swap) and np.array_equal(swap@DD,DD@swap)
        left, right = [], []
        for site in np.eye(l,dtype=int):
            A=np.diag(np.r_[site,site])
            B=np.diag(np.r_[site,np.roll(site,-1)])
            left.append(np.block([[A,zero],[zero,B]]))
            right.append(np.block([[B,zero],[zero,A]]))
        for a,b in zip(left,right):
            assert np.array_equal(swap@a@swap,b)
        for a,b in product(left,right):
            assert np.array_equal(a@b,b@a)
            comm=DD@a-a@DD
            assert np.array_equal(comm@b,b@comm)
        for i in range(l):
            assert gg[i,i]==-gg[2*l+i,2*l+i]
            for a,b in product(left,right):
                q=a@b
                assert q[i,i]==q[2*l+i,2*l+i]
        results.append(l)
    return results


if __name__ == "__main__":
    print(json.dumps(dict(engine_sha256=engine_sha,entropy=entropy_checks(),
                          doubled_real_module_lengths=grading_checks(),su2=loop_checks(),
                          coarse_and_unweighted_subdivided_casimir=casimir_control()),indent=2))
