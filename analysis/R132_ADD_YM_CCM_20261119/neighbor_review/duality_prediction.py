"""Exact checks for the 26-dimensional witness and the two-step length observable."""
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from itertools import product
from pathlib import Path
import json

import numpy as np
from sympy import Matrix

ROOT = Path(__file__).resolve().parents[3]
ENGINE = ROOT / "analysis/ADD_NEIGHBOR_SYNTHESIS_20261117/verify.py"
ENGINE_HASH = "d46a47443e610ffe42a0160aaae0487e6c0a9be9e6b96bf72ce39962cf7cf9a1"
DIMS = (1, 1, 1, 1, 2, 2, 2, 2, 2, 2)


def load(path):
    spec = spec_from_file_location(path.stem, path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def matrices26():
    # Hom(C^dj, C^di); each ordered pair has multiplicity one.
    plus = [(4, 0), (5, 1), (6, 2), (7, 3), (8, 9), (0, 1)]
    cells = plus + [(j, i) for i, j in plus]
    basis = [(i, j, u, v) for i, j in cells for u in range(DIMS[i]) for v in range(DIMS[j])]
    pos = {entry: k for k, entry in enumerate(basis)}
    n = len(basis)
    eye = np.eye(n, dtype=int)
    flip = eye[[pos[j, i, v, u] for i, j, u, v in basis]]
    gamma = np.diag([1 if (i, j) in plus else -1 for i, j, _, _ in basis])
    link = np.zeros_like(eye)
    link[pos[0, 1, 0, 0], pos[0, 4, 0, 0]] = 1
    link += link.T.copy()
    D = link + flip @ link @ flip
    units = {}
    for i, dim in enumerate(DIMS):
        for s, t in product(range(dim), repeat=2):
            unit = np.zeros_like(eye)
            for k, (a, j, u, v) in enumerate(basis):
                if a == i and u == t:
                    unit[pos[i, j, s, v], k] = 1
            units[i, s, t] = unit
    opposite = {key: flip @ a.T @ flip for key, a in units.items()}
    assert n == 26 and all(np.any(a) for a in units.values())
    assert np.array_equal(flip @ flip, eye) and np.array_equal(gamma @ gamma, eye)
    assert not np.any(flip @ gamma + gamma @ flip)
    assert np.array_equal(D, D.T) and np.array_equal(flip @ D, D @ flip)
    assert not np.any(D @ gamma + gamma @ D)
    noncommuting = 0
    for a in units.values():
        assert np.array_equal(gamma @ a, a @ gamma)
        comm = D @ a - a @ D
        noncommuting += bool(np.any(comm))
        for b in opposite.values():
            assert np.array_equal(a @ b, b @ a)
            assert np.array_equal(comm @ b, b @ comm)
    form = Matrix([[int(np.trace(gamma @ units[i, 0, 0] @ opposite[j, 0, 0]))
                    for j in range(10)] for i in range(10)])
    assert form == -form.T and form.det() == 1 and noncommuting
    reversal = [int(f"{s:04b}"[::-1], 2) for s in range(16)]
    orbits = [(s,) for s in range(16) if reversal[s] == s]
    orbits.extend((s, t) for s, t in enumerate(reversal) if s < t)
    projectors = {s: units[i, j, j] for i, orbit in enumerate(orbits) for j, s in enumerate(orbit)}
    assert np.array_equal(sum(projectors.values()), eye)
    result = dict(dim=n, intersection_determinant=int(form.det()), intersection_rank=form.rank(),
                basis_pairs=len(units)**2, noncommuting_left_units=noncommuting,
                nonzero_D_entries=int(np.count_nonzero(D)), D_rank=Matrix(D).rank())
    return result, projectors


def grading_counts():
    onto = enabled = 0
    for assignment in product(range(4), repeat=6):
        if len(set(assignment)) != 4:
            continue
        onto += 1
        for signs in product((1, -1), repeat=6):
            # A shared scalar admits an odd link precisely if both signs occur there.
            enabled += len(set(zip(assignment, signs))) > 4
    assert (onto, enabled) == (1560, 74880)
    return dict(onto=onto, signed=64*onto, signed_allowing_nontrivial_D=enabled)


def counts(w):
    # Counts start at every position, including occurrences that wrap or overlap.
    n = len(w)
    wrap = (w * 4)[:n+3]
    pairs = list(zip(wrap, wrap[1:]))[:n]
    triples = list(zip(wrap, wrap[1:], wrap[2:]))[:n]
    quads = list(zip(wrap, wrap[1:], wrap[2:], wrap[3:]))[:n]
    return [pairs.count((1, 2)), pairs.count((2, 1)), triples.count((2, 1, 2)),
            triples.count((1, 2, 1)), quads.count((2, 1, 2, 1))]


def prediction(w):
    n12, n21, n212, n121, n2121 = counts(w)
    return [len(w), len(w)-n12, len(w)-2*n12+n21+n212+n121-n2121]


def actual(engine, w):
    x = engine.named(w)
    sizes = [len(x)]
    for _ in range(2):
        y = engine.forward(x, (1, -1))
        assert engine.equal(engine.backward(y, (1, -1)), x)
        sizes.append(len(y))
        x = y
    return sizes


def compare_three_point_counts(u, v, alphabet):
    """All oriented, translation-summed, typed triples, including coincident sites."""
    n = len(u)
    assert len(v) == n
    def masks(w):
        return [[sum((w[(i+d) % n] == s) << i for i in range(n))
                 for s in alphabet] for d in range(n)]
    a, b = masks(u), masks(v)
    for d, e in product(range(n), repeat=2):
        for i, j, k in product(range(len(alphabet)), repeat=3):
            assert (a[0][i] & a[d][j] & a[e][k]).bit_count() == (b[0][i] & b[d][j] & b[e][k]).bit_count()
    return n*n*len(alphabet)**3


def fiber_trace_counts(w, projectors):
    # Q_w is block diagonal in position. Read each block by its normalized
    # finite-space trace, then form the five cyclic traces on position space.
    shift = np.roll(np.eye(len(w), dtype=int), 1, axis=1)
    site = {}
    for s in (1, 2):
        rank = np.trace(projectors[s])
        raw = [np.trace(projectors[s] @ projectors[label]) for label in w]
        assert all(value in (0, rank) for value in raw)
        site[s] = np.diag(np.array(raw) // rank)
    result = []
    for pattern in [(1, 2), (2, 1), (2, 1, 2), (1, 2, 1), (2, 1, 2, 1)]:
        operator = site[pattern[0]]
        for s in pattern[1:]:
            operator = operator @ shift @ site[s]
        result.append(int(np.trace(operator @ np.linalg.matrix_power(shift.T, len(pattern)-1))))
    return result


def dynamics(engine, projectors):
    checked = 0
    for n in range(1, 10):
        for w in product(range(3), repeat=n):
            assert actual(engine, w) == prediction(w)
            checked += 1
    parent = [tuple(map(int, s)) for s in ("01110212", "01120211")]
    binary = [tuple(map(int, s)) for s in ("111111221212222222112121", "111112111121222221222212")]
    masked = [tuple(0 if i % 5 == 0 else w[i % 24] for i in range(120)) for w in binary]
    cases = {}
    for name, pair, alphabet in [("R131", parent, None), ("binary", binary, (1, 2)), ("masked", masked, (0, 1, 2))]:
        u, v = pair
        assert list(map(bool, u)) == list(map(bool, v))
        rows = []
        for w in pair:
            sizes = actual(engine, w)
            assert sizes == prediction(w)
            assert counts(w) == fiber_trace_counts(w, projectors)
            rows.append(dict(lengths=sizes, counts_12_21_212_121_2121=counts(w)))
        assert rows[0]["lengths"][2] != rows[1]["lengths"][2]
        cases[name] = {"words": ["".join(map(str, w)) for w in pair], "checks": rows}
        if alphabet:
            verified = compare_three_point_counts(u, v, alphabet)
            cases[name]["equal_three_point_counts"] = verified
    return dict(exhaustive_initial_words=checked, cases=cases)


if __name__ == "__main__":
    assert sha256(ENGINE.read_bytes()).hexdigest() == ENGINE_HASH
    old = load(Path(__file__).with_name("check.py"))
    assert old.minimum_dimension() == 24 and old.witness() == (24, 784, 8)
    result26, projectors = matrices26()
    output = dict(engine_sha256=ENGINE_HASH, witness26=result26, six_mixed=grading_counts(),
                  dynamics=dynamics(load(ENGINE), projectors), original_entropy=old.entropy_control())
    print(json.dumps(output, indent=2))
