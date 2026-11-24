"""Exact R141 event audit. Run from any directory. Computational inputs are pinned in donor_replay."""
from collections import defaultdict
from fractions import Fraction as Q
from pathlib import Path
import json
import sys

import sympy as sp

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'donor_replay'))
import previous as engine

h = engine.h


def distribution(coefficients, state):
    return [row[0] + sum(b*x for b, x in zip(row[1:], state)) for row in coefficients]


def inverse(q):
    if len(q) != 5 or sum(q) != 1 or 96*q[3] - 8*q[4] != 25:
        return None
    z = (32*q[4]-5)/3
    y = (31-256*q[0]-19*z)/4
    x = (51+z-256*q[1])/4-y
    return (x, y, z) if x*x+y*y+z*z <= 1 else None


def first_switch(switch):
    # Two actual first-step ADD coins. The marker flips at length two on steps 1 and 2.
    state = {engine.start: [h.ONE, h.ZERO]}
    for step in range(1, 9):
        nxt = defaultdict(lambda: [h.ZERO, h.ZERO])
        for graph, v in state.items():
            for action, target in h.moves(graph):
                amp = h.STEP[switch if step == 1 else 1][action]
                nxt[target] = engine.addvec(nxt[target], engine.scale(amp, v))
        if step <= 2:
            for graph in nxt:
                if len(graph) == 2:
                    nxt[graph] = nxt[graph][::-1]
        state = nxt
    return engine.read_distribution(state, engine.den)


def extensions(rows):
    eye = sp.eye(2)
    x = sp.Matrix([[0,1],[1,0]])
    y = sp.Matrix([[0,-sp.I],[sp.I,0]])
    z = sp.diag(1,-1)
    kron = sp.kronecker_product
    gamma = [kron(x,eye),kron(y,eye),kron(z,z),kron(z,x)]
    for i, g in enumerate(gamma):
        for j, f in enumerate(gamma):
            assert g*f+f*g == (2*sp.eye(4) if i==j else sp.zeros(4))
    embedding = kron(eye,sp.Matrix([1,0]))
    effects = []
    for (a,b,c,d),w in zip(rows,[-8,8,0,0,0]):
        mat = a*sp.eye(4) + sum((v*g for v,g in zip([b,c,d,w],gamma)),sp.zeros(4))
        assert embedding.H*mat*embedding == a*eye + b*x+c*y+d*z
        assert a*a >= b*b+c*c+d*d+w*w and a>=0
        effects.append(mat/256)
    assert sum(effects,sp.zeros(4)) == sp.eye(4)
    state = (sp.eye(4) + (4*gamma[1]+19*gamma[2]+8*gamma[3])/21)/4
    assert state.is_positive_semidefinite and state.trace()==1
    prob = [sp.simplify((state*e).trace()) for e in effects]
    assert sum(prob)==1 and prob[0]==sp.Rational(5,128)
    # A second, inequivalent realization retains all original effects on a 2D subspace.
    direct_sum = [sp.diag(embedding.H*e*embedding,p) for e,p in zip(effects,prob)]
    assert sum(direct_sum,sp.zeros(3))==sp.eye(3)
    assert all(e.is_positive_semidefinite for e in direct_sum)
    assert [e[2,2] for e in direct_sum]==prob
    return dict(probabilities=[str(p) for p in prob],four_dimensional_state_rank=state.rank(),
                direct_sum_dimension=3,euclidean_threshold=8)


def schedules():
    base = engine.schedules()
    target = engine.ends[19]
    paths = [(lengths, actions) for lengths,g,actions in engine.paths if g == target]
    assert len(paths)==2 and len({p[0] for p in paths})==2
    rows=[]
    for schedule,aa,bb,i2,p19,p4 in base['rows']:
        switches = [int(s) for s in schedule]
        a,b = [h.amplitude(actions,switches) for _,actions in paths]
        re,im = h.mul((a[0],-a[1]),b)
        assert Q(h.dot(a,a),engine.den)==Q(aa) and Q(h.dot(b,b),engine.den)==Q(bb)
        assert 2*Q(re,engine.den)==Q(i2)
        rows.append(dict(s=schedule,amplitude_A=list(a),amplitude_B=list(b),
                         gram_AB=[str(Q(re,engine.den)),str(Q(im,engine.den))],
                         mu_A=aa,mu_B=bb,I2=i2,P19=p19,P4=p4))
    return dict(event='unmarked eight-step witness, named graph 19',
                paths=[dict(lengths=l,actions=a) for l,a in paths],
                amplitude_denominator=h.DEN,gram_convention='conj(A)*B, real and imaginary parts',
                histogram=base['weights'],active_arms=base['active_arms'],mean_P19='765/16384',rows=rows)


def main():
    ports = engine.effects()
    lengths = engine.by_length(ports)
    coeff = [lengths[i] for i in range(1,6)]
    rows = [[int(256*v) for v in row] for row in coeff]
    assert rows==[[31,0,-4,-19],[51,-4,-4,1],[64,4,8,-8],[70,0,0,2],[40,0,0,24]]
    assert sum(ports[i][0] for i,g in enumerate(engine.ends) if len(g)==1)==Q(31,256)
    assert len(engine.ends[0])==3 and ports[0][0]==Q(5,128)
    engine.test_tomography(ports)
    mix = distribution(coeff,(0,0,0))
    for r in [(0,0,0),(1,0,0),(0,-1,0),(0,0,1),(Q(1,3),Q(2,3),Q(2,3))]:
        assert inverse(distribution(coeff,r))==r
    negative = distribution(coeff,(1,1,0))
    assert all(p>0 for p in negative) and sum(negative)==1 and inverse(negative) is None
    assert 96*negative[3]-8*negative[4]==25
    assert 21**2-(4**2+19**2)==64
    dynamic={}
    for switch,state in [(0,(0,0,1)),(1,(1,0,0))]:
        actual = first_switch(switch)
        assert actual==distribution(ports,state)
        q = distribution(coeff,state)
        dynamic[str(switch)] = dict(state=state,q=[str(v) for v in q])
    audit = dict(length_effects_times_256=rows,port0_effect_times_256=[int(256*n) for n in ports[0]],
                 port0_length=len(engine.ends[0]),mixture_P0=str(ports[0][0]),mixture_q=[str(p) for p in mix],
                 length1_ports={str(i):str(row[0]) for i,(row,g) in enumerate(zip(ports,engine.ends)) if len(g)==1},
                 q1_min='(31-sqrt(377))/256',q1_min_numeric=float((31-sp.sqrt(377))/256),
                 q1_gap_numeric=float((21-sp.sqrt(377))/256),positive_determinant_shifted_effect='1/1024',
                 negative_control_q=[str(p) for p in negative],fixed_first_coin=dynamic,
                 extension=extensions(rows))
    for name,obj in [('CHECKS.json',audit),('SCHEDULES.json',schedules())]:
        out=json.dumps(obj,ensure_ascii=False,indent=2)+'\n'
        if '--check' in sys.argv:
            assert (ROOT/name).read_text()==out, name
        else:
            (ROOT/name).write_text(out)
    print('PASS: 40 named ports, 5 lengths, two preparations, positivity and extension witnesses, 256 schedules')


if __name__=='__main__':
    main()
