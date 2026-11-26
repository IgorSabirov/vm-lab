"""Exact scan of the fixed H6 input. All updates below use Gaussian integers."""
from collections import Counter
from math import isqrt
from pathlib import Path
import json
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'input'))
from horizon import NamedGraphs

ZERO = (0,) * 6
START = (1, 0, 1, 0, 0, 0)
def norms(v):
    return tuple(v[i]**2 + v[i+1]**2 for i in (0, 2, 4))

def fourier(v):
    # Omit the common 1/sqrt(3). Two intensities are B +/- C*sqrt(3).
    total = sum(norms(v))
    A = sum(v[::2])**2 + sum(v[1::2])**2
    real = imag = 0
    for i in (0, 2, 4):
        j = (i+2) % 6
        real += v[j]*v[i] + v[j+1]*v[i+1]
        imag += v[j+1]*v[i] - v[j]*v[i+1]
    B, C = total-real, imag
    assert A+2*B == 3*total and B*B >= 3*C*C
    return A, B, C

def exact_fourier_koide(A, B, C):
    """Test the positive-root equation; handles zero components if trace > 0."""
    if A+2*B == 0:
        return False
    D = B*B - 3*C*C
    d = isqrt(D)
    if d*d != D:
        return False
    rem = A + 2*B - 4*d
    return rem >= 0 and rem*rem == 32*A*(B+d)

def add_move(old, v, a, b, length):
    # M e_j=e_(j+1), J e_j=e_(-j). Flattened re/im pairs.
    order = (4, 0, 2) if length == 2 else (0, 4, 2) if length == 3 else (0, 2, 4)
    w = list(old)
    for dst, src in zip((0, 2, 4), order):
        x, y = v[src:src+2]
        w[dst] += a*x - b*y
        w[dst+1] += a*y + b*x
    return tuple(w)

def archive_eight():
    fixture = json.loads((HERE/'input/inputs/HISTORIES.json').read_text())
    result = [ZERO for _ in fixture['named_endpoints']]
    for path in fixture['branches']:
        v = START
        for length in path['lengths']:
            v = add_move(ZERO, v, 1, 0, length)
        for endpoint, a, b in path['amplitudes']:
            result[endpoint] = add_move(result[endpoint], v, 16*a, 16*b, 0)
    return result

def run(steps=48):
    reference=json.loads((HERE/'input/horizons.json').read_text())
    fixture=json.loads((HERE/'input/inputs/HISTORIES.json').read_text())
    stored_eight=archive_eight()
    graph = NamedGraphs()
    initial = tuple((graph.intern(('atom',i)), x) for i,x in enumerate((1,2,0)))
    current = {initial:START}
    stats=[]
    for t in range(1,steps+1):
        following={}
        for g, v in current.items():
            for h,a,b in graph.moves(g):
                following[h] = add_move(following.get(h,ZERO),v,a,b,len(h))
        current=following
        if t==8:
            def immutable(x):
                return tuple(map(immutable,x)) if isinstance(x,list) else x
            def canonical(x):
                return min(x[i:]+x[:i] for i in range(len(x)))
            compare={canonical(tuple((graph.decode(u),b) for u,b in h)):v for h,v in current.items()}
            assert [compare[immutable(h)] for h in fixture['named_endpoints']]==stored_eight
        counters=Counter()
        stream_half=[]
        stream_q=[]
        for v, count in Counter(current.values()).items():
            pops=norms(v)
            N=sum(pops)
            if N==0:
                continue
            A,B,C=fourier(v)
            counters['nonzero']+=count
            counters['norm']+=count*N
            counters['singlet']+=count*A
            counters['character_positive']+=count*int(min(pops)>0)
            counters['holonomy_positive']+=count*int(A>0 and B*B>3*C*C)
            if 2*A==3*N:
                counters['p1_half']+=count
                stream_half.append(v)
            if exact_fourier_koide(A,B,C):
                counters['fourier_exact_Q']+=count
                stream_q.append(v)
        assert counters['norm']==2*4**t and counters['singlet']==4*4**t
        cols=('nonzero','character_positive','holonomy_positive','p1_half','fourier_exact_Q')
        row={'t':t,'ends':len(current),**{k:counters[k] for k in cols}}
        if stream_half: row['p1_examples']=stream_half[:2]
        if stream_q: row['fourier_Q_examples']=stream_q[:2]
        if t<=20:
            prev=reference[t-1]
            assert row['ends']==prev['ends']
            assert all(row[k]==prev['actual_input'][k] for k in cols[:4])
        stats.append(row)
    return stats

if __name__=='__main__':
    print(json.dumps(run(),indent=2))
