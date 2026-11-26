"""R149 v0.3. Reproduce the new observations from the pinned corpus, offline."""
import argparse
import json
import sys
from collections import Counter
from fractions import Fraction
from itertools import product
from pathlib import Path

import mpmath as mp
import sympy as sp

HERE = Path(__file__).resolve().parent
ANALYSIS = HERE.parent
# A standalone kit supplies the same corpus files beside this script.
BASE = HERE / 'inputs' if (HERE/'inputs/R141_R148_MODEL').is_dir() else ANALYSIS
MODEL = BASE/'R141_R148_MODEL'
sys.path[:0] = [str(MODEL/'code'), str(MODEL/'name_arithmetic'), str(MODEL/'ym_graph/step5')]
import r130_reference as ref
import check as step5
import replay as names_replay

def decimal(x, places=16):
    return mp.nstr(x,places,strip_zeros=False)

def circular_delta(a):
    return mp.atan2(mp.sin(a),mp.cos(a))

def winding(vertices):
    val = [mp.zeta(z) for z in vertices]
    changes = [mp.arg(b/a) for a,b in zip(val,val[1:]+val[:1])]
    w = sum(changes)/(2*mp.pi)
    assert abs(w-mp.nint(w))<mp.mpf('1e-23') and max(map(abs,changes))<mp.pi*.92
    phase=[0.]
    acc=mp.mpf(0)
    for d in changes:
        acc+=d/(2*mp.pi);phase.append(round(float(acc),7))
    return int(mp.nint(w)),float(max(map(abs,changes))),float(min(map(abs,val))),phase

def contours():
    zeros=[mp.zetazero(i) for i in range(1,4)]
    records=[]
    def check(label,expected,path):
        grids=[winding(path(n)) for n in (96,192)]
        assert all(x[0]==expected for x in grids)
        records.append(dict(label=label,wind=expected,grids=[96,192],max_phase_step=[round(x[1],8) for x in grids],min_boundary_abs=round(grids[1][2],10),phase_turns=grids[1][3]))
    for label,center,r,w in [('ρ₁',zeros[0],r,w) for r,w in [(.3,1),(.5,1),(2,1),(4,1),(7,2)]]+[('Полюс 1',1,.5,-1),('Нуль −2',-2,.5,1)]:
        check(f'{label} · r={r}',w,lambda n:[center+r*mp.expj(2*mp.pi*k/n) for k in range(n)])
    cs=[mp.mpc('.2',1),mp.mpc('.8',1),mp.mpc('.8',26),mp.mpc('.2',26)]
    check('Прямоугольник [0,2; 0,8] × [1; 26]',3,lambda n:[a+(b-a)*k/n for a,b in zip(cs,cs[1:]+cs[:1]) for k in range(n)])
    phase=[]
    for t in (10,14,14.3,20):
        t=mp.mpf(str(t));z=mp.zeta(.5+1j*t);th=mp.siegeltheta(t);Z=mp.expj(th)*z
        err=abs(circular_delta(mp.arg(z)+th-mp.pi*int(Z.real<0)))
        assert abs(Z.imag)<mp.mpf('1e-28') and err<mp.mpf('1e-27')
        phase.append(dict(t=float(t),Z=decimal(Z.real),error=decimal(err)))
    # The standard S(T) follows the continuous branch along 2,2+iT,1/2+iT.
    counts=[]
    for t,expected in [(14,0),(20,1),(26,3),(50,10),(100,29)]:
        for subdivisions in [64,128]:
            path=[2+1j*mp.mpf(t)*k/subdivisions for k in range(subdivisions+1)]
            path.extend(2+1j*t-mp.mpf('1.5')*k/subdivisions for k in range(1,subdivisions+1))
            zz=[mp.zeta(z) for z in path]; arg=sum(mp.arg(b/a) for a,b in zip(zz,zz[1:]))
            n=mp.siegeltheta(t)/mp.pi+1+arg/mp.pi
            assert abs(n-expected)<mp.mpf('1e-23') and int(mp.nzeros(t))==expected
        counts.append(dict(t=t,theta_over_pi=decimal(mp.siegeltheta(t)/mp.pi),S=decimal(arg/mp.pi),N=expected))
    return dict(ordinates=[decimal(z.imag) for z in zeros],contours=records,hardy=phase,counts=counts)

def modular():
    def completed(s):return mp.pi**(-s/2)*mp.gamma(s/2)*mp.zeta(s)
    def phi(s):return completed(2*s-1)/completed(2*s)
    uni=[]
    for t in [1,5,mp.im(mp.zetazero(1))/2,10,14]:
        v=phi(mp.mpc('.5',t));assert abs(abs(v)-1)<mp.mpf('1e-27')
        uni.append([decimal(t),decimal(abs(v)),decimal(mp.arg(v))])
    s=mp.mpc('.7','3')
    assert abs(phi(s)*phi(1-s)-1)<mp.mpf('1e-27')
    for t in (3,9,17):assert abs(circular_delta(mp.arg(phi(mp.mpc('.5',t)))-2*mp.arg(completed(2j*t))))<mp.mpf('1e-27')
    rho=mp.zetazero(1);res=completed(rho-1)/(2*mp.diff(completed,rho))
    tails=[]
    for e in ('.05','.01','.002','.0001'):
        v=phi(rho/2+mp.mpf(e));tails.append([e,decimal(abs(v)),decimal(abs(mp.mpf(e)*v/res-1))])
    assert float(tails[-1][-1])<.001
    src=(BASE/'NOW_RESULTS_SYNTHESIS_20261106/R147.json').read_text()
    for term in ['2,9546326624','0,6525249472']:assert term in src or term.replace(',','.') in src
    ang=mp.mpf('2.9546326624')-mp.mpf('.6525249472');d=mp.expj(ang);shift=-ang/(2*mp.pi)
    return dict(unitary=uni,pole=[decimal(rho.real/2),decimal(rho.imag/2)],pole_probes=tails,
                r147=dict(phase_sum=decimal(ang),det=[decimal(d.real),decimal(d.imag)],shift=decimal(shift),mod1=decimal(shift%1),gap_to_2_over_pi=decimal(2/mp.pi-shift%1)))

