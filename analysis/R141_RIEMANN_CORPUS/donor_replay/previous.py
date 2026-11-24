"""R140/H6 review. Run python verify.py; exact Gaussian integer arithmetic."""
from collections import Counter, defaultdict
from fractions import Fraction as F
from itertools import product
import json
import check_h6 as h

ends = list(map(h.freeze, h.table['named_endpoints']))
start = h.rooted(h.graph_ops['named'](tuple(h.table['initial_word'])))
paths = h.exact_paths()
den = h.DEN ** 2


def addvec(a, b):
    return [h.add(x, y) for x, y in zip(a, b)]


def scale(a, b):
    return [h.mul(a, x) for x in b]


def geometry_step(state):
    size = len(next(iter(state.values())))
    following = defaultdict(lambda: [h.ZERO] * size)
    for g, vec in state.items():
        for action, target in h.moves(g):
            following[target] = addvec(following[target], scale(h.STEP[1][action], vec))
    return following


def read_distribution(state, normalization):
    out = [F(sum(h.dot(v, v) for v in state[g]), normalization) for g in ends]
    assert sum(out) == 1
    return out


def effects():
    pieces = defaultdict(lambda: h.ZERO)
    for lengths, graph, actions in paths:
        arm = int(lengths[0] == 2)
        tag = arm ^ int(lengths[1] == 2)
        key = ends.index(graph), arm, tag
        pieces[key] = h.add(pieces[key], h.amplitude(actions, (1,) * 8))
    rows = []
    for e in range(len(ends)):
        aa = bb = re = im = 0
        for tag in (0, 1):
            a, b = pieces[e, 0, tag], pieces[e, 1, tag]
            aa += h.dot(a, a)
            bb += h.dot(b, b)
            r, i = h.mul((a[0], -a[1]), b)
            re += r
            im += i
        rows.append([F(n, den) for n in (aa + bb, 2 * re, -2 * im, aa - bb)])
    assert [sum(col) for col in zip(*rows)] == [1, 0, 0, 0]
    assert all(a >= 0 and a*a >= x*x + y*y + z*z for a,x,y,z in rows)
    assert [i for i, (_,x,y,_) in enumerate(rows) if x or y] == [0,4,8,19,35]
    return rows


def direct_logical(u, v):
    # The first-step coin sets the phase convention of the two logical basis kets.
    # Integer amplitudes u,v allow testing the poles, four equatorial states and
    # an asymmetric complex superposition without square roots or floats.
    state = geometry_step({start:[h.ONE,h.ZERO]})
    for graph, vec in tuple(state.items()):
        state[graph] = scale(v, vec[::-1]) if len(graph)==2 else scale(u, vec)
    for step in range(2,9):
        state = geometry_step(state)
        if step == 2:
            for graph, vec in tuple(state.items()):
                if len(graph)==2:
                    state[graph] = vec[::-1]
    norm = F(den * (h.dot(u,u)+h.dot(v,v)), 2)
    return read_distribution(state, norm)


def by_length(rows):
    grouped = defaultdict(lambda:[F(0)]*4)
    for g,row in zip(ends,rows):
        grouped[len(g)] = [a+b for a,b in zip(grouped[len(g)],row)]
    assert set(grouped) == {1,2,3,4,5}
    return grouped


def length_reconstruction(prob):
    z = (32*prob[5]-5)/3
    y = (31-19*z-256*prob[1])/4
    x = (51+z-256*prob[2])/4-y
    assert 96*prob[4]-8*prob[5] == 25
    return [x,y,z]


def test_tomography(rows):
    checks = {}
    cases = {'+X':(h.ONE,h.ONE), '-X':(h.ONE,(-1,0)), '+Y':(h.ONE,(0,1)),
             '-Y':(h.ONE,(0,-1)), '+Z':(h.ONE,h.ZERO), '-Z':(h.ZERO,h.ONE),
             'oblique':((2,1),(-1,3))}
    for name,(u,v) in cases.items():
        uu,vv = h.dot(u,u),h.dot(v,v)
        r,i = h.mul((u[0],-u[1]),v)
        x,y,z = F(2*r,uu+vv),F(2*i,uu+vv),F(uu-vv,uu+vv)
        predicted = [a+b*x+c*y+d*z for a,b,c,d in rows]
        observed = direct_logical(u,v)
        assert predicted == observed
        assert [32*(observed[4]-observed[19]),
                16*(observed[0]-observed[8]-observed[35]),
                8*observed[13]-1] == [x,y,z]
        length_prob = Counter()
        for g,p in zip(ends,observed):
            length_prob[len(g)] += p
        assert length_reconstruction(length_prob) == [x,y,z]
        checks[name] = [str(observed[i]) for i in (0,4,8,13,19,35)]
    return checks


