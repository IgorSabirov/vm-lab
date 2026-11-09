"""Input provenance and blocking preflight for the conditional R040 package."""
from __future__ import annotations
import hashlib
import json
import math
import re
from pathlib import Path

REQUIRED = ["E_V", "E_1", "E_2", "t_1", "t_2", "gamma_d", "kappa", "g", "bath_onsite"]
ALLOWED_SOURCE = {"ADD_DERIVED", "MODEL_ASSUMPTION", "EXTERNAL_CALIBRATION", "NOT_AVAILABLE"}


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def preflight(manifest: dict) -> dict:
    blockers = []
    model = manifest.get("model", {})
    provenance = manifest.get("provenance", {})
    for name in REQUIRED:
        value = model.get(name)
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            blockers.append({"id": f"MODEL_{name.upper()}_MISSING", "field": f"model.{name}",
                             "reason": "finite numerical input required"})
            continue
        record = provenance.get(name, {})
        source = record.get("source")
        if source not in ALLOWED_SOURCE:
            blockers.append({"id": f"PROVENANCE_{name.upper()}_INVALID", "field": f"provenance.{name}.source",
                             "reason": "explicit source class required"})
        elif source == "NOT_AVAILABLE":
            blockers.append({"id": f"PROVENANCE_{name.upper()}_NOT_AVAILABLE", "field": f"provenance.{name}",
                             "reason": "input is explicitly unavailable"})
        elif source in {"ADD_DERIVED", "EXTERNAL_CALIBRATION"}:
            if not record.get("evidence_ref"):
                blockers.append({"id": f"PROVENANCE_{name.upper()}_EVIDENCE_MISSING", "field": f"provenance.{name}.evidence_ref",
                                 "reason": "source claim requires a resolvable evidence reference"})
            evidence_sha = record.get("evidence_sha256")
            if not isinstance(evidence_sha, str) or re.fullmatch(r"[0-9a-fA-F]{64}", evidence_sha) is None:
                blockers.append({"id": f"PROVENANCE_{name.upper()}_EVIDENCE_DIGEST_MISSING", "field": f"provenance.{name}.evidence_sha256",
                                 "reason": "ADD-derived/external-calibration claims require a frozen evidence SHA-256; digest proves identity, not claim truth"})
        elif source == "MODEL_ASSUMPTION" and not record.get("assumption"):
            blockers.append({"id": f"PROVENANCE_{name.upper()}_ASSUMPTION_MISSING", "field": f"provenance.{name}.assumption",
                             "reason": "model assumption must be stated, not merely tagged"})
    for name, predicate, reason in [
        ("kappa", lambda x: x > 0.0, "kappa must be positive"),
        ("g", lambda x: x > 0.0, "bath contact g must be positive"),
        ("t_2", lambda x: abs(x) > 1e-14, "t_2 must be nonzero for the inherited dark-state parameterization"),
        ("gamma_d", lambda x: abs(x) > 1e-14, "gamma_d must be nonzero for the inherited dark-state parameterization"),
    ]:
        value = model.get(name)
        if isinstance(value,(int,float)) and math.isfinite(float(value)) and not predicate(float(value)):
            blockers.append({"id":f"MODEL_{name.upper()}_OUT_OF_DOMAIN","field":f"model.{name}","reason":reason})
    if manifest.get("model_class") != "CONDITIONAL_R040_TRIMER_WITH_1D_TIGHT_BINDING_BATH":
        blockers.append({"id":"MODEL_CLASS_UNDECLARED","field":"model_class",
                         "reason":"this executor accepts only the stated conditional R040 + 1D bath class"})
    if manifest.get("model_assumptions_accepted") is not True:
        blockers.append({"id":"MODEL_ASSUMPTIONS_NOT_ACCEPTED","field":"model_assumptions_accepted",
                         "reason":"do not run a conditional main calculation before explicit model acceptance"})
    freeze_sha=manifest.get("freeze_record_sha256")
    if (manifest.get("freeze_state") != "FROZEN" or not manifest.get("freeze_record_ref")
            or not isinstance(freeze_sha,str) or re.fullmatch(r"[0-9a-fA-F]{64}",freeze_sha) is None):
        blockers.append({"id":"MANIFEST_NOT_FROZEN","field":"freeze_state",
                         "reason":"freeze record reference and SHA-256 must be committed before main submit"})
    if manifest.get("energy_unit") in (None, ""):
        blockers.append({"id":"ENERGY_UNIT_MISSING","field":"energy_unit","reason":"energy unit must be declared"})
    if manifest.get("time_unit") in (None, ""):
        blockers.append({"id":"TIME_UNIT_MISSING","field":"time_unit","reason":"time unit must be declared"})
    scan = manifest.get("continuum_scan", {})
    sizes = scan.get("ring_sizes")
    if not isinstance(sizes, list) or len(sizes) < 3 or any(type(n) is not int or n < 3 for n in sizes):
        blockers.append({"id":"CONTINUUM_SIZES_INVALID","field":"continuum_scan.ring_sizes",
                         "reason":"at least three integer ring sizes >=3 must be frozen"})
    elif sizes != sorted(set(sizes)):
        blockers.append({"id":"CONTINUUM_SIZES_NOT_STRICTLY_INCREASING","field":"continuum_scan.ring_sizes",
                         "reason":"ring sizes must be unique and strictly increasing"})
    zpoints = scan.get("resolvent_test_points")
    if not isinstance(zpoints, list) or len(zpoints) < 2 or any(
        not isinstance(z, list) or len(z) != 2 or not all(isinstance(x,(int,float)) and math.isfinite(float(x)) for x in z) or z[1] <= 0
        for z in zpoints
    ):
        blockers.append({"id":"RESOLVENT_TEST_POINTS_INVALID","field":"continuum_scan.resolvent_test_points",
                         "reason":"at least two finite complex test points with Im(z)>0 are required"})
    numerics = manifest.get("numerics", {})
    for key in ("determinant_relative_tolerance", "resolvent_relative_tolerance",
                "pole_residual_tolerance", "spectral_measure_quad_epsabs",
                "spectral_measure_quad_epsrel", "off_axis_green_abs_tolerance"):
        value = numerics.get(key)
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)) or float(value) <= 0:
            blockers.append({"id": f"NUMERICS_{key.upper()}_INVALID", "field": f"numerics.{key}",
                             "reason": "a finite positive frozen tolerance is required"})
    fp = numerics.get("feshbach_test_points")
    if not isinstance(fp, list) or len(fp) < 2 or any(
        not isinstance(z, list) or len(z) != 2 or not all(isinstance(x,(int,float)) and math.isfinite(float(x)) for x in z) or z[1] <= 0
        for z in fp
    ):
        blockers.append({"id":"FESHBACH_TEST_POINTS_INVALID","field":"numerics.feshbach_test_points",
                         "reason":"at least two finite upper-half-plane complex points are required"})
    pole_seeds = manifest.get("pole_search", {}).get("seeds")
    if not isinstance(pole_seeds, list) or len(pole_seeds) < 1 or any(
        not isinstance(z, list) or len(z) != 2 or not all(isinstance(x,(int,float)) and math.isfinite(float(x)) for x in z) or z[1] >= 0
        for z in pole_seeds
    ):
        blockers.append({"id":"SECOND_SHEET_SEEDS_INVALID","field":"pole_search.seeds",
                         "reason":"at least one finite lower-half-plane seed must be frozen"})
    runtime = manifest.get("runtime_gate", {})
    required_runtime = ("calibration_ref", "calibration_sha256", "forecast_ref", "forecast_sha256",
                        "environment_fingerprint", "forecast_seconds", "lower_seconds",
                        "upper_seconds", "hard_wall_seconds", "memory_limit_mib", "disk_limit_mib")
    missing_runtime = [k for k in required_runtime if runtime.get(k) is None]
    for key in ("calibration_sha256", "forecast_sha256", "environment_fingerprint"):
        value=runtime.get(key)
        if not isinstance(value,str) or re.fullmatch(r"[0-9a-fA-F]{64}",value) is None:
            missing_runtime.append(key+"(sha256)")
    runtime_numeric = ("forecast_seconds", "lower_seconds", "upper_seconds", "hard_wall_seconds",
                       "memory_limit_mib", "disk_limit_mib")
    bad_runtime_numeric = [k for k in runtime_numeric if not isinstance(runtime.get(k),(int,float))
                           or not math.isfinite(float(runtime.get(k))) or float(runtime.get(k)) <= 0]
    if not bad_runtime_numeric:
        forecast = float(runtime["forecast_seconds"])
        lower = float(runtime["lower_seconds"])
        upper = float(runtime["upper_seconds"])
        hard_wall = float(runtime["hard_wall_seconds"])
        if not (lower <= forecast <= upper <= hard_wall):
            blockers.append({"id":"VM_RUNTIME_INTERVAL_INCONSISTENT","field":"runtime_gate",
                             "reason":"require lower_seconds <= forecast_seconds <= upper_seconds <= hard_wall_seconds"})
    if runtime.get("status") != "CALIBRATED" or missing_runtime or bad_runtime_numeric:
        blockers.append({"id":"VM_RUNTIME_NOT_CALIBRATED","field":"runtime_gate",
                         "reason":"target-VM calibration and forecast are required; missing=" + ",".join(missing_runtime)
                                   + "; invalid=" + ",".join(bad_runtime_numeric)})
    loading = manifest.get("loading", {})
    static_control = loading.get("static_no_load_control", {})
    if static_control.get("enabled") is not True:
        blockers.append({"id":"STATIC_NO_LOAD_CONTROL_DISABLED","field":"loading.static_no_load_control.enabled",
                         "reason":"the R041 constant-H orthogonal-input negative control must be included"})
    else:
        n_sites = static_control.get("bath_ring_sites")
        times = static_control.get("times")
        if type(n_sites) is not int or n_sites < 3:
            blockers.append({"id":"STATIC_NO_LOAD_RING_INVALID","field":"loading.static_no_load_control.bath_ring_sites",
                             "reason":"finite closed-ring control requires an integer N>=3"})
        if not isinstance(times, list) or len(times) < 2 or any(
            not isinstance(t,(int,float)) or not math.isfinite(float(t)) for t in times
        ) or any(float(b) <= float(a) for a,b in zip(times,times[1:])):
            blockers.append({"id":"STATIC_NO_LOAD_TIMES_INVALID","field":"loading.static_no_load_control.times",
                             "reason":"at least two finite strictly increasing time points are required"})
    if loading.get("enabled") is True:
        blockers.append({"id":"LOADING_REQUIRES_SEPARATE_EXECUTOR","field":"loading.enabled",
                         "reason":"this package main runner is spectral-only; loading.py is an API requiring a separately frozen protocol and resource model"})
    return {
        "status": "READY_FOR_VM_MAIN" if not blockers else "BLOCKED_MISSING_OR_UNACCEPTED_INPUTS",
        "blockers": blockers,
        "blocker_count": len(blockers),
        "scientific_status": "CONDITIONAL_MODEL_ONLY; NOT_ADD_DERIVED",
        "submit_allowed": not blockers,
    }


def canonical_digest(manifest_path: str | Path, code_root: str | Path) -> dict:
    manifest_path = Path(manifest_path)
    files = sorted(p for p in Path(code_root).rglob("*") if p.is_file()
                   and "__pycache__" not in p.parts
                   and ".pyc" not in p.suffix
                   and "output" not in p.parts)
    h = hashlib.sha256()
    entries = []
    for path in files:
        digest = sha256_file(path)
        rel = path.relative_to(code_root).as_posix()
        entries.append({"path": rel, "sha256": digest})
        h.update(rel.encode("utf-8")); h.update(b"\0"); h.update(digest.encode("ascii")); h.update(b"\n")
    return {"manifest_sha256": sha256_file(manifest_path), "code_tree_sha256": h.hexdigest(),
            "files": entries}
