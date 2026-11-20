"""Independent controls for the entropy, gauge and reader claims in the review."""
from collections import Counter, defaultdict
from itertools import combinations, permutations, product
from math import comb, exp, factorial, log, prod
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import json

import numpy as np


ANALYSIS = Path(__file__).resolve().parents[2]
spec = spec_from_file_location("r132", ANALYSIS / "R132_ADD_YM_CCM_20261119/verify.py")
r132 = module_from_spec(spec)
spec.loader.exec_module(r132)
engine, engine_sha = r132.load_engine()


def energies(length):
    return np.tile(2*np.abs(np.sin(np.pi*np.arange(length)/length)), 2)


def h(x):
    q = np.exp(-x)
    return np.log1p(q) + x*q/(1+q)


def fixed_p(es, p, beta):
    # Coefficients of product(1+z exp(-beta e)), and unnormalised energies.
    z = np.zeros(p+1)
    energy = np.zeros_like(z)
    z[0] = 1
    for e in es:
        w = exp(-beta*e)
        energy[1:] += w*(energy[:-1] + e*z[:-1])
        z[1:] += w*z[:-1]
    return log(z[p]) + beta*energy[p]/z[p]


def entropies():
    for l in range(1, 7):
        es = energies(l)
        for p in range(2*l+1):
            sums = np.array([sum(c) for c in combinations(es, p)])
            for beta in (0, 1, 4):
                weights = np.exp(-beta*sums)
                weights /= weights.sum()
                value = fixed_p(es, p, beta)
                assert np.isclose(value, -weights @ np.log(weights))
                deficit = log(comb(2*l, p))-value
                assert -1e-11 <= deficit <= 2*p*beta+1e-11
    return [{"L": l, "p": 2, "beta": 1, "uniform": log(comb(2*l, 2)),
             "fixed_p": fixed_p(energies(l), 2, 1), "all_p": float(h(energies(l)).sum())}
            for l in (3, 6, 100, 1000)]


def group_checks():
    group = list(permutations(range(3)))
    def mul(a, b):
        return tuple(a[i] for i in b)
    def inv(a):
        return tuple(a.index(i) for i in range(3))
    fibres = defaultdict(set)
    for a, b in product(group, repeat=2):
        fibres[mul(a, b)].add((a, b))
    for (a, b) in product(group, repeat=2):
        orbit = {(mul(a, c), mul(inv(c), b)) for c in group}
        assert fibres[mul(a, b)] == orbit
        assert (mul(a,b),group[0]) in orbit
    conjugacy = {frozenset(mul(mul(c,k),inv(c)) for c in group) for k in group}
    return {"labelled_pairs": 36, "local_gauge_orbits": len(fibres),
            "sizes": sorted(map(len, fibres.values())), "unbased_cycle_classes": len(conjugacy)}


def port_classes(w, shift):
    return tuple(sum((((v >> shift) & 1) | (((v >> (shift+2)) & 1) << 1)) == s
                     for v in w) for s in range(4))


def check_transition(w):
    p = sum(x.bit_count() for x in w)
    y = engine.word(engine.forward(engine.named(w), (1,-1)))
    assert sum(x.bit_count() for x in y) == p
    for shift in (0,1):
        assert port_classes(w, shift)[1:] == port_classes(y, shift)[1:]
    pairs = list(zip(w, w[1:]+w[:1]))
    assert len(y)-len(w) == w.count(3)+w.count(12)-pairs.count((1,2))-pairs.count((8,4))


def add_checks():
    for l in range(1, 4):
        counts = Counter()
        for w in product(range(16), repeat=l):
            check_transition(w)
            counts[port_classes(w,0), port_classes(w,1)] += 1
        for (a,b), n in counts.items():
            assert n == prod(factorial(l)//prod(factorial(x) for x in k) for k in (a,b))
    rng = np.random.default_rng(20261120)
    longer = set()
    while len(longer)<500:
        l = int(rng.integers(4,25))
        longer.add(tuple(map(int,rng.integers(16,size=l))))
    for w in longer:
        check_transition(w)
    witness = {}
    for text in ("120","021","120000","300000","01110212","01120211"):
        w = tuple(map(int,text))
        lengths = [len(w)]
        x = engine.named(w)
        for _ in range(2):
            x = engine.forward(x,(1,-1))
            lengths.append(len(x))
        witness[text] = lengths
    return {"full_alphabet_exhaustive": 4368, "long_distinct": len(longer), "lengths": witness}


def two_step_check():
    pats = ((1,2),(2,1),(2,1,2),(1,2,1),(2,1,2,1))
    checked = 0
    for l in range(1,9):
        # Coordinates identify each edge with its start, as in the parent report.
        S = np.eye(l,dtype=int) + r132.graph_operators(l)[l:,:l]
        closes = {len(pat):np.linalg.matrix_power(S.T,len(pat)-1) for pat in pats}
        for w in product(range(3),repeat=l):
            P = {s:np.diag(np.asarray(w)==s) for s in (1,2)}
            counts = []
            for pat in pats:
                mat = P[pat[0]]
                for s in pat[1:]:
                    mat = mat @ S @ P[s]
                counts.append(int(np.trace(mat @ closes[len(pat)])))
            a,b,c,d,e = counts
            first = engine.forward(engine.named(w),(1,-1))
            second = engine.forward(first,(1,-1))
            assert len(first)==l-a and len(second)==l-2*a+b+c+d-e
            checked += 1
    return checked


def phase_control():
    s = np.roll(np.eye(3),1,axis=1)
    lam = np.diag([1j,1,1])
    u = np.array([1j,1,-1j])
    original = s - np.eye(3)
    transformed = np.diag(u) @ s - np.eye(3)
    assert np.allclose(transformed,lam@original@lam.conj().T)
    assert np.prod(u)==1
    assert np.max(np.abs(transformed.conj()-lam@original.conj()@lam.conj().T))==2
    return 2


def reader_and_grading():
    w = np.array([1, 2, 0])
    D = r132.graph_operators(3)
    V, E = np.diag([1]*3+[0]*3), np.diag([0]*3+[1]*3)
    gamma = V-E
    I = np.eye(6,dtype=int)
    w_counts = {}
    for x in (w,w[::-1]):
        p1, p2 = [np.diag(np.tile(x == s,2)) for s in (1,2)]
        a, b = p1 @ D @ p2 @ D, p2 @ D @ p1 @ D
        assert np.array_equal(a @ gamma, gamma @ a)
        assert np.trace(E @ a) == np.trace(V @ b)
        w_counts[''.join(map(str,x))] = int(np.trace(V @ b))
    both = np.zeros_like(I)
    for site in np.eye(3,dtype=int):
        left = np.diag(np.tile(site,2))
        right = np.diag(np.r_[site,np.roll(site,-1)])
        both += left @ right
    assert np.array_equal(2*both-I, gamma)
    return w_counts


def scaling():
    # Hold size fixed and change temperature in the low-energy, large-volume regime.
    L = 512
    k = np.square(2*np.sin(np.pi*np.arange(L)/L))
    spectra = (np.sqrt(k), np.sqrt(k[:,None]+k[None,:]))
    return {str(d): {str(b):float(h(b*es).sum()) for b in (8,16,32)}
            for d,es in enumerate(spectra, start=1)}


if __name__ == "__main__":
    print(json.dumps(dict(engine_sha256=engine_sha, add=add_checks(), entropy=entropies(),
                          gauge=group_checks(), vertex_reader=reader_and_grading(),
                          two_step_words=two_step_check(), conjugation_error=phase_control(),
                          scalar_branch_512=scaling()),indent=2))
