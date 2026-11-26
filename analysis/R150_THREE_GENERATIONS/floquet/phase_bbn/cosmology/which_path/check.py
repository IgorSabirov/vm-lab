"""R130 which-path readout, word-only echo, H6 port 19, and the supplied toy code."""
from collections import defaultdict
from fractions import Fraction
from hashlib import sha1
from pathlib import Path
import json
import math

import numpy as np
import sympy as sp
import r130_reference as graph

SEED=(1,2,0,0,12,0,0)
SEAM=(3,0,0,8,4,0,0)  # t=0 of the active layer (u,v)=(4,3)


def anchor(g):
    i=next(i for i,(_,s) in enumerate(g) if s&1)
    return g[i:]+g[:i]


def word_at(t):
    masks=[0]*7
    for bit,j in zip((1,2,4,8),(0,t,4,(3+t)%7)):
        masks[j]|=bit
    return tuple(masks)


def shift(psi,reverse=False,steps=7,seam=1):
    for _ in range(steps):
        out=defaultdict(complex)
        for g,a in psi.items():
            if reverse:
                q=graph.transport(g,2,True)
                terms=((q,(1+1j)/2),(graph.interact(q,(1,-1)),(1-1j)/2))
            else:
                terms=((graph.transport(g,2),(1-1j)/2),(graph.forward(g,(1,-1)),(1+1j)/2))
            for state,weight in terms:
                end=anchor(state)
                if not reverse and graph.word(end)==SEAM: weight*=seam
                out[end]+=a*weight
        psi={g:a for g,a in out.items() if a}
    return psi


def select_b(psi):
    return {g:a for g,a in psi.items() if graph.word(g)==SEED}


def dot(x,y):
    return sum(a.conjugate()*y.get(g,0) for g,a in x.items())


def norm(x):
    return dot(x,x).real


def depth(n):
    if n[0]=='atom': return 0
    return 1+max(depth(v) for v in n[1:])


def named_test():
    assert SEAM==word_at(0) and SEED==word_at(1)
    seed=anchor(graph.named(SEED))
    full=shift({seed:1})
    assert norm(full)==1 and shift(full,reverse=True)=={seed:1}
    marked=select_b(full)
    small,big=sorted(marked,key=lambda g:abs(marked[g]))
    A,B=marked[small],marked[big]
    assert A==(1-1j)/16 and B==-1j/2
    dep=[[depth(n) for n,w in s] for s in (small,big)]
    assert dep==[[8,8,7,9,9,9,7],[2]*7]
    x=select_b(shift({small:A},reverse=True))
    y=select_b(shift({big:B},reverse=True))
    # Forward seam contributes once to the big arm and zero times to the small one.
    # Check structurally by propagating the seam crossing count as a path label.
    tagged={(seed,0):1}
    for t in range(7):
        nxt=defaultdict(complex)
        for (g,n),amp in tagged.items():
            for target,weight in shift({g:1},steps=1).items():
                nxt[target,n+int(graph.word(target)==SEAM)]+=amp*weight
        tagged=nxt
    assert {(g,n):v for (g,n),v in tagged.items() if g in marked and v}=={(small,0):A,(big,1):B}
    assert set(g for (g,n),v in tagged.items() if graph.word(g)==SEED and v)==set(marked)
    baseline=norm(x)+norm(y)
    overlap=dot(x,y)
    assert baseline*16384==1089 and overlap*16384==32-32j
    phases={}
    for h in (1,-1,1j,-1j):
        ret=select_b(shift({seed:1},seam=h))
        assert ret=={small:A,big:B*h}
        joint=norm(select_b(shift(ret,reverse=True)))
        assert joint==baseline+2*(h*overlap).real
        plus=abs(A+B*h)**2/2
        minus=abs(A-B*h)**2/2
        assert abs(plus+minus-norm(ret))<1e-14
        phases[str(h)]=dict(word=str(Fraction(norm(ret))),echo_word_joint=str(Fraction(joint)),
                             plus_joint=str(Fraction(plus).limit_denominator(16384)),
                             minus_joint=str(Fraction(minus).limit_denominator(16384)))
    a={small:1}; b={big:1}
    for _ in range(12):
        a=shift(a,steps=1); b=shift(b,steps=1)
        assert not(a.keys() & b.keys())
    return dict(name_depths=dep,weights=['1/128','32/128'],word_b='33/128',
                coherence_echo_baseline=str(Fraction(baseline)),echo_overlap='(32-32i)/16384',
                four_seams=phases,next_forward_steps_disjoint=12)


