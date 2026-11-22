"""Uniform mixed labelled rings. Print exact within-class loss and fixed-width cost."""
from collections import Counter
from fractions import Fraction
from itertools import product
import json
from math import comb, factorial, prod

from fibonacci import bareiss, class_metrics, fibonacci, original_matrix, partitions


def run_partitions(weight, runs, minimum=1):
    """Increasing tuples, in the order of the proposed conditional code."""
    if runs == 1:
        if weight >= minimum:
            yield (weight,)
        return
    for first in range(minimum, weight // runs + 1):
        for tail in run_partitions(weight - first, runs - 1, first):
            yield (first,) + tail


def from_words(n):
    census = Counter()
    for bits in product("01", repeat=n):
        word = "".join(bits)
        if "0" in word and "1" in word:
            cut = word.index("0")
            rotated = word[cut:] + word[:cut]
            lengths = tuple(sorted(len(run) for run in rotated.split("0") if run))
            census[lengths] += 1
            if n <= 8:
                assert bareiss(original_matrix(word)) == prod(fibonacci(2*l+1) for l in lengths)
    return census


def analyze(n, counts):
    census = from_words(n) if n <= 12 else None
    baseline = class_metrics(n, counts)
    mixed = 2**n - 2
    same_mass = Fraction()
    ambiguous = 0
    for weight in range(1, n):
        for r in range(1, min(weight, n-weight) + 1):
            ordered = comb(weight-1, r-1)
            gaps = comb(n-weight-1, r-1)
            class_size = n * ordered * gaps // r
            sizes = []
            determinants = set()
            singleton_counts = Counter()
            for lengths in run_partitions(weight, r):
                multiplicities = Counter(lengths)
                orders = factorial(r) // prod(factorial(m) for m in multiplicities.values())
                size, remainder = divmod(n * orders * gaps, r)
                assert remainder == 0
                sizes.append(size)
                singleton_counts[multiplicities[1]] += orders
                determinants.add(prod(fibonacci(2*l+1) for l in lengths))
                if census is not None:
                    assert census[lengths] == size
            assert len(determinants) == len(sizes) == counts[weight][r]
            assert sum(sizes) == class_size
            if weight > r:
                for j in range(r + 1):
                    k = r - 1 - j
                    expected = comb(r, j)*comb(weight-r-1, k) if 0 <= k <= weight-r-1 else 0
                    assert singleton_counts[j] == expected
            if len(sizes) > 1:
                ambiguous += class_size
            same_mass += Fraction(sum(s*s for s in sizes), class_size)
    assert ambiguous == baseline["labelled_ambiguous"]
    return dict(n=n, mixed=mixed, has_twin=str(Fraction(ambiguous, mixed)),
                different_on_redraw=str(1 - same_mass/mixed),
                max_distinct=baseline["max_distinct"],
                worst_case_bits=(baseline["max_distinct"] - 1).bit_length())


def main():
    # The two equal-determinant words are distinct rotation orbits even at r=2.
    a, b = "101000", "100100"
    assert b not in (a+a)[:-1]
    assert bareiss(original_matrix(a)) == bareiss(original_matrix(b)) == 4
    counts = partitions(24)
    rows = [analyze(n, counts) for n in range(3, 25)]
    assert rows[-1]["different_on_redraw"] == "1484917166086/1937306843615"
    print(json.dumps(dict(sampling="uniform mixed labelled word, uniform in its class with replacement",
                          direct_word_count_checked_through=12, sizes=rows), indent=2))


if __name__ == "__main__":
    main()
