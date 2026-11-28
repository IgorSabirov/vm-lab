#!/usr/bin/env python3
"""One reviewed finite bridge replay; calibration and publication are separate."""
from __future__ import annotations
import contextlib
import datetime as dt
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RUN_ID = os.environ.get("GITHUB_RUN_ID") or ("local-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
OUT = HERE / "runs" / RUN_ID
MODULES = ("register_bridge", "history_bridge")

def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def write(name, obj):
    path = OUT / name
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")
    return path

def git_blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    plan = json.loads((HERE / "RUN_PLAN.json").read_text())
    source_manifest = json.loads((HERE / "SOURCE_MANIFEST.json").read_text())
    for row in source_manifest["inputs"]:
        p = ROOT / row["path"]
        actual = git_blob(p.read_bytes())
        if actual != row["git_blob_sha"]:
            raise AssertionError("Pinned source mismatch: " + row["path"])
    review = (HERE / "REVIEW.md").read_text()
    if "REVIEWED_BEFORE_EXECUTION" not in review:
        raise AssertionError("Pre-execution review is incomplete")
    for path, digest in source_manifest["reviewed_implementation"].items():
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != digest or digest not in review:
            raise AssertionError("Reviewed implementation hash mismatch: " + path)
    code_paths = sorted(HERE.glob("*.py"))
    code_hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in code_paths}
    for row in source_manifest["inputs"]:
        code_hashes[row["path"]] = hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest()
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    environment = {
        "python": sys.version, "platform": platform.platform(),
        "packages": {n: importlib.metadata.version(n) for n in ("numpy", "scipy", "sympy")},
        "executor": "GitHub Actions" if os.environ.get("GITHUB_ACTIONS") == "true" else "explicit local invocation",
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "source_commit": sha,
        "thread_environment": {k: os.environ.get(k) for k in
                               ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")},
    }
    write("environment.json", environment)
    write("source_hashes.json", code_hashes)
    receipt = {
        "schema": "mirror-r140-execution-v1", "source_commit": sha,
        "source_baseline": source_manifest["source_commit"],
        "run_id": os.environ.get("GITHUB_RUN_ID"), "started_at_utc": stamp(),
        "command": "python " + str(Path(__file__).relative_to(ROOT)),
        "plan": "RUN_PLAN.json", "status": "STARTED", "main_executions": 0,
        "new_physical_model_selected": False,
    }
    write("run_receipt.json", receipt)
    with (OUT / "stdout.txt").open("w") as stdout, (OUT / "stderr.txt").open("w") as stderr:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                modules = {name: importlib.import_module(name) for name in MODULES}
                calibration = {}
                for name, mod in modules.items():
                    start = time.perf_counter()
                    sample = mod.calibrate(ROOT)
                    calibration[name] = {"seconds": time.perf_counter() - start, "sample": sample}
                write("calibration.json", calibration)
                cal_seconds = sum(x["seconds"] for x in calibration.values())
                expected = max(5.0, 20.0 * cal_seconds)
                forecast = {
                    "written_before_main": True, "created_at_utc": stamp(),
                    "calibration_seconds": cal_seconds,
                    "expected_main_seconds": expected,
                    "range_seconds": [max(0.2, expected / 10.0), max(120.0, expected * 10.0)],
                    "model": "Conservative finite exact-matrix/8-step estimate; scale 20 times representative calibration, floor 5 s; range is a forecast, never a termination rule.",
                    "scope": plan["contracts"],
                    "preparation_and_publication_excluded": True,
                    "hard_runtime_limit": None,
                }
                write("forecast.json", forecast)
                start = time.perf_counter()
                outputs = {}
                timings = {}
                receipt["main_executions"] = 1
                for name, mod in modules.items():
                    one = time.perf_counter()
                    outputs[name] = mod.run(ROOT)
                    timings[name] = time.perf_counter() - one
                    write(name + ".json", outputs[name])
                    print(name + ": completed")
                    stdout.flush()
                elapsed = time.perf_counter() - start
                write("RESULTS.json", {
                    "status": "PASS", "source_commit": sha,
                    "register_results": "register_bridge.json",
                    "history_results": "history_bridge.json",
                    "module_seconds": timings, "main_seconds": elapsed,
                    "scientific_acceptance": "owner decision, not inferred from completion",
                })
                receipt.update(status="PASS", exit_code=0, finished_at_utc=stamp(),
                               calibration_seconds=cal_seconds, main_seconds=elapsed,
                               module_seconds=timings,
                               forecast_ratio=elapsed / expected,
                               forecast_assessment="below" if elapsed < forecast["range_seconds"][0] else
                               "above" if elapsed > forecast["range_seconds"][1] else "within")
                print("Bridge replay PASS")
            except BaseException as exc:
                traceback.print_exc()
                receipt.update(status="FAILED", exit_code=1, finished_at_utc=stamp(),
                               error_type=type(exc).__name__, error=str(exc))
                write("run_receipt.json", receipt)
                raise
    write("run_receipt.json", receipt)
    print(json.dumps({k: receipt[k] for k in ("status", "source_commit", "main_seconds", "calibration_seconds")}))
if __name__ == "__main__":
    main()
