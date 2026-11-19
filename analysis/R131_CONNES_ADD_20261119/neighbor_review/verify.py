"""Integer diagnostics and named R130 trajectories for the R131 follow-up."""
from collections import Counter
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from itertools import product
import json
from pathlib import Path

import numpy as np


PARENT = Path(__file__).resolve().parents[1]
EPS = (1, -1)
PAIRS = {
    "published": ("00012021", "00100212"),
    "submitted": ("001122", "001221"),
    "shorter": ("01122", "01221"),
    "joint": ("01110212", "01120211"),
}


def load_module(name, path):
    spec = spec_from_file_location(name, path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digits(text):
    return tuple(map(int, text))


def stats(word):
    """Use the b-to-a cyclic order. Labels 0,1,2 cover the initial words."""
    n = len(word)
    sites = np.array(word)
    shift = np.roll(np.eye(n, dtype=np.int64), 1, axis=1)
    powers = [np.linalg.matrix_power(shift, d) for d in range(n)]
    projectors = [np.diag((sites == t).astype(np.int64)) for t in range(3)]
    sources = projectors
    targets = [shift @ p @ shift.T for p in projectors]
    counts = {}
    for d, move in enumerate(powers):
        for s, t in product(range(3), repeat=2):
            direct = sum(word[i] == s and word[(i+d) % n] == t for i in range(n))
            counted = np.trace(projectors[s] @ move @ projectors[t] @ move.T)
            assert counted == direct
            counts[s, t, d] = direct
            if d == 1:
                assert np.trace(sources[s] @ targets[t]) == direct
    p1 = projectors[1]
    one_triples = sum(all(word[(i+j) % n] == 1 for j in range(3)) for i in range(n))
    assert np.trace(p1 @ shift @ p1 @ shift @ p1 @ powers[2].T) == one_triples
    return counts, one_triples


def reversal_test(engine):
    def reversal(z):
        return engine.interact(engine.r2(z), EPS)

    z = engine.named((3,))
    back = engine.backward(z, EPS)
    rfr = engine.r2(engine.forward(engine.r2(z), EPS))
    tft = reversal(engine.forward(reversal(z), EPS))
    assert not engine.equal(rfr, back) and engine.equal(tft, back)
    return {name: engine.word(x) for name, x in (("RFR", rfr), ("TFT", tft), ("inverse", back))}


def label_map_test(engine):
    word = tuple(range(16))
    initial = engine.named(word)
    mapped = engine.r2(initial)
    perm = engine.word(mapped)
    assert perm == tuple(int(f"{i:04b}"[::-1], 2) for i in word)
    assert [u for u, _ in initial] == [u for u, _ in mapped]
    for s, t in product(range(16), repeat=2):
        assert [(a == s and b == t) for a, b in zip(word, word[1:] + word[:1])] == [
            a == perm[s] and b == perm[t] for a, b in zip(perm, perm[1:] + perm[:1])]
    return perm


def shorter_joint_search(engine):
    """Each bucket fixes exact occupancy and all oriented two-point counts."""
    records = []
    for n in range(1, 8):
        buckets = {}
        words_checked = 0
        for w in product(range(3), repeat=n):
            if 0 not in w or min(w.count(1), w.count(2)) < 2:
                continue
            occupied = tuple(s != 0 for s in w)
            counts = tuple(sum(w[i] == s and w[(i + d) % n] == t for i in range(n))
                           for d in range(n) for s, t in product(range(3), repeat=2))
            after = engine.forward(engine.forward(engine.named(w), EPS), EPS)
            key = occupied, counts
            assert buckets.setdefault(key, len(after)) == len(after)
            words_checked += 1
        records.append({"length": n, "inputs": words_checked, "distinct_data": len(buckets)})
    return records


def main():
    prior = load_module("r131_reference", PARENT / "verify.py")
    engine = load_module("r130_named", prior.ENGINE)
    original_checks = (PARENT / "CHECKS.json").read_bytes()
    assert (json.dumps(prior.main(), indent=2) + "\n").encode() == original_checks
    result = {"original_verifier_sha256": sha256((PARENT / "verify.py").read_bytes()).hexdigest(),
              "original_checks_sha256": sha256(original_checks).hexdigest(),
              "r130_engine_sha256": sha256(prior.ENGINE.read_bytes()).hexdigest(),
              "pairs": {}}
    for name, texts in PAIRS.items():
        a, b = map(digits, texts)
        ca, a111 = stats(a)
        cb, b111 = stats(b)
        snapshots = [prior.snapshot(w) for w in (a, b)]
        for w, snapshot in zip((a, b), snapshots):
            for order in (w, w[::-1]):
                for k in range(len(w)):
                    assert prior.snapshot(order[k:] + order[:k]) == snapshot
            assert prior.snapshot(tuple(int(s != 0) for s in w)) == snapshot
        runs = [prior.trajectory(engine, w, 2) for w in (a, b)]
        rows = [{"word": text, "trajectory": run, "snapshot": snap,
                 "C11_1": counts[1, 1, 1], "C12_1": counts[1, 2, 1],
                 "C12_2": counts[1, 2, 2], "typed_111": triples}
                for text, run, snap, counts, triples in zip(texts, runs, snapshots, (ca, cb), (a111, b111))]
        result["pairs"][name] = {
            "same_occupancy_sitewise": tuple(map(bool, a)) == tuple(map(bool, b)),
            "same_histogram": Counter(a) == Counter(b),
            "pair_entries": len(ca), "differing_pair_entries": sum(ca[k] != cb[k] for k in ca),
            "dihedrally_related": any(b == u[i:] + u[:i] for u in (a, a[::-1]) for i in range(len(a))),
            "states": rows}
        if name == "joint":
            assert ca == cb and (a111, b111) == (1, 0)
            assert all(snap == {"trace_V_delta_V_delta_V_delta_squared": 324, "occupied_triples": 2}
                       for snap in snapshots)
            result["pairs"][name]["common_counts_by_lag_source_target"] = [
                [[ca[s, t, d] for t in range(3)] for s in range(3)] for d in range(len(a))
            ]
        if name == "submitted":
            assert (ca[1, 1, 1], cb[1, 1, 1], ca[1, 2, 2], cb[1, 2, 2]) == (1, 0, 2, 1)
            assert all(snap == {"trace_V_delta_V_delta_V_delta_squared": 232, "occupied_triples": 2}
                       for snap in snapshots)
    expected = {"published": (False, True, [7, 8]), "submitted": (True, False, [4, 5]),
                "shorter": (True, False, [3, 4]), "joint": (True, True, [8, 7])}
    for name, (support, all_pairs, ends) in expected.items():
        pair = result["pairs"][name]
        assert pair["same_occupancy_sitewise"] == support and pair["same_histogram"]
        assert (pair["differing_pair_entries"] == 0) == all_pairs
        assert not pair["dihedrally_related"]
        assert [s["trajectory"][-1]["length"] for s in pair["states"]] == ends
    result["no_shorter_joint_witness_in_declared_domain"] = shorter_joint_search(engine)
    result["single_vertex_state_3"] = reversal_test(engine)
    result["R_label_permutation_0_to_15"] = label_map_test(engine)
    return result


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
