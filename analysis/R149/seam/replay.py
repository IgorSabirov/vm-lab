"""R149. Run with Python 3, NumPy and SymPy. No input files required."""
from itertools import combinations
from math import prod

import numpy as np
import sympy as sp


def fib(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def lucas(n):
    return 2 * fib(n + 1) - fib(n)


def runs_with_cut(bits):
    start = bits.index(0)
    strip = bits[start:] + bits[:start]
    return [len(run) for run in ''.join(map(str, strip)).split('0') if run]


def masked_difference(bits, seam):
    n, m = len(bits), len(seam)
    s = np.zeros((n*m, n*m), complex)
    for i in range(n):
        j = (i + 1) % n
        s[i*m:(i+1)*m, j*m:(j+1)*m] = np.eye(m) if j else seam
    mask = np.repeat(bits, m)
    return (s - np.eye(n*m)) * mask[:, None] * mask[None, :]


def kernel(bits, seam):
    b = masked_difference(bits, seam)
    return b @ b.conj().T


def norm_from_phases(n, phases):
    phases = np.mod(phases, 2*np.pi)
    return np.mean(np.cos((phases-np.pi)/(2*n))) / (n*np.sin(np.pi/(2*n)))


def check_closed_norm(n, seam, phases):
    b = masked_difference([1]*n, seam)
    measured = np.linalg.svd(b, compute_uv=False).mean() / 2
    assert abs(measured - norm_from_phases(n, phases)) < 1e-12


def random_unitary(m, rng):
    z = rng.normal(size=(m, m)) + 1j*rng.normal(size=(m, m))
    q, r = np.linalg.qr(z)
    d = np.diag(r)
    return q * (d / abs(d))


def seam_checks():
    rng = np.random.default_rng(20261125)
    full = cut = crossing = 0
    for n in range(3, 10):
        for phi in (0, np.pi/7, 2*np.pi/3, np.pi, 5*np.pi/3):
            check_closed_norm(n, np.array([[np.exp(1j*phi)]]), [phi])
        for m in (1, 2, 3, 5):
            seam = random_unitary(m, rng)
            phases = np.angle(np.linalg.eigvals(seam))
            check_closed_norm(n, seam, phases)
            for code in range(2**n):
                bits = [(code >> i) & 1 for i in range(n)]
                k = kernel(bits, seam)
                sign, ld = np.linalg.slogdet(np.eye(n*m) + k)
                if all(bits):
                    expected = np.log(lucas(2*n) - 2*np.cos(phases)).sum()
                    full += 1
                else:
                    expected = m * sum(np.log(float(fib(2*l+1))) for l in runs_with_cut(bits))
                    one = np.linalg.eigvalsh(kernel(bits, np.eye(1)))
                    assert np.allclose(np.linalg.eigvalsh(k), np.repeat(one, m), atol=1e-11, rtol=0)
                    cut += 1
                    crossing += int(bits[0] and bits[-1])
                assert abs(sign-1) < 1e-11 and abs(ld-expected) < 1e-10
    return full, cut, crossing


def c1_step(w):
    # Unlabelled projection of R130 C1. I merges 12 and splits 3.
    # Q transports the low bit from the next vertex, keeping the high bit.
    n = len(w)
    starts = {i for i in range(n) if (w[i], w[(i+1) % n]) == (1, 2)}
    ends = {(i+1) % n for i in starts}
    start = next(i for i in range(n) if i not in ends)
    v = []
    walked = 0
    while walked < n:
        i = (start + walked) % n
        if i in starts:
            v.append(3)
            walked += 2
        else:
            v.extend((1, 2) if w[i] == 3 else (w[i],))
            walked += 1
    return [(s & 2) | (v[(i+1) % len(v)] & 1) for i, s in enumerate(v)]


def local_counts(w):
    return w.count(3), sum((s, w[(i+1) % len(w)]) == (1, 2) for i, s in enumerate(w))


def gd_checks():
    records = {}
    for a, b in combinations(range(6), 2):
        d = min(b-a, 6-b+a)
        if d == 1:
            continue
        bits = [int(i not in (a, b)) for i in range(6)]
        counts = [sum((s, bits[(i+1) % 6]) == pair for i, s in enumerate(bits))
                  for pair in ((0,0), (0,1), (1,0), (1,1))]
        assert counts == [0, 2, 2, 2]
        k = sp.Matrix(kernel(bits, np.eye(1)).real.astype(int).tolist())
        orbit_sum = sum((k.extract([(i+h) % 6 for i in range(6)],
                                   [(i+h) % 6 for i in range(6)]) for h in range(6)), sp.zeros(6))
        w = [1+s for s in bits]
        states = [w]
        for _ in range(4):
            states.append(c1_step(states[-1]))
        row = ((sp.eye(6)+k).det(), tuple(map(len, states)), local_counts(states[3]))
        assert row == {2:(26, (6,4,6,8,9), (1,0)), 3:(25, (6,4,6,8,10), (2,0))}[d]
        assert (sp.eye(6)+orbit_sum/6).det() == sp.Rational(39200,729)
        records.setdefault(d, []).append(orbit_sum)
    assert len(records[2]) == 6 and len(records[3]) == 3
    assert all(x == records[2][0] for group in records.values() for x in group)
    return {d:len(group) for d, group in records.items()}


def exact_checks():
    for n in range(3,121):
        z = [fib(2*d-1) * fib(2*(n-d)-1) for d in range(1,n//2+1)]
        assert all(x > y for x,y in zip(z,z[1:]))
        for d,value in enumerate(z,1):
            assert 5*(fib(2*n-1)-value) == lucas(2*n)-lucas(2*(n-2*d))
    t = sp.symbols('t')
    ds = [1,1+t]
    for _ in range(4):
        ds.append(sp.expand((1+2*t)*ds[-1] - t**2*ds[-2]))
    def loss(a,b):
        return ds[a+b+1]-ds[a]*ds[b]
    assert sp.factor(loss(1,1)*loss(2,2)-loss(1,2)**2) == t**6*(t-1)
    for d in (18,19,20):
        print('n=40, d=', d, 'Z=', fib(2*d-1)*fib(2*(40-d)-1))
    print('Exact n=6 closed and cut readings:')
    for scalar in ((320,320,320),(320,323,323),(323,323,323),(89,)*3,(26,)*3,(25,)*3):
        print(scalar, prod(scalar))


if __name__ == '__main__':
    exact_checks()
    print('G-d labelled words per distance:', gd_checks())
    print('closed / cut / cut with active seam edge:', seam_checks())
