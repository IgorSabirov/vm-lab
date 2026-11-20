"""P10: read-only, independent reconstruction from immutable stage bundles.

This module does not call the producing stages' estimators.  It checks byte
provenance, independently calculates the four-point cumulant, fits the saved
response, integrates physical energy fluxes, reconstructs BBN observables and
the five-corner convergence gate.  The Planck replay uses the pinned external
likelihood itself, rather than trusting an earlier number or Gaussian Neff.

A numerical audit does not ratify a physical model.  Missing stages remain
PARTIAL, external model preparations remain CONDITIONAL, and a text declaring
"proof" never excuses an omitted branch.  The one supported proof checker is
a concrete violation of the declared isolated graph Hamiltonian on a saved
transition, scoped to that exact XA law and preparation.
"""
from __future__ import annotations

import csv
import base64
import hashlib
import importlib.metadata
import importlib.util
import itertools
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys

import numpy as np

from .common import (G_NEWTON_MEV_MINUS2, HBAR_MEV_S, InputError, OpenInput,
                     canonical_hash, read_json, sha256, write_csv, write_json)

KEY_FIELDS = ("claim_id", "model_id", "point_id", "thermal_path")
CORNERS = ("00", "10", "01", "11full", "11add")
SECTORS = ("X", "gamma", "nu", "free", "relic")
SPECIES = ("n", "p", "d", "t", "He3", "a", "Li7", "Be7")
DEFAULT_REQUIREMENTS = {
    "XA_carrier": ("P0", "P1", "P2", "P4", "P5", "P6", "P7", "P8", "P9"),
    "XB_SU3_cosmology": ("P0", "P1", "P5", "P6", "P7", "P8", "P9"),
    "graph_as_XB_marker": ("P0", "P2", "P3", "P4"),
}


def _key(value):
    if not isinstance(value, dict) or set(value) != set(KEY_FIELDS):
        raise InputError("Every expected/result key must contain the four claim/model/point/path fields")
    if any(not isinstance(value[k], str) or not value[k] for k in KEY_FIELDS):
        raise InputError("Empty or non-string matrix key")
    if value["claim_id"] not in DEFAULT_REQUIREMENTS:
        raise InputError("Unknown scientific claim")
    if value["thermal_path"] not in ("isolated_during_transition", "exchange_during_transition"):
        raise InputError("Unknown thermal path")
    return tuple(value[k] for k in KEY_FIELDS)


def _coverage_policy(config, inputs, expected_keys):
    """Bind non-validation matrix membership to frozen P0, before any audit.

    'full' means every P0 point and every applicable registered claim.  A
    registered_subset must name its restricted scope explicitly and can only
    produce a scoped conditional result.  Neither form changes the P0 origin
    of a point.  An empty independently calibrated set is not a complete
    physical calculation.
    """
    mode = config.get("_mode", "validation")
    if mode == "validation":
        return dict(scope="software_only", physical_completeness=False,
                    independently_calibrated_points=0, omitted_registered_keys=None,
                    reason="Engineering subset; no claim of physical matrix completeness")
    for name in ("model_register", "decision_rules"):
        if name not in inputs:
            raise OpenInput(f"P10 non-validation coverage requires frozen P0 {name}")
    registry = read_json(inputs["model_register"])
    decisions = read_json(inputs["decision_rules"])
    plan_path = Path(__file__).resolve().parents[2] / "PLAN.json"
    plan = read_json(plan_path)
    if registry.get("plan_sha256") != sha256(plan_path) or decisions.get("plan_sha256") != registry.get("plan_sha256"):
        raise InputError("P0 coverage files do not bind the executed R135 plan")
    if not registry.get("register_sha256") or decisions.get("register_sha256") != registry.get("register_sha256"):
        raise InputError("P0 model and decision snapshots come from different registries")
    rules = decisions.get("rules", [])
    if len({r["claim"] for r in rules}) != len(rules) or set(r["claim"] for r in rules) != set(plan["claims"]):
        raise InputError("P0 decision rules omit or duplicate a registered scientific claim")
    models = {m["model_id"]: m for m in registry.get("models", [])}
    if len(models) != len(registry.get("models", [])):
        raise InputError("Duplicate P0 model")
    allowed = {}
    for rule in rules:
        model_ids = rule.get("models", [])
        if not model_ids or len(set(model_ids)) != len(model_ids) or not set(model_ids) <= set(models):
            raise InputError("P0 claim refers to an unknown or duplicated model")
        allowed[rule["claim"]] = set(model_ids)
    points = registry.get("points", [])
    point_ids = [p["point_id"] for p in points]
    if len(set(point_ids)) != len(point_ids):
        raise InputError("P0 contains a duplicated point identity")
    for point in points:
        if point["model_id"] not in models or point["thermal_path"] not in models[point["model_id"]]["thermal_paths"]:
            raise InputError("P0 point has an incompatible model or thermal path")
        if point.get("role") not in ("diagnostic", "literature_benchmark", "physical_candidate"):
            raise InputError("Unknown P0 preparation origin")
    calibrated = sum(p.get("role") == "physical_candidate" for p in points)
    policy = config.get("coverage")
    if not isinstance(policy, dict) or policy.get("scope") not in ("full", "registered_subset"):
        raise InputError("P10 requires explicit coverage.scope = full or registered_subset")
    full_keys = {_key(dict(claim_id=claim, model_id=point["model_id"], point_id=point["point_id"],
                          thermal_path=point["thermal_path"]))
                 for point in points for claim in allowed if point["model_id"] in allowed[claim]}
    if policy["scope"] == "full":
        if any(name in policy for name in ("claims", "point_ids", "roles", "models", "thermal_paths")):
            raise InputError("Full coverage cannot silently filter P0 claims, points, origins or paths")
        derived = full_keys
        if not calibrated:
            raise OpenInput("Full physical R135 coverage has zero independently calibrated P0 points; external model benchmarks remain conditional")
    else:
        selected_points, claims = policy.get("point_ids"), policy.get("claims")
        if (not isinstance(selected_points, list) or not selected_points or len(set(selected_points)) != len(selected_points)
                or not set(selected_points) <= set(point_ids)):
            raise InputError("A registered subset must name unique existing P0 point IDs")
        if (not isinstance(claims, list) or not claims or len(set(claims)) != len(claims)
                or not set(claims) <= set(allowed)):
            raise InputError("A registered subset must name unique existing P0 claims")
        derived = {key for key in full_keys if key[2] in selected_points and key[0] in claims}
        if not derived:
            raise OpenInput("No P0 point applies to the declared scientific claim subset")
        if mode == "physical" and not any(p["point_id"] in selected_points and p["role"] == "physical_candidate" for p in points):
            raise OpenInput("Physical subset has zero independently calibrated points")
    if set(expected_keys) != derived:
        missing = sorted(derived - set(expected_keys))
        extra = sorted(set(expected_keys) - derived)
        raise InputError(f"Expected matrix differs from frozen P0 coverage: omitted={missing}; unregistered={extra}")
    for key in expected_keys:
        if key[1] not in allowed[key[0]]:
            raise InputError("A claim has been assigned to a model outside its P0 decision rule")
    return dict(scope=policy["scope"], physical_completeness=False,
                independently_calibrated_points=calibrated,
                omitted_registered_keys=len(full_keys - derived),
                registry_sha256=sha256(inputs["model_register"]),
                decision_rules_sha256=sha256(inputs["decision_rules"]),
                point_origins={p["point_id"]: p["role"] for p in points})


def _finite(value, label):
    try:
        number = float(value)
    except (ValueError, TypeError) as exc:
        raise InputError(f"{label}: invalid numeric value") from exc
    if not math.isfinite(number):
        raise InputError(f"{label}: nonfinite number")
    return number


def _close(actual, reported, label, *, rtol=2e-10, atol=1e-12):
    a, b = _finite(actual, label), _finite(reported, label)
    if abs(a - b) > atol + rtol * max(abs(a), abs(b)):
        raise InputError(f"Independent audit mismatch for {label}: reconstructed={a:.17g}, reported={b:.17g}")


def _bridge_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _csv(path):
    with Path(path).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def _safe_member(root, relative):
    p = Path(relative)
    if p.is_absolute() or not p.parts or any(part in ("..", ".", "") for part in p.parts):
        raise InputError("Unsafe audit bundle path")
    resolved = root
    for part in p.parts:
        resolved = resolved / part
        if resolved.is_symlink():
            raise InputError("Audit bundle contains a symlink")
    if not resolved.is_file():
        raise InputError(f"Missing audit artifact: {relative}")
    return resolved


