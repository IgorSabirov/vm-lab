"""Check the fifth-step length formula against the pinned named R130 C1 engine."""
from collections import Counter
from itertools import product
import json

import r130_reference as engine


def canonical(word):
    return min(word[i:] + word[:i] for i in range(len(word)))


def gaps_between_marks(bits):
    marks = [i for i, bit in enumerate(bits) if bit]
    if not marks:
        return ()
    ends = marks[1:] + [marks[0] + len(bits)]
    return tuple(end - start - 1 for start, end in zip(marks, ends))


def overlap(bits, distance):
    return sum(bit * bits[(i + distance) % len(bits)] for i, bit in enumerate(bits))


def length_flux(word):
    merges = sum(v == 1 and word[(i + 1) % len(word)] == 2 for i, v in enumerate(word))
    return word.count(3), merges


def trace(bits):
    graph = engine.named(tuple(1 + bit for bit in bits))
    rows = []
    for t in range(6):
        word = engine.word(graph)
        splits, merges = length_flux(word)
        rows.append(dict(t=t, word=''.join(map(str, canonical(word))), length=len(word),
                         splits=splits, merges=merges))
        if t < 5:
            graph = engine.forward(graph)
            assert len(graph) == len(word) + splits - merges
    return rows


def symbolic_blocks(gaps, t):
    out = []
    for g in gaps:
        if t == 0:
            block = (2,) + (1,) * g
        elif t == 1:
            block = (3,) + (1,) * (g-1)
        elif t == 2:
            block = (0, 3) + (1,) * (g-1)
        elif t == 3:
            block = (0, 1, 0, 3) + (1,) * (g-2)
        elif t == 4:
            block = (1, 0, 1, 0) + ((2,) if g == 2 else (3,) + (1,) * (g-3) + (0,))
        else:
            raise ValueError(t)
        out.extend(block)
    return ''.join(map(str, canonical(tuple(out))))


def r141_det(bits):
    if all(bits):
        a, b = 2, 3
        for _ in bits:
            a, b = b, 3*b-a
        return a-2
    j = bits.index(0)
    runs = ''.join(map(str, bits[j:] + bits[:j])).split('0')
    answer = 1
    for run in runs:
        a, b = 1, 2
        for _ in run:
            a, b = b, 3*b-a
        answer *= a
    return answer


def features(bits):
    n = len(bits)
    pairs = Counter(zip(bits, bits[1:] + bits[:1]))
    windows = Counter(tuple(bits[(i+j) % n] for j in range(4)) for i in range(n))
    f, r = windows[(0, 1, 0, 1)], windows[(1, 0, 1, 0)]
    return dict(pairs=[pairs[p] for p in product(range(2), repeat=2)], D=r141_det(bits),
                M_plus=f+r, M_minus=f-r, C3=overlap(bits, 3))


def case(raw):
    bits = tuple(map(int, raw))
    return dict(bits=raw, gaps=gaps_between_marks(bits), features=features(bits), trace=trace(bits))


def verify():
    summaries = []
    for n in range(6, 13):
        necklaces = sorted({canonical(w) for w in product(range(2), repeat=n)})
        checked = 0
        for bits in necklaces:
            gaps = gaps_between_marks(bits)
            if not gaps or min(gaps) < 2:
                continue
            rows = trace(bits)
            k = len(gaps)
            c3 = overlap(bits, 3)
            assert c3 == gaps.count(2)
            assert [row['word'] for row in rows[:5]] == [symbolic_blocks(gaps,t) for t in range(5)]
            assert [row['length'] for row in rows] == [n,n-k,n,n+k,n+2*k,n+3*k-c3]
            assert (rows[4]['splits'], rows[4]['merges']) == (k-c3, 0)
            checked += 1
        summaries.append(dict(n=n, examined=len(necklaces), in_proved_family=checked))
    pair = [case('00001001'), case('00010001')]
    control = [case('000100111'), case('000111001')]
    assert [x['features']['C3'] for x in pair] == [1,0]
    assert [x['trace'][5]['length'] for x in pair] == [13,14]
    assert control[0]['features'] == control[1]['features']
    assert [x['trace'][5]['length'] for x in control] == [16,15]
    return dict(reference='c425c839a28efc4539b498302eb33a9000a5c74e',
                domain='cyclic binary preparation 0->1, 1->2; C1; k>=1; each gap >=2 zeros',
                counts=summaries, target_pair=pair, outside_domain=control)


if __name__ == '__main__':
    print(json.dumps(verify(), indent=2))
