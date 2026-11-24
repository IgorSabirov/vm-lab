"""Exact finite checks for the R140 witness. Run with Python 3, without external packages."""
from collections import defaultdict, Counter
from fractions import Fraction
from functools import cache
from itertools import product
from pathlib import Path
from runpy import run_path
import json

ROOT = Path(__file__).resolve().parent
graph_ops = run_path(str(ROOT / 'graph_engine.py'))
table = json.loads((ROOT / 'HISTORIES.json').read_text())
ONE = (1, 0)
ZERO = (0, 0)
DEN = 2 ** 8


def add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def mul(a, b):
    return (a[0]*b[0] - a[1]*b[1], a[0]*b[1] + a[1]*b[0])


def dot(a, b):
    return a[0]*b[0] + a[1]*b[1]


def freeze(x):
    return tuple(map(freeze, x)) if isinstance(x, list) else x


def rooted(g):
    return min(g[i:] + g[:i] for i in range(len(g)))


@cache
def moves(g):
    keep = rooted(graph_ops['transport'](g, 2))
    flip = rooted(graph_ops['forward'](g, (1, -1)))
    return [('idle', keep)] if keep == flip else [('stay', keep), ('flip', flip)]


def exact_paths():
    initial = rooted(graph_ops['named'](tuple(table['initial_word'])))
    layer = [((), initial, ())]
    for _ in range(8):
        layer = [(lengths + (len(g),), g, actions + (action,))
                 for lengths, prev, actions in layer for action, g in moves(prev)]
    return layer


# The numerator of each transition is a Gaussian integer. The common step denominator
# is 2, including an idle move. Switch 0 means theta=0, switch 1 means theta=pi/4.
STEP = [{'stay': (2,0), 'flip': ZERO, 'idle': (2,0)},
        {'stay': (1,-1), 'flip': (1,1), 'idle': (2,0)}]


def amplitude(actions, switches):
    value = ONE
    for move, switch in zip(actions, switches):
        value = mul(value, STEP[switch][move])
    return value


def witness():
    paths = exact_paths()
    endpoints = [freeze(g) for g in table['named_endpoints']]
    rows = {tuple(item['lengths']): i for i, item in enumerate(table['branches'])}
    vals = defaultdict(lambda: ZERO)
    support19 = []
    for lengths, graph, actions in paths:
        key = rows[lengths], endpoints.index(graph)
        vals[key] = add(vals[key], amplitude(actions, (1,) * 8))
        if key[1] == 19:
            support19.append((key[0], actions))
    all_exported = {(i, e):(x*16,y*16) for i,row in enumerate(table['branches'])
                    for e,x,y in row['amplitudes']}
    assert {k:v for k,v in vals.items() if v!=ZERO} == all_exported
    assert sorted(row for row,_ in support19) == [60,80]
    assert [(t, vals[t,19]) for t in (80,60)] == [(80,(-16,16)), (60,(16,-16))]
    coh = defaultdict(lambda: ZERO)
    rec = Counter()
    for (_,end), value in vals.items():
        coh[end] = add(coh[end], value)
        rec[end] += dot(value,value)
    dark = [i for i in range(len(endpoints)) if coh[i]==ZERO and rec[i]]
    assert dark == [10,15,17,19]
    assert all(Fraction(rec[i],DEN**2) == Fraction(1,64) for i in dark)
    assert all(end == 19 for (i,end),v in vals.items() if i in (60,80) and v!=ZERO)
    weights = {}
    outcomes = sorted(support19, reverse=True)
    for name, choices in [('fixed-pi-over-four', [(1,)*8]),
                          ('angle-drawn-once', [(0,)*8, (1,)*8]),
                          ('one-bit-alternating', [tuple(i%2 for i in range(8)), tuple(1-i%2 for i in range(8))]),
                          ('independent-at-each-step', list(product(range(2), repeat=8)))]:
        counts = Counter()
        for switches in choices:
            a,b = [amplitude(actions,switches) for _,actions in outcomes]
            counts['A'] += dot(a,a)
            counts['B'] += dot(b,b)
            counts['I2'] += 2*dot(a,b)
            counts['union'] += dot(add(a,b),add(a,b))
        weights[name] = {k:str(Fraction(v,len(choices)*DEN**2)) for k,v in counts.items()}
    assert weights['angle-drawn-once']['union'] == '0'
    # The squared one-step factors averaged over both angles are 3/4 for staying
    # and 1/4 for flipping. The two idle vs active factors contribute 10/16.
    iid = weights["independent-at-each-step"]
    assert Fraction(iid["A"]) == Fraction(1,4) * Fraction(3,4)**6
    assert Fraction(iid["B"]) == Fraction(1,4)**3 * Fraction(3,4)**4
    assert Fraction(iid["I2"]) == -2 * Fraction(1,4)**4 * Fraction(3,4)**2 * Fraction(10,16)
    # A controllable pi phase on paths with first observed length 2.
    with_phase = ZERO
    for _,actions in outcomes:
        v = amplitude(actions,(1,)*8)
        with_phase = add(with_phase,mul(v,(-1,0) if actions[0]=='flip' else ONE))
    assert Fraction(dot(with_phase,with_phase),DEN**2) == Fraction(1,32)
    return dict(graphs=len(endpoints), histories=len(rows), dark_outcomes=dark,
                fixed_named_end=19, contributing_rows=sorted(i for i,_ in support19),
                angles=weights, phase_pi='1/32')


