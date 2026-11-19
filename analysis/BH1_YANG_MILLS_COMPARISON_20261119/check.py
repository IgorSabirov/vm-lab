"""Recheck the finite R130 claims and an analytic two-branch BH1 control."""
from collections import Counter
from fractions import Fraction
from functools import lru_cache
from importlib.util import module_from_spec, spec_from_file_location
from itertools import product
from pathlib import Path

rule = Path(__file__).resolve().parents[1] / "ADD_NEIGHBOR_SYNTHESIS_20261117" / "verify.py"
spec = spec_from_file_location("r130", rule)
r = module_from_spec(spec)
spec.loader.exec_module(r)


@lru_cache(maxsize=16000)
def step(w):
    return r.cyclic(r.word(r.forward(r.named(w), (1, -1))))


def macro(w):
    pairs = tuple(zip(w, w[1:] + w[:1]))
    return len(w), tuple(w.count(j) for j in range(16)), pairs.count((1, 2)), pairs.count((8, 4))


def closed_orbits():
    seeds = {r.cyclic(w) for n in range(1, 4) for w in product(range(16), repeat=n)}
    closed, sizes = set(), Counter()
    for w in sorted(seeds):
        if w in closed:
            continue
        path = set()
        v = w
        for _ in range(80):
            if len(v) > 128:
                break
            if v in path:
                if v == w:
                    closed.update(path)
                    sizes[len(path)] += 1
                break
            path.add(v)
            v = step(v)
    labels = {w: macro(w) for w in closed}
    counts = [len(set(labels.values()))]
    while True:
        ids = {}
        refined = {w: ids.setdefault((v, labels[step(w)]), len(ids)) for w, v in labels.items()}
        counts.append(len(ids))
        if counts[-1] == counts[-2]:
            break
        labels = refined
    assert sizes == {1: 191, 2: 20, 3: 152} and len(closed) == 687 and counts == [483, 667, 667]
    print("Closed cyclic words:", len(closed), "periods:", dict(sorted(sizes.items())), "partitions:", counts)


def sparse_rings():
    for n in range(3, 55):
        for d in range(n - 1):
            w = [0] * n
            w[0] = 2
            w[d] |= 1
            y = step(tuple(w))
            a = next(i for i, v in enumerate(y) if v & 1)
            b = next(i for i, v in enumerate(y) if v & 2)
            prediction = (n, d-1) if d else (n+1, n-1)
            assert (len(y), (a-b) % len(y)) == prediction
    for n in range(2, 8):
        allowed = set()
        for a1, b1, a2, b2 in product(range(n), repeat=4):
            if a1 == a2 or b1 == b2:
                continue
            w = [0] * n
            for bit, pos in enumerate((a1, b1, a2, b2)):
                w[pos] |= 1 << bit
            allowed.add(r.cyclic(tuple(w)))
        assert len(allowed) == n*(n-1)**2
    print("Sparse recurrence checked for L=3..54; six-charge counts checked for L=2..7")


def coexistence_example():
    # V=R^3 with volume convention absorbed in the constants. At coexistence
    # s*Tc^4 = B+K/R^4. Compare the jump in E-3pV with the phase-line slope.
    for radius, offset, k in product(range(1, 6), range(4), range(1, 6)):
        r4 = radius**4
        s_tc4 = offset + Fraction(k, r4)
        delta_e = 4*radius**3*s_tc4
        delta_d = 4*radius**3*offset
        slope = 1-Fraction(k, r4)/s_tc4
        assert delta_d/delta_e == slope
    print("Coexistence slope checked for 100 exact rational parameter sets")


if __name__ == "__main__":
    closed_orbits()
    sparse_rings()
    coexistence_example()
