"""Keep exact R130 names and directed cyclic order through eight steps."""
from collections import Counter, defaultdict
from fractions import Fraction
import json
import r130_reference as graph
from r150_extension import canonical, layer, abs2, branches


def anchor(state):
    j=next(j for j,(_,s) in enumerate(state) if s&1)
    return state[j:]+state[:j]


def exchange_labels(state):
    return tuple((u, ((s&3)<<2) | (s>>2)) for u,s in state)


def channel_two(state):
    return exchange_labels(graph.interact(exchange_labels(state),(-1,)))


def named_row(w,model):
    a=graph.interact(w,(1,))
    b=channel_two(w)
    both=graph.interact(w,(1,-1))
    assert anchor(both) == anchor(channel_two(a)) == anchor(graph.interact(b,(1,)))
    assert anchor(channel_two(b)) == anchor(graph.interact(a,(1,))) == w
    terms=([(w,1-1j),(both,1+1j)] if model=='shared' else
           [(w,-1j),(a,1),(b,1),(both,1j)])
    row=defaultdict(complex)
    for v,coef in terms:
        row[anchor(graph.transport(v,2))]+=coef
    assert sum(abs2(v) for v in row.values())==4
    projected=defaultdict(complex)
    for v,coef in row.items():
        projected[canonical(graph.word(v))]+=coef
    assert {s:v for s,v in projected.items() if v}==dict(branches(graph.word(w),model))
    return [(v,y) for v,y in row.items() if y]


def run(model,stop=8,seam=1):
    seed=layer(7,4)[1]
    state=anchor(graph.named(seed))
    psi={state:1+0j}
    rows={}
    for t in range(1,stop+1):
        nxt=defaultdict(complex)
        for w,x in psi.items():
            for v,y in named_row(w,model):
                phase=seam if model=="shared" and graph.word(v)==layer(7,4)[0] else 1
                nxt[v]+=x*y*phase
        psi={v:x for v,x in nxt.items() if x}
        den=4**t
        words=Counter()
        for v,x in psi.items():
            words[graph.word(v)]+=abs2(x)
        assert sum(words.values())==den
        rows[t]=dict(named_states=len(psi),words=len(words),
                     same_length=str(Fraction(sum(v for w,v in words.items() if len(w)==7),den)),
                     same_word=str(Fraction(words[seed],den)),
                     identical_initial_named_state=str(Fraction(abs2(psi.get(state,0)),den)))
    return rows


def pair_readout():
    states=layer(7,4)
    w=anchor(graph.named(states[1]))
    partners={'generated_by_both_channels':anchor(graph.interact(w,(1,-1))),
              'fresh_atom_labels':anchor(graph.named(states[0]))}
    out={}
    for label,v in partners.items():
        assert graph.word(v)==states[0]
        for sign in [-1,1]:
            psi=defaultdict(complex)
            for u,g in [(w,1),(v,sign)]:
                for target,coef in named_row(u,'factorized'):
                    psi[target]+=coef*g
            assert sum(abs2(x) for x in psi.values())==8
            out[f'{label}_sign_{sign}']=str(Fraction(sum(abs2(x) for w,x in psi.items() if len(w)!=7),8))
    return out


if __name__=='__main__':
    data={s:run(s) for s in ('shared','factorized')}
    data['shared_seam_probability_word_at_7']={str(h):run('shared',7,h)[7]['same_word'] for h in (1,-1,1j,-1j)}
    data['factorized_pair_leak']=pair_readout()
    print(json.dumps(data,indent=2))
