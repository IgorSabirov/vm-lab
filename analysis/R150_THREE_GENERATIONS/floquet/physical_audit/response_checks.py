"""Extended R150 audit. Run from the directory containing replay.py."""
import json
import math
import numpy as np
import sympy as sp
from collections import Counter
from replay import four_words,restrict_map,rewrite,reverse_channels,canonical,orbits,layer,mass,chi


def matrices(L):
    Q=sp.zeros(L); I=sp.eye(L)
    I.row_swap(0,1)
    R=sp.zeros(L)
    for t in range(L):
        Q[(t+1)%L,t]=1
        R[(1-t)%L,t]=1
    return Q,I,R


def joint(L):
    Q,I,R=matrices(L)
    E=sp.eye(L)
    x,z,h=sp.symbols('x z h')
    K=(E+I+z*(E-I))/2
    W=sp.diag(h,*[1]*(L-1))*Q*K
    poly=x**L+(z-1)*x**(L-1)/2+h*((z-1)*x/2-z)
    assert sp.expand(W.charpoly(x).as_expr()-poly)==0
    J=Q*R
    H6=W.subs({h:1,z:-sp.I})
    assert J*J.conjugate()==E and J*H6.conjugate()*J.H==H6.H
    n=L-1
    cycle=E[:,0]+sum([E[:,i] for i in range(2,L)],sp.zeros(L,1))
    a=cycle/sp.sqrt(n); b=E[:,1]; uniform=sp.ones(L,1)/sp.sqrt(L)
    def shift_norm(y):
        d=(H6-E)*y
        return str(sp.simplify((d.H*d)[0]))
    assert ((H6-E)*uniform).applyfunc(sp.simplify)==sp.zeros(L,1)
    answer={'joint_at_plus1':str(sp.factor(poly.subs(x,1))),
            'joint_at_minus1':str(sp.factor(poly.subs(x,-1))),
            'H6_residual_norm_squared':[shift_norm(y) for y in [a,b,uniform]],
            'antiunitary_QR_K':True}
    e=.001
    for psi in (0.,.0008,-.0005):
        M=np.array(W.subs({z:-np.exp(1j*e),h:np.exp(1j*psi)}),dtype=complex)
        ev=np.linalg.eigvals(M)
        plus=sorted(ev,key=lambda u:abs(u-1))[:2]; minus=min(ev,key=lambda u:abs(u+1))
        near=sorted(float(np.angle(u)) for u in plus)
        G=e/2*np.array([[1.,-1/math.sqrt(n)],[-1/math.sqrt(n),1/n]])+np.diag([0,psi/n])
        target=np.linalg.eigvalsh(G)
        delta_pi=float(np.angle(-minus))
        assert np.max(np.abs(near-target))<2e-8 and abs(delta_pi-(e/2+psi)/n)<2e-8
        answer[str((e,psi))]=[near,target.tolist(),delta_pi,(e/2+psi)/n]
    generic=W.subs({z:-sp.I,h:sp.I})
    answer['joint_z_minus_i_h_i']=[L-(generic-sign*E).rank() for sign in (1,-1)]
    special=W.subs({z:-sp.I,h:(3+sp.I)/(1+3*sp.I)})
    answer['pi_resonance_z_minus_i']=[L-(special-sign*E).rank() for sign in (1,-1)]
    return answer


