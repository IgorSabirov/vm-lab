"""Finite field certificate for all additive nearest-neighbour C1 readouts."""
from itertools import product
import numpy as np

def insert(pivots, row, p=3):
    row = row.copy() % p
    for k in range(len(row)):
        if not row[k]:
            continue
        if k not in pivots:
            pivots[k] = (row * pow(int(row[k]), -1, p)) % p
            return True
        row = (row - row[k] * pivots[k]) % p
    return False

def pairs(w):
    return np.bincount([4*s + w[(i+1) % len(w)] for i,s in enumerate(w)], minlength=16)

def c1_step(w):
    start = int((w[-1],w[0]) == (1,2))
    out = []
    i = start
    while i < start + len(w):
        s = w[i % len(w)]
        if (s,w[(i+1)%len(w)]) == (1,2):
            out.append(3)
            i += 2
        else:
            out.extend((1,2) if s == 3 else (s,))
            i += 1
    return tuple((s&2) | (out[(i+1)%len(out)]&1) for i,s in enumerate(out))

def certificate(ref):
    pivots, witnesses, dims = {}, [], {}
    masks = np.array([[s&1, (s>>1)&1] for s in range(4)])
    # Integer bit charges of the tail, and telescoping differences of three vertex indicators.
    basis = np.array([[*masks[x], *(int(x==k)-int(y==k) for k in (1,2,3))]
                      for x,y in product(range(4),repeat=2)])
    span = {}
    for vec in basis.T:
        insert(span,vec)
    assert len(span) == 5
    total = 0
    for n in range(1,8):
        for w in product(range(4),repeat=n):
            v = c1_step(w)
            if n <= 5:
                assert ref['cyclic'](v) == ref['cyclic'](ref['word'](ref['forward'](ref['named'](w))))
            row = pairs(v) - pairs(w)
            assert not np.any((row @ basis) % 3)
            if insert(pivots,row):
                witnesses.append({'w':w,'next':v,'delta':row.tolist()})
            total += 1
        dims[n] = len(pivots)
    return dict(total=total,ranks_by_length=dims,rank=len(pivots),
                candidate_dimension=5,certifying_words=witnesses)

def c2(ref):
    eps = (1,-1)
    tested = 0
    mods = (2,3,4,5,7,9)
    def counts(w):
        return [sum(bool(s&bit) for s in w) for bit in (1,2,4,8)]
    for n in range(1,4):
        for w in product(range(16),repeat=n):
            x = ref['named'](w)
            f = ref['word'](ref['forward'](x,eps))
            t = ref['word'](ref['interact'](ref['r2'](x),eps))
            assert counts(w) == counts(f)
            assert counts(t) == counts(w)[::-1]
            for m in mods:
                assert (sum(f)-sum(w)) % m == 0
                assert sum((s&1)-((s>>1)&1)+((s>>2)&1)-((s>>3)&1) for s in [*w,*t]) % m == 0
            assert (sum(t)+sum(w)) % 3 == 0
            tested += 1
    return {'tested':tested,'moduli':mods,'T_reflects_mod3':True,'F_fixes_mod3':True}

A_PAIRS = ((2,1),(2,3),(3,1),(3,3))
B_PAIRS = ((1,2),(1,3),(3,2),(3,3))

def rails(s):
    return (s & 1) | ((s >> 1) & 2), ((s >> 1) & 1) | ((s >> 2) & 2)

def local14(x,y):
    ax,bx=rails(x)
    ay,by=rails(y)
    return tuple(int(bool(x & bit)) for bit in (1,2,4,8)) + (
        int(ax==3),int(bx==3)) + tuple(int((ax,ay)==p) for p in A_PAIRS) + tuple(
        int((bx,by)==p) for p in B_PAIRS)

def signature(w):
    return tuple(map(sum,zip(*(local14(x,w[(i+1)%len(w)]) for i,x in enumerate(w)))))

