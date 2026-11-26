"""Exact C2 and H6 tests. A mass comparison with quoted data is kept separate."""
from collections import Counter, defaultdict
from hashlib import sha1
from itertools import product
import json
from math import cos, gcd, hypot, pi, sqrt
from pathlib import Path

import sympy as s
import r130_reference as graph
import word_rule as port

ROOT=Path(__file__).resolve().parent


def charge(w):
    return sum(int((a&5)==5)-int((a&10)==10) for a in w)


def charge_tests():
    total=0
    for length in range(1,5):
        for w in product(range(16), repeat=length):
            i=port.I_word(w)
            assert charge(i)==charge(w)==charge(port.transport_word(i))==-charge(port.T_word(w))
            total+=1
    return total


def perm(states, act):
    ix={w:i for i,w in enumerate(states)}
    m=s.zeros(len(states))
    for j,w in enumerate(states):
        m[ix[port.canon_cycle(act(w))],j]=1
    return m


def spectral_counts(U,T):
    n=U.rows
    assert U.H*U==s.eye(n) and T*U*T==U.H
    result={}
    for phase in (1,-1):
        A=U-phase*s.eye(n)
        pair=[n-s.Matrix.vstack(A,T-sign*s.eye(n)).rank() for sign in (1,-1)]
        result[str(phase)]=pair
    return result


def c2():
    selected={}
    coin_comparison={}
    for L in range(3,16,2):
        u=(L+1)//2
        states=[port.canon_cycle(port.state_to_word((t,u,(t+u-1)%L),L)) for t in range(L)]
        U=perm(states,port.F_word)
        T=perm(states,port.T_word)
        result=spectral_counts(U,T)
        assert result=={'1':[2,0],'-1':[1,0]}
        selected[str(L)]=result
        shift,interaction=(perm(states,fn) for fn in (port.transport_word,port.I_word))
        identity=s.eye(L)
        z=-s.I
        coin=((1+z)*identity+(1-z)*interaction)/2
        coherent=shift*coin
        assert (coherent.H*coherent-identity).applyfunc(s.expand)==s.zeros(L)
        assert s.simplify(coherent.det()-z)==0 and z!=z.conjugate()
        n0=L-(coherent-identity).rank()
        npi=L-(coherent+identity).rank()
        assert (n0,npi)==(1,0)
        x=s.Symbol('x')
        expected=x**L+(z-1)*(x**(L-1)+x)/2-z
        assert s.expand(coherent.charpoly(x).as_expr()-expected)==0
        coin_comparison[str(L)]=[n0,npi]
    states=[]
    for t,u,z in product(range(3),repeat=3):
        v=(z-t)%3
        if u==0 or v==0 or (u-v)%3==1:
            states.append(port.canon_cycle(port.state_to_word((t,u,z),3)))
    U,T=(perm(states,fn) for fn in (port.F_word,port.T_word))
    # e^{-i pi chi/2}; exact phases, including chi=0.
    twist=s.diag(*[(-s.I)**charge(w) for w in states])
    before=spectral_counts(U,T)
    after=spectral_counts(twist*U,T)
    assert before=={'1':[5,2],'-1':[1,0]}
    assert after=={'1':[3,0],'-1':[1,0]}
    # 12-cycle, chi=+1: H=1+i(F-F†) vanishes on a Fourier eigenmode with sin(k)=1/2.
    w=port.canon_cycle(port.state_to_word((0,0,1),12))
    cyc=[w]
    for _ in range(11):
        cyc.append(port.canon_cycle(port.F_word(cyc[-1])))
    assert len(set(cyc))==12 and all(charge(t)==1 for t in cyc)
    U12=perm(cyc,port.F_word)
    residual_rank=(s.eye(12)+s.I*(U12-U12.T)).rank()
    assert residual_rank==10
    return dict(active=selected,H6_coin_on_active_quotient_zero_pi=coin_comparison,core_L3_F=before,core_L3_unitary_pi_over_2=after,
                H_lambda1_nullity_charged_12cycle=12-residual_rank)


def clean(A):
    return A.applyfunc(lambda z:s.expand_complex(z).expand().simplify())


