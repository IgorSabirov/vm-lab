"""Finite tests for R130/R141 and R135/R140/R144. Python 3 and SymPy."""
import argparse
from collections import Counter, defaultdict
from itertools import combinations, product
import json
from pathlib import Path

from sympy import Matrix, QQ, eye
from sympy.polys.matrices import DomainMatrix

K = QQ.cyclotomic_field(3)
omega = K.unit


def cyclic(word):
    return min(word[i:] + word[:i] for i in range(len(word)))


def forward_word(word):
    """One C1 step on cyclic words, projected from the named-ring dynamics."""
    n = len(word)
    merges = {i for i in range(n) if (word[i], word[(i + 1) % n]) == (1, 2)}
    ends = {(i + 1) % n for i in merges}
    start = next(i for i in range(n) if i not in ends)
    intermediate = []
    for k in range(n):
        i = (start + k) % n
        if i in ends:
            continue
        if i in merges:
            intermediate.append(3)
        elif word[i] == 3:
            intermediate.extend([1, 2])
        else:
            intermediate.append(word[i])
    m = len(intermediate)
    return tuple((intermediate[i] & 2) | (intermediate[(i + 1) % m] & 1)
                 for i in range(m))


def active_det(bits):
    n = len(bits)
    b = Matrix(n, n, lambda i, j: bits[i] * bits[j] *
               (int(i == (j + 1) % n) - int(i == j)))
    return int((eye(n) + b * b.T).det())


def run_determinant(bits):
    """Equivalent exact block formula from R141, with the fully closed ring handled separately."""
    if all(bits):
        return cycle_trace(len(bits), 3) - 2
    start = bits.index(0)
    blocks = ''.join(map(str, bits[start:] + bits[:start])).split('0')
    value = 1
    for block in blocks:
        a, b = 1, 2
        for _ in block:
            a, b = b, 3*b - a
        value *= a
    return value


def four_contacts(bits):
    # Under 0 -> 1 and 1 -> 2, the R135 positive orientation is 0101.
    windows = Counter(tuple(bits[(i+j) % len(bits)] for j in range(4))
                      for i in range(len(bits)))
    forward, reverse = windows[(0, 1, 0, 1)], windows[(1, 0, 1, 0)]
    return forward + reverse, forward - reverse


def word_experiment():
    words = sorted({cyclic(w) for w in product(range(2), repeat=6)})
    rows = {}
    for bits in words:
        counts = Counter((bits[i], bits[(i + 1) % len(bits)]) for i in range(len(bits)))
        state = tuple(1 + b for b in bits)
        lengths = [len(state)]
        for _ in range(4):
            state = forward_word(state)
            lengths.append(len(state))
        rows[''.join(map(str, bits))] = dict(
            pairs=[counts[p] for p in product(range(2), repeat=2)],
            det=active_det(bits), four_contacts=four_contacts(bits), lengths=lengths)
        assert active_det(bits) == run_determinant(bits)
    # Count unordered pairs of distinct cyclic words at uniform weight per necklace.
    same_pairs = []
    for (left, a), (right, b) in combinations(rows.items(), 2):
        if a['pairs'] == b['pairs']:
            same_pairs.append(dict(words=[left, right], det_equal=a['det'] == b['det'],
                                   length4_equal=a['lengths'][4] == b['lengths'][4]))
    return dict(cyclic_words=rows, pairs_with_equal_pair_counts=same_pairs)


def extension():
    summaries = []
    for n in range(6, 11):
        words = sorted({cyclic(w) for w in product(range(2), repeat=n)})
        classes = {k: defaultdict(list) for k in ('pairs', 'pairs_det', 'pairs_contacts', 'all')}
        for bits in words:
            pair_counts = Counter(zip(bits, bits[1:] + bits[:1]))
            counts = tuple(pair_counts[p] for p in product(range(2), repeat=2))
            det = run_determinant(bits)
            contacts = four_contacts(bits)
            word = tuple(1+b for b in bits)
            for _ in range(4):
                word = forward_word(word)
            lengths = [len(word), len(forward_word(word))]
            for kind, key in [('pairs', counts), ('pairs_det', counts+(det,)),
                              ('pairs_contacts', counts+contacts), ('all', counts+(det,)+contacts)]:
                classes[kind][key].append((''.join(map(str, bits)), lengths))
        for kind, partition in classes.items():
            for index, horizon in enumerate((4, 5)):
                failures = [[(a[0], a[1][index]), (b[0], b[1][index])]
                            for matches in partition.values()
                            for a, b in combinations(matches, 2) if a[1][index] != b[1][index]]
                summaries.append(dict(length=n, horizon=horizon, necklaces=len(words), features=kind,
                                      classes=len(partition), conflicting_pairs=len(failures),
                                      first_failure=failures[0] if failures else None))
    return summaries


def matrix_det(n, q, permutation, power, probe):
    """Direct 3n by 3n matrix over Q(omega), no spectral reduction."""
    entries = defaultdict(dict)

    def add(i, j, value):
        entries[i][j] = entries[i].get(j, K.zero) + value

    for site in range(n):
        for c in range(3):
            i = 3 * site + c
            add(i, i, K(q))
            if site + 1 < n:
                j, amplitude, inverse = i + 3, K.one, K.one
            else:
                j = permutation[c]
                exponent = (power + probe) % 3
                amplitude, inverse = omega ** exponent, omega ** (-exponent % 3)
            add(j, i, -amplitude)
            add(i, j, -inverse)
    value = DomainMatrix(dict(entries), (3*n, 3*n), K).det()
    integer = int(K.to_sympy(value))
    assert value == K(integer)
    return integer


def cycle_trace(n, q):
    a, b = 2, q
    for _ in range(n):
        a, b = b, q*b-a
    return a


def holonomy_experiment():
    controls = [
        ('I', (0, 1, 2), 0, [0, 0, 0]),
        ('M', (1, 2, 0), 0, [0, 1, 2]),
        ('omega_I', (0, 1, 2), 1, [1, 1, 1]),
        ('inverse_omega_I', (0, 1, 2), 2, [2, 2, 2]),
    ]
    rows = []
    for n, q in [(3, 3), (6, 3), (6, 4)]:
        v = cycle_trace(n, q)
        for name, permutation, power, eigen_exponents in controls:
            for probe in range(3):
                expected = 1
                for exponent in eigen_exponents:
                    factor = 2 if (probe + exponent) % 3 == 0 else -1
                    expected *= v - factor
                direct = matrix_det(n, q, permutation, power, probe)
                assert direct == expected, (n, q, name, probe, direct, expected)
                rows.append(dict(n=n, q=q, holonomy=name, probe_power=probe,
                                 V_n=v, determinant=direct))
    return rows


def reference_check(path):
    import importlib.util
    spec = importlib.util.spec_from_file_location('r130_reference', path)
    ref = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ref)
    steps = 0
    for n in range(6, 11):
        for raw in product(range(2), repeat=n):
            word = tuple(b + 1 for b in raw)
            graph = ref.named(word)
            for _ in range(5):
                graph = ref.forward(graph)
                word = forward_word(word)
                assert cyclic(ref.word(graph)) == cyclic(word)
                steps += 1
    return steps


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--reference', type=Path,
                        help='Optional path to pinned R130 r130_reference.py')
    args = parser.parse_args()
    out = dict(words=word_experiment(), length_extension=extension(),
               twisted_rings=holonomy_experiment())
    if args.reference:
        import sys
        print(f'R130 reference checks: {reference_check(args.reference)}', file=sys.stderr)
    print(json.dumps(out, indent=2))
