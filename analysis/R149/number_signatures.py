"""Exact counts and a finite-size spectral check for R149.02/.04/.07/.08.
Run with Python 3 and SymPy. Pass R149.html (default: the repo-root file).
"""
from collections import Counter
from itertools import product
from math import comb, cos, isclose, pi, sin, sqrt, tan
from pathlib import Path
import json
import re
import sys

import sympy as sp

html_path = Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parents[2]/'R149.html'
model = json.loads(re.search(r'<script[^>]*id="model"[^>]*>(.*?)</script>', html_path.read_text(), re.S)[1])

# D_l(2) from the atlas recurrence versus the Jacobsthal closed form.
d = [1,3]
for ell in range(2,30):
    d.append(5*d[-1]-4*d[-2])
assert d == [(2**(2*l+1)+1)//3 for l in range(len(d))]
pell=[0,1]
for n in range(2,20):
    pell.append(2*pell[-1]+pell[-2])
for n in range(2,20,2):
    assert sp.chebyshevt(n,3)-1 == 4*pell[n]**2
print("Jacobsthal odd indices:",d[:6],"Pell(6):",pell[6])

# First returns of the adjacency operator S + S* = 2I-H0 on Z.
first=[]
for k in range(1,8):
    total=0
    for path in product((-1,1), repeat=2*k):
        x=0
        for step in path[:-1]:
            x+=step
            if x==0:
                break
        else:
            total+=int(x+path[-1]==0)
    assert total == 2*comb(2*k-2,k-1)//k
    first.append(total)
print("First returns on the infinite chain:",first)

raw=sp.Matrix(model['checks']['raw']['transitions'])/3
rank=raw.rank()
assert raw.shape==(27,27) and rank==9
print("Lost complex dimensions / raw dimension:",sp.Rational(raw.cols-rank,raw.cols))

# The three physical holonomy sectors have equal identity action. Compare
# traceless complex commuting algebras with and without the sector labels.
def traceless_commutant(generator):
    entries=sp.symbols('a:9')
    matrix=sp.Matrix(3,3,entries)
    constraints=list(matrix*generator-generator*matrix)+[sp.trace(matrix)]
    return len(entries)-sp.linear_eq_to_matrix(constraints,entries)[0].rank()

assert model['checks']['raw']['neutral_rank']==3
assert traceless_commutant(sp.eye(3))==8 and traceless_commutant(sp.diag(0,1,2))==2
print("Traceless commutant dimensions for identity / holonomy labels:",8,2)

for length in [4,5,8,16,64,256]:
    energies=[2*sin(pi*k/length) for k in range(length)]*2
    band_mean=sum(energies)/(4*length)
    assert isclose(band_mean,1/(length*tan(pi/(2*length))),rel_tol=1e-14)
    multiplicities=Counter(round(x,12) for x in energies)
    cumulative=0
    shells=[]
    for e, count in sorted(multiplicities.items()):
        cumulative+=count
        shells.append(cumulative)
    print("L =",length,"mean energy / band edge =",round(band_mean,9),"first closures =",shells[:6])
print("Infinite-length normalized mean:",2/pi)
