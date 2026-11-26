"""Run from any directory with Python 3, NumPy and SymPy."""
import json
from math import pi
from pathlib import Path

import numpy as np
import sympy as sp


def lucas(k):
    a, b = 2, 1
    for _ in range(k):
        a, b = b, a+b
    return a


def exact_checks():
    u, z, trace, dual = sp.symbols('u z trace dual', nonzero=True)
    p = 1-u*z*trace+u**2*z**2*dual-u**3*z**3
    reverse = 1-u/z*dual+u**2/z**2*trace-u**3/z**3
    coeff = sp.expand(p*reverse/u**3)
    C = u+1/u
    # On the centre grid frequencies congruent modulo 3 are summed.
    mean = sum(coeff.coeff(z,k) for k in (-3,0,3))
    first = coeff.coeff(z,1)+coeff.coeff(z,-2)
    assert sp.simplify(mean-(u**3+u**-3+C*trace*dual-2)) == 0
    assert sp.simplify(first+(u**2+u**-2-C)*trace+dual**2) == 0
    x = sp.Rational(3,2)
    for l in range(41):
        previous = sp.chebyshevu(l-1,x) if l else 0
        assert sp.chebyshevu(l,x)-previous == sp.fibonacci(2*l+1)
        assert sp.chebyshevu(l,1) == l+1
    assert all(lucas(4*n)-lucas(2*n) == (lucas(2*n)-2)*(lucas(2*n)+1)
               for n in range(3,41))
    for s, target in ((2,pi**2/6),(4,pi**4/90)):
        size = 500
        partial = sum(k**(-s) for k in range(1,size+1))
        assert (size+1)**(1-s)/(s-1) <= target-partial <= size**(1-s)/(s-1)


CENTRE = np.exp(2j*pi*np.arange(3)/3)


def su3(rng):
    a = rng.normal(size=(3,3)) + 1j*rng.normal(size=(3,3))
    q, r = np.linalg.qr(a)
    q *= np.diag(r)/abs(np.diag(r))
    q[:,0] *= np.linalg.det(q).conjugate()
    return q


def holonomy(links):
    h = np.eye(3,dtype=complex)
    for link in links:
        h = h @ link
    return h


def readings(links, mask):
    n = len(links)
    active = np.repeat(mask,3)
    ring = np.eye(3*n)
    out = []
    for z in CENTRE:
        shift = np.zeros((3*n,3*n),complex)
        for i,link in enumerate(links):
            j = (i+1) % n
            shift[3*i:3*i+3,3*j:3*j+3] = z*link if j==0 else link
        b = (shift-ring)*active[:,None]*active[None,:]
        sign,ld = np.linalg.slogdet(ring+b@b.conj().T)
        assert abs(sign-1) < 1e-12
        out.append(np.exp(ld))
    return np.array(out)


def first_mode(values):
    return np.dot(values-values[0], CENTRE.conjugate())/3


def recover(values,n):
    y = first_mode(values)
    A = lucas(4*n)-lucas(2*n)
    trace = 0j
    for _ in range(20):
        t = -(y+trace.conjugate()**2)/A
        trace = t if abs(t)<=3 else 3*t/abs(t)
    adjoint = (np.mean(values)-lucas(6*n)+2)/lucas(2*n)-1
    return trace, adjoint


def ihara_inverse(links, mask, v):
    n = len(links)
    directed = []
    for i, link in enumerate(links):
        j = (i+1) % n
        if mask[i] and mask[j]:
            directed.extend([(i,j,link),(j,i,link.conj().T)])
    transfer = np.zeros((3*len(directed),3*len(directed)), complex)
    for a,(i,j,_) in enumerate(directed):
        for b,(j2,k,transport) in enumerate(directed):
            if j==j2 and k!=i:
                transfer[3*a:3*a+3,3*b:3*b+3] = transport
    return np.linalg.det(np.eye(len(transfer))-v*transfer)


def check():
    exact_checks()
    rng = np.random.default_rng(149132)
    full = cut = gauges = 0
    v = (3-np.sqrt(5))/2
    exact_centres = []
    for n in (3,4,5,6):
        eye = np.eye(3,dtype=complex)
        shift = np.roll(eye,1,axis=0)
        fixed = [z*eye for z in CENTRE]+[shift]
        for i in range(len(fixed)+16):
            links = [eye]*(n-1)+[fixed[i]] if i<len(fixed) else [su3(rng) for _ in range(n)]
            h = holonomy(links)
            trace = np.trace(h)
            w = [1]*n
            d = readings(links,w)
            recovered,adjoint = recover(d,n)
            assert abs(recovered-trace)<2e-9
            assert abs(adjoint-(abs(trace)**2-1))<2e-8
            assert abs(ihara_inverse(links,w,v)-v**(3*n)*d[0])<1e-11
            split = su3(rng)
            longer = [split,split.conj().T@links[0],*links[1:]]
            y_long = first_mode(readings(longer,[1]*(n+1)))
            a = lucas(4*n)-lucas(2*n)
            a_long = lucas(4*(n+1))-lucas(2*(n+1))
            linear_trace = (first_mode(d)-y_long)/(a_long-a)
            assert abs(linear_trace-trace)<2e-9
            full += 1
            frame = [su3(rng) for _ in range(n)]
            gauged = [frame[k]@link@frame[(k+1)%n].conj().T for k,link in enumerate(links)]
            assert np.allclose(readings(gauged,w),d,atol=1e-8,rtol=2e-12)
            gauges += 1
            for k in range(n):
                w = [int(j!=k) for j in range(n)]
                opened = readings(links,w)
                expected = int(sp.fibonacci(2*n-1))**3
                assert np.allclose(opened,expected,atol=1e-8,rtol=2e-12)
                assert abs(ihara_inverse(links,w,v)-1)<1e-11
                cut += 1
            if n==6 and i<4:
                exact_centres.append([round(float(v)) for v in d])
    centre = [320**3,323**3,323**3]
    assert exact_centres[:3] == [centre[k:]+centre[:k] for k in range(3)]
    assert exact_centres[3] == [320*323**2]*3
    return dict(seed=149132, lengths=[3,4,5,6], dense_closed_triplets=full,
                gauge_changes=gauges, dense_single_cut_triplets=cut,
                trace_preserving_subdivisions=full, ihara_closed=full, ihara_cut=cut,
                exact_fourier_identities=2, exact_character_indices=[0,40],
                n6_rows_I_omegaI_omega2I_M=exact_centres,
                trace_tolerance=2e-9, adjoint_trace_tolerance=2e-8)


if __name__ == '__main__':
    result=check()
    saved=Path(__file__).with_name('checks.json')
    if saved.is_file():
        assert json.loads(saved.read_text()) == result
    print(json.dumps(result, indent=2))
