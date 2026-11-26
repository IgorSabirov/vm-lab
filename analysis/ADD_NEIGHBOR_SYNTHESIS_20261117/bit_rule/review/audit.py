"""Exact audit of the two reviews. Run from any directory with Python and SymPy."""
import json
import sys
from itertools import product
from math import gcd
from pathlib import Path
from runpy import run_path

import sympy as sp

ANALYSIS = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ANALYSIS / "R141_RIEMANN_CORPUS" / "donor_replay"))
import previous as donor

I = sp.eye(3)
M = I[:, [1, 2, 0]]
J = I[:, [0, 2, 1]]
omega = (-1 + sp.I * sp.sqrt(3)) / 2
hval = [1, omega, omega.conjugate()]
D = sp.diag(*hval)
P = sp.ones(3) / 3
F = sp.Matrix([[hval[i*j % 3] / sp.sqrt(3) for j in range(3)] for i in range(3)])
c = sp.Matrix([1, 1, 0]) / sp.sqrt(2)
psi = sp.Matrix([1+h for h in hval]) / sp.sqrt(6)

def simple(x):
    return sp.simplify(sp.expand_complex(x))

def same(x, y):
    diff = x-y
    if isinstance(diff, sp.MatrixBase):
        assert diff.applyfunc(simple) == sp.zeros(*diff.shape)
    else:
        assert simple(diff) == 0

def value(x, projector):
    return simple((x.H * projector * x)[0])

def endpoint_vector(ordered):
    """Keep all three character amplitudes while advancing every reachable graph."""
    state = {donor.start: [donor.h.ONE, donor.h.ONE, donor.h.ZERO]}
    for _ in range(8):
        advanced = donor.geometry_step(state)
        state = {}
        for graph, vector in advanced.items():
            if ordered and len(graph) == 2:
                vector = [vector[2], vector[0], vector[1]]
            elif ordered and len(graph) == 3:
                vector = [vector[0], vector[2], vector[1]]
            state[graph] = vector
    numerator = state[donor.ends[19]]
    return sp.Matrix([a + sp.I*b for a,b in numerator]) / (donor.h.DEN*sp.sqrt(2))


def paths_and_readings():
    same(F.H * F, I)
    same(F*c, psi)
    same(F*M*F.H, D)
    same(F*P*F.H, I[:,0]*I[:,0].H)
    same(F*J*F.H, J)
    akey, bkey = (3,3,3,2,2,2,2,2), (2,2,2,2,3,3,3,2)
    data = donor.h.table
    a, b = [next((r+sp.I*j)/16 for row in data["branches"] if tuple(row["lengths"])==key
                  for g,r,j in row["amplitudes"] if g==19) for key in (akey,bkey)]
    same(a*b.conjugate(), -sp.Rational(1,128))
    def history_op(key):
        u=I
        for length in key:
            u=({2:M, 3:J}[length])*u
        return u
    ua, ub = history_op(akey), history_op(bkey)
    same(ub.H*ua, M)
    result = {}
    effects = {'all':I,'h=1':P, 'h=omega':F.H*sp.diag(0,1,0)*F,
               'h=omega^2':F.H*sp.diag(0,0,1)*F}
    for label,(u,v) in {'flat':(I,I),'H6':(ua,ub)}.items():
        row={}
        x,y=a*u*c,b*v*c
        for sector,eff in effects.items():
            ma,mb,total=[value(z,eff) for z in (x,y,x+y)]
            cross=simple(total-ma-mb)
            xf,yf=F*x,F*y
            pe=F*eff*F.H
            same(value(xf+yf,pe)-value(xf,pe)-value(yf,pe),cross)
            row[sector]={'mu_A':str(ma),'mu_B':str(mb),'P19':str(total),'I2':str(cross)}
        for key in row['all']:
            assert sum(sp.Rational(row[g][key]) for g in list(effects)[1:])==sp.Rational(row['all'][key])
        propagated=endpoint_vector(label=='H6')
        same(propagated,x+y)
        for sector,eff in effects.items():
            same(value(propagated,eff),sp.Rational(row[sector]['P19']))
        rule='ordered' if label=='H6' else 'flat'
        full=donor.field_distribution(rule,[donor.h.ONE,donor.h.ONE,donor.h.ZERO])
        assert sum(full)==1 and str(full[19])==row['all']['P19']
        result[label]=row
    expected={'flat':('-1/64','-1/96','-1/384'), 'H6':('-1/128','-1/96','1/768')}
    for key,(all_,zero,other) in expected.items():
        assert [result[key][h]['I2'] for h in effects]==[all_,zero,other,other]
    mismatch=value(psi,M)
    same(simple(sp.re(mismatch)),sp.Rational(1,4))
    same(value(psi,P),sp.Rational(1,2))
    same(value(c,P),sp.Rational(2,3))
    same(value(c,M),sp.Rational(1,2))
    same(value(psi,D),sp.Rational(1,2))
    same((M+M.H)/2,(3*P-I)/2)
    return {'two_arm_events':result,'p1_correct':str(value(c,P)),
            's_correct':str(value(c,M)),'p1_mismatched':str(value(psi,P)),
            's_mismatched':str(mismatch),'I2_mismatched':str(simple(-sp.re(mismatch)/64)),
            'direct_graph_probabilities_verified':True}