def verify_bundle(manifest_path, expected_key=None, expected_stage=None):
    """Read without importing the producing contract or changing its directory."""
    manifest_path = Path(manifest_path)
    if manifest_path.name != "MANIFEST.json" or manifest_path.is_symlink():
        raise InputError("Expected an immutable stage MANIFEST.json")
    root = manifest_path.resolve().parent
    manifest = read_json(manifest_path)
    if manifest.get("schema") != "r135-stage-manifest-v1":
        raise InputError("Unknown stage manifest schema")
    listed = {}
    for record in manifest.get("files", []):
        relative = record["path"]
        if relative in listed or relative == "MANIFEST.json":
            raise InputError("Duplicate or self-referential manifest entry")
        path = _safe_member(root, relative)
        if path.stat().st_size != record["bytes"] or sha256(path) != record["sha256"]:
            raise InputError(f"Changed raw artifact: {relative}")
        listed[relative] = path
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    if actual != set(listed) | {"MANIFEST.json"}:
        raise InputError("Bundle contains unlisted files or omits a declared file")
    if not {"REQUEST.json", "EXECUTION_RECEIPT.json", "SOURCE.json"}.issubset(listed):
        raise InputError("Missing request/receipt/source provenance")
    request = read_json(listed["REQUEST.json"])
    receipt = read_json(listed["EXECUTION_RECEIPT.json"])
    source = read_json(listed["SOURCE.json"])
    digest = canonical_hash(request)
    if digest != manifest.get("request_sha256") or digest != receipt.get("request_sha256"):
        raise InputError("Request/receipt/manifest digest mismatch")
    if canonical_hash(request.get("config")) != request.get("config_sha256") or receipt.get("config_sha256") != request.get("config_sha256"):
        raise InputError("Configuration hash mismatch")
    if not re.fullmatch(r"[0-9a-f]{40}", receipt.get("execution_sha", "")) or receipt["execution_sha"] != request.get("execution_sha"):
        raise InputError("Executed source commit binding mismatch")
    source_digest = canonical_hash(source.get("files"))
    if source.get("sha256") != source_digest or request.get("source_sha256") != source_digest or receipt.get("source_sha256") != source_digest:
        raise InputError("Source inventory binding mismatch")
    if source.get("files") is None or len({x["path"] for x in source["files"]}) != len(source["files"]):
        raise InputError("Duplicate source inventory path")
    key = _key(request.get("key"))
    if _key(receipt.get("key")) != key or (expected_key is not None and _key(expected_key) != key):
        raise InputError("Matrix key does not match the executed stage")
    stage = request.get("stage")
    if receipt.get("stage") != stage or (expected_stage is not None and expected_stage != stage):
        raise InputError("Stage identity mismatch")
    if receipt.get("mode") != request.get("mode"):
        raise InputError("Stage evidence mode mismatch")
    if receipt.get("scientific_acceptance") != "owner_review":
        raise InputError("Stage incorrectly claims automatic scientific acceptance")
    if receipt.get("result", {}).get("software_status") == "PASS":
        plan = read_json(Path(__file__).resolve().parents[2] / "PLAN.json")
        definition = next((s for s in plan["stages"] if s["id"] == stage), None)
        if definition is None or not set(definition["deliverables"]) <= set(listed):
            raise InputError("A successful parent bundle omits a declared stage deliverable")
    return dict(root=root, manifest=manifest, files=listed, request=request, receipt=receipt,
                stage=stage, key=key, manifest_sha256=sha256(manifest_path), source=source)


def _partitions(items):
    """Independent recursive enumeration of all set partitions."""
    blocks = []
    def visit(position):
        if position == len(items):
            yield tuple(tuple(block) for block in blocks)
            return
        item = items[position]
        for block in blocks:
            block.append(item)
            yield from visit(position + 1)
            block.pop()
        blocks.append([item])
        yield from visit(position + 1)
        blocks.pop()
    yield from visit(0)


def connected_four_point(counts):
    """Reconstruct directly from the 81-cell joint probability table."""
    values = np.asarray(counts)
    if values.shape != (81,) or values.dtype.kind not in "iu" or np.any(values < 0) or values.sum() == 0:
        raise InputError("Malformed or empty raw four-point table")
    joint = values.reshape((3,) * 4) / values.sum()
    answer = 0.0
    for a in range(3):
        b = (a + 1) % 3
        for pattern in ((a, b, a, b), (b, a, b, a)):
            for partition in _partitions(tuple(range(4))):
                value = (-1) ** (len(partition) - 1) * math.factorial(len(partition) - 1)
                for block in partition:
                    index = tuple(pattern[i] if i in block else slice(None) for i in range(4))
                    value *= float(joint[index].sum())
                answer += value
    return float(answer)


def _batch_connected(counts):
    n = len(counts)
    joint = counts.reshape((n, 3, 3, 3, 3)) / counts.sum(axis=1).reshape(n, 1, 1, 1, 1)
    answers = np.zeros(n)
    for a in range(3):
        b = (a + 1) % 3
        for pattern in ((a, b, a, b), (b, a, b, a)):
            marginal = {}
            for mask in range(1, 16):
                group = tuple(i for i in range(4) if mask & (1 << i))
                index = (slice(None),) + tuple(pattern[i] if i in group else slice(None) for i in range(4))
                marginal[group] = joint[index].reshape(n, -1).sum(axis=1)
            for partition in _partitions(tuple(range(4))):
                contribution = np.ones(n) * ((-1) ** (len(partition) - 1) * math.factorial(len(partition) - 1))
                for group in partition:
                    contribution *= marginal[tuple(sorted(group))]
                answers += contribution
    return answers


def _rebuild_bootstrap(rows, low, high, cut, report):
    grouped = {}
    for row in rows:
        grouped.setdefault(row["chain_id"], []).append(row)
    draws, length = int(report["draws"]), int(report["block_length"])
    if draws < 20 or length < 1:
        raise InputError("Invalid saved bootstrap policy")
    generator = np.random.Generator(np.random.PCG64(int(report["bootstrap_seed"])))
    replicas = np.zeros((draws, 2, 81), dtype=np.int64)
    for chain, history in grouped.items():
        blocks = []
        for start in range(0, len(history), length):
            counts = np.zeros((2, 81), dtype=np.int64)
            for row in history[start:start + length]:
                stratum = 0 if row["plaquette"] <= low else 1 if row["plaquette"] >= high else None
                if stratum is not None:
                    measurement = next(item for item in row["counts_by_cut"] if abs(item["cut_rad"] - cut) <= 1e-14)
                    for axis in "xyz":
                        counts[stratum] += np.asarray(measurement["axes"][axis]["counts"])
            blocks.append(counts)
        blocks = np.asarray(blocks)
        selection = generator.integers(len(blocks), size=(draws, len(blocks)))
        for replica, index in enumerate(selection):
            replicas[replica] += blocks[index].sum(axis=0)
    valid = np.all(replicas.sum(axis=2) > 0, axis=1)
    _close(1 - valid.mean(), report["empty_draw_fraction"], "empty bootstrap fraction")
    if not np.any(valid):
        if report["interval95"] is not None:
            raise InputError("Finite interval reported without any valid bootstrap sample")
        return None
    values = _batch_connected(replicas[valid, 1]) - _batch_connected(replicas[valid, 0])
    interval = np.quantile(values, [.025, .975])
    if not np.allclose(interval, report["interval95"], rtol=1e-10, atol=2e-13):
        raise InputError("Independent block bootstrap does not reproduce the confidence interval")
    return interval.tolist()


