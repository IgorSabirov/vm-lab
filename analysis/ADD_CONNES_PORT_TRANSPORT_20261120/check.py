"""Compare the graded R132 ring to the independent named ADD transition."""
from functools import lru_cache
from importlib.util import module_from_spec, spec_from_file_location
from itertools import product
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location("r132", ROOT / "R132_ADD_YM_CCM_20261119/verify.py")
r132 = module_from_spec(spec)
spec.loader.exec_module(r132)
engine, engine_hash = r132.load_engine()
EPS = (1, -1)


def endpoints(d, vertex_projections, edge_projections):
    source = -sum(pe @ d @ pv for pe, pv in zip(edge_projections, vertex_projections))
    return source, d + source


@lru_cache(None)
def ring(n):
    D = r132.graph_operators(n)
    d = D[n:, :n]
    ident = np.eye(n, dtype=int)
    sites = [np.diag(row) for row in ident]
    source, target = endpoints(d, sites, sites)
    return d, sites, source, target


def port_word(w, source, target, swap=False):
    if swap:
        source, target = target, source
    w = np.asarray(w)
    b = source @ np.diag(w & 10) @ source.T
    a = target @ np.diag(w & 5) @ target.T
    return tuple((a + b).diagonal().tolist())


def sector_counts(w, s, t, d, *, at_target=False):
    v_s, v_t = np.asarray(w) == s, np.asarray(w) == t
    e_s, e_t = (np.roll(x, -1) if at_target else x for x in (v_s, v_t))
    # Basis formula for the block traces, sum of |d_ij|^2 at selected incidences.
    weights = d * d.conj()
    return (int(e_s @ weights @ v_t), int(v_s @ weights.T @ e_t))


def check_word(w):
    n = len(w)
    d, _, source, target = ring(n)
    named = engine.named(w)
    if n > 1:
        assert port_word(w, source, target) == engine.word(engine.transport(named, 2))
        assert port_word(w, source, target, swap=True) == engine.word(engine.transport(named, 2, True))
        # Name of the i-th second output is old u_(i+1), by the join relations.
        twice = engine.transport(engine.transport(named, 2), 2)
        for i, (u, bits) in enumerate(twice):
            assert u == named[(i + 1) % n][0]
            assert bits == ((w[(i + 2) % n] & 5) | (w[i] & 10))
    else:
        assert np.count_nonzero(d) == 0
        assert engine.word(engine.transport(named, 2)) == w
    split = w.count(3) + w.count(12)
    merge = sum(sector_counts(w, s, t, d)[0] for s, t in ((1, 2), (8, 4)))
    assert n + split - merge == len(engine.forward(named, EPS))


def check_labels(w):
    n = len(w)
    d = ring(n)[0]
    for s, t in product(range(3), repeat=2):
        forward = sum(a == s and w[(i + 1) % n] == t for i, a in enumerate(w))
        backward = sum(a == t and w[(i + 1) % n] == s for i, a in enumerate(w))
        diagonal = w.count(s) if s == t else 0
        expected = (forward + diagonal, backward + diagonal) if n > 1 else (0, 0)
        assert sector_counts(w, s, t, d) == expected
        assert sector_counts(w[::-1], s, t, d) == expected[::-1]
        assert sector_counts(w, s, t, d, at_target=True) == expected[::-1]


def covariance_and_metric(n, rng):
    d, p, source, target = ring(n)
    # Independent changes of basis on vertices and edges.
    U, W = [np.linalg.qr(rng.normal(size=(n, n)) + 1j*rng.normal(size=(n, n)))[0]
            for _ in range(2)]
    source1, target1 = endpoints(W @ d @ U.conj().T,
                                 [U @ a @ U.conj().T for a in p],
                                 [W @ a @ W.conj().T for a in p])
    for a, b in ((source1, source), (target1, target)):
        assert np.allclose(a, W @ b @ U.conj().T)
    ix = np.arange(n)
    for origin in range(n):
        direct = abs(ix - origin)
        distances = np.minimum(direct, n - direct)
        f = np.diag(distances)
        comm = d @ f - f @ d
        assert np.array_equal((comm @ target.T).diagonal(), np.roll(distances, -1) - distances)
        assert np.isclose(np.linalg.norm(comm, ord=2), 1)


def main():
    exhaustive = 0
    for n in range(1, 4):
        for w in product(range(16), repeat=n):
            check_word(w)
            exhaustive += 1
    rng = np.random.default_rng(20261120)
    longer = 0
    for n in (4, 5, 8, 13, 24):
        for _ in range(32):
            check_word(tuple(rng.integers(16, size=n).tolist()))
            longer += 1
    triples = 0
    for n in range(1, 8):
        for w in product(range(3), repeat=n):
            check_labels(w)
            triples += 9
    for n in range(2, 13):
        covariance_and_metric(n, rng)
    witnesses = {}
    for w in ((1, 2, 0), (0, 2, 1)):
        d = ring(len(w))[0]
        states = [engine.named(w)]
        for _ in range(2):
            states.append(engine.forward(states[-1], EPS))
        full_D = r132.graph_operators(3)
        p1, p2 = [np.diag(np.tile(np.array(w) == s, 2)) for s in (1, 2)]
        observable = p1 @ full_D @ p2 @ full_D
        counts = sector_counts(w, 1, 2, d)
        assert counts == (int(np.trace(observable[3:, 3:])), int(np.trace(observable[:3, :3])))
        witnesses[''.join(map(str, w))] = dict(edge_vertex=counts, lengths=list(map(len, states)))
    assert witnesses['120']['lengths'] == [3, 2, 1]
    assert witnesses['021']['lengths'] == [3, 3, 4]
    print(json.dumps(dict(engine_sha256=engine_hash, full_alphabet_exhaustive_words=exhaustive,
                          full_alphabet_longer_words=longer, ternary_word_label_pairs=triples,
                          unitary_and_distance_tests_lengths=list(range(2, 13)),
                          witnesses=witnesses), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
