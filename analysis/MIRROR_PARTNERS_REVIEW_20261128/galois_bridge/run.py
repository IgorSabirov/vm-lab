#!/usr/bin/env python3
"""Run only the newly reviewed arithmetic checks; reuse the archived R140 run."""
from __future__ import annotations
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent

def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")

def main():
    run = os.environ.get("GITHUB_RUN_ID", "local-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    out = HERE / "runs" / run
    out.mkdir(parents=True, exist_ok=False)
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    receipt = {"schema": "galois-h6-finite-v1", "run_id": run,
               "source_commit": source, "baseline_commit": "7aae9af516972c6e7975095baaaf56e4f70af8c5",
               "started_at_utc": datetime.now(timezone.utc).isoformat(), "status": "STARTED",
               "main_executions": 0, "old_R140_histories_reexecuted": False,
               "new_physical_model_selected": False}
    dump(out / "run_receipt.json", receipt)
    try:
        manifest = json.loads((HERE / "SOURCE_MANIFEST.json").read_text())
        for item in manifest["inputs"]:
            raw = (ROOT / item["path"]).read_bytes()
            blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
            assert blob == item["git_blob_sha"], item["path"]
            assert hashlib.sha256(raw).hexdigest() == item["sha256"], item["path"]
        assert hashlib.sha256((ROOT / manifest["attachment"]["path"]).read_bytes()).hexdigest() == manifest["attachment"]["sha256"]
        review = json.loads((HERE / "REVIEW.json").read_text())
        assert review["status"] == "REVIEWED_BEFORE_EXECUTION"
        check_hash = hashlib.sha256((HERE / "check.py").read_bytes()).hexdigest()
        assert check_hash == review["check_sha256"]
        dump(out / "environment.json", {"python": sys.version, "platform": platform.platform(),
             "arithmetic": "stdlib exact integer and rational arithmetic", "dependencies": [],
             "source_commit": source})
        dump(out / "source_hashes.json", {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(HERE.glob("*.py"))})
        spec = importlib.util.spec_from_file_location("galois_checks", HERE / "check.py")
        module = importlib.util.module_from_spec(spec)
        with (out / "stdout.txt").open("w") as stdout, (out / "stderr.txt").open("w") as stderr:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                spec.loader.exec_module(module)
                start = time.perf_counter()
                calibration = module.calibrate(ROOT)
                cal_s = time.perf_counter() - start
                dump(out / "calibration.json", {"seconds": cal_s, "data": calibration})
                forecast = {"created_before_main": True, "expected_seconds": max(1.0, 20 * cal_s),
                            "range_seconds": [0.001, max(30.0, 200 * cal_s)],
                            "purpose": "calibration and plan/actual; not a runtime cap",
                            "basis": "bounded matrices at most 24, rings modulo 2 and 4, n=1..12"}
                dump(out / "forecast.json", forecast)
                start = time.perf_counter()
                receipt["main_executions"] = 1
                result = module.run(ROOT)
                elapsed = time.perf_counter() - start
                assert result["status"] == "PASS"
                dump(out / "checks.json", result)
        receipt.update(status="PASS", exit_code=0, calibration_seconds=cal_s, main_seconds=elapsed,
                       forecast_ratio=elapsed / forecast["expected_seconds"],
                       forecast_assessment=("below" if elapsed < forecast["range_seconds"][0]
                                            else "above" if elapsed > forecast["range_seconds"][1] else "within"))
        dump(out / "RESULTS.json", {"status": "PASS", "source_commit": source,
             "checks": "checks.json", "main_seconds": elapsed, "calibration_seconds": cal_s,
             "proofs": ["ALGEBRA_PROOF.md", "SHEETS_PROOF.md", "TOPOLOGY_PROOF.md"],
             "scientific_scope": "finite operator equivalence plus separately stated analytic proofs"})
    except Exception as exc:
        receipt.update(status="FAIL", exit_code=1, error=repr(exc), traceback=traceback.format_exc())
        dump(out / "RESULTS.json", {"status": "FAIL", "source_commit": source, "error": repr(exc)})
        raise
    finally:
        receipt["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        dump(out / "run_receipt.json", receipt)
        print(json.dumps({k: receipt.get(k) for k in ("status", "source_commit", "main_seconds", "calibration_seconds")}))

if __name__ == "__main__":
    main()