def dynamics():
    actual=step5.verify();stored=json.loads((MODEL/'ym_graph/step5/results.json').read_text())
    assert json.loads(json.dumps(actual))==stored
    weights=Counter()
    for w in product((0,1),repeat=8):
        gaps=step5.gaps_between_marks(w)
        if len(gaps)==2 and min(gaps)>=2:weights[step5.trace(w)[5]['length']]+=1
    assert weights=={13:8,14:4}
    cycles=names_replay.closed_sector()
    by_period={int(k):int(v) for k,v in cycles['primitive_cycles'].items()}
    assert by_period=={2:4,10:204}
    n=sum(k*v for k,v in by_period.items());fix=[sum(k*v for k,v in by_period.items() if j%k==0) for j in range(1,31)]
    for j,points in enumerate(fix,1):
        coeff=sum(Fraction(-v,j//k) for k,v in by_period.items() if j%k==0)
        assert coeff==Fraction(-points,j)
    z=sp.symbols('z');p=sp.Poly((1-z**2)**4,z)*sp.Poly((1-z**10)**204,z)
    cc=p.all_coeffs();assert cc==cc[::-1] and p.degree()==n
    mult=[sum(v for period,v in by_period.items() if k*period%10==0) for k in range(10)]
    assert mult==[208,204,204,204,204,208,204,204,204,204]
    x=ref.named((1,2,12));initial=x;shapes=[];sizes=[]
    def node_size(u):
        stack=[u];size=0
        while stack:
            v=stack.pop();size+=1
            if v[0]=='v':stack.extend(v[1:])
            elif v[0] in ('l','r'):stack.append(v[1])
        return size
    linear_period=None
    for t in range(201):
        w=ref.word(x);assert ref.cyclic(w)==(1,2,12)
        if t<=6:shapes.append(w)
        if t and w==ref.word(initial) and linear_period is None:linear_period=t
        u=next(n for n,v in x if v==12)
        k=node_size(u);assert k==(2*t+5 if t else 1)
        if t in (0,1,2,3,10,100,200):sizes.append([t,k])
        x=ref.forward(x,(1,-1))
    return dict(pair=actual['target_pair'],outside=actual['outside_domain'],family=actual['counts'],uniform_labelled=dict(weights),
        sector=dict(states=n,cycles=by_period,degree=n,multiplicities=mult,fix=fix,reciprocal=True),
        name=dict(size=sizes,canonical_period=1,list_return=linear_period,raw_words=shapes,nonreturns=200))

def geometry():
    M=sp.Matrix([[1,1],[1,0]]);C=sp.Matrix([[0,1],[-1,2]]);T=sp.Matrix([[3,-1],[1,0]])
    assert C.det()==1 and T==C*M**2*C.inv() and T.trace()==3
    L=sp.Matrix([[1,1],[0,1]]);R=sp.Matrix([[1,0],[1,1]])
    assert L*R==M**2 and (L**2*R).trace()==4
    S3=sp.Matrix([[-2,1],[1,2]]);S4=sp.Matrix([[-2,1],[1,1]])
    assert T.det()==1 and M.T*S3*M==-S3 and (M**2).T*S3*M**2==S3
    assert S3.det()==-5 and S4.det()==-3
    primary=json.loads((BASE/'R141_R147_MODEL/evidence/r147_hyperbolic_clifford_results.json').read_text())
    assert sp.Matrix(primary['lorentz']['S']).applyfunc(sp.sympify)==S3
    for q,S in [(3,S3),(4,S4)]:
        A=sp.Matrix([[q-1,1],[q-2,1]])
        assert A.det()==1 and A.T*S*A==S
        raw=json.loads((MODEL/'results/extensions.json').read_text())['integral_forms'][str(q)]['S']
        assert S==sp.Matrix(raw).applyfunc(sp.sympify)
    # In the companion basis an invariant form is proportional to [[2,-q],[-q,2]].
    A4=sp.Matrix([[4,-1],[1,0]]);J4=sp.Matrix([[2,-4],[-4,2]])
    assert A4.T*J4*A4==J4
    assert S4==sp.Matrix([[-2,1],[1,1]]) and S4.det()==-3
    return dict(S3=S3.tolist(),S4=S4.tolist(),form_discriminants=[20,12],s3det=-5,s4det=-3,trace_T=3,
                modular_length=decimal(2*mp.acosh(mp.mpf('1.5'))),lorentz_length=primary['lorentz']['ell'],
                gauss_controls={'LR':3,'LLR':4},G7='OPEN')
def run():
    mp.mp.dps=35
    return {'precision_dps':mp.mp.dps,'words':dynamics(),'zeta':contours(),'scattering':modular(),'geometry':geometry()}
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');a=parser.parse_args()
    text=json.dumps(run(),ensure_ascii=False,indent=2,default=int)+'\n'
    if a.check:
        assert json.loads(text)==json.loads((HERE/'CHECKS.json').read_text())
        print('R149 v0.3: all checks passed')
    else:print(text,end='')