def exact_counts(L):
    f=restrict_map(four_words(L))
    T={w:canonical(rewrite(reverse_channels(w))) for w in f}
    output={}; cycles=orbits(f)
    for label in ('bare_F','charge_only','both','mass_only','static_both'):
        totals=Counter(); support=Counter()
        for c in cycles:
            w=c[0]; n=len(c)
            value=mass(w); charge=chi(w)
            assert all(mass(a)==value and chi(a)==charge for a in c)
            if label in ('both','mass_only','static_both') and value:
                continue  # Proof: irrational pi for the unitary, algebraic integer for the static operator.
            if label=='charge_only' and charge and n%4:
                continue
            # This test enumerates odd L only, hence no charged-cycle 4|n.
            for sign in (1,-1):
                if sign==-1 and n%2: continue
                trace=0 if T[w] not in c else (1 if sign==1 else (-1)**c.index(T[w]))
                totals[(sign,'dim')]+=1
                totals[(sign,'trace')]+=trace
                support[str(layer(w))]+=1
        pairs=[]
        for sign in (1,-1):
            d,s=totals[sign,'dim'],totals[sign,'trace']
            pairs.append([(d+s)//2,(d-s)//2])
        output[label]={'zero_pi_parities':pairs,'net':[p-m for p,m in pairs]}
        if label=='static_both':
            output[label]={'nullity':sum(map(sum,pairs)), 'T_parity':[sum(x) for x in zip(*pairs)],'support':dict(sorted(support.items()))}
    return output


def cylinder():
    L=7; n=5
    Q,I,R=matrices(L); F=Q*I
    Ht=sp.I*(F-F.T); Tt=I*R
    M=sp.diag(3,-2,0,2,-3)
    S=sp.zeros(n)
    for j in range(n-1):
        S[j+1,j]=1
    hop=sp.I*(S-S.T)
    ru=sp.eye(n)[::-1,:]
    T=sp.kronecker_product(ru,Tt)
    out={}
    for mass_gain,hopping in [(sp.Rational(1,49),sp.Rational(1,5)),(0,sp.Rational(1,5)),(sp.Rational(1,49),0)]:
        A=mass_gain*M+hopping*hop
        H=sp.kronecker_product(sp.eye(n),Ht)+sp.kronecker_product(A,sp.eye(L))
        assert T*H*T==-H and H==H.H
        k=A.nullspace()[0]
        p=[sp.simplify(sp.conjugate(q)*q/(k.H*k)[0]) for q in k]
        # Ht has eigenvalues 0 (3), +sqrt(3) (2), -sqrt(3) (2).
        assert A.rank()==4 and (A*A-3*sp.eye(n)).det()!=0
        for a in Ht.nullspace():
            y=sp.kronecker_product(k,a)
            assert T*y==y and H*y==sp.zeros(35,1)
        out[str((mass_gain,hopping))]={'zero_T':[3,0],'layer_probabilities':list(map(str,p)),
                                      'center_weight':float(p[2])}
    return out


def other_checks():
    gaps={}
    for L in (12,17,19,21,101,9999,10001):
        val=min(abs(1-2*math.sin(2*math.pi*j/L)) for j in range(L))
        gaps[str(L)]=[val,L*val]
    flux={}
    for n in (6,7,8,9,16):
        jzero=[j for j in range(n) if (2*j+1)%n==0]
        charge12=[j for j in range(n) if (4*j-n)%(4*n)==0 or (4*j-3*n)%(4*n)==0]
        flux[str(n)]={'pi_flux_zeros':jzero,'pi_over_two_charge_resonant_indices':charge12}
    S=sp.zeros(6); P=sp.zeros(6); A=sp.diag(*[(-1)**j for j in range(6)])
    for j in range(6):
        S[(j+1)%6,j]=1
        P[(-j)%6,j]=1
    assert (S-S.T)*A+A*(S-S.T)==sp.zeros(6)
    S[0,5]=-1
    Ppi=P*sp.diag(1,-1,-1,-1,-1,-1)
    assert Ppi**2==sp.eye(6) and Ppi*S*Ppi==S.T and Ppi.trace()==0
    weyl={}
    for k in (2,8,32,128):
        d=Counter()
        for i in range(k):
            d[i+1]+=1
            d[i-1]-=1
        weyl[k]=str(sp.sqrt(sp.Rational(sum(v*v for v in d.values()),k)))
    active_gaps={}
    for L in (5,7,9,11,13):
        size=L-1; g=2*math.sin(2*math.pi/size); mmax=(L-1)//2
        layer_mass=[((2*u-1+mmax)%L)-mmax for u in range(2,L)]
        for f in (.1,.6,.95):
            mu=f*g/mmax
            levels=[mu*v+2*math.sin(2*math.pi*j/size) for v in layer_mass for j in range(size)]+[mu*v for v in layer_mass]
            gap=min(abs(a) for a in levels if abs(a)>1e-9)
            assert abs(gap-min(2*mu,g-mu*mmax))<1e-12
            active_gaps[str((L,f))]=gap
    return {'active_gap_checks':active_gaps,'weyl_norm':weyl,'Tpi_trace_cycle':int(Ppi.trace()),'passive_gap':[gaps,'L*g tends to pi*sqrt(3)/6 or pi*sqrt(3)/2 by residue'],
            'flux':flux,'near_zero_ratio_L7_phi0.1':math.sin(.1/6)/math.sin(.1/7),
            'strict_derivative_ratio':7/6}


if __name__=='__main__':
    print(json.dumps({'joint':{str(L):joint(L) for L in (7,9)},
                      'core':{str(L):exact_counts(L) for L in (3,5,7,9,11,13,15)},
                      'cylinder':cylinder(), 'other':other_checks()},indent=2))