def c2_edge_certificate(ref):
    """Reduce whole batches modulo three. Keep independent original differences as witnesses."""
    eps = (1,-1)
    known = np.array([list(local14(x,y))+[int(x==k)-int(y==k) for k in range(1,16)]
                      for x,y in product(range(16),repeat=2)], dtype=np.int16)
    known_span = {}
    for v in known.T:
        insert(known_span,v)
    assert len(known_span)==29
    pivots, words, ranks = {}, [], {}
    def reduce_batch(states):
        rows = np.zeros((len(states),256), dtype=np.int16)
        for j,w in enumerate(states):
            v=ref['word'](ref['forward'](ref['named'](w),eps))
            for seq,sign in [(v,1),(w,-1)]:
                for k,s in enumerate(seq):
                    rows[j,16*s+seq[(k+1)%len(seq)]] += sign
        assert not np.any((rows @ known) % 3)
        rows %= 3
        active = np.ones(len(rows),dtype=bool)
        for k in range(256):
            nonzero = active & (rows[:,k] != 0)
            if not np.any(nonzero):
                continue
            if k not in pivots:
                idx = int(np.flatnonzero(nonzero)[0])
                pivots[k] = rows[idx]*pow(int(rows[idx,k]),-1,3) % 3
                words.append(states[idx])
                active[idx] = False
            rows[nonzero,k:] = (rows[nonzero,k:] - rows[nonzero,k,None]*pivots[k][k:]) % 3
    # Independent rows already prove the all-length upper bound if it meets the analytic lower bound.
    for n in range(1,5):
        chunk=[]
        for w in product(range(16),repeat=n):
            chunk.append(w)
            if len(chunk)==256:
                reduce_batch(chunk);chunk=[]
                if len(pivots)==227:
                    break
        if chunk: reduce_batch(chunk)
        ranks[n]=len(pivots)
        if len(pivots)==227: break
    return {'rank':len(pivots),'known_dimension':29,'ranks_by_length':ranks,'certifying_inputs':words}

def certify_independently(words, ref, channels):
    """A second elimination: exact SymPy domain arithmetic on the unmodified named engine."""
    from sympy import GF
    from sympy.polys.matrices import DomainMatrix
    p = GF(3)
    alphabet = 4**channels
    eps = (1,) if channels == 1 else (1,-1)
    rows = []
    for w in words:
        w = tuple(w)
        nxt = ref['word'](ref['forward'](ref['named'](w),eps))
        row = [0] * (alphabet ** 2)
        for state, sign in ((w,-1),(nxt,1)):
            for i,x in enumerate(state):
                row[alphabet*x+state[(i+1)%len(state)]] += sign
        rows.append(row)
    rank = DomainMatrix.from_list(rows,p).rank()
    assert rank == len(rows)
    return rank

def single_particle(ref):
    """Intrinsic rotations on anchored quiet rings, read once per two half-transports."""
    rows = {}
    for n in range(3,13):
        anchored=[u for u,_ in ref['named']((0,)*n)]
        def phase(state):
            assert set(u for u,_ in state)==set(anchored)
            ((u,s),)=[(u,s) for u,s in state if s]
            return (-anchored.index(u) if s==1 else anchored.index(u)) % n
        def two_steps(x):
            return ref['forward'](ref['forward'](x,(1,-1)),(1,-1))
        def reverse(x):
            return ref['interact'](ref['r2'](x),(1,-1))
        for particle in (1,8):
            for i in range(n):
                w=[0]*n;w[i]=particle
                x=ref['named'](w);seq=x;orbit=[phase(x)]
                for k in range(1,n+1):
                    seq=two_steps(seq)
                    orbit.append(phase(seq))
                    assert orbit[-1]==(orbit[0]+k)%n
                    assert phase(reverse(seq))==(-orbit[-1])%n
                    assert ref['equal'](seq,x)==(k==n)
                assert len(set(orbit))==n
        rows[n]={'inputs':2*n,'period_of_F2':n}
    return rows
