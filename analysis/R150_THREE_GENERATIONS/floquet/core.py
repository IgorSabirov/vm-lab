"""Exact transport and fixed-length checks. Run: python core.py"""
import itertools
import json
from collections import deque
from math import gcd
import sympy as sp

import r130_reference as ref
from word_rule import (F_word, I_word, R2_word, T_word, backward_word,
                       canon_cycle, state_to_word, transport_word, word_to_state)


def key(w):
    return len(w), word_to_state(w)


def coords(k, length):
    t, u, last = k
    return u, (last - t) % length, t


def local_chi(w):
    def has_both(s, mask):
        return int((s & mask) == mask)
    return sum(has_both(s, 5) - has_both(s, 10) for s in w)


def closed_set(f, states):
    predecessors = {}
    for k, y in f.items():
        predecessors.setdefault(y, []).append(k)
    gone = set()
    todo = deque(k for k in states if f[k] not in states)
    while todo:
        k = todo.popleft()
        if k not in gone:
            gone.add(k)
            todo.extend(predecessors.get(k, []))
    return states - gone


def cycles(perm):
    unseen = set(perm)
    result = []
    while unseen:
        w = next(iter(unseen))
        cycle = []
        while w in unseen:
            unseen.remove(w)
            cycle.append(w)
            w = perm[w]
        assert w == cycle[0]
        result.append(cycle)
    return result


