"""Run the two-step witness on the pinned, named R130 operator. Python + NumPy."""
from collections import Counter
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
ENGINE = HERE.parent / "ADD_NEIGHBOR_SYNTHESIS_20261117" / "verify.py"
A = (0, 0, 0, 1, 2, 0, 2, 1)
B = (0, 0, 1, 0, 0, 2, 1, 2)
EPS = (1, -1)


def pair_counts(word):
    return [dict(Counter((s, word[(i + d) % len(word)]) for i, s in enumerate(word)))
            for d in range(len(word))]


def snapshot(word):
    length = len(word)
    identity = np.eye(length, dtype=np.int64)
    shift = np.roll(identity, 1, axis=1)
    laplacian = 2 * identity - shift - shift.T
    incidence = np.vstack((shift - identity, identity - shift))
    assert np.array_equal(incidence.T @ incidence, 2 * laplacian)
    occupied = np.diag([int(s != 0) for s in word])
    step = occupied @ laplacian
    trace = np.trace(step @ step @ step @ laplacian)
    occupied_triples = sum(all(word[(i + j) % length] != 0 for j in range(3))
                           for i in range(length))
    return {"trace_V_delta_V_delta_V_delta_squared": int(trace),
            "occupied_triples": occupied_triples}


def trajectory(engine, initial, steps):
    state = engine.named(initial)
    rows = []
    for step in range(steps + 1):
        word = engine.word(state)
        splits = sum(s in (3, 12) for s in word)
        merges = sum((s, word[(i + 1) % len(word)]) in ((1, 2), (8, 4))
                     for i, s in enumerate(word))
        rows.append({"t": step, "word": word, "length": len(word),
                     "splits_available": splits, "merges_available": merges})
        if step < steps:
            after = engine.forward(state, EPS)
            assert len(after) == len(state) + splits - merges
            assert engine.equal(engine.backward(after, EPS), state)
            state = after
    return rows


def main():
    digest = sha256(ENGINE.read_bytes()).hexdigest()
    assert digest == "d46a47443e610ffe42a0160aaae0487e6c0a9be9e6b96bf72ce39962cf7cf9a1"
    spec = spec_from_file_location("named_r130", ENGINE)
    engine = module_from_spec(spec)
    spec.loader.exec_module(engine)
    counts = pair_counts(A)
    assert counts == pair_counts(B)
    counts_array = [[[row.get((s, t), 0) for t in range(3)] for s in range(3)] for row in counts]
    traces = [snapshot(w) for w in (A, B)]
    assert [r["trace_V_delta_V_delta_V_delta_squared"] for r in traces] == [184, 186]
    assert [r["occupied_triples"] for r in traces] == [0, 1]
    trajectories = [trajectory(engine, w, 2) for w in (A, B)]
    assert [[row["length"] for row in run] for run in trajectories] == [[8, 7, 7], [8, 7, 8]]
    controls = [trajectory(engine, w, 1)[1]["length"]
                for w in ((1, 2, 0, 0, 0, 0), (2, 1, 0, 0, 0, 0))]
    assert controls == [5, 6]
    return {"engine_sha256": digest, "eps": EPS, "word_direction": "b to a",
            "correlation_axes": ["lag", "source_label", "target_label"],
            "common_correlations": counts_array, "entries_compared": 72,
            "observables_at_t0": traces, "named_trajectories_projected_to_words": trajectories,
            "six_site_order_control_next_lengths": controls}


if __name__ == "__main__":
    print(json.dumps(main(), indent=2) + "\n", end="")
