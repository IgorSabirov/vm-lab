"""Exact projection of author-clarified C1 onto oriented cyclic bit words.

Names are omitted ONLY for observables invariant under naming. The two named
implementations remain the independent references for local algebra.
"""
import math
import numpy as np


def interaction(w):
    w = np.asarray(w, dtype=np.uint8)
    starts = (w == 1) & (np.roll(w, -1) == 2)
    ends = np.roll(starts, 1)
    # Rotate a boundary-crossing merge to the beginning, preserving orientation.
    if ends[0]:
        w = np.roll(w, 1)
        starts = np.roll(starts, 1)
        ends = np.roll(ends, 1)
    splits = w == 3
    widths = np.ones(len(w), dtype=np.int64) + splits - ends
    offsets = np.cumsum(widths) - widths
    out = np.empty(int(widths.sum()), dtype=np.uint8)
    keep = ~ends
    out[offsets[keep]] = w[keep]
    out[offsets[starts]] = 3
    out[offsets[splits]] = 1
    out[offsets[splits] + 1] = 2
    return out, int(splits.sum()), int(starts.sum())


def half_shift(w, inverse=False):
    if inverse:
        return (w & 1) | (np.roll(w, -1) & 2)
    return (np.roll(w, -1) & 1) | (w & 2)


def step(w, inverse=False):
    if inverse:
        return interaction(half_shift(w, True))
    x, split, merge = interaction(w)
    return half_shift(x), split, merge


def pattern_measure(w):
    """Appendix B distance allows the pair's own particle after one circuit."""
    n = len(w)
    starts = np.flatnonzero((w == 1) & (np.roll(w, -1) == 2))
    if not len(starts):
        return 0, 0
    apos = np.flatnonzero(w & 1)
    bpos = np.flatnonzero(w & 2)
    best = n
    for i in starts:
        da = (apos - (i + 1)) % n
        db = (i - bpos) % n
        da[da == 0] = n
        db[db == 0] = n
        best = min(best, int(da.min()), int(db.min()))
    return len(starts), best


def counts(w):
    return int(np.count_nonzero(w & 1)), int(np.count_nonzero(w & 2))


def entropy(length, particles):
    # A finite combinatorial Boltzmann entropy, natural logarithms.
    if particles in (0, 2 * length):
        return 0.0
    return (math.lgamma(2 * length + 1) - math.lgamma(particles + 1)
            - math.lgamma(2 * length - particles + 1))


def local_entropy(w, radius):
    """Graph-distance ball: min(L,2r+1) distinct vertices; no repeated sites."""
    n = len(w)
    width = min(n, 2 * radius + 1)
    occ = (w & 1) + ((w >> 1) & 1)
    if width == n:
        value = entropy(n, int(occ.sum()))
        return value, value * n
    # All cyclic length-width windows; centring does not alter the sum.
    padded = np.concatenate((occ, occ[:width-1]))
    cumulative = np.concatenate(([0], np.cumsum(padded, dtype=np.int64)))
    pc = cumulative[width:] - cumulative[:-width]
    table = np.array([entropy(width, p) for p in range(2 * width + 1)])
    total = float(table[pc].sum())
    return total / n, total


def cyclic_equal(a, b):
    a, b = bytes(a), bytes(b)
    return len(a) == len(b) and b in a + a
