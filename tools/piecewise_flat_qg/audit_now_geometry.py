"""SPDX-License-Identifier: GPL-3.0-or-later.

Read-only geometry diagnostics for an existing NOW Engine snapshot.
This does not run the experiment or infer an arrow of time from its geometry.
"""
import argparse
from collections import Counter
import hashlib
from itertools import combinations
import json
from pathlib import Path
import platform
import time

import numpy as np
from signature_kernel import SignatureKernel


def signed_intervals(points):
    """Input columns are (t, x); the imported metric is diag(-1,+1)."""
    delta = points[:, None, :] - points[None, :, :]
    return delta[..., 1] ** 2 - delta[..., 0] ** 2


def gram_from_intervals(q, anchor=-1):
    """Unnormalized anchored Gram form; does not divide by null edge lengths."""
    q = np.asarray(q, dtype=float)
    if q.ndim != 2 or q.shape[0] != q.shape[1] or q.shape[0] < 2:
        raise ValueError("Require a square signed-interval array")
    if not np.isfinite(q).all() or not np.array_equal(q, q.T) or np.any(np.diag(q)):
        raise ValueError("Intervals must be finite, symmetric, with zero diagonal")
    anchor %= len(q)
    others = [i for i in range(len(q)) if i != anchor]
    a = q[anchor, others]
    return (a[:, None] + a[None, :] - q[np.ix_(others, others)]) / 2


def classify(kernel, matrix):
    r = kernel.classify(matrix, strict=False)
    return {k: v[0].tolist() for k, v in r.items()}


def reference_checks(kernel):
    # All ten squared edge lengths are positive, yet inertia is Lorentzian.
    q = np.ones((5, 5)) - np.eye(5)
    q[0, 1] = q[1, 0] = 9
    g = gram_from_intervals(q)
    c = classify(kernel, g)
    # Five events spanning only 1+1 cannot make a nondegenerate 4-simplex.
    points = np.array([[0., 0.], [1., 0.], [0., 2.], [3., 1.], [4., -2.]])
    rank_control = classify(kernel, gram_from_intervals(signed_intervals(points)))
    # Euclidean/Hilbert squared distances give a PSD Gram form.
    e = np.vstack([np.zeros(4), np.eye(4)])
    distances = ((e[:, None, :] - e[None, :, :]) ** 2).sum(-1)
    psd = classify(kernel, gram_from_intervals(distances))
    checks = {
        "all_spacelike_can_be_lorentzian": c["reliable"] and c["counts"] == [3, 1, 0],
        "all_spacelike_has_no_causal_vertex_edges": bool(np.all(q[np.triu_indices(5, 1)] > 0)),
        "five_1plus1_events_have_two_zero_directions": rank_control["reliable"] and rank_control["counts"] == [1, 1, 2],
        "hilbert_distances_are_psd": psd["reliable"] and psd["counts"] == [4, 0, 0],
    }
    return dict(checks=checks, all_spacelike_example=dict(q=q.tolist(), gram=g.tolist(),
                classification=c, eigenvalues=np.linalg.eigvalsh(g).tolist()),
                rank_control=rank_control, hilbert_control=psd)


def audit_snapshot(kernel, snapshot):
    events = [item["event"] for item in snapshot["log"] if item["kind"] == "event"]
    points = np.array([[e["t"], snapshot["lines"][e["owner"]]["x0"] +
                       snapshot["lines"][e["owner"]]["v"] * e["t"]] for e in events])
    if len(points) < 3:
        raise ValueError("At least three event records are required")
    q = signed_intervals(points)
    mirrored = points * np.array([-1., 1.])
    # A mirror of coordinates is NOT a simulated physical reverse process.
    reverse_q_error = float(np.max(np.abs(q - signed_intervals(mirrored))))
    # At most 64 non-collinear triples of the first 16 distinct event positions.
    # Deliberate bounded algebra/adapter check, not a sample of signature rates.
    unique = list(dict.fromkeys(map(tuple, points)))[:16]
    matrices, triples = [], []
    for indices in combinations(range(len(unique)), 3):
        tri = np.array([unique[i] for i in indices])
        a, b = tri[1] - tri[0], tri[2] - tri[0]
        if abs(a[0]*b[1]-a[1]*b[0]) <= 1e-10:
            continue
        matrices.append(gram_from_intervals(signed_intervals(tri)))
        triples.append(tri.tolist())
        if len(matrices) == 64:
            break
    if not matrices:
        raise ValueError("No non-collinear diagnostic triple in the bounded prefix")
    classified = kernel.classify(np.array(matrices), strict=False)
    counts = Counter(tuple(x) for x in classified["counts"].tolist())
    channels = []
    for item in snapshot["log"]:
        if item["kind"] != "channel":
            continue
        dt, dx = item["received"] - item["sent"], item["x1"] - item["x0"]
        channels.append(dict(id=item["id"], dt=dt, q=dx*dx-dt*dt))
    tol = snapshot["config"]["thresholds"]["causal_interval_tolerance"]
    checks = dict(
        all_tested_triangles_reliable=bool(classified["reliable"].all()),
        all_tested_triangles_1plus1=all(x == (1, 1, 0) for x in counts),
        time_coordinate_reflection_preserves_intervals=reverse_q_error == 0,
        channel_cone_containment=bool(channels) and all(c["q"] <= tol for c in channels),
        channel_orientation_is_forward=bool(channels) and all(c["dt"] >= -tol for c in channels),
        reflected_channels_change_orientation=bool(channels) and any(c["dt"] > tol for c in channels),
    )
    return dict(checks=checks, event_count=len(events), channel_count=len(channels),
                triangle_count=len(matrices), triangle_signature_counts={str(k): v for k, v in counts.items()},
                triangles=triples, channels=channels, maximum_reflection_interval_error=reverse_q_error,
                interpretation="Imported 1+1 geometry recovered; sign of time orientation is absent from q. No reverse dynamics run.")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--library", required=True, type=Path)
    p.add_argument("--snapshot", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    started = time.perf_counter()
    raw = a.snapshot.read_bytes()
    kernel = SignatureKernel(a.library)
    reference = reference_checks(kernel)
    trace = audit_snapshot(kernel, json.loads(raw))
    result = dict(passed=all(reference["checks"].values()) and all(trace["checks"].values()),
                  reference=reference, trace=trace, snapshot_sha256=hashlib.sha256(raw).hexdigest(),
                  library_sha256=hashlib.sha256(a.library.read_bytes()).hexdigest(),
                  python=platform.python_version(), numpy=np.__version__,
                  elapsed_seconds=time.perf_counter()-started,
                  execution="Read-only analysis of existing trace and explicit small matrices; no new model trajectories",
                  evidence_scope="Technical integration and counterexamples, not scientific confirmation from smoke")
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(dict(passed=result["passed"], reference_checks=reference["checks"],
                         trace_checks=trace["checks"], triangles=trace["triangle_count"],
                         channels=trace["channel_count"], seconds=result["elapsed_seconds"])))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
