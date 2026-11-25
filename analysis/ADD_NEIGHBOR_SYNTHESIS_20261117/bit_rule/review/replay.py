"""Run once from any directory: python replay.py > results.json."""
import json
from itertools import product
from pathlib import Path
from runpy import run_path
import numpy as np
import ports, geometry, transport

ANALYSIS = Path(__file__).resolve().parents[3]
REF=run_path(str(ANALYSIS/'ADD_NEIGHBOR_SYNTHESIS_20261117/verify.py'))
EPS=(1,-1)

def extra_controls():
    triad={}
    for w in ((1,2,12),(0,3,12),(0,2,13)):
        x=REF['named'](w)
        lengths=[len(w)];q=ports.signature(w)
        for _ in range(18):
            x=REF['forward'](x,EPS);lengths.append(len(x))
            assert ports.signature(REF['word'](x))==q
        triad[str(w)]={'charges':q,'lengths':lengths}
    cols={}
    witness=None
    for n in (2,3,4):
        for w in product(range(16),repeat=n):
            v=REF['word'](REF['forward'](REF['named'](w),EPS))
            sig=ports.signature(w)
            assert sig==ports.signature(v)
            k=(n,sig)
            if witness is None and k in cols and len(v)!=cols[k][1]:
                witness={'first':cols[k][0],'second':w,'after_one':[cols[k][1],len(v)],'charges':sig}
            cols.setdefault(k,(w,len(v)))
    # A stronger counterexample: same fourteen integer charges, different infinite growth regimes.
    bounded=(3,4,8); growing=(1,12,2)
    assert ports.signature(bounded)==ports.signature(growing)==(1,1,1,1,0,0)+(0,)*8
    def advance(w):
        return REF['cyclic'](REF['word'](REF['forward'](REF['named'](w),EPS)))
    period=[bounded]
    for _ in range(3):period.append(advance(period[-1]))
    assert period[-1]==period[0] and len(set(period))==3
    family=lambda k: (1,)+(0,)*k+(2,0,12,0)
    assert advance(advance(growing))==REF['cyclic'](family(1))
    for k in range(1,65):
        assert advance(family(k))==REF['cyclic'](family(k+1))
    same_sector={'bounded':bounded,'period_words':period,'growing':growing,
                 'intermediate':advance(growing),'t2':family(1),'checked_family_k':64}
    z=REF['named']((0,0,0))
    assert REF['equal'](z,REF['forward'](REF['forward'](z,EPS),EPS))
    assert witness is not None
    stamped={}
    for mask in ('010111','011011'):
        w=tuple(int(c)+1 for c in mask); sizes=[len(w)]
        for _ in range(4):
            w=ports.c1_step(w);sizes.append(len(w))
        stamped[mask]=sizes
    moduli=[m for m in range(2,13) if 1%m!=2%m and 3%m==0]
    assert moduli==[3]
    # Same disjoint-union relation holds before and after modular reduction.
    checked=0
    for bits in (2,3,4):
        for x,y in product(range(1,2**bits),repeat=2):
            if x&y:continue
            for m in range(2,14):
                assert ((x+y)-(x|y))%m==0
                checked+=1
    return {'triad':triad,'equal14_opposite_growth':same_sector,'equal14_witness':witness,'tested_C2_words_n2_4':sum(16**n for n in (2,3,4)),
            'masked_C1_lengths':stamped,'fixed_two_step_zero_named':True,'disjoint_merge_checks':checked}

if __name__=='__main__':
    result={'C1_pair_certificate':ports.certificate(REF),'C2_pair_certificate':ports.c2_edge_certificate(REF),
            'T_and_F':ports.c2(REF),'ports':extra_controls(),'raw':transport.raw(REF),'H6':transport.history(),
            'seam':geometry.seam(),'ising_and_masks':geometry.combinatorics(),'two_cycles':geometry.two_cycles()}
    c1 = [r['w'] for r in result['C1_pair_certificate']['certifying_words']]
    c2 = result['C2_pair_certificate']['certifying_inputs']
    result['independent_mod3_ranks'] = [ports.certify_independently(c1,REF,1),
                                        ports.certify_independently(c2,REF,2)]
    result['independent_sets'] = geometry.alternating()
    result['anchored_particle_dihedral'] = ports.single_particle(REF)
    print(json.dumps(result,indent=2,ensure_ascii=False))