def audit_p3(bundle, artifact_index=None):
    root = bundle["root"]
    mixing = read_json(root / "mixing.json")
    rows = []
    with (root / "heldout_counts.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                rows.append(json.loads(line))
    if not rows:
        return dict(status="PARTIAL", reason="NO_HELDOUT_CONFIGURATION", recomputed={})
    identities = [r["config_id"] for r in rows]
    if len(set(identities)) != len(identities) or any(r.get("role") != "heldout" for r in rows):
        raise InputError("Duplicated or non-heldout configurations in confirmatory sample")
    low, high = map(float, mixing["frozen_cuts"])
    if not low < high:
        raise InputError("Invalid frozen plaquette strata")
    calibration = read_json(root / "calibration.json")
    lock = dict(calibration)
    declared_lock = lock.pop("lock_sha256", None)
    digest = hashlib.sha256(json.dumps(lock, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    if digest != declared_lock:
        raise InputError("Frozen calibration was changed")
    _close(low, calibration["lower_cut"], "lower plaquette cut")
    _close(high, calibration["upper_cut"], "upper plaquette cut")
    if set(r["chain_id"] for r in rows) & set(calibration["calibration_chain_ids"]):
        raise InputError("Calibration/heldout chain overlap")
    wanted = set(calibration["selected_config_ids"])
    calibration_raw = {}
    possible = {root / "measurements.jsonl"}
    possible.update(p for p in (artifact_index or {}).values() if p.name == "measurements.jsonl")
    for candidate in possible:
        if not candidate.is_file():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row["config_id"] in wanted and row["role"] == "calibration" and row["grid_id"] == mixing["grid_id"]:
                if row["config_id"] in calibration_raw and canonical_hash(calibration_raw[row["config_id"]]) != canonical_hash(row):
                    raise InputError("Conflicting raw calibration configuration identity")
                calibration_raw[row["config_id"]] = row
    reasons = []
    if set(calibration_raw) != wanted:
        reasons.append("RAW_CALIBRATION_CONFIGURATIONS_NOT_AVAILABLE")
    else:
        values = [calibration_raw[identity]["plaquette"] for identity in calibration["selected_config_ids"]]
        cuts = np.quantile(values, [.25, .75], method="linear")
        _close(cuts[0], low, "independently reconstructed lower calibration quartile")
        _close(cuts[1], high, "independently reconstructed upper calibration quartile")
    summaries = _csv(root / "ym_connected.csv")
    answers = {}
    for summary in summaries:
        cut = float(summary["cut_rad"])
        tables = np.zeros((2, 81), dtype=np.int64)
        for row in rows:
            stratum = 0 if row["plaquette"] <= low else 1 if row["plaquette"] >= high else None
            matches = [m for m in row["counts_by_cut"] if abs(float(m["cut_rad"]) - cut) <= 1e-14]
            if len(matches) != 1:
                raise InputError("Incomplete or duplicate raw sector masks")
            for axis in "xyz":
                measurement = matches[0]["axes"][axis]
                n = np.asarray(measurement["counts"])
                if n.shape != (81,) or n.dtype.kind not in "iu" or np.any(n < 0):
                    raise InputError("Invalid raw table")
                if int(n.sum()) != measurement["accepted"] or not 0 <= measurement["accepted"] <= measurement["total"]:
                    raise InputError("Invalid raw coverage")
                if stratum is not None:
                    tables[stratum] += n
        if np.any(tables.sum(axis=1) == 0):
            if summary["D4"]:
                raise InputError("Reported D4 for an empty stratum")
            answers[str(cut)] = dict(status="EMPTY_STRATUM")
            continue
        d4 = connected_four_point(tables[1]) - connected_four_point(tables[0])
        _close(d4, summary["D4"], f"D4 cut={cut}", atol=2e-13)
        _close(tables[0].sum(), summary["low_windows"], "low pooled window count", rtol=0, atol=0)
        _close(tables[1].sum(), summary["high_windows"], "high pooled window count", rtol=0, atol=0)
        reported = [e for e in mixing["estimates"] if abs(e["cut_rad"] - cut) <= 1e-14]
        if len(reported) != 1 or not np.array_equal(tables, reported[0]["primary"]["pooled_counts"]):
            raise InputError("Pooled raw tables differ from the statistics artifact")
        interval = _rebuild_bootstrap(rows, low, high, cut, reported[0]["primary"])
        answers[str(cut)] = dict(D4=d4, interval95=interval, low_windows=int(tables[0].sum()), high_windows=int(tables[1].sum()))
    if len(answers) != len(summaries):
        raise InputError("Duplicate P3 summary cut")
    return dict(status="PARTIAL" if reasons else "RECONSTRUCTED", recomputed=answers, reasons=reasons,
                scientific_status=mixing.get("scientific_status", "INCONCLUSIVE"),
                interval_check="primary bootstrap independently resampled and recomputed")


def _energy(word, definition):
    h = definition["hamiltonian"]
    onsite = h["onsite"]
    value = float(h.get("constant_MeV", 0)) + sum(float(onsite[str(s)]) for s in word)
    pairs = h.get("pairs", {})
    value += sum(float(pairs.get(f"{word[i]},{word[(i + 1) % len(word)]}", 0)) for i in range(len(word)))
    for term in h.get("motifs", []):
        motif = term["labels"]
        count = sum(all(word[(i + j) % len(word)] == label for j, label in enumerate(motif)) for i in range(len(word)))
        value += float(term["coefficient_MeV"]) * count
    return value


def audit_p2(bundle):
    root = bundle["root"]
    law = read_json(root / "graph_law.json")
    prediction = read_json(root / "heldout_prediction.json")
    mapping = read_json(root / "state_map.json")
    definition = law["definition"]
    if prediction["law_sha256"] != canonical_hash(definition) or prediction.get("outcomes_read") is not False:
        raise InputError("Graph prediction is not bound to a pre-outcome law")
    residuals, reached = [], set()
    for preparation, trajectory in prediction["all_orbits"].items():
        for row in trajectory:
            reached.update(row["word"])
            _close(_energy(row["word"], definition), row["energy_MeV"], "graph Hamiltonian on raw word")
        for first, second in zip(trajectory, trajectory[1:]):
            records = [r for r in law["balance"] if r["preparation_id"] == preparation and r["step"] == second["step"]]
            if len(records) != 1:
                raise InputError("Missing or duplicated graph balance event")
            if definition["balance"]["kind"] == "isolated":
                transfer = 0.0
            else:
                transfer = float(definition["balance"]["transfers_MeV"][preparation][second["step"] - 1])
            residual = _energy(second["word"], definition) - _energy(first["word"], definition) - transfer
            _close(residual, records[0]["residual_MeV"], "graph energy balance")
            residuals.append(dict(preparation_id=preparation, step=second["step"], residual_MeV=residual))
    if sorted(reached) != mapping["reachable_labels"]:
        raise InputError("Saved reachable-label coverage differs from raw orbits")
    return dict(status="RECONSTRUCTED", residuals=residuals, law_sha256=canonical_hash(definition),
                balance_kind=definition["balance"]["kind"], reachable_labels=sorted(reached))


def audit_p4(bundle):
    root = bundle["root"]
    if not (root / "response_spec.json").exists():
        return dict(status="PARTIAL", reason="RAW_RESPONSE_FIT_SPECIFICATION_MISSING")
    spec = read_json(root / "response_spec.json")
    cases = spec.get("cases", [spec])
    raw = _csv(root / "retarded_response.csv")
    estimates = _csv(root / "relaxation_times.csv")
    if len(estimates) != len(cases) or len({r["case_id"] for r in estimates}) != len(cases):
        raise InputError("Missing or duplicate relaxation case")
    clock = spec.get("clock")
    physical = bool(clock and clock.get("unit") == "s" and clock.get("source") and
                    clock.get("origin") in ("measured_independently", "derived", "external_model"))
    factor = float(clock["seconds_per_time_unit"]) if physical else 1.0
    answers = {}
    for i, case in enumerate(cases):
        identifier = str(case.get("case_id", i))
        rows = [r for r in raw if r["case_id"] == identifier]
        summary = next((r for r in estimates if r["case_id"] == identifier), None)
        if summary is None or len(rows) < 4:
            raise InputError("Incomplete raw response")
        t = np.array([_finite(r["time"], "response time") for r in rows])
        y = np.array([_finite(r["response"], "response") for r in rows])
        if t[0] != 0 or np.any(np.diff(t) <= 0) or y[0] == 0:
            raise InputError("Invalid raw response chronology or zero overlap")
        z = y / y[0]
        area = float(np.trapezoid(z, t))
        analysis = read_json(root / f"response_analysis_{i}.json")
        _close(area, analysis["observed_integral"], "observed response integral")
        _close(z[-1], analysis["final_relative_amplitude"], "response final relative amplitude")
        result = dict(observed_integral=area, resolved=analysis["resolved"])
        if analysis["resolved"]:
            choose = z > 0
            if "fit_window" in case:
                lo, hi = np.array(case["fit_window"], float) * factor
                choose &= (t >= lo) & (t <= hi)
            x, logy = t[choose], np.log(z[choose])
            w = np.ones(len(x)) if case.get("sigma") is None else (y[choose] / np.array(case["sigma"])[choose]) ** 2
            mean_x = float(np.average(x, weights=w))
            mean_y = float(np.average(logy, weights=w))
            denominator = float(np.dot(w, (x - mean_x) ** 2))
            slope = float(np.dot(w * (x - mean_x), logy - mean_y) / denominator)
            if slope >= 0:
                raise InputError("A growing raw response was reported as a resolved decay")
            tau = -1 / slope
            _close(tau, summary["tau"], "fitted relaxation time")
            _close(tau, analysis["tau"], "relaxation analysis tau")
            _close(area + z[-1] * tau, analysis["integral_tau"], "tail-completed response integral")
            if summary["H_tau"]:
                if not physical or summary["mode_kind"] != "within_phase":
                    raise InputError("Htau cannot use a model/sweep clock or volume-switching mode")
                _close(float(case.get("H_s_inv", spec.get("H_s_inv"))) * tau,
                       summary["H_tau"], "Hubble-scaled relaxation")
            result["tau"] = tau
        elif summary["tau"]:
            raise InputError("An unresolved response was assigned an uncensored tau")
        answers[identifier] = result
    return dict(status="RECONSTRUCTED", recomputed=answers, physical_clock_declared=physical)


def _cumulative_trapezoid(y, t):
    y = np.asarray(y)
    shape = (len(t) - 1,) + (1,) * (y.ndim - 1)
    steps = np.diff(t).reshape(shape) * (y[1:] + y[:-1]) / 2
    return np.concatenate([np.zeros_like(y[:1]), np.cumsum(steps, axis=0)])


def _event(t, y, target):
    if y[0] >= target:
        return dict(censored=True, censoring="left", time_s=None, upper_bound_s=float(t[0]))
    hits = np.flatnonzero(y >= target)
    if not len(hits):
        return dict(censored=True, time_s=None, lower_bound_s=float(t[-1]))
    i = int(hits[0])
    time = t[0] if i == 0 else t[i - 1] + (t[i] - t[i - 1]) * (target - y[i - 1]) / (y[i] - y[i - 1])
    return dict(censored=False, time_s=float(time))


def _audit_parameter_intervals(root, ensemble):
    """Rebuild reported parameter quantiles from every retained raw draw."""
    if not isinstance(ensemble, dict) or ensemble.get("status") == "NOT_SUPPLIED":
        return dict(status="NOT_SUPPLIED")
    draws = ensemble.get("draws", [])
    if len(draws) != ensemble.get("draw_count") or len({d["id"] for d in draws}) != len(draws):
        raise InputError("Missing or duplicate propagated uncertainty draw")
    failed = [d["id"] for d in draws if d["status"] != "COMPLETE"]
    if failed:
        if ensemble["status"] != "INCOMPLETE_UNCERTAINTY" or ensemble.get("corners"):
            raise InputError("Failed uncertainty draws were dropped from a reported interval")
        return dict(status="INCOMPLETE_UNCERTAINTY", failed_draws=failed)
    if ensemble["interpretation"] not in ("probability_samples", "sensitivity_set"):
        raise InputError("Uncertainty draws have no statistical interpretation")
    if ensemble["status"] == "EMPIRICAL_PARAMETER_INTERVAL" and len(draws) < 40:
        raise InputError("A parameter confidence interval used fewer than its registered 40 samples")
    quantiles = [.025, .5, .975] if ensemble["interpretation"] == "probability_samples" else [0, .5, 1]
    if ensemble.get("quantile_probabilities") != quantiles:
        raise InputError("Parameter interval changed its frozen quantile convention")
    values = {corner: {n: [] for n in ("1", "10")} for corner in CORNERS}
    for draw in draws:
        directory = root / "uncertainty" / draw["id"]
        parameters = read_json(directory / "parameters.json")
        if canonical_hash({"inputs": parameters["inputs"], "config": parameters["config"]}) != draw["parameters_sha256"]:
            raise InputError("Propagated parameter realization hash mismatch")
        if set(draw["corners"]) != set(CORNERS):
            raise InputError("An uncertainty realization omits a portal corner")
        for corner in CORNERS:
            raw = read_json(directory / f"raw_history_{corner}.json")
            records, summary = raw["records"], raw["summary"]
            if canonical_hash(summary) != canonical_hash(draw["corners"][corner]):
                raise InputError("Propagated summary differs from its saved raw-history summary")
            t = np.asarray([r["time_s"] for r in records])
            if np.any(np.diff(t) <= 0):
                raise InputError("Invalid uncertainty history chronology")
            f = np.asarray([r["phase_fraction"] for r in records])
            old = np.asarray([r["old_physical_volume"] for r in records])
            energy = np.asarray([r["comoving_energy_sources_MeV4"] for r in records])
            normalization = summary["a0"] ** 3 * summary["latent_heat_MeV4"]
            for n in ("1", "10"):
                time = summary["t0_s"] + int(n) / summary["H0_s_inv"]
                if not t[0] <= time <= t[-1]:
                    raise InputError("Uncertainty draw is missing its fixed-H0 landmark")
                landmark = dict(phase_fraction=float(np.interp(time, t, f)),
                                old_physical_volume=float(np.interp(time, t, old)),
                                delivered_energy_over_a0cubed_L={sector: float(np.interp(time, t, energy[:, i]) / normalization)
                                                                for i, sector in enumerate(SECTORS)})
                stored = summary["landmarks"][n]
                for name in ("phase_fraction", "old_physical_volume"):
                    _close(landmark[name], stored[name], "raw uncertainty landmark " + name)
                for sector in SECTORS:
                    _close(landmark["delivered_energy_over_a0cubed_L"][sector],
                           stored["delivered_energy_over_a0cubed_L"][sector], "raw propagated channel energy")
                values[corner][n].append(landmark)
    for corner in CORNERS:
        for n in ("1", "10"):
            stored = ensemble["corners"][corner][n]
            for name in ("phase_fraction", "old_physical_volume"):
                expected = np.quantile([r[name] for r in values[corner][n]], quantiles)
                if not np.allclose(expected, stored[name], rtol=1e-10, atol=1e-12):
                    raise InputError("Propagated uncertainty quantiles do not match all raw realizations")
            for sector in SECTORS:
                expected = np.quantile([r["delivered_energy_over_a0cubed_L"][sector] for r in values[corner][n]], quantiles)
                if not np.allclose(expected, stored["delivered_energy_over_a0cubed_L"][sector], rtol=1e-10, atol=1e-12):
                    raise InputError("Propagated energy interval does not match all raw realizations")
    return dict(status="RECONSTRUCTED", draw_count=len(draws), interpretation=ensemble["interpretation"],
                quantile_probabilities=quantiles)


def audit_p7(bundle, quadrature_rtol=1e-3):
    root = bundle["root"]
    rows = _csv(root / "phase_history.csv")
    balance = read_json(root / "balance.json")
    payload = read_json(root / "channel_history.json")
    if set(balance["corners"]) != set(CORNERS) or set(payload["histories"]) != set(CORNERS):
        raise InputError("P7 must preserve all five independent histories")
    answers, unresolved = {}, []
    for corner in CORNERS:
        history = [r for r in rows if r["corner"] == corner]
        meta = balance["corners"][corner]
        def column(name):
            return np.array([_finite(row[name], name) for row in history])
        t, a, h, f, intensity = [column(name) for name in
                                  ("time_s", "scale_factor", "H_s_inv", "phase_fraction", "I")]
        if len(t) < 3 or np.any(np.diff(t) <= 0) or np.any(a <= 0) or np.any(h < 0) or np.any((f < 0) | (f > 1)):
            raise InputError("Invalid physical history chronology, scale factor or phase fraction")
        if len(set(t)) != len(t):
            raise InputError("Duplicate P7 sample coordinate")
        initial_f = float(meta.get("initial_phase_fraction", f[0]))
        old_fraction = (1 - initial_f) * np.exp(-intensity)
        if not np.allclose(f, 1 - old_fraction, rtol=1e-10, atol=1e-12):
            raise InputError("Phase fraction differs from saved homogeneous survival exponent")
        if not np.allclose(column("old_physical_volume"), a ** 3 * old_fraction, rtol=1e-10, atol=1e-12):
            raise InputError("Old physical volume omitted expansion or disagrees with raw phase fraction")
        rho = np.column_stack([column(f"rho_{s}_MeV4") for s in SECTORS])
        friedmann = np.sqrt(8 * np.pi * G_NEWTON_MEV_MINUS2 * rho.sum(axis=1) / 3) / HBAR_MEV_S
        if not np.allclose(h, friedmann, rtol=1e-10, atol=1e-15):
            raise InputError("Saved expansion history violates the declared Friedmann equation")
        pressure = np.column_stack([column(f"p_{s}_MeV4") for s in SECTORS])
        q = np.column_stack([column(f"Q_{s}_MeV4_s") for s in SECTORS])
        energy = np.column_stack([column(f"E_{s}_comoving_MeV4") for s in SECTORS])
        work = np.column_stack([column(f"work_{s}_comoving_MeV4") for s in SECTORS])
        normalization = float(meta["a0"]) ** 3 * float(meta["latent_heat_MeV4"])
        scale = max(sum(meta["initial_energy_MeV4"]), normalization)
        if normalization <= 0 or scale <= 0:
            raise InputError("Invalid latent-energy normalization")
        if np.max(np.abs(q.sum(axis=1))) > 1e-10 * max(float(np.abs(q).max()), 1e-300):
            raise InputError("Energy transfer violates reciprocal sector conservation")
        flux = a[:, None] ** 3 * q
        power = 3 * h[:, None] * a[:, None] ** 3 * pressure
        numeric_energy = _cumulative_trapezoid(flux, t)
        numeric_work = _cumulative_trapezoid(power, t)
        coarse = np.unique(np.r_[np.arange(0, len(t), 2), len(t) - 1])
        coarse_energy = _cumulative_trapezoid(flux[coarse], t[coarse])[-1]
        coarse_work = _cumulative_trapezoid(power[coarse], t[coarse])[-1]
        relative_energy = float(np.max(np.abs(numeric_energy - energy)) /
                                max(float(np.abs(energy).max()), scale * 1e-12))
        relative_work = float(np.max(np.abs(numeric_work - work)) /
                              max(float(np.abs(work).max()), scale * 1e-12))
        quad_error = max(relative_energy, relative_work)
        if quad_error > quadrature_rtol:
            unresolved.append(f"OUTPUT_QUADRATURE_UNRESOLVED:{corner}")
        closed = a[:, None] ** 3 * rho - np.array(meta["initial_energy_MeV4"])[None, :] - energy + work
        relative_sector = float(np.abs(closed).max() / scale)
        relative_total = float(np.abs(closed.sum(axis=1)).max() / scale)
        _close(relative_sector, meta["max_relative_sector_balance"], "sector energy balance", atol=1e-12)
        _close(relative_total, meta["max_relative_total_balance"], "total energy balance", atol=1e-12)
        radiation = None
        if all(f"E4_{sector}_MeV4" in history[0] for sector in SECTORS):
            e4 = np.column_stack([column(f"E4_{s}_MeV4") for s in SECTORS])
            trace4 = np.column_stack([column(f"trace4_{s}_MeV4") for s in SECTORS])
            initial4 = np.array(meta["initial_energy_MeV4"])[None, :] * meta["a0"]
            closure4 = a[:, None] ** 4 * rho - initial4 - e4 - trace4
            relative4 = float(np.abs(closure4).max() / (scale * meta["a0"]))
            _close(relative4, meta["max_relative_radiation_balance"], "radiation-weighted energy balance", atol=1e-12)
            integrated4 = _cumulative_trapezoid(a[:, None] ** 4 * q, t)
            integrated_trace = _cumulative_trapezoid(a[:, None] ** 4 * h[:, None] * (rho - 3 * pressure), t)
            error4 = float(np.abs(integrated4 - e4).max() / max(float(np.abs(e4).max()), scale * 1e-12))
            trace_error = float(np.abs(integrated_trace - trace4).max() / max(float(np.abs(trace4).max()), scale * 1e-12))
            if max(error4, trace_error) > quadrature_rtol:
                unresolved.append(f"RADIATION_OUTPUT_QUADRATURE_UNRESOLVED:{corner}")
            radiation = dict(relative_balance=relative4, relative_E4_quadrature_error=error4,
                             relative_trace_quadrature_error=trace_error)
        for target, stored in meta["events"].items():
            reconstructed = _event(t, f, float(target))
            if reconstructed["censored"] != stored["censored"]:
                raise InputError("Event censoring disagrees with saved trajectory")
            if not reconstructed["censored"]:
                _close(reconstructed["time_s"], stored["time_s"], "phase-fraction event")
            elif reconstructed.get("censoring") == "left":
                if stored.get("censoring") != "left":
                    raise InputError("An already completed transition was reported with the wrong censoring direction")
                _close(reconstructed["upper_bound_s"], stored["upper_bound_s"], "left-censored preparation time")
            else:
                _close(reconstructed["lower_bound_s"], stored["lower_bound_s"], "censored observation horizon")
        landmark_data = {}
        for n in (1, 10):
            time = float(meta["t0_s"]) + n / float(meta["H0_s_inv"])
            if not t[0] <= time <= t[-1]:
                raise InputError("A reported 1H/10H landmark lies outside the saved history")
            stored = meta["landmarks"][str(n)]
            _close(time, stored["time_s"], "fixed initial-Hubble landmark")
            fraction = float(np.interp(time, t, f))
            _close(fraction, stored["phase_fraction"], "phase fraction at fixed H0 time")
            delivered = {}
            for j, sector in enumerate(SECTORS):
                delivered[sector] = float(np.interp(time, t, numeric_energy[:, j]) / normalization)
                stored_from_raw = float(np.interp(time, t, energy[:, j]) / normalization)
                _close(stored_from_raw, stored["delivered_energy_over_a0cubed_L"][sector], "delivered energy normalization")
            landmark_data[str(n)] = dict(phase_fraction=fraction,
                                         directly_integrated_energy_over_a0cubed_L=delivered)
        # Check adapter payload is exactly the same history rather than a
        # substituted prescribed heating curve.
        channel = payload["histories"][corner]
        for field, reference in (("time_s", t), ("scale_factor", a), ("phase_fraction", f)):
            if not np.allclose(np.asarray(channel[field]), reference, rtol=0, atol=0):
                raise InputError("P7 canonical payload differs from archived raw history")
        for j, sector in enumerate(SECTORS):
            if not np.array_equal(np.asarray(channel["Q_MeV4_s"][sector]), q[:, j]):
                raise InputError("Channel source payload does not match the integrated history")
        answers[corner] = dict(landmarks=landmark_data, relative_sector_balance=relative_sector,
                               relative_total_balance=relative_total,
                               relative_energy_quadrature_error=relative_energy,
                               relative_work_quadrature_error=relative_work,
                               output_refinement_energy_delta=(numeric_energy[-1] - coarse_energy).tolist(),
                               output_refinement_work_delta=(numeric_work[-1] - coarse_work).tolist(),
                               radiation_weighted_check=radiation)
    uncertainty = _audit_parameter_intervals(root, balance.get("uncertainty_ensemble"))
    if uncertainty["status"] == "INCOMPLETE_UNCERTAINTY":
        unresolved.append("INCOMPLETE_PARAMETER_UNCERTAINTY")
    return dict(status="PARTIAL" if unresolved else "RECONSTRUCTED", recomputed=answers,
                reasons=unresolved, quadrature_rtol=quadrature_rtol,
                uncertainty_status=balance.get("uncertainty_ensemble", "NOT_SUPPLIED"),
                uncertainty_audit=uncertainty)


def mixed_gate(values, floor=1e-6):
    """Independent reconstruction of the frozen T3 numerical decision."""
    x = np.asarray(values, dtype=float)
    if x.shape != (3, 5) or not np.isfinite(x).all() or np.any(x <= 0):
        return dict(status="FAIL_CONVERGENCE", mixed_residual=[])
    residual = (x[:, 3] - x[:, 4]) / x[:, 0]
    abundance_ok = np.all(np.abs(x[:-1] - x[1:]) <= 0.1 * floor * x[1:])
    residual_ok = np.all(np.abs(np.diff(residual)) <= 0.1 * np.maximum(floor, np.abs(residual[1:])))
    status = "FAIL_CONVERGENCE" if not (abundance_ok and residual_ok) else (
        "RESOLVED" if abs(residual[-1]) > floor else "BELOW_NUMERICAL_FLOOR")
    return dict(status=status, mixed_residual=residual.tolist(),
                each_abundance_converged=bool(abundance_ok), residual_converged=bool(residual_ok))


def _lookup_input(bundle, name, artifact_index):
    candidates = [r for r in bundle["request"].get("inputs", []) if r.get("name") == name]
    if len(candidates) != 1:
        return None
    digest = candidates[0]["sha256"]
    if digest in artifact_index:
        return artifact_index[digest]
    original = Path(candidates[0]["path"])
    # A surviving external input is usable only with the frozen digest.  A
    # relative path cannot be interpreted relative to an unrelated audit cwd.
    if original.is_absolute() and original.is_file() and not original.is_symlink() and sha256(original) == digest:
        return original
    return None


def audit_p8(bundle, artifact_index):
    root = bundle["root"]
    bbn = read_json(root / "bbn_inputs.json")
    weak = read_json(root / "weak_rates_manifest.json")
    cmb = read_json(root / "class_inputs.json")
    source_path = _lookup_input(bundle, "channel_history", artifact_index)
    if source_path is None:
        return dict(status="PARTIAL", reason="COMPUTED_P7_HISTORY_NOT_AVAILABLE_TO_AUDITOR")
    if sha256(source_path) != bbn["source_P7_file_sha256"]:
        raise InputError("P8 source history digest differs from the audited P7 artifact")
    source = read_json(source_path)["histories"]
    if set(bbn["histories"]) != set(CORNERS) or set(cmb["histories"]) != set(CORNERS):
        raise InputError("P8 dropped a portal corner")
    for corner in CORNERS:
        item = bbn["histories"][corner]
        canonical = item["canonical"]
        if item["source_history_sha256"] != _bridge_hash(source[corner]):
            raise InputError("P8 has substituted a history from another computation")
        for name, values in canonical["history"].items():
            if name not in source[corner] or canonical_hash(values) != canonical_hash(source[corner][name]):
                raise InputError("P8 changed a computed physical history field")
        if _bridge_hash(canonical["history"]) != canonical["provenance"]["history_sha256"]:
            raise InputError("Canonical BBN history hash mismatch")
        if _bridge_hash(canonical["rates"]) != canonical["provenance"]["rates_sha256"]:
            raise InputError("Canonical nuclear table hash mismatch")
        if canonical_hash(item["weak_rates"]) != weak["histories"][corner]["weak_rates_sha256"]:
            raise InputError("Weak-rate provenance mismatch")
        if cmb["histories"][corner]["source_P7_history_sha256"] != _bridge_hash(source[corner]):
            raise InputError("CMB matching refers to a different P7 history")
    return dict(status="RECONSTRUCTED", computed_histories_retained=5,
                distinction="prepared inputs; actual native reads independently verified at P9")


def _bbn_likelihood(DH, yp, releases, theory):
    measurements = {r["observable"]: r for r in releases if r.get("state", r.get("kind")) == "published_statistic"}
    names = ("log10_D_over_H", "Y_p")
    mean = np.array([measurements[n]["value"] for n in names])
    covariance = np.diag([measurements[n]["sigma"] ** 2 for n in names]) + np.asarray(theory)
    delta = np.array([math.log10(DH), yp]) - mean
    sign, logdet = np.linalg.slogdet(covariance)
    if sign != 1:
        raise InputError("Nonpositive BBN likelihood covariance")
    chi2 = float(delta @ np.linalg.solve(covariance, delta))
    return -.5 * (chi2 + logdet + 2 * math.log(2 * math.pi))


_PLANCK_CACHE = {}


def _planck_replay(spectra, nuisance, root):
    """Separate raw clipy evaluation and independent nuisance-prior arithmetic."""
    os.environ["CLIPY_NOJAX"] = "1"
    try:
        import clipy
    except ImportError as exc:
        raise OpenInput("Planck audit requires the pinned clipy environment") from exc
    package = Path(__file__).resolve().parents[1] / "planck_pr3"
    release, policy = read_json(package / "release.json"), read_json(package / "nuisance.json")
    cache_key = (str(Path(root).resolve()), sha256(package / "release.json"))
    if cache_key not in _PLANCK_CACHE:
        for line in (package / "wheels.lock").read_text().splitlines():
            match = re.match(r"([\w.-]+)==([^ ]+)", line)
            if match:
                try:
                    actual = importlib.metadata.version(match[1])
                except importlib.metadata.PackageNotFoundError as exc:
                    raise OpenInput(f"Planck audit dependency absent: {match[1]}") from exc
                if actual != match[2]:
                    raise OpenInput(f"Planck audit dependency differs from pinned version: {match[1]}")
        distribution = importlib.metadata.distribution("clipy-like")
        direct = json.loads(distribution.read_text("direct_url.json") or "{}")
        archive = (package / "clipy.lock").read_text().split("--hash=sha256:")[1].strip()
        if direct.get("archive_info", {}).get("hashes", {}).get("sha256") != archive:
            raise InputError("Planck audit clipy archive is not the pinned source")
        verified = 0
        for record in distribution.files or []:
            if str(record).startswith("clipy/") and str(record).endswith(".py"):
                declared = record.hash
                if declared is None or declared.mode != "sha256":
                    raise InputError("Planck audit code lacks installed-file digest")
                digest = base64.urlsafe_b64encode(hashlib.sha256(distribution.locate_file(record).read_bytes()).digest()).decode().rstrip("=")
                if digest != declared.value:
                    raise InputError("Planck audit installed code has changed")
                verified += 1
        if not verified:
            raise InputError("Planck audit clipy source inventory is empty")
        for relative, (size, digest) in release["members"].items():
            path = _safe_member(Path(root), relative)
            if path.stat().st_size != size or sha256(path) != digest:
                raise InputError("Planck audit release hash mismatch")
        _PLANCK_CACHE[cache_key] = {name: clipy.clik(str(Path(root) / component["path"]))
                                    for name, component in release["components"].items()}
    if spectra["unit"] != "microK^2" or spectra["convention"] != "Cl":
        raise InputError("CMB audit requires Cl in microkelvin squared")
    ell = np.asarray(spectra["ell"])
    if not np.array_equal(ell, np.arange(2, len(ell) + 2)) or ell[-1] < 2508:
        raise InputError("CMB audit found a missing multipole")
    cl = np.zeros((6, 2509))
    for i, name in enumerate(("TT", "EE", "BB", "TE", "TB", "EB")):
        if name in spectra:
            cl[i, 2:] = np.asarray(spectra[name])[:2507]
    if set(nuisance) != set(policy["parameters"]):
        raise InputError("Incomplete Planck nuisance vector")
    prior = 0.0
    for name, specification in policy["parameters"].items():
        value = _finite(nuisance[name], name)
        if "fixed" in specification:
            _close(value, specification["fixed"], "fixed nuisance", rtol=0, atol=1e-12)
            continue
        distribution = specification["prior"]
        if distribution["dist"] == "uniform":
            lo, hi = distribution["min"], distribution["max"]
            if not lo <= value <= hi:
                raise InputError("Planck nuisance lies outside registered prior")
            prior -= math.log(hi - lo)
        elif distribution["dist"] == "norm":
            sigma = distribution["scale"]
            prior -= .5 * ((value - distribution["loc"]) / sigma) ** 2 + math.log(sigma * math.sqrt(2 * math.pi))
        else:
            raise InputError("Unsupported registered nuisance prior")
    # The common SZ prior is recorded explicitly by the frozen Planck policy.
    sz = policy["joint_SZ"]
    combination = sum(nuisance[name] * weight for name, weight in sz["weights"].items())
    prior -= .5 * ((combination - sz["mean"]) / sz["sigma"]) ** 2 + math.log(sz["sigma"] * math.sqrt(2 * math.pi))
    components = {}
    for name, likelihood in _PLANCK_CACHE[cache_key].items():
        components[name] = float(likelihood(cl[:, :max(likelihood.lmax) + 1], nuisance))
    return dict(logL=float(sum(components.values())), log_prior=float(prior), components=components)


def _replay_batch(batch, config, workdir):
    root = config.get("planck_data_root")
    if root is None:
        raise OpenInput("PLANCK_RAW_REPLAY_NOT_AVAILABLE")
    interpreter = config.get("planck_python")
    if interpreter is None:
        return {name: _planck_replay(item["spectra"], item["nuisance"], root)
                for name, item in batch.items()}
    executable = Path(interpreter)
    if not executable.is_file() or sha256(executable) != config.get("planck_python_sha256"):
        raise InputError("Planck audit interpreter is not the explicitly pinned executable")
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    request = {"batch": batch, "data_root": str(Path(root).resolve()),
               "audit_source_sha256": sha256(Path(__file__))}
    request_path, output_path = workdir / "request.json", workdir / "result.json"
    write_json(request_path, request)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    environment["CLIPY_NOJAX"] = "1"
    with (workdir / "replay.log").open("w") as log:
        subprocess.run([str(executable), "-m", "r135.audit", "planck-replay", str(request_path), str(output_path)],
                       env=environment, stdout=log, stderr=subprocess.STDOUT, check=True)
    result = read_json(output_path)
    if result["request_sha256"] != canonical_hash(request) or result["audit_source_sha256"] != request["audit_source_sha256"]:
        raise InputError("Independent Planck replay result does not bind its exact request/code")
    return result["results"]


def _cmb_replay_plan(root, rows, precision, config):
    """Bind each refinement to its actual spectrum and own nuisance vector.

    Profiling may choose a different nuisance vector at each accuracy, so the
    finest vector cannot be silently reused to audit a coarse likelihood.
    """
    path = root / "planck_evaluations.json"
    archive = read_json(path).get("evaluations", {}) if path.is_file() else {}
    batch, saved = {}, {}
    for row in rows:
        name = f"{row['engine']}/{row['corner']}"
        directory = root / "class" / row["engine"] / row["corner"]
        final = read_json(directory / "likelihood.json")["CMB"]
        gate = precision.get(name, {"status": "NOT_VALIDATED"})
        if gate["status"] not in ("PASS", "FAIL_CMB_CONVERGENCE", "NOT_VALIDATED"):
            raise InputError("Unknown CMB accuracy refinement status")
        if gate["status"] == "NOT_VALIDATED":
            tags = [name]
        else:
            levels = config.get("class_refinement", [])
            values = np.asarray(gate.get("logL_by_accuracy", []), float)
            if len(levels) not in (2, 3) or len(values) != len(levels) or not np.isfinite(values).all():
                raise InputError("CMB refinement does not match the registered accuracy levels")
            limit = float(config.get("max_cmb_delta_logL", 0))
            if not np.isfinite(limit) or limit <= 0:
                raise InputError("CMB refinement has no registered numerical tolerance")
            _close(limit, gate["max_delta_logL"], "registered CMB numerical tolerance")
            changes = np.abs(np.diff(values))
            if not np.allclose(changes, gate["adjacent_delta_logL"], rtol=1e-10, atol=1e-12):
                raise InputError("CMB refinement differences do not follow its saved likelihood values")
            status = "PASS" if np.all(changes <= limit) else "FAIL_CMB_CONVERGENCE"
            if gate["status"] != status:
                raise InputError("CMB likelihood refinement failed its registered numerical tolerance")
            tags = [f"{name}@accuracy{i}" for i in range(len(levels) - 1)] + [name]
        for index, tag in enumerate(tags):
            refined = directory if tag == name else directory.with_name(directory.name + f".accuracy-{index}")
            record = archive.get(tag, final if tag == name and len(tags) == 1 else None)
            if record is None:
                raise InputError("Missing actual Planck nuisance vector for a CMB accuracy refinement")
            spectra = read_json(refined / "spectra.json")
            if canonical_hash(spectra) != record["spectra_sha256"]:
                raise InputError("CMB accuracy refinement is bound to a different raw spectrum")
            if len(tags) > 1:
                _close(record["logL"], gate["logL_by_accuracy"][index], "CMB refinement likelihood source")
            if tag == name and canonical_hash(record) != canonical_hash(final):
                raise InputError("Final CMB likelihood differs from its complete Planck evaluation")
            batch[tag] = dict(spectra=spectra, nuisance=record["nuisance"])
            saved[tag] = record
    if archive and set(archive) != set(batch):
        raise InputError("Planck evaluations omit or add a registered spectrum/refinement")
    return batch, saved


def audit_p9(bundle, artifact_index, replay_config=None, workdir=None):
    root = bundle["root"]
    rows = _csv(root / "abundances.csv")
    keyed = {(r["engine"], int(r["level"]), r["corner"]): r for r in rows}
    expected = set(itertools.product(("linx", "primat"), range(3), CORNERS))
    if len(keyed) != len(rows) or set(keyed) != expected:
        raise InputError("Missing or duplicated native BBN run; expected 2 engines x 3 refinements x 5 histories")
    reconstructed = {}
    prepared_path = _lookup_input(bundle, "bbn_inputs", artifact_index)
    prepared = read_json(prepared_path)["histories"] if prepared_path is not None else None
    for key, summary in keyed.items():
        engine, level, corner = key
        directory = root / "bbn" / engine / str(level) / corner
        with np.load(directory / "trajectory.npz", allow_pickle=False) as archive:
            t, y = archive["time_s"], archive["Y"]
            species = archive["species"].tolist()
        if species != list(SPECIES) or y.shape != (len(t), 8) or np.any(np.diff(t) <= 0) or not np.isfinite(y).all():
            raise InputError("Malformed raw native BBN trajectory")
        last = y[-1]
        if last[1] <= 0:
            raise InputError("Invalid final proton abundance")
        obs = read_json(directory / "observables.json")
        DH, yp = float(last[2] / last[1]), float(4 * last[5])
        _close(DH, summary["D_H"], "D/H from raw final abundances")
        _close(yp, summary["Yp"], "helium from raw final abundances")
        _close(DH, obs["D_H"], "native D/H summary")
        _close(yp, obs["Yp"], "native helium summary")
        baryon = float(np.max(np.abs(y @ np.array([1, 1, 2, 3, 3, 4, 7, 7]) - 1)))
        _close(baryon, summary["max_baryon_error"], "raw baryon closure", atol=1e-14)
        masses = obs.get("atomic_mass_ratios", obs)
        if masses.get("He4Overma") is not None and masses.get("HOverma") is not None:
            he_mass = float(masses["He4Overma"]) * yp / 4
            cmb_he = he_mass / (he_mass + float(masses["HOverma"]) * (1 - yp))
            _close(cmb_he, summary["YHe_CMB"], "CMB helium mass convention")
        receipt = read_json(directory / "receipt.json")
        if receipt["engine"] != engine or receipt.get("history_reads", 0) <= 0:
            raise InputError("Native backend receipt does not establish actual history reads")
        if receipt.get("actual_kernel") != {"linx": "LINX.NuclearRates", "primat": "PRIMAT._K_LT"}[engine]:
            raise InputError("Unexpected native nuclear kernel")
        fingerprint = read_json(directory / "input.json")
        if canonical_hash(fingerprint) != receipt["input_cache_key"]:
            raise InputError("A cache entry was reused for a different complete input")
        native_input = fingerprint["input"]
        if prepared is not None and canonical_hash(native_input) != canonical_hash(prepared[corner]):
            raise InputError("Native solver did not read the P8 payload for this corner")
        history = native_input["canonical"]["history"]
        weak = native_input["weak_rates"]
        if _bridge_hash(history) != receipt["history_sha256"] or canonical_hash(weak) != receipt["weak_rates_sha256"]:
            raise InputError("Consumed history/weak-rate fingerprint mismatch")
        for sample in (receipt["first_rhs_input"], receipt["last_rhs_input"]):
            time = float(sample["time_s"])
            if not history["time_s"][0] <= time <= history["time_s"][-1]:
                raise InputError("Backend extrapolated beyond the source history")
            for name in ("T_gamma_MeV", "n_b_cm3"):
                actual = np.exp(np.interp(time, history["time_s"], np.log(history[name])))
                _close(actual, sample[name], "native read of " + name, rtol=1e-7)
            for name in ("lambda_n_to_p_s_inv", "lambda_p_to_n_s_inv"):
                actual = np.interp(time, weak["time_s"], weak[name])
                _close(actual, sample[name], "native read of " + name, rtol=1e-10)
        for filename, digest in receipt["files"].items():
            if sha256(_safe_member(directory, filename)) != digest:
                raise InputError("Native consumption receipt artifact hash mismatch")
        reconstructed[key] = dict(D_H=DH, Yp=yp)
    gates, table = read_json(root / "convergence.json"), _csv(root / "mixed_response.csv")
    gate_rows = {(r["engine"], r["observable"], int(r["level"])): r for r in table}
    if len(gate_rows) != len(table):
        raise InputError("Duplicate mixed-response record")
    reconstructed_gates = {}
    floor = float(bundle["request"]["config"].get("relative_floor", 1e-6))
    for engine in ("linx", "primat"):
        for observable in ("D_H", "Yp"):
            data = [[reconstructed[engine, level, corner][observable] for corner in CORNERS] for level in range(3)]
            result = mixed_gate(data, floor)
            name = f"{engine}/{observable}"
            if gates[name]["status"] != result["status"]:
                raise InputError("Mixed gate ignored an unstable abundance or residual")
            for level, residual in enumerate(result["mixed_residual"]):
                row = gate_rows.get((engine, observable, level))
                if row is None or row["status"] != result["status"]:
                    raise InputError("Missing or inconsistent mixed-response row")
                _close(residual, row["mixed_residual"], "five-corner mixed response", atol=2e-14)
            reconstructed_gates[name] = result
    likelihood_rows = _csv(root / "likelihood_grid.csv")
    reasons, likelihood_values = [], {}
    if prepared is None:
        reasons.append("P8_PARENT_NOT_AVAILABLE_TO_AUDITOR")
    data_file = bundle["files"].get("data_release_lock.json") or _lookup_input(bundle, "data_release_lock", artifact_index)
    if likelihood_rows and data_file is None:
        reasons.append("FROZEN_OBSERVATIONAL_RELEASE_NOT_AVAILABLE_TO_AUDITOR")
    data = read_json(data_file) if data_file is not None else {}
    releases = data.get("data_releases", data.get("releases", data.get("datasets", [])))
    likelihood_keys = [(r["engine"], r["corner"]) for r in likelihood_rows]
    if len(set(likelihood_keys)) != len(likelihood_keys):
        raise InputError("Duplicate likelihood point")
    if likelihood_keys and set(likelihood_keys) != set(itertools.product(("linx", "primat"), CORNERS)):
        raise InputError("Likelihood coverage must include both native engines and every history corner")
    cmb_precision = read_json(root / "cmb_convergence.json") if (root / "cmb_convergence.json").exists() else {}
    for summary in likelihood_rows:
        name = f"{summary['engine']}/{summary['corner']}"
        gate = cmb_precision.get(name, {"status": "NOT_VALIDATED"})
        if summary.get("cmb_precision_status") is not None and summary["cmb_precision_status"] != gate["status"]:
            raise InputError("CMB precision row contradicts its registered refinement artifact")
        if gate["status"] != "PASS":
            reasons.append(f"CMB_NUMERICAL_PRECISION_UNRESOLVED:{name}")
    replayed = {}
    if likelihood_rows:
        batch, saved_evaluations = _cmb_replay_plan(root, likelihood_rows, cmb_precision, bundle["request"]["config"])
        try:
            replayed = _replay_batch(batch, replay_config or {}, workdir)
            if set(replayed) != set(batch):
                raise InputError("Independent Planck replay omitted a spectrum/refinement")
            for tag, replay in replayed.items():
                saved = saved_evaluations[tag]
                _close(replay["logL"], saved["logL"], "full Planck raw likelihood including refinement", atol=1e-5)
                _close(replay["log_prior"], saved["log_prior"], "Planck nuisance prior including refinement", atol=1e-10)
                if set(replay["components"]) != set(saved["components"]):
                    raise InputError("Planck component coverage differs on replay")
                for component, value in replay["components"].items():
                    _close(value, saved["components"][component], "raw Planck " + component, atol=1e-5)
        except OpenInput as exc:
            reasons.append(str(exc))
    for summary in likelihood_rows:
        engine, corner = summary["engine"], summary["corner"]
        directory = root / "class" / engine / corner
        result = read_json(directory / "likelihood.json")
        observed = reconstructed[engine, 2, corner]
        if releases:
            bbn = _bbn_likelihood(observed["D_H"], observed["Yp"], releases,
                                  bundle["request"]["config"]["theory_covariance_logD_Yp"])
            _close(bbn, result["BBN"]["logL_BBN"], "independent BBN likelihood")
        else:
            bbn = result["BBN"]["logL_BBN"]
        cmb = result["CMB"]
        spectra = read_json(directory / "spectra.json")
        if canonical_hash(spectra) != cmb["spectra_sha256"]:
            raise InputError("Likelihood was evaluated on a different spectrum")
        if f"{engine}/{corner}" in replayed:
            replay = replayed[f"{engine}/{corner}"]
            _close(replay["logL"], cmb["logL"], "full Planck raw likelihood", atol=1e-5)
            _close(replay["log_prior"], cmb["log_prior"], "Planck nuisance prior", atol=1e-10)
        _close(sum(cmb["components"].values()), cmb["logL"], "component likelihood sum")
        _close(bbn + cmb["logL"], summary["logL"], "joint likelihood")
        _close(bbn + cmb["logL"] + cmb["log_prior"], summary["log_posterior"], "joint posterior")
        likelihood_values[f"{engine}/{corner}"] = float(summary["logL"])
    if not likelihood_rows:
        reasons.append("OBSERVATIONAL_LIKELIHOOD_NOT_EVALUATED")
    return dict(status="PARTIAL" if reasons else "RECONSTRUCTED", native_runs=len(rows),
                mixed_gates=reconstructed_gates, likelihood=likelihood_values,
                cmb_precision=cmb_precision, independently_replayed_spectra=len(replayed),
                reasons=sorted(set(reasons)))


def _proof(proof, bundle, checked, key):
    if proof.get("schema") != "R135-necessary-condition-proof-v1" or _key(proof.get("key")) != key:
        raise InputError("Proof is not bound to the exact registered claim/model/point/path")
    if proof.get("kind") != "graph_energy_balance_counterexample" or key[0] != "XA_carrier":
        raise InputError("No independent checker exists for this proof kind or scientific claim")
    if bundle["stage"] != "P2" or checked.get("balance_kind") != "isolated":
        raise InputError("Energy-conservation counterexample requires the declared isolated graph law")
    if proof.get("law_sha256") != checked["law_sha256"]:
        raise InputError("Proof concerns another Hamiltonian")
    if proof.get("necessary_condition") != "energy_conservation_for_declared_isolated_graph_law":
        raise InputError("An unregistered predicate cannot excuse downstream physics")
    witnesses = [r for r in checked["residuals"] if r["preparation_id"] == proof.get("preparation_id") and r["step"] == proof.get("step")]
    tolerance = float(bundle["request"]["config"].get("energy_atol_MeV", 1e-12))
    if len(witnesses) != 1 or abs(witnesses[0]["residual_MeV"]) <= tolerance:
        raise InputError("The proposed counterexample does not violate its necessary condition")
    law = read_json(bundle["root"] / "graph_law.json")
    predictions = read_json(bundle["root"] / "heldout_prediction.json")
    engine_path = Path(__file__).resolve().parents[5] / "analysis/ADD_NEIGHBOR_SYNTHESIS_20261117/verify.py"
    if not engine_path.is_file() or sha256(engine_path) != law["source_engine_sha256"]:
        raise InputError("Proof requires the exact registered R130 transition operator")
    spec = importlib.util.spec_from_file_location("_r135_independent_proof_engine", engine_path)
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)
    preparations = [p for p in bundle["request"]["config"].get("preparations", []) if p["id"] == proof["preparation_id"]]
    if len(preparations) != 1:
        raise InputError("Proof preparation was not declared in the executed request")
    state = engine.named(tuple(preparations[0]["word"]))
    saved = predictions["all_orbits"][proof["preparation_id"]]
    for step in range(proof["step"] + 1):
        if list(engine.word(state)) != saved[step]["word"]:
            raise InputError("Proposed witness is not an actual transition of the declared graph law")
        if step < proof["step"]:
            state = engine.forward(state, tuple(law["definition"].get("eps", [1])))
    exempt = proof.get("exempt_stages", [])
    allowed = {"P4", "P5", "P6", "P7", "P8", "P9"}
    if not isinstance(exempt, list) or len(set(exempt)) != len(exempt) or not set(exempt) <= allowed:
        raise InputError("Proof attempts to omit an unrelated stage")
    return dict(status="VERIFIED_NECESSARY_CONDITION_FAILURE", witness=witnesses[0],
                exempt_stages=exempt, domain="only this declared isolated graph law and saved preparation")


def _lineage_audit(bundle, bundles):
    """The point-specific history cannot silently migrate to another key."""
    required = {"P7": {"initial_history": "P1"},
                "P8": {"channel_history": "P7"},
                "P9": {"bbn_inputs": "P8", "class_inputs": "P8"}}.get(bundle["stage"], {})
    reasons = []
    for name, parent_stage in required.items():
        records = [r for r in bundle["request"].get("inputs", []) if r.get("name") == name]
        if len(records) != 1:
            reasons.append(f"UNBOUND_STAGE_INPUT:{name}:{parent_stage}")
            continue
        digest = records[0]["sha256"]
        candidates = [candidate for candidate in bundles if candidate["stage"] == parent_stage and
                      any(record["sha256"] == digest for record in candidate["manifest"]["files"])]
        if not candidates:
            reasons.append(f"PARENT_BUNDLE_NOT_SUPPLIED:{name}:{parent_stage}")
        elif not any(candidate["key"] == bundle["key"] for candidate in candidates):
            raise InputError(f"Point-specific {name} was taken from another claim/model/point/path")
    return reasons


def run(config, inputs, out):
    expected = config.get("expected_keys")
    if not isinstance(expected, list) or not expected:
        raise InputError("P10 requires the exact preregistered expected matrix keys")
    expected_keys = [_key(item) for item in expected]
    if len(set(expected_keys)) != len(expected_keys):
        raise InputError("Duplicate expected matrix key")
    coverage = _coverage_policy(config, inputs, expected_keys)
    results = config.get("results")
    if not isinstance(results, list):
        raise InputError("P10 results must be an explicit list of stage manifest inputs")
    bundles, indexed, artifacts = [], {}, {}
    for item in results:
        key = _key(item["key"])
        if key not in expected_keys:
            raise InputError("An unregistered point was substituted into the final matrix")
        stage = item["stage"]
        if stage not in {f"P{i}" for i in range(10)}:
            raise InputError("Invalid audited stage")
        unit = item.get("unit_id", "")
        if unit and stage != "P3":
            raise InputError("Only independent P3 grid units may share a point/stage key")
        identity = (key, stage, unit)
        if identity in indexed:
            raise InputError("Duplicate result key/stage/unit")
        name = item["manifest_input"]
        if name not in inputs:
            raise OpenInput(f"Stage manifest input missing: {name}")
        bundle = verify_bundle(inputs[name], item["key"], stage)
        if Path(out).resolve().is_relative_to(bundle["root"]):
            raise InputError("Audit outputs must be outside all read-only source bundles")
        bundle["unit_id"], bundle["input_name"] = unit, name
        indexed[identity] = bundle
        bundles.append(bundle)
        for record in bundle["manifest"]["files"]:
            artifacts[record["sha256"]] = bundle["files"][record["path"]]
    observed_keys = {bundle["key"] for bundle in bundles}
    missing = set(expected_keys) - observed_keys
    if missing:
        raise InputError("Missing point/claim/path from final matrix: " + repr(sorted(missing)))
    audits = {}
    for bundle in bundles:
        stage = bundle["stage"]
        state = bundle["receipt"]["result"]
        if state.get("software_status") not in ("PASS", "FAIL_CONVERGENCE"):
            result = dict(status="PARTIAL", reason="PARENT_STAGE_NOT_SUCCESSFUL", parent_result=state)
        elif stage == "P2":
            result = audit_p2(bundle)
        elif stage == "P3":
            result = audit_p3(bundle, artifacts)
        elif stage == "P4":
            result = audit_p4(bundle)
        elif stage == "P7":
            result = audit_p7(bundle, float(config.get("quadrature_rtol", 1e-3)))
        elif stage == "P8":
            result = audit_p8(bundle, artifacts)
        elif stage == "P9":
            workdir = Path(out) / "planck_audit" / bundle["manifest_sha256"][:16]
            result = audit_p9(bundle, artifacts, config, workdir)
        else:
            result = dict(status="HASH_AND_PROVENANCE_VERIFIED", scientific_quantities="checked_at_consumer_where_present")
        lineage_reasons = _lineage_audit(bundle, bundles)
        if lineage_reasons:
            result["status"] = "PARTIAL"
            result["lineage_reasons"] = lineage_reasons
        audits[bundle["input_name"]] = result
    proof_results = {}
    for record in config.get("proofs", []):
        name = record["proof_input"]
        if name not in inputs:
            raise InputError("Claimed proof artifact is missing")
        proof = read_json(inputs[name])
        key = _key(proof.get("key"))
        if key not in expected_keys or key in proof_results:
            raise InputError("Unregistered or duplicate proof key")
        candidates = [b for b in bundles if b["key"] == key and b["stage"] == "P2"]
        if len(candidates) != 1:
            raise InputError("Proof has no unique raw P2 witness bundle")
        parent = candidates[0]
        proof_results[key] = _proof(proof, parent, audits[parent["input_name"]], key)
    requirements = config.get("required_stages", DEFAULT_REQUIREMENTS)
    if set(requirements) - set(DEFAULT_REQUIREMENTS):
        raise InputError("Required-stage map contains an unknown scientific claim")
    matrix = []
    for key in expected_keys:
        present = [b for b in bundles if b["key"] == key]
        required = requirements.get(key[0], DEFAULT_REQUIREMENTS[key[0]])
        if not isinstance(required, (list, tuple)) or not required or len(set(required)) != len(required):
            raise InputError("Each claim needs a nonempty, unique explicit required-stage set")
        if set(required) - {f"P{i}" for i in range(10)}:
            raise InputError("Required stage is unknown")
        if config.get("_mode") != "validation" and not set(DEFAULT_REQUIREMENTS[key[0]]) <= set(required):
            raise InputError("Physical audit cannot silently remove a required scientific stage")
        exempt = set(proof_results.get(key, {}).get("exempt_stages", []))
        stages = {b["stage"] for b in present}
        missing_stages = sorted(set(required) - stages - exempt, key=lambda x: int(x[1:]))
        partial = [b["input_name"] for b in present if audits[b["input_name"]]["status"] == "PARTIAL"]
        unresolved = [b["input_name"] for b in present if b["receipt"]["result"].get("evidence_status") in
                      ("OPEN_INPUT", "INCONCLUSIVE", "TECHNICAL_FAILURE")
                      and not (key in proof_results and b["stage"] == "P2")]
        diagnostic = any(b["receipt"]["mode"] == "validation" for b in present)
        physical = all(b["receipt"]["mode"] == "physical" for b in present)
        if missing_stages or partial or unresolved:
            status = "PARTIAL"
        elif key in proof_results:
            status = "NECESSARY_CONDITION_FAILED"
        elif diagnostic:
            status = "DIAGNOSTIC_PIPELINE"
        else:
            status = "CONDITIONAL_PIPELINE"
        matrix.append({**dict(zip(KEY_FIELDS, key)), "status": status,
                       "coverage_scope": coverage["scope"],
                       "point_origin": coverage.get("point_origins", {}).get(key[2], "validation_fixture"),
                       "required_stages": ";".join(required), "present_stages": ";".join(sorted(stages, key=lambda s: int(s[1:]))),
                       "missing_stages": ";".join(missing_stages), "partial_audits": ";".join(partial),
                       "open_parent_evidence": ";".join(unresolved), "proof_checked": key in proof_results,
                       "independently_calibrated_mode": physical, "scientific_acceptance": "owner_review"})
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "claim_matrix.csv", matrix)
    write_json(out / "audit_details.json", {"schema": "R135-independent-audit-v1", "stages": audits,
               "coverage": coverage,
               "proofs": [{"key": dict(zip(KEY_FIELDS, key)), **value} for key, value in proof_results.items()],
               "source_manifests": [{"input_name": b["input_name"], "sha256": b["manifest_sha256"],
                                     "execution_sha": b["receipt"]["execution_sha"]} for b in bundles]})
    partial_count = sum(row["status"] == "PARTIAL" for row in matrix)
    report = ["# R135: independent numerical audit", "",
              f"Matrix keys checked: {len(matrix)}. Partial rows: {partial_count}.", "",
              f"Coverage scope: {coverage['scope']}. Independently calibrated P0 points: {coverage['independently_calibrated_points']}.", "",
              "The audit read archived inputs and reconstructed numerical quantities. Scientific acceptance remains with the owner.", "",
              "| Claim | Model | Point | Thermal path | Result | Missing stages |", "|---|---|---|---|---|---|"]
    for row in matrix:
        report.append("| " + " | ".join(str(row[field]).replace("|", "\\|") for field in
                                         (*KEY_FIELDS, "status", "missing_stages")) + " |")
    report += ["", "Raw checks and exact manifest bindings are in audit_details.json.",
               "An external benchmark or validation fixture does not establish an independently calibrated cosmological X.",
               "Missing raw likelihood replay, an unresolved output quadrature, or an absent dependent stage leaves the corresponding row partial.", ""]
    (out / "FINAL_REPORT.md").write_text("\n".join(report), encoding="utf-8")
    return dict(software_status="PASS", evidence_status="INCONCLUSIVE" if partial_count else "CONDITIONAL",
                metrics=dict(matrix_rows=len(matrix), audited_bundles=len(bundles), partial_rows=partial_count,
                             necessary_conditions_failed=len(proof_results), coverage_scope=coverage["scope"],
                             physical_completeness=False,
                             independently_calibrated_points=coverage["independently_calibrated_points"]),
                limitations=["The audit reconstructs archived numerical results and does not confer scientific acceptance."])


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] != "planck-replay":
        raise SystemExit("usage: python -m r135.audit planck-replay request.json result.json")
    request = read_json(Path(sys.argv[2]))
    if request["audit_source_sha256"] != sha256(Path(__file__)):
        raise SystemExit("independent audit source hash mismatch")
    answers = {name: _planck_replay(item["spectra"], item["nuisance"], request["data_root"])
               for name, item in request["batch"].items()}
    write_json(Path(sys.argv[3]), {"schema": "R135-independent-Planck-replay-v1",
               "request_sha256": canonical_hash(request),
               "audit_source_sha256": sha256(Path(__file__)), "results": answers})
