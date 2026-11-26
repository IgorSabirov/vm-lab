"""Exact replay for the cyclic binary operator. Python 3.9+, standard library."""
import json
from collections import Counter, defaultdict
from fractions import Fraction
from functools import lru_cache
from itertools import product
from math import comb, factorial, prod


@lru_cache(None)
def fib(k):
    if k < 2:
        return k
    return fib(k - 1) + fib(k - 2)


def factor(length):
    return fib(2 * length + 1)


def determinant(matrix):
    """Fraction-free Gaussian elimination with row swaps, independent of the ring."""
    rows = [row[:] for row in matrix]
    size = len(rows)
    previous, sign = 1, 1
    for k in range(size - 1):
        if not rows[k][k]:
            pivot_row = next((i for i in range(k + 1, size) if rows[i][k]), None)
            if pivot_row is None:
                return 0
            rows[k], rows[pivot_row] = rows[pivot_row], rows[k]
            sign *= -1
        pivot = rows[k][k]
        for i in range(k + 1, size):
            left = rows[i][k]
            for j in range(k + 1, size):
                rows[i][j] = (rows[i][j] * pivot - left * rows[k][j]) // previous
        previous = pivot
    return sign * rows[-1][-1]


def gram(word):
    n = len(word)
    # Build P(S-I)P by its entries. Sparse dot products construct BB^T.
    b = [{j: word[i] * word[j] * (int(j == (i+1) % n) - int(i == j))
          for j in {i, (i+1) % n} if word[i] and word[j]} for i in range(n)]
    return [[sum(x * row_j.get(k, 0) for k, x in row_i.items())
             for row_j in b] for row_i in b]


def shift_gram(k, t):
    return [[t * value + int(i == j) for j, value in enumerate(row)]
            for i, row in enumerate(k)]


def run_lengths(word):
    anchor = word.index(0)  # Defined on the zero and mixed sectors.
    rotated = word[anchor+1:] + word[:anchor+1]
    runs = []
    active = 0
    for bit in rotated:
        if bit:
            active += 1
        elif active:
            runs.append(active)
            active = 0
    return runs


@lru_cache(None)
def matchings(vertices, t):
    return sum(comb(vertices - k, k) * t**k for k in range(vertices//2 + 1))


def predicted(n, runs, t):
    if runs is None:  # Fully active, bipartite support is a cycle.
        return matchings(2*n, t) + t*matchings(2*n-2, t) - 2*t**n
    return prod(matchings(2*length, t) for length in runs)


@lru_cache(None)
def composition_sum(total, parts, power):
    # Coefficient of (sum_{l>=1} factor(l)^power z^l)^parts.
    if parts == 0:
        return int(total == 0)
    return sum(factor(length)**power * composition_sum(total-length, parts-1, power)
               for length in range(1, total-parts+2))


def verify(max_n=12):
    tested = Counter()
    by_det = {}
    pair_class = []
    for n in range(3, max_n+1):
        data = {}
        groups = defaultdict(list)
        for word in product((0, 1), repeat=n):
            k = gram(word)
            runs = None if all(word) else run_lengths(word)
            for t in (1, 2, -1):
                direct = determinant(shift_gram(k, t))
                assert direct == predicted(n, runs, t), (word, t)
                if t == 1:
                    data[word] = direct
                tested["direct_determinants"] += 1
            tested["words"] += 1
            if not runs:
                continue
            tested["mixed_words"] += 1
            profile = tuple(sorted(runs))
            value = data[word]
            assert by_det.setdefault(value, profile) == profile
            m, r = sum(word), len(runs)
            groups[m, r].append((profile, value))
            if (n, m, r) == (6, 4, 2):
                pair_class.append((value, k))

        all_active = (1,) * n
        assert data[all_active] == fib(2*n-1) + fib(2*n+1) - 2
        assert data[(0,) + (1,)*(n-1)] == fib(2*n-1)
        for word, before in data.items():
            if not any(word) or all(word):
                continue
            for j, bit in enumerate(word):
                if not bit:
                    continue
                a = b = 0
                while word[(j-a-1) % n]:
                    a += 1
                while word[(j+b+1) % n]:
                    b += 1
                after = data[word[:j]+(0,)+word[j+1:]]
                other = before // factor(a+b+1)
                assert before - after == other * fib(2*a+2) * fib(2*b+2)
                tested["single_cuts_from_mixed"] += 1

        for (m, r), values in groups.items():
            q, s = divmod(m, r)
            minimum = factor(q)**(r-s) * factor(q+1)**s
            maximum = factor(m-r+1) * 2**(r-1)
            observed = [v for _, v in values]
            assert (min(observed), max(observed)) == (minimum, maximum)
            for power in (1, 2):
                measured = Fraction(sum(v**power for v in observed), len(observed))
                expected = Fraction(composition_sum(m, r, power), comb(m-1, r-1))
                assert measured == expected
            for profile, count in Counter(profile for profile, _ in values).items():
                permutations = factorial(r) // prod(factorial(v) for v in Counter(profile).values())
                assert r * count == n * comb(n-m-1, r-1) * permutations
            assert (minimum != maximum) == (r >= 2 and m >= r+2)
            tested["mixed_classes"] += 1

        two_holes = []
        for d in range(1, n//2+1):
            word = tuple(int(i not in (0, d)) for i in range(n))
            value = data[word]
            assert value == factor(d-1) * factor(n-d-1)
            two_holes.append(value)
            tested["two_hole_distances"] += 1
        for d in range(1, len(two_holes)):
            assert two_holes[d-1]-two_holes[d] == fib(2*(n-2*d-1))

    count = len(pair_class)
    avg_det = Fraction(sum(v for v, _ in pair_class), count)
    variance = sum((v-avg_det)**2 for v, _ in pair_class)/count
    summed = [[count*int(i == j) + sum(k[i][j] for _, k in pair_class)
               for j in range(6)] for i in range(6)]
    det_avg = Fraction(determinant(summed), count**6)
    assert (avg_det, variance, det_avg) == (Fraction(77,3), Fraction(2,9), Fraction(39200,729))
    for a in range(20):
        for b in range(a+2, 41):
            assert factor(a)*factor(b)-factor(a+1)*factor(b-1) == fib(2*(b-a-1))
            tested["balancing_examples"] += 1
    for t in (-3, -1, 0, 1, 2, 3, 4):
        def loss(a, b):
            return (matchings(2*(a+b+1), t)
                    - matchings(2*a, t) * matchings(2*b, t))
        assert loss(0,0)*loss(1,1)-loss(0,1)*loss(1,0) == t*t*(t-1)
        for a in range(8):
            for b in range(8):
                left, right = matchings(2*a,t), matchings(2*b,t)
                prev_left = matchings(2*a-1,t) if a else 0
                prev_right = matchings(2*b-1,t) if b else 0
                assert loss(a,b) == (t*left*right + t*(prev_left*right + left*prev_right)
                                     + t*t*prev_left*prev_right)
                tested["weighted_cut_checks"] += 1
    return {"min_n": 3, "max_n": max_n, "t": [1, 2, -1],
            "counts": dict(tested), "distinct_mixed_profiles": len(by_det),
            "n6_r2_m4": {"frequency": dict(Counter(v for v, _ in pair_class)),
                         "mean": str(avg_det), "variance": str(variance),
                         "det_of_mean": str(det_avg), "gap": str(det_avg-avg_det)},
            "status": "PASS"}


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))