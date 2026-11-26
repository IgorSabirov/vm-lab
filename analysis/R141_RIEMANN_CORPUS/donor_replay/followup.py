"""Follow-up controls selected after the rank-at-seven result (not preregistered)."""
from collections import Counter,defaultdict
from fractions import Fraction as F
from itertools import product
import json
import sympy as sp
import previous as model
import check_h6 as h


def sequential(u,v):
    state=model.geometry_step({model.start:[h.ONE,h.ZERO]})
    for g,x in state.items():
        state[g]=model.scale(v,x[::-1]) if len(g)==2 else model.scale(u,x)
    for step in range(2,8):
        state=model.geometry_step(state)
        if step==2:
            state={g:(x[::-1] if len(g)==2 else x) for g,x in state.items()}
    joint=Counter()
    for l in sorted({len(g) for g in state}):
        packet={g:x for g,x in state.items() if len(g)==l}
        for g,vec in model.geometry_step(packet).items():
            joint[l,len(g)] += sum(h.dot(a,a) for a in vec)
    norm=F(4**8*(h.dot(u,u)+h.dot(v,v)),2)
    assert sum(joint.values())==norm
    return {k:n/norm for k,n in joint.items()}


def measure_rank():
    cases=[(h.ONE,h.ONE),(h.ONE,(-1,0)),(h.ONE,(0,1)),(h.ONE,(0,-1)),(h.ONE,h.ZERO),(h.ZERO,h.ONE)]
    probs=[sequential(*case) for case in cases]
    rows={}; only_last=defaultdict(lambda:[F(0)]*4)
    for lengths in sorted(probs[0]):
        x1,x2,y1,y2,z1,z2=[p[lengths] for p in probs]
        assert x1+x2==y1+y2==z1+z2
        row=[(x1+x2)/2,(x1-x2)/2,(y1-y2)/2,(z1-z2)/2]
        only_last[lengths[1]]=[a+b for a,b in zip(only_last[lengths[1]],row)]
        rows[lengths]=row
    variable=sp.symbols('eta')
    coherent_lengths=model.by_length(model.effects())
    coherent=sp.Matrix([coherent_lengths[l] for l in range(1,6)])
    recorded=sp.Matrix([only_last[l] for l in range(1,6)])
    channel=(1-variable)*coherent+variable*recorded
    minor=sp.factor(channel[[0,1,3,4],:].det())
    assert sp.simplify(minor-25*(variable-1)/4194304)==0
    assert all(row[1]==0 for row in rows.values())
    return {'mixture_minor_lengths_1_2_4_5':str(minor),'joint_rank': sp.Matrix(list(rows.values())).rank(),'discarded_first_rank':sp.Matrix(list(only_last.values())).rank(),
            'effects_joint':{str(k):list(map(str,v)) for k,v in rows.items()}}


def minor_test(p):
    # Exact ring Z[sqrt(p)], represented as (a,b); divisibility by sqrt(p) iff p|a.
    def prod(a,b):return (a[0]*b[0]+p*a[1]*b[1],a[0]*b[1]+a[1]*b[0])
    def add(a,b):return (a[0]+b[0],a[1]+b[1])
    def power(a):
        b=(1,0)
        for _ in range(p):b=prod(a,b)
        return b
    def minor(u,up,M,N):
        def combine(row,a):return add(prod(row[0],a[0]),prod(row[1],a[1]))
        x,y=[power(combine(u,M[idx])) for idx in (0,1)]
        m,n=[combine(up,N[idx]) for idx in (0,1)]
        a,b=prod(n,x),prod(m,y)
        return a[0]-b[0],a[1]-b[1]
    tested=sharp=broken=0
    for a,b,c,d in product([(0,0),(1,0),(0,1),(1,1)],repeat=4):
        M=[(a,b),(c,d)]
        N=[[add(power(v),(p,0)) for v in col] for col in M]
        mutated=[[add(N[0][0],(1,0)),N[0][1]],N[1]]
        for b1,b2 in product(range(2),repeat=2):
            u,up=[[(1,0),(0,k)] for k in (b1,b2)]
            x,y=minor(u,up,M,N)
            assert x%p==0
            tested+=1
            sharp+=bool(y%p)
            broken+=bool(minor(u,up,M,mutated)[0]%p)
    assert sharp>0 and broken>0
    return dict(prime=p,cases=tested,exact_order_one=sharp,failures_after_congruence_break=broken)


print(json.dumps(dict(intermediate=measure_rank(),minors=[minor_test(p) for p in (2,3,5)]),indent=2))