def h6():
    data=Path(__file__).with_name('HISTORIES.json').read_bytes()
    assert sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()=='6b0c85bf5cc008cf21442dcd6fb4777155dc079f'
    d=json.loads(data)
    E=sp.eye(3); M=E[:,[1,2,0]]; J=E[:,[0,2,1]]
    arms={}
    c=sp.Matrix([1,1,0])/sp.sqrt(2)
    for branch in d['branches']:
        word=branch['lengths']
        for g,a,b in branch['amplitudes']:
            if g!=19: continue
            k=E
            for L in word:k={2:M,3:J}.get(L,E)*k
            arms[''.join(map(str,word))]=((a+sp.I*b)*k/16)*c
    assert set(arms)=={'33322222','22223332'}
    a=arms['33322222']; b=arms['22223332']
    raw=lambda x,y:sp.simplify((x.H*y)[0])
    assert [raw(a,a),raw(b,b),raw(b,a)]==[sp.Rational(1,128),sp.Rational(1,128),-sp.Rational(1,256)]
    phi=sp.symbols('phi',real=True)
    result=b+sp.exp(sp.I*phi)*a
    probs=[sp.trigsimp(sp.expand_complex(v*v.conjugate()).expand()) for v in result]
    target=[sp.Rational(1,256)]*2+[(1-sp.cos(phi))/128]
    assert all(sp.simplify(a-b)==0 for a,b in zip(target,probs))
    return dict(norms=['1/128','1/128'],overlap='-1/256',normalized_overlap='-1/2',
                coordinate_probabilities=[str(v) for v in target],visibility='1/2',
                scalar_singlet_cross_at_0='-1/64')


def toy():
    eye=np.eye(4,dtype=complex)
    k00,k01,k10,k11=eye.T
    X_name_controls_word=eye[:,[0,3,2,1]]
    X_word_controls_name=eye[:,[0,1,3,2]]
    pplus=np.ones((2,2))/2
    word_plus=np.kron(pplus,np.eye(2))
    joint_plus=np.kron(pplus,np.diag([1,0]))
    probe=lambda p,E:(p.conj()@E@p).real
    def purity(p,axis):
        rho=np.outer(p,p.conj()).reshape(2,2,2,2)
        red=np.trace(rho,axis1=axis,axis2=axis+2)
        return np.trace(red@red).real
    out=[]
    for ph in (0,.7,math.pi):
        h=np.exp(1j*ph)
        a=(k00+h*k01)/math.sqrt(2)
        b=(k00+h*k11)/math.sqrt(2)
        first=X_name_controls_word@a
        second=X_word_controls_name@b
        assert np.allclose(first,b)
        assert np.allclose([purity(a,0),purity(a,1),purity(first,0),purity(first,1)],[1,1,.5,.5])
        assert np.allclose([probe(b,joint_plus),probe(b,word_plus),probe(second,word_plus)],[.25,.5,(1+math.cos(ph))/2])
        out.append(dict(phi=ph,word_plus_before=float(probe(b,word_plus)),
                        joint_plus_name0_before=float(probe(b,joint_plus)),
                        word_plus_after=float(probe(second,word_plus))))
    return out


if __name__=='__main__':
    print(json.dumps(dict(R130=named_test(),H6=h6(),toy=toy()),indent=2,ensure_ascii=False))