def verify_length(length):
    states = {(length, k) for k in itertools.product(range(length), repeat=3)}
    step, reversal, shift, reflection = {}, {}, {}, {}
    theoretical = set()
    for x in states:
        _, k = x
        w = state_to_word(k, length)
        u,v,t = coords(k, length)
        f, tw = F_word(w), T_word(w)
        step[x], reversal[x] = key(f), key(tw)
        shift[x], reflection[x] = key(transport_word(w)), key(R2_word(w))
        assert key(backward_word(f)) == key(F_word(backward_word(w))) == x
        assert key(T_word(F_word(tw))) == key(backward_word(w))
        assert key(T_word(tw)) == x
        named = ref.named(w)
        for calculated, source in ((f,ref.forward(named,(1,-1))),
                                   (tw,ref.interact(ref.r2(named),(1,-1))),
                                   (transport_word(w),ref.transport(named,2)),
                                   (I_word(w),ref.interact(named,(1,-1)))):
            assert key(calculated) == key(ref.word(source))
        assert local_chi(w) == int(u == 0) - int(v == 0)
        assert local_chi(f) == local_chi(w) == -local_chi(tw)
        if u*v == 0:
            assert key(I_word(w)) == x
            theoretical.add(x)
        else:
            d = (u-v) % length
            split = int(t==0) + int(t==d)
            merge = int(u!=1 and v!=length-1)*(int(t==1) + int(t==(d-1)%length))
            assert len(f)-length == split-merge
            if d==1:
                theoretical.add(x)
                new_t = {0:1,1:0}.get(t,t)
                assert coords(key(I_word(w))[1],length) == (u,v,new_t)
    trace_R = sum(reflection[x] == x for x in states)
    assert trace_R == length*gcd(length,2)
    core = closed_set(step, states)
    assert core == theoretical
    for perm in (step, reversal, shift, reflection):
        assert {perm[x] for x in core} == core
    f = {x:step[x] for x in core}
    z = {x:reversal[x] for x in core}
    assert all(z[f[z[f[x]]]] == x for x in core)
    fixed = sum(z[x]==x for x in core)
    # Independent parity count using the indicator vectors of F² cycles.
    squares = cycles({x:f[f[x]] for x in core})
    fixed_indicators = sum(z[c[0]] in set(c) for c in squares)
    dims = [(len(squares)+sgn*fixed_indicators)//2 for sgn in (1,-1)]
    assert fixed == fixed_indicators
    if length >= 2:
        assert len(core) == 3*length*(length-1)
        assert fixed == 3-(-1)**length
        assert len(squares) == (2*length-1)*gcd(length,2)+(length-2)*(1+gcd(length-1,2))
    active_center = set()
    for x in core:
        u,v,_ = coords(x[1],length)
        if u and v and (2*u-1)%length==0:
            active_center.add(x)
    if length >= 3 and length%2:
        assert len(active_center)==length
        assert {f[x] for x in active_center} == {z[x] for x in active_center} == active_center
        cs = cycles({x:f[f[x]] for x in active_center})
        assert len(cs)==3 and all(z[c[0]] in c for c in cs)
    else:
        assert not active_center
    row = dict(L=length,checked=len(states),core=len(core),transport_reflection_trace=trace_R,trace=fixed,kernel=dims)
    return row,core,f,z


def permutation(seq,mapping):
    n=len(seq)
    index={x:i for i,x in enumerate(seq)}
    result=sp.zeros(n)
    for j,x in enumerate(seq):
        result[index[mapping[x]],j]=1
    return result


def audit_op(op,T):
    dim=T.rows
    residual=T*op+op*T
    counts=[dim-sp.Matrix.vstack(op,T-s*sp.eye(dim)).rank() for s in (1,-1)]
    total=dim-op.rank()
    return dict(rank=op.rank(),nullity=total,pure_parity_zeros=counts,
                projected_plus_rank=((sp.eye(dim)-T)*op*(sp.eye(dim)+T)).rank(),
                max_anticommutator=str(max(abs(val) for val in residual)))


def check_couplings(core,f,z):
    seq=sorted(core)
    F,T=(permutation(seq,map_) for map_ in (f,z))
    words=[state_to_word(k,n) for n,k in seq]
    D=F-F.T
    X=sp.diag(*map(local_chi,words))
    assert F*X==X*F and T*X==-X*T
    good={(0,7,8),(2,5,8),(0,2,13)}
    other={(0,4,11),(1,4,10),(0,1,14)}
    for w in words:
        sorted_w=tuple(sorted(w))
        assert local_chi(w)==int(sorted_w in good)-int(sorted_w in other)
    def by_q2(w):
        value=sum(s*s for s in w)
        return int(value in (93,113,173))-int(value in (117,137,197))
    fixed, passive = (9, 0, 6), (10, 4, 1)
    assert key(T_word(fixed)) == key(fixed)
    assert by_q2(fixed) == by_q2(passive) == -1
    assert (local_chi(fixed), local_chi(passive)) == (0, -1)
    naive=sp.diag(*map(by_q2,words))
    results={}
    for label,operator in [('D',D),('D+Q2_lookup',D+naive),('D+chi',D+X),
                           ('iD+chi',sp.I*D+X)]:
        results[label]=audit_op(operator,T)
    assert [results[s]['pure_parity_zeros'] for s in results]==[[6,2],[3,0],[4,0],[4,0]]
    assert (sp.I*D+X).H==sp.I*D+X
    assert results['D+Q2_lookup']['max_anticommutator']=='2'
    assert results['D+Q2_lookup']['nullity']==3
    return results


def fourier():
    w=(-1+sp.I*sp.sqrt(3))/2
    norm=lambda A: A.applyfunc(lambda x: sp.simplify(sp.expand_complex(x)))
    U=norm(sp.Matrix(3,3,lambda j,k:w**(j*k)/sp.sqrt(3)))
    M=sp.Matrix([[0,0,1],[1,0,0],[0,1,0]])
    J=sp.Matrix([[1,0,0],[0,0,1],[0,1,0]])
    B=sp.I*(M-M**2)
    E=[norm(U[:,j]*U[:,j].H) for j in range(3)]
    assert M**3==J**2==sp.eye(3) and J*M*J==M.T
    assert norm(U.H*U)==sp.eye(3)
    assert norm(U.H*B*U)==sp.diag(0,sp.sqrt(3),-sp.sqrt(3))
    assert norm(B-sp.sqrt(3)*(E[1]-E[2]))==sp.zeros(3)
    psi=norm((U[:,0]+U[:,1])/sp.sqrt(2))
    assert norm(psi.H*B*psi)[0]==sp.sqrt(3)/2
    assert norm((M**-8-sp.eye(3))*E[0])==sp.zeros(3)
    c0,c1,c2=sp.symbols('c0:3')
    C=c0*sp.eye(3)+c1*M+c2*M**2
    assert all(sp.simplify((J**p*C).H*(J**p*C)-C.H*C)==sp.zeros(3) for p in (0,1))
    mixed=(sp.eye(3)+J).H*(sp.eye(3)+J)
    assert (mixed*M-M*mixed).norm()==2*sp.sqrt(6)
    values=[]
    for b in (2,3):
        c=2*(1+b)+sp.sqrt(3*(1+4*b+b*b))
        a=sp.Matrix([1,b,c])
        assert sp.simplify(sum(a)**2/(3*a.dot(a)))==sp.Rational(1,2)
        pred=sp.sqrt(3)*(b*b-c*c)/a.dot(a)
        for transform,sign in ((U,1),(U.H,-1)):
            pos=transform*a
            assert sp.simplify(norm(pos.H*B*pos)[0]/a.dot(a)-sign*pred)==0
        values.append(dict(b=b,position_from_columns=float(pred),position_from_adjoint=-float(pred)))
    return values


def main():
    rows=[]
    for length in range(1,15):
        row,core,f,z=verify_length(length)
        rows.append(row)
        if length==3:
            coupling=check_couplings(core,f,z)
            states=sorted((3,k) for k in itertools.product(range(3),repeat=3))
            def lifted(operation):
                return {x:key(operation(state_to_word(x[1],3))) for x in states}
            transport=permutation(states,lifted(transport_word))
            reflection=permutation(states,lifted(R2_word))
            transport_stats=audit_op(transport-transport.T,reflection)
            exits=sum(y[0]!=3 for y in lifted(F_word).values())
            assert transport_stats['pure_parity_zeros']==[6,3] and exits==4
    w=(0,9,6)
    for _ in range(3):
        w=F_word(w)
    growing=lambda k:(1,)+(0,)*k+(2,0,12,0)
    assert canon_cycle(w)==canon_cycle(growing(1))
    for k in range(1,25):
        assert canon_cycle(F_word(growing(k)))==canon_cycle(growing(k+1))
    results=dict(rows=rows,comparison_count=4*sum(row['checked'] for row in rows),
                 length3=coupling,transport_L3=transport_stats,one_step_exits_L3=exits,fourier=fourier())
    print(json.dumps(results,indent=2))


if __name__=='__main__':
    main()