def schedules():
    pair = [(l,ac) for l,g,ac in paths if g==ends[19]]
    assert len(pair)==2
    assert all(ends.index(g)==19 for l,g,ac in paths if l in {row[0] for row in pair})
    totals, gates, pair_gates = Counter(), Counter(), Counter()
    records = []
    for s in product(range(2), repeat=8):
        a,b = [h.amplitude(ac,s) for _,ac in pair]
        aa,bb,inter = (F(i,den) for i in (h.dot(a,a),h.dot(b,b),2*h.dot(a,b)))
        p = aa+bb+inter
        # Second calculation directly propagates the state to the named graph.
        state = {start:h.ONE}
        for switch in s:
            following = defaultdict(lambda:h.ZERO)
            for g, v in state.items():
                for action, target in h.moves(g):
                    following[target] = h.add(following[target],h.mul(h.STEP[switch][action],v))
            state = following
        assert p == F(h.dot(state[ends[19]],state[ends[19]]),den)
        p4 = F(h.dot(state[ends[4]],state[ends[4]]),den)
        if p4 + p == F(1,32):
            pair_gates[(bool(aa),bool(bb))] += 1
        totals[p] += 1
        gates[(bool(aa),bool(bb))] += 1
        records.append([''.join(map(str,s)),str(aa),str(bb),str(inter),str(p),str(p4)])
    assert sum(p*n for p,n in totals.items())/256 == F(765,16384)
    assert totals[F(1,128)] == 2
    assert sum(pair_gates.values())==14 and pair_gates[True,True]==1
    return {'weights':{str(p):n for p,n in sorted(totals.items())},
            'active_arms':{str(k):n for k,n in sorted(gates.items())},
            'passing_pair_sum':{str(k):n for k,n in sorted(pair_gates.items())},
            'columns':['schedule','mu_A','mu_B','I2','P19','P4'], 'rows':records}


def shape_counts():
    trails = []
    for lengths,g,actions in paths:
        if g != ends[19]:
            continue
        graph = start
        counts = []
        for action in actions:
            graph = dict(h.moves(graph))[action]
            counts.append(sum(name[0]=='atom' for name,_ in graph))
        trails.append([list(lengths),counts,sum(counts)])
    assert [t[2] for t in trails] == [3,5]
    return trails


def field_distribution(rule, initial):
    # Character basis e_n(h)=h^n of the neutral Z3 field. M_h shifts n, J sends n to -n.
    state = {start: initial}
    for step in range(1,9):
        following = geometry_step(state)
        state = {}
        for g, vec in following.items():
            shift, sign = 0, 1
            if rule=='atom_count':
                shift = sum(name[0]=='atom' for name,_ in g)
            if rule=='length_mark':
                shift = int(len(g)==2)
            if rule=='ordered' and len(g)==2:
                shift = 1
            if rule=='ordered' and len(g)==3:
                sign = -1
            result = [h.ZERO]*3
            for n,v in enumerate(vec):
                result[(sign*n+shift)%3] = v
            state[g] = result
    return read_distribution(state, den*sum(h.dot(a,a) for a in initial))


def field_checks():
    result = {}
    for rule in ['length_mark','atom_count','ordered']:
        result[rule] = {}
        for initial,vec in [('character_zero',[h.ONE,h.ZERO,h.ZERO]),
                            ('holonomy_one',[h.ONE,h.ONE,h.ONE])]:
            p = field_distribution(rule,vec)
            result[rule][initial] = {str(e):str(p[e]) for e in [4,19]}
            assert p[4]+p[19] == F(1,32)
            assert p[19] == (F(1,64) if rule!='length_mark' and initial=='character_zero' else 0)
    return result


if __name__ == '__main__':
    rows = effects()
    result = {
        'logical_effect_columns':['constant','X','Y','Z'],
        'logical_effects':[[str(v) for v in row] for row in rows],
        'length_effects':{k:list(map(str,v)) for k,v in sorted(by_length(rows).items())},
        'direct_check_ports':[0,4,8,13,19,35],
        'direct_tests':test_tomography(rows),
        'baseline':h.witness(), 'register_echo':h.memory_echo(),
        'schedule_audit':schedules(), 'name_counts':shape_counts(),'field':field_checks(),
        'algebra_R132':h.label_algebra()
    }
    print(json.dumps(result,indent=2))