def h6():
    src=(ROOT.parents[1]/'R140_HAAR_SORKIN'/'HISTORIES.json').read_bytes()
    gitid=sha1(b'blob '+str(len(src)).encode()+b'\0'+src).hexdigest()
    assert gitid=='6b0c85bf5cc008cf21442dcd6fb4777155dc079f'
    data=json.loads(src)
    ident=s.eye(3)
    M=ident[:,[1,2,0]]
    J=ident[:,[0,2,1]]
    select={2:M,3:J}
    def op(lengths):
        A=ident
        for L in lengths:
            A=select.get(L,ident)*A
        return A
    def tup(x):
        return tuple(map(tup,x)) if isinstance(x,list) else x
    ks=[s.zeros(3) for _ in data['named_endpoints']]
    arms={}
    for branch in data['branches']:
        lengths=branch['lengths']
        for g,a,b in branch['amplitudes']:
            A=(a+s.I*b)*op(lengths)/16
            ks[g]+=A
            if g==19:
                arms[tuple(lengths)]=A
    # Rebuild all endpoints from the named graph, with post-step length control.
    base=graph.cyclic(graph.named(tuple(data['initial_word'])))
    nodes={base:ident}
    for _ in range(8):
        following=defaultdict(lambda:s.zeros(3))
        for x,K in nodes.items():
            idle=graph.cyclic(graph.transport(x,2))
            flip=graph.cyclic(graph.forward(x,(1,-1)))
            for z,coeff in ((idle,1-s.I),(flip,1+s.I)):
                following[z]+=coeff*select.get(len(z),ident)*K
        nodes={z:A.applyfunc(s.expand) for z,A in following.items()}
    assert len(nodes)==len(ks)==40
    for z,K in zip(data['named_endpoints'],ks):
        assert clean(nodes[tup(z)]/256-K)==s.zeros(3)
    assert clean(sum((K.H*K for K in ks),s.zeros(3)))==ident
    A=arms[tuple(map(int,'33322222'))]
    B=arms[tuple(map(int,'22223332'))]
    overlap=clean(B.H*A)
    assert overlap==-M/128
    P=s.ones(3)/3
    B2=s.I*(M-M**2)
    assert clean(overlap+overlap.H)==(ident-3*P)/128
    assert clean(s.I*overlap-s.I*overlap.H)==-B2/128
    E19=clean(ks[19].H*ks[19])
    assert E19==3*(ident-P)/128
    c=s.Matrix([1,1,0])/s.sqrt(2)
    p0=clean(c.H*E19*c)[0]
    ppi=clean(c.H*(-A+B).H*(-A+B)*c)[0]
    assert (p0,ppi)==(s.Rational(1,128),s.Rational(3,128))
    om=(-1+s.I*s.sqrt(3))/2
    U=s.Matrix(3,3,lambda j,k: (1,om,om.conjugate())[j*k%3]/s.sqrt(3))
    effects_definitions={'endpoint':[ident], 'fourier_columns':[clean(v*v.H) for v in U.columnspace()],
                        'coordinate':[ident[:,j]*ident[:,j].T for j in range(3)]}
    ranks={}
    for name,ps in effects_definitions.items():
        effects=[clean(K.H*p*K) for K in ks for p in ps]
        table=s.Matrix([list(e) for e in effects])
        ranks[name]=[table.rank(),table.applyfunc(s.re).rank()]
    assert ranks=={'endpoint':[3,2],'fourier_columns':[3,2],'coordinate':[9,6]}
    eps=[]
    for k in range(3):
        E=clean(ks[1].H*effects_definitions['coordinate'][k]*ks[1])
        if k == 0:
            assert E == s.diag(0, s.Rational(1, 32), 0)
        eps.append([str(E[j,j]) for j in range(3)])
    return dict(git_blob=gitid,branches=len(data['branches']),endpoints=len(ks),ranks=ranks,
                end19_p0=str(p0),end19_ppi=str(ppi),end1_coordinate_effect_diagonals=eps)


def masses():
    masses=[0.51099895069,105.6583755,1776.93]
    errors=[0.00000000016,0.0000023,0.09]
    a=list(map(sqrt,masses))
    S=sum(a)
    Q=sum(masses)/S**2
    sigma=hypot(*[(1/S**2-sum(masses)/(x*S**3))*e for x,e in zip(a,errors)])
    d=2/9
    e,mu,tau=[1+sqrt(2)*cos(d+x) for x in [2*pi/3,-2*pi/3,0]]
    r=(mu/e)**2
    return dict(Q=Q,sigma_Q_diagonal=sigma,tau_root_MeV=(2*(a[0]+a[1])+sqrt(3*(a[0]**2+4*a[0]*a[1]+a[1]**2)))**2,
                predicted_ratio=r,CODATA_ratio=206.7682827,standard_uncertainty_ratio=0.0000046,
                standardized_difference=(r-206.7682827)/0.0000046)


if __name__=='__main__':
    print(json.dumps(dict(all_charge_words=charge_tests(),c2=c2(),h6=h6(),masses=masses()),indent=2))