def general_dimension():
    rows={}
    for m in range(2,25):
        step=sp.eye(m)[:,[(k+1)%m for k in range(m)]]
        reflect=sp.eye(m)[:,[(-k)%m for k in range(m)]]
        ua=step**5*reflect; ub=step*reflect*step**4
        r=ub.T*ua;assert r==step**(-8)
        d=gcd(m,8);q=m//d
        assert len((r-sp.eye(m)).nullspace())==d
        assert r**q==sp.eye(m)
        rows[m]={'fixed_dimension':d,'order':q,'number_of_distinct_real_parts':1+q//2}
    return rows

def position():
    ref=run_path(str(ANALYSIS/'ADD_NEIGHBOR_SYNTHESIS_20261117/verify.py'))
    states = list(product((1,8),range(3)))
    named = [ref['named'](tuple(p if j==i else 0 for j in range(3))) for p,i in states]
    def perm(op):
        indices = [next(i for i,y in enumerate(named) if ref['equal'](op(x),y)) for x in named]
        return sp.eye(6)[:,indices]
    f=lambda x:ref['forward'](x,(1,-1))
    s=perm(lambda x:f(f(x)))
    t=perm(lambda x:ref['interact'](ref['r2'](x),(1,-1)))
    W=sp.zeros(3,6)
    for j,(p,i) in enumerate(states):
        W[(-i if p==1 else i)%3,j]=1/sp.sqrt(2)
    same(W*W.H,I);same(W*s,M*W);same(W*t,J*W)
    assert W.rank()==3 and W.H*W!=sp.eye(6)
    same(M*P,P);same(J*P,P)
    K=P+sp.Rational(1,2)*(I-P)
    obs=-(K.H*(M+M.H)*K)/128
    same(obs,(-2*P+sp.Rational(1,4)*(I-P))/128)
    clock1=I[:,0]
    pos_omega=sp.Matrix([1,omega.conjugate(),omega])/sp.sqrt(3)
    pos_omegabar=pos_omega.conjugate()
    for vec in (pos_omega,pos_omegabar):
        same(value(vec,obs),sp.Rational(1,512))
    assert clock1!=sp.ones(3,1)/sp.sqrt(3)
    return {'W_times_sqrt2':(W*sp.sqrt(2)).tolist(),'full_C2_dimension':6,'quotient_dimension':3,
            'doublet_I2_after_common_half_amplitude':'1/512',
            'phase_probe_pi_over_2_I2': [str(simple(-sp.re(sp.I*value(v,M))/64)) for v in (pos_omega,pos_omegabar)]}

def seam():
    import geometry
    z0=320
    vals={}
    for name,phase in {'real_pair':[-1,-1,1],'imaginary_pair':[sp.I,sp.I,-1]}.items():
        H=sp.diag(*phase)
        assert H.det()==1
        ds=[simple(abs(v-1)**2) for v in phase]
        assert sum(ds)==8
        vals[name]={'D':8,'I2_mixed':'1/192','Z6':int(sp.prod(z0+t for t in ds))}
    assert vals['real_pair']['Z6']!=vals['imaginary_pair']['Z6']
    # Direct determinant on permutation covers, without floating arithmetic.
    import numpy as np
    checks=0
    monodromy = sp.Matrix([[2, 1], [1, 1]])  # R146: square of the Fibonacci matrix.
    for m in range(1,7):
        eye=np.eye(m,dtype=int);shift=np.roll(eye,1,axis=0)
        for n in range(3,7):
            cover = geometry.ring((1,)*n,[eye]*(n-1)+[shift])
            assert cover == geometry.luc(2*m*n)-2
            assert cover == abs((monodromy**(m*n) - sp.eye(2)).det())
            checks+=1
    g=sp.diag(*([1]*18))
    for k in (0,1):g[3*k:3*k+3,3*k:3*k+3]=M.H
    mask=sp.diag(*[s for s in (1,1,0,1,1,1) for _ in range(3)])
    def kernel(h):
        shift=sp.zeros(18)
        for i in range(6):
            j=(i+1)%6
            shift[3*j:3*j+3,3*i:3*i+3]=h if j==0 else I
        b=mask*(shift-sp.eye(18))*mask
        return b*b.H
    km,ki=kernel(M),kernel(I)
    assert max(abs(k) for k in km-ki)==1 and g*km*g.H==ki
    return {'same_D_counterexample':vals,'exact_regular_covers':checks,'m6_n6':geometry.luc(72)-2,
            'gauge_residual_before_after':[1,0]}

if __name__=='__main__':
    print(json.dumps({'events':paths_and_readings(),'relative_shift':general_dimension(),
                      'C2_intertwiner':position(),'seam':seam()},ensure_ascii=False,indent=2,default=str))
