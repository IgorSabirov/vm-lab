"""Physical-sector, raw-matrix and ordered-history controls."""
from itertools import product
from math import gcd
from pathlib import Path
import json
import re
import runpy
import numpy as np
import sympy as sp
from geometry import ring,luc

A=(3,3,3,2,2,2,2,2)
B=(2,2,2,2,3,3,3,2)
ANALYSIS = Path(__file__).resolve().parents[3]

def paths(m):
    ident=np.eye(m,dtype=int)
    M=ident[:,[(i+1)%m for i in range(m)]]
    J=ident[:,[(-i)%m for i in range(m)]]
    def gates(path):return [M if k==2 else J for k in path]
    def compose(gs):
        out=ident
        for g in gs:out=g@out
        return out
    a,b=compose(gates(A)),compose(gates(B))
    return M,J,a,b,gates,compose

def history():
    data=json.loads((ANALYSIS/'R140_HAAR_SORKIN/HISTORIES.json').read_text())
    arms={tuple(row['lengths']):(re,im) for row in data['branches'] for idx,re,im in row['amplitudes'] if idx==19}
    assert arms=={A:(-1,1),B:(1,-1)} and data['amplitude_denominator']=='sqrt(256)'
    orders={}
    for m in range(2,16):
        M,J,a,b,_,_=paths(m);R=b.T@a
        assert np.array_equal(R,np.linalg.matrix_power(M.T,8))
        order=next(i for i in range(1,m+1) if np.array_equal(np.linalg.matrix_power(R,i),np.eye(m)))
        assert order==m//gcd(m,8)
        orders[m]=order
    M,J,a,b,gates,compose=paths(3)
    # Each oriented arc carries the individual history gates. S has forward column transport reversed.
    loop=gates(A)+[g.T for g in reversed(gates(B))]
    assert np.array_equal(compose(loop),M)
    links=[g.T for g in loop]  # S maps the next vertex frame back to the previous one.
    w=[1]*16
    closed=ring(w,links)
    l=luc(32)
    assert closed==(l-2)*(l+1)**2
    cuts=[]
    for i in range(16):
        mask=w.copy();mask[i]=0
        cuts.append(ring(mask,links))
        assert cuts[-1]==ring(mask,[np.eye(3,dtype=int)]*16)
    I=sp.eye(3);u,v=sp.Matrix(a),sp.Matrix(b);g=sp.Matrix(M)
    e=I[:,0];plus=sp.ones(3,1);omega=(-1+sp.sqrt(3)*sp.I)/2
    fourier=sp.Matrix([1,sp.conjugate(omega),omega])
    states={'e0':e*e.H,'mix':I/3,'uniform_pure':plus*plus.H/3,'M_eigen_omega':fourier*fourier.H/3}
    table=[]
    for kind,r in [('I',I),('M',g),('Minv',g.T)]:
        for name,rho in states.items():
            overlap=sp.simplify(sp.trace(rho*r))
            delta=sp.simplify(r*rho*r.H-rho)
            dist=sp.simplify(sum(abs(value)*k for value,k in delta.eigenvals().items())/2)
            for eta in (0,sp.Rational(1,2),1):
                defect=sp.simplify(-eta*sp.re(overlap)/64)
                table.append(dict(field=name,relative=kind,eta=str(eta),s=str(overlap),D_field=str(dist),
                                  I2=str(defect),P19=str(sp.Rational(1,64)+defect)))
    return {'orders':orders,'spacetime_loop_det':closed,'all_16_single_cuts':cuts,'visibility':table}

def raw(ref):
    atlas = (ANALYSIS / "R149_DEFECT_ATLAS" / "R149.html").read_text()
    model = re.search(r'<script\b[^>]*\bid="model"[^>]*>(.*?)</script>', atlas, re.S)
    if model is None:
        raise ValueError("Missing R149 atlas model")
    data = json.loads(model.group(1))["checks"]["raw"]
    hub=runpy.run_path(str(ANALYSIS/'R140_HAAR_SORKIN/verify.py'))
    g=ref['named']((1,2,12))
    _,counts,lift=hub['raw_transition'](g)
    states=list(product(range(3),repeat=3))
    # Each old triple (a,b,c) goes to the three triples (a+b,t,c-t).
    exact=sp.Matrix([[int(x[0]==(y[0]+y[1])%3 and (x[1]+x[2])%3==y[2])
                      for y in states] for x in states])
    assert np.array_equal(np.array(exact,dtype=int),3*lift)
    assert exact==sp.Matrix(data['transitions']) and counts==[1,1]
    sectors=[]
    for h in range(3):
        idx=[i for i,x in enumerate(states) if sum(x)%3==h]
        sectors.append(exact.extract(idx,idx).rank())
    phys=sp.Matrix([[int(sum(x)%3==h) for h in range(3)] for x in states])/3
    assert (exact/3)*phys==phys and phys.T*phys==sp.eye(3)
    # Dropping an interior link and composing it into its neighbour are different operations.
    counter=[(x,(x[0]+x[1])%3) for x in product(range(3),repeat=2) if x[1]!=0]
    assert all(sum(x)%3==new for x,new in counter)
    return {'entries':729,'mismatches':0,'nonzero':sum(int(x!=0) for x in exact),
            'rank':exact.rank(),'ranks_fixed_h_raw':sectors,'gauge_invariant_dim':3,
            'physical_action':'identity','nonzero_internal_link_control':len(counter)}