def gauge_orbits():
    result = {}
    for length in (2,3):
        links = list(product(range(3), repeat=length))
        orbits = {}
        for g in links:
            h = sum(g) % 3
            orbit = {tuple((g[i]+k[i]-k[(i+1)%length]) % 3 for i in range(length)) for k in links}
            fiber = {v for v in links if sum(v)%3==h}
            assert orbit == fiber
            orbits[h] = len(orbit)
        result[length] = orbits
    return result




def direct_evolution(mode):
    """Propagate on graph x register without enumerating length histories."""
    start = rooted(graph_ops['named'](tuple(table['initial_word'])))
    state = {start: [ONE]*4}
    for step in range(1,9):
        following = defaultdict(lambda: [ZERO]*4)
        for graph,vec in state.items():
            for action,target in moves(graph):
                following[target] = [add(x,mul(STEP[1][action],v))
                                     for x,v in zip(following[target],vec)]
        state = following
        if step in (1,2):
            for graph,vec in state.items():
                if len(graph)==2:
                    vec[2:] = [mul((-1,0),x) for x in vec[2:]]
                if step == 1 and mode == 'swap':
                    vec[1], vec[2] = vec[2], vec[1]
                if step == 1 and mode == 'flip_first_bit':
                    vec[:] = vec[2:] + vec[:2]
    return [Fraction(sum(dot(v,v) for v in state[freeze(g)]), (2*DEN)**2)
            for g in table['named_endpoints']]


def memory_echo():
    """Two coherent length-controlled Z gates; same geometry, coin, and initial two qubits."""
    paths = exact_paths()
    ends = list(map(freeze, table['named_endpoints']))
    results = {}
    distributions = {}
    for mode in ('identity', 'swap', 'flip_first_bit'):
        final = defaultdict(lambda: [ZERO]*4)
        partial = {}
        for lengths, graph, actions in paths:
            # Start |++> with common denominator 2; bit 1 is the high bit of the register.
            mem = [1,1,1,1]
            if lengths[0] == 2:
                mem = [v if j<2 else -v for j,v in enumerate(mem)]
            if mode == 'swap':
                mem = [mem[j] for j in (0,2,1,3)]
            if mode == 'flip_first_bit':
                mem = [mem[j ^ 2] for j in range(4)]
            if lengths[1] == 2:
                mem = [v if j<2 else -v for j,v in enumerate(mem)]
            a = amplitude(actions,(1,)*8)
            event = ends.index(graph)
            vec = [mul(a,(v,0)) for v in mem]
            final[event] = [add(u,v) for u,v in zip(final[event],vec)]
            if event == 19:
                partial[lengths] = vec
        norm = sum(dot(v,v) for vec in final.values() for v in vec)
        assert norm == (2*DEN)**2
        a,b = partial.values()
        assert Fraction(sum(dot(v,v) for v in a),norm) == Fraction(1,128)
        assert Fraction(sum(dot(v,v) for v in b),norm) == Fraction(1,128)
        crossed = Fraction(2*sum(dot(x,y) for x,y in zip(a,b)), norm)
        prob = Fraction(sum(dot(v,v) for v in final[19]),norm)
        results[mode] = dict(I2=str(crossed), P19=str(prob))
        distributions[mode] = [Fraction(sum(dot(v,v) for v in final[j]),norm) for j in range(len(ends))]
        assert direct_evolution(mode) == distributions[mode]
    assert [m['P19'] for m in results.values()] == ['0','1/64','1/32']
    total_variation = sum(abs(p-q) for p,q in zip(distributions['identity'], distributions['flip_first_bit'])) / 2
    # Reduced density matrices at the cut following the first mark and the intervention.
    # The common state denominator is four: the first graph coin contributes two,
    # the initial |++> register another two. No density matrix is estimated.
    plus = [[mul(z,(sign,0)) for sign in row] for z,row in
            [((1,-1), [1,1,1,1]), ((1,1), [1,1,-1,-1])]]
    minus = [plus[0], [mul((-1,0),v) for v in plus[1]]]
    def gram_entry(row,col):
        value = ZERO
        for a,b in zip(row,col):
            value = add(value,mul(a,(b[0],-b[1])))
        return value
    def gram(rows):
        return [[gram_entry(row,col) for col in rows] for row in rows]
    assert gram(plus) == gram(minus) == [[(8,0),ZERO],[ZERO,(8,0)]]
    assert gram(list(zip(*plus))) == gram(list(zip(*minus)))
    assert gram_entry(plus[0]+plus[1],minus[0]+minus[1]) == ZERO
    results['common_continuation'] = dict(equal_graph_marginals=True,equal_register_marginals=True,
        global_state_overlap='0',graph_entropy_bits=1,final_graph_total_variation=str(total_variation),
        endpoint_changes={j:str(q-p) for j,(p,q) in enumerate(zip(distributions['identity'],distributions['flip_first_bit'])) if p!=q},
        equal_mixture_P19=str((distributions['identity'][19]+distributions['flip_first_bit'][19])/2))
    return results


def label_algebra():
    reversal = [int(f'{s:04b}'[::-1],2) for s in range(16)]
    fixed = sum(s == r for s,r in enumerate(reversal))
    pairs = (16-fixed)//2
    # A matrix commuting with every individual label projector is diagonal;
    # commutation with bit reversal sets its two entries on every pair equal.
    assert (fixed,pairs,fixed+pairs)==(4,6,10)
    return dict(scalar_blocks=fixed, pair_blocks=pairs, generated_dimension=fixed+4*pairs,
                commutant_dimension=fixed+pairs, reversal_plus=fixed+pairs, reversal_minus=pairs)


if __name__ == '__main__':
    print(json.dumps({'witness':witness(),'Z3_orbits':gauge_orbits(),
                      'two_qubit_echo':memory_echo(), 'R132':label_algebra()},indent=2))
