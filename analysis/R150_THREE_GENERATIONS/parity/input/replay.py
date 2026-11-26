"""Exact checks of 2/3. Run with Python 3 in this folder; no third-party packages."""
from collections import Counter, defaultdict
from fractions import Fraction
from itertools import combinations
from math import gcd
from step5 import canonical, gaps_between_marks, trace

def fibonacci_step(v):
    a, b = v
    return (a + b) % 2, a

def parity_orbit():
    states = [(1, 0), (1, 1), (0, 1)]
    for i, state in enumerate(states):
        assert fibonacci_step(state) == states[(i + 1) % 3]
    for a, b in states:
        assert sum((a * x + b * y) % 2 for x, y in states) == 2
    for q in (3, 4, 5):
        prev, curr = 2, q  # tr(A**n) for det A=1, tr A=q
        odd = []
        for n in range(1, 301):
            z = curr - 2
            odd.append(z % 2)
            assert z % 2 == (q % 2 and n % 3 != 0)
            prev, curr = curr, q * curr - prev
        print("trace", q, "odd ring determinants", Fraction(sum(odd), len(odd)))

def marked_rings():
    for n in range(6, 13):
        marked, orbits = Counter(), defaultdict(set)
        for a, b in combinations(range(n), 2):
            word = tuple(int(i in (a, b)) for i in range(n))
            gaps = gaps_between_marks(word)
            if min(gaps) < 2:
                continue
            length = trace(word)[5]["length"]  # direct named C1 evolution
            assert length == n + 6 - gaps.count(2)
            marked[length] += 1
            orbits[length].add(canonical(word))
        print("n", n, "marked", dict(sorted(marked.items())), "necklaces",
              {k: len(orbits[k]) for k in sorted(orbits)})
        if n >= 7:
            assert Fraction(marked[n + 5], sum(marked.values())) == Fraction(2, n - 5)
        if n == 8:
            assert marked == {13: 8, 14: 4} and all(len(x) == 1 for x in orbits.values())

def seam():
    for m in (3, 4, 5, 6, 8, 12, 24):
        # U maps j to j-8 (mod m). Compute the disjoint cycles explicitly.
        remaining = set(range(m))
        cycles = []
        while remaining:
            j = min(remaining)
            orbit = []
            while j in remaining:
                orbit.append(j)
                remaining.remove(j)
                j = (j - 8) % m
            cycles.append(orbit)
        # Exactly one constant vector per cycle spans the kernel of (I-U)^*(I-U).
        rank = m - len(cycles)
        assert {len(c) for c in cycles} == {m // gcd(m, 8)}
        print("seam dimension", m, "defect fraction", Fraction(rank, m))
        if len(cycles[0]) == 3:
            assert Fraction(rank, m) == Fraction(2, 3)

if __name__ == "__main__":
    parity_orbit()
    marked_rings()
    seam()
