"""Finite observation of the frozen, named one-channel R130 full map F=QI."""
from collections import Counter
from fractions import Fraction
from itertools import product
from math import fsum, log2
import json
import r130_reference as add


def information(rows):
    joint = Counter(rows)
    ht, ty, t = Counter(), Counter(), Counter()
    for (past, now, future), n in joint.items():
        ht[past,now] += n
        ty[now,future] += n
        t[now] += n
    terms = []
    violations = 0
    for (past, now, future), n in joint.items():
        ratio = Fraction(n * t[now], ht[past,now]*ty[now,future])
        violations += ratio != 1
        terms.append(n*log2(float(ratio)))
    return {'bits':fsum(terms)/len(rows), 'nonfactorizing_occupied_cells':violations}


def study(n):
    length_rows, charge_rows, suff_rows = [], [], []
    for word in product(range(4),repeat=n):
        x1 = add.forward(add.named(word))
        x2 = add.forward(x1)
        x3 = add.forward(x2)
        past, now, future = len(x1), len(x2), len(x3)
        bits = add.word(x2)
        charges = (sum(s & 1 for s in bits),sum((s>>1) & 1 for s in bits))
        assert charges == (sum(s & 1 for s in word),sum((s>>1)&1 for s in word))
        splits, merges = bits.count(3), add.nf(bits)
        assert future == now+splits-merges
        length_rows.append((past,now,future))
        charge_rows.append((past,(now,*charges),future))
        suff_rows.append((past,(now,splits,merges),future))
    strata = Counter(t for _,t,_ in length_rows)
    now = min(strata,key=lambda t:(-strata[t],t))
    buckets = {}
    for h,t,y in length_rows:
        if t == now:
            buckets.setdefault(h,Counter())[y] += 1
    choices = sorted(buckets,key=lambda h:(-sum(buckets[h].values()),h))[:2]
    example = {}
    if len(choices)==2:
        left,right=[buckets[i] for i in choices]
        tv = sum(abs(Fraction(left[k],sum(left.values()))-Fraction(right[k],sum(right.values())))
                 for k in set(left)|set(right))/2
        example = {'N2':now,'N1':choices,'N3_counts':[dict(left),dict(right)],'TV':str(tv)}
    sufficient = information(suff_rows)
    assert sufficient['nonfactorizing_occupied_cells']==0
    return {'L':n,'words':len(length_rows),'given_N2':information(length_rows),
            'given_N2_and_conserved_bits':information(charge_rows),'given_counts':sufficient,
            'example':example,'joint_N1_N2_N3':[[*k,v] for k,v in sorted(Counter(length_rows).items())]}


def swap_control():
    """Choose the first L=6 input with N2=8 and an effective adjacent bit exchange."""
    for word in product(range(4), repeat=6):
        x1 = add.forward(add.named(word))
        x2 = add.forward(x1)
        if len(x2) != 8:
            continue
        for j in range(len(x2)):
            k = (j+1) % len(x2)
            alternate = list(x2)
            alternate[j] = (x2[j][0], x2[k][1])
            alternate[k] = (x2[k][0], x2[j][1])
            alternate = tuple(alternate)
            m, m2 = add.nf(add.word(x2)), add.nf(add.word(alternate))
            if m == m2:
                continue
            before, after = len(add.forward(x2)), len(add.forward(alternate))
            assert Counter(add.word(x2)) == Counter(add.word(alternate))
            assert [u for u,_ in x2] == [u for u,_ in alternate]
            assert after-before == m-m2
            return {'input':word, 'N1':len(x1), 'N2':len(x2), 'positions_zero_based':[j,k],
                    'original_word':add.word(x2),'intervened_word':add.word(alternate),
                    'merges':[m,m2],'next_lengths':[before,after]}
    raise AssertionError('no effective swap')


if __name__ == '__main__':
    print(json.dumps({'runs':[study(n) for n in range(3,8)],'local_swap':swap_control()},ensure_ascii=False,indent=2))
