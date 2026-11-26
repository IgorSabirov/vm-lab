"""Run with Python 3, NumPy, SciPy and mpmath. Writes JSON to stdout.
word_rule.py is the verbatim R150 reference in the same directory.
"""
from collections import Counter, defaultdict
from functools import lru_cache
from itertools import product
from fractions import Fraction
import json
import math
import numpy as np
import mpmath as mp
from word_rule import I_word, F_word, transport_word, state_to_word


def canonical(w):
    # The unique bit 1 labels the origin at all lengths considered here.
    i = next(j for j, s in enumerate(w) if s & 1)
    return w[i:] + w[:i]


@lru_cache(None)
def single(w, c):
    pair = ((1, 2), (8, 4))[c]
    full = sum(pair)
    out = []
    for j, s in enumerate(w):
        if (w[j-1], s) == pair:
            continue
        if (s, w[(j+1) % len(w)]) == pair:
            out.append(full)
        elif s == full:
            out.extend(pair)
        else:
            out.append(s)
    return canonical(tuple(out))


def transport(w):
    return canonical(transport_word(w))


@lru_cache(None)
def branches(w, model):
    a, b = single(w, 0), single(w, 1)
    both = single(a, 1)
    assert both == single(b, 0) == canonical(I_word(w))
    assert single(a, 0) == single(b, 1) == w
    assert transport(both) == canonical(F_word(w))
    if model == 'shared':
        terms = [(w, 1-1j), (both, 1+1j)]
    else:
        # At z=-i the common amplitude denominator at every step is 2.
        terms = [(w, -1j), (a, 1), (b, 1), (both, 1j)]
    row = defaultdict(complex)
    for state, weight in terms:
        row[transport(state)] += weight
    assert sum(abs2(v) for v in row.values()) == 4
    return tuple((s, v) for s, v in row.items() if v)


def abs2(x):
    return int(x.real)**2 + int(x.imag)**2


def measure(probability, seed, t, active_layer):
    lengths = Counter()
    for s, mass in probability.items():
        lengths[len(s)] += mass
    total = 4**t
    assert sum(lengths.values()) == total
    return dict(lengths={k:str(Fraction(v,total)) for k,v in sorted(lengths.items())},
                same_length=str(Fraction(lengths[len(seed)],total)),
                initial_word=str(Fraction(probability.get(seed,0),total)),
                initial_layer=str(Fraction(sum(probability.get(w,0) for w in active_layer),total)))


def evolve(seed, model, active_layer, stop=24):
    psi = {seed:1+0j}
    mixed = {seed:1}
    records = {}
    for t in range(1, stop+1):
        nxt = defaultdict(complex)
        diag = Counter()
        for w, x in psi.items():
            for v, y in branches(w,model):
                nxt[v] += x*y
        for w, p in mixed.items():
            for v, y in branches(w,model):
                diag[v] += p*abs2(y)
        # Gaussian integer components <=2**24 here, exactly represented in binary64.
        psi = {w:x for w,x in nxt.items() if x}
        mixed = diag
        prob = {w:abs2(x) for w,x in psi.items()}
        records[t] = {'coherent':measure(prob,seed,t,active_layer),
                      'dephased_after_each_step':measure(mixed,seed,t,active_layer)}
    return records


def layer(L, u):
    v = (u-1) % L
    return [state_to_word((t,u,(v+t)%L),L) for t in range(L)]


def compressed_checks():
    rows = []
    z = -1j
    for L in range(3,25):
        Q = np.roll(np.eye(L),1,axis=0)
        plus = np.zeros(L)
        plus[:2] = 1/math.sqrt(2)
        minus = plus.copy()
        minus[1] *= -1
        target = Q @ (np.eye(L) + (z-1)*np.outer(minus,minus)
                      + ((1+z*z)/2-1)*np.outer(plus,plus))
        for u in range(2,L):
            states = layer(L,u)
            ix = {w:i for i,w in enumerate(states)}
            W = np.zeros((L,L),complex)
            for j,w in enumerate(states):
                for v,y in branches(w,'factorized'):
                    if v in ix:
                        W[ix[v],j] = y/2
            assert np.max(np.abs(target-W)) < 1e-14
        defect = np.eye(L)-W.conj().T@W
        assert np.max(np.abs(defect-np.outer(plus,plus))) < 1e-14
        spectrum = np.linalg.eigvals(W)
        dark = [v for v in spectrum if abs(abs(v)-1)<1e-10]
        assert len(dark) == int((L-2)%4 == 0)
        assert all(abs(v-1j)<1e-10 for v in dark)
        rows.append(dict(L=L,layer_count=L-2,peripheral=len(dark),
                         spectral_radius=float(np.max(np.abs(spectrum)))))
    return rows


