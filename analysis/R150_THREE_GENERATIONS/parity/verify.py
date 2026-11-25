"""Run in the extracted directory: python verify.py (Python 3 + SymPy)."""
from collections import Counter
from fractions import Fraction
from itertools import combinations, product
from pathlib import Path
import contextlib
import io
import json
import sys
import sympy as sp

from h6_scan import run, fourier, exact_fourier_koide
from input import replay
from step5 import trace, gaps_between_marks

ROOT = Path(__file__).resolve().parent
F = sp.Matrix([[1,1],[1,0]])
R = sp.Matrix([[1,1],[0,1]])
states=[(1,0),(1,1),(0,1)]
def action(A,v):
    return tuple(int(x)%2 for x in A*sp.Matrix(v))

def rank_mod2(rows):
    pivots = {}
    for x in rows:
        while x:
            index=x.bit_length()-1
            if index not in pivots:
                pivots[index]=x
                break
            x ^= pivots[index]
    return len(pivots)

def rank_mask(w):
    n=len(w)
    B=[]
    for i in range(n):
        j=(i+1)%n
        B.append(((1<<i) ^ ((w[j])<<j)) if w[i] else 0)
    rows=[(1<<i)^sum((((b&c).bit_count()%2)<<j) for j,c in enumerate(B)) for i,b in enumerate(B)]
    return rank_mod2(rows)

def active_runs(w):
    k=w.index(0)
    return [len(s) for s in ''.join(map(str,w[k:]+w[:k])).split('0') if s]

def check():
    prior=io.StringIO()
    with contextlib.redirect_stdout(prior):
        replay.parity_orbit(); replay.marked_rings(); replay.seam()
    assert prior.getvalue()==(ROOT/'input/results.txt').read_text()
    mods={tuple(x%2 for x in A) for A in (sp.eye(2),F,F**2,R,R*F,R*F**2)}
    assert len(mods)==6
    assert [states.index(action(F,v)) for v in states]==[1,2,0]
    assert [states.index(action(R,v)) for v in states]==[0,2,1]
    bit_words=[''.join(str((a*x+b*y)%2) for x,y in states) for a,b in [(1,0),(0,1),(1,1)]]
    assert bit_words==['110','011','101']
    counts={}
    for n in range(3,13):
        odds=0
        for w in product(range(2),repeat=n):
            r=rank_mask(w)
            if all(w):
                assert n-r==(2 if n%3==0 else 0)
                S=sp.eye(n)[:,list(range(1,n))+[0]]
                assert (3*sp.eye(n)-S-S.T).det()==(F**(2*n)).trace()-2
                pred=n%3!=0
            else:
                pred=all(k%3!=1 for k in active_runs(w))
            assert (r==n)==pred
            odds+=int(pred)
        counts[n]=odds
    ring_stats=[]
    for n in range(6,21):
        outcomes=Counter()
        for a,b in combinations(range(n),2):
            w=tuple(int(i in (a,b)) for i in range(n))
            gaps=gaps_between_marks(w)
            if min(gaps)>=2:
                L=trace(w)[-1]['length']
                assert L==n+6-gaps.count(2)
                outcomes[L]+=1
        if n>=7:
            assert outcomes[n+5]==n and sum(outcomes.values())==n*(n-5)//2
        ring_stats.append(dict(n=n,L5=dict(outcomes)))
    parity_table={k:(3*k-2*(k%2))%4 for k in range(4)}
    assert parity_table=={0:0,1:1,2:2,3:3}
    for v in product(range(4),repeat=3):
        k=sum(x%2 for x in v)
        assert (3*sum(x*x for x in v)-2*sum(v)**2)%4==k%4
    # Positive Fourier control and a signed false positive.
    good=fourier((10,0,7,1,7,-1))
    signed=fourier((2,0,1,1,1,-1))
    edge=fourier((2,0,-1,1,-1,-1))
    assert good==(576,12,6) or good==(576,12,-6)
    assert exact_fourier_koide(*good) and not exact_fourier_koide(*signed)
    assert exact_fourier_koide(*edge)
    # Independently compare the integer criterion to a radical calculation.
    checks=[]
    for v in ((1,0,1,0,0,0),(10,0,7,1,7,-1),(2,0,-1,1,-1,-1),(2,0,1,1,1,-1),
              (1,2,3,-1,2,0),(1,1,1,1,1,1),(0,0,1,0,-1,0)):
        a,b,c=fourier(v)
        m=[a,b+c*sp.sqrt(3),b-c*sp.sqrt(3)]
        qflag=sp.simplify(3*sum(m)-2*sum(sp.sqrt(x) for x in m)**2).equals(0)
        assert qflag==exact_fourier_koide(a,b,c)
        checks.append(bool(qflag))
    candidates=[]
    for d in range(1,11):
        for a,b in product(range(-d,d+1),repeat=2):
            if 2*(a*a+b*b)!=d*d: continue
            eig=[d+2*a,d-a+b*sp.sqrt(3),d-a-b*sp.sqrt(3)]
            if min(eig)>0 and len(set(eig))==3: candidates.append((d,a,b))
    assert {d for d,_,_ in candidates}=={10}
    horizons=run(48)
    assert horizons==json.loads((ROOT/'h6_results.json').read_text())
    totals={key:sum(h[key] for h in horizons) for key in horizons[0] if key not in ('t',)}
    return dict(bit_words=bit_words,group_order=len(mods),binary_rings=sum(2**n for n in counts),
                odd_determinants_by_n=counts,marked=ring_stats,mod4_residues=parity_table,
                independent_fourier_controls=checks,positive_integer_examples_up_to_d10=candidates,
                H6_totals=totals)
if __name__=='__main__':
    print(json.dumps(check(),indent=2))