def finite_spectral_tests():
    mp.mp.dps = 65
    cubic = {}
    for L in (7,9,15):
        arr = []
        for delta in map(mp.mpf, ('0.1', '0.01','0.001','0.0001')):
            z = -mp.exp(1j*delta)
            phi = -delta/2
            h = mp.exp(1j*phi)
            def p(x):
                return x**L+(z-1)*x**(L-1)/2+h*((z-1)*x/2-z)
            root = mp.findroot(p, -1)
            angle = mp.arg(-root)
            phi_star = -2*mp.atan(mp.tan(delta/2)/2)
            assert abs(mp.exp(1j*phi_star)-(3-z)/(1-3*z)) < mp.mpf('1e-60')
            arr.append(dict(delta=float(delta),shift=float(angle),
                            scaled=float(angle*(L-1)/delta**3),
                            compensation=float(phi_star)))
        cubic[L] = arr
    z = -1j
    A, B = (1+z)/2, (1-z)/2
    echo = {}
    for L in (5,7,9,12):
        vals = {}
        for phase in (0.,math.pi/4,math.pi/2,math.pi,5*math.pi/4):
            h = np.exp(1j*phase)
            Q = np.roll(np.eye(L,dtype=complex),1,axis=0)
            Q[0,-1] = h
            coin = np.eye(L,dtype=complex)
            coin[:2,:2] = [[A,B],[B,A]]
            W = Q@coin
            for t in range(L):
                assert abs(np.linalg.matrix_power(W,t)[1,1]-B**t) < 1e-12
            prob = abs(np.linalg.matrix_power(W,L)[1,1])**2
            markov = np.linalg.matrix_power(abs(W)**2,L)[1,1]
            assert abs(prob-abs(B**L+h*A**2)**2)<1e-12
            vals[phase]=[float(prob),float(markov)]
        echo[L]=dict(phase_probabilities=vals,minimum=(abs(B)**L-abs(A)**2)**2,
                     maximum=(abs(B)**L+abs(A)**2)**2)
    return dict(cubic_compensation=cubic,first_echo=echo)


def clock_protocol():
    import scipy.linalg as la
    records={}
    for L in (7,9):
        Q=np.roll(np.eye(L),1,axis=0)
        v=np.zeros(L); v[0]=1; v[1]=-1
        I=np.eye(L)-np.outer(v,v)
        F=Q@I
        # A specified Hermitian phase lift Q=exp(i Gq), I=exp(i Gi).
        Gq=np.zeros((L,L),complex)
        for k in range(L):
            w=np.exp(-2j*np.pi*k*np.arange(L)/L)/math.sqrt(L)
            Gq+=np.angle(np.exp(2j*np.pi*k/L))*np.outer(w,w.conj())
        Gi=np.pi*np.outer(v,v)/2
        assert np.max(np.abs(la.expm(1j*Gq)-Q)) < 1e-13
        assert np.max(np.abs(la.expm(1j*Gi)-I)) < 1e-13
        G=I.T@Gq@I+Gi
        cycle=[0,*range(2,L)]
        b=np.eye(L)[:,1]; s=np.zeros(L); a=np.zeros(L)
        s[cycle]=1/math.sqrt(L-1)
        a[cycle]=(-1.)**np.arange(L-1)/math.sqrt(L-1)
        E=np.column_stack([b,s])
        plus=np.linalg.eigvalsh(E.T@G@E)
        pi=(a@G@a).real
        eps=1e-6
        U=la.expm(1j*(1+eps)*Gq)@la.expm(1j*(1+eps)*Gi)
        roots=np.linalg.eigvals(U)
        small=sorted(np.angle(sorted(roots,key=lambda x:abs(x-1))[:2])/eps)
        p=np.angle(-min(roots,key=lambda x:abs(x+1)))/eps
        assert np.max(abs(plus-small))<2e-5 and abs(pi-p)<2e-5
        records[L]=dict(zero_slopes=plus.tolist(),pi_slope=pi,
                        finite_zero=small,finite_pi=p)
    return records


def detector_parity():
    # A diagonal word readout on the phase-sensitive superposition (s+a)/sqrt(2).
    checks={}
    for L in (5,7,9,15):
        n=L-1
        s=np.ones(n)/math.sqrt(n)
        a=(-1.)**np.arange(n)/math.sqrt(n)
        psi=(s+a)/math.sqrt(2)
        obs=(-1.)**np.arange(n)
        contrast=[float(np.dot(obs,np.roll(psi,t)**2)) for t in range(4)]
        checks[L]=dict(half_step_weight=2/n,contrast=contrast)
    return checks


if __name__=='__main__':
    checked=0
    for L in range(2,12):
        for key in product(range(L),repeat=3):
            w=state_to_word(key,L)
            branches(w,'factorized')
            checked+=1
    L=7; states=layer(L,4); seed=states[1]
    results={'reference_words_checked':checked,'seed':seed,'sizes_and_layers':compressed_checks(),
             'dynamics':{model:evolve(seed,model,states) for model in ('shared','factorized')},
             'spectra':finite_spectral_tests(),'clock':clock_protocol(),'readout':detector_parity()}
    print(json.dumps(results,indent=2,sort_keys=True))
