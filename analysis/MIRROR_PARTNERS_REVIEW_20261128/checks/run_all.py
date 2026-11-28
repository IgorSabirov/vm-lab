#!/usr/bin/env python3
"""Run the preserved audit and two followups in a fresh output copy.

The packaged historical results, logs and receipts are never overwritten.
This runner was prepared during packaging; packaging did not execute it.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parent
JOBS = (
    "original_audit/run_all.py",
    "followup/algebra/check.py",
    "followup/graphs/verify.py",
)
GENERATED = (
    "original_audit/run_receipt.json",
    "original_audit/original_cells_replay.json",
    "original_audit/original_cells_replay.txt",
    "original_audit/dynamics/results.json",
    "original_audit/charges/results.json",
    "original_audit/graphs/results.json",
    "followup/algebra/results.json",
    "followup/graphs/results.json",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path,
        help="New output directory; default: a unique directory under checks/runs/",
    )
    args = parser.parse_args()
    if args.output is not None:
        output = args.output.expanduser().resolve()
        for name in ("original_audit", "followup"):
            if output.is_relative_to(ROOT / name):
                parser.error("The output directory must be outside the preserved input trees.")
        output.mkdir(parents=True, exist_ok=False)
    else:
        runs = ROOT / "runs"
        runs.mkdir(exist_ok=True)
        prefix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-")
        output = Path(tempfile.mkdtemp(prefix=prefix, dir=runs))

    for name in ("original_audit", "followup"):
        shutil.copytree(
            ROOT / name, output / name,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    # Only disposable copies are cleaned, so failed jobs cannot expose old
    # result files as if they were freshly produced.
    for relative in GENERATED:
        (output / relative).unlink(missing_ok=True)
    shutil.rmtree(output / "original_audit/logs", ignore_errors=True)
    logs = output / "logs"
    logs.mkdir()
    receipt = {
        "kind": "new_reproduction_run",
        "started_at_utc": utc_now(),
        "python": sys.version,
        "historical_results_preserved": True,
        "jobs": [],
    }
    print(f"New run output: {output}", flush=True)
    for relative in JOBS:
        script = output / relative
        started = utc_now()
        tick = time.perf_counter()
        process = subprocess.run(
            [sys.executable, str(script)], cwd=script.parent,
            text=True, encoding="utf-8", errors="replace", capture_output=True,
        )
        stem = relative.replace("/", "_").removesuffix(".py")
        stdout = f"logs/{stem}.stdout.txt"
        stderr = f"logs/{stem}.stderr.txt"
        (output / stdout).write_text(process.stdout, encoding="utf-8")
        (output / stderr).write_text(process.stderr, encoding="utf-8")
        receipt["jobs"].append({
            "script": relative, "started_at_utc": started,
            "finished_at_utc": utc_now(), "exit_code": process.returncode,
            "elapsed_seconds": time.perf_counter() - tick,
            "stdout": stdout, "stderr": stderr,
        })
        (output / "RUN_RECEIPT.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"{relative}: exit={process.returncode}", flush=True)
    receipt["finished_at_utc"] = utc_now()
    receipt["exit_code"] = int(any(job["exit_code"] for job in receipt["jobs"]))
    receipt["generated_paths_present"] = [
        relative for relative in GENERATED if (output / relative).is_file()
    ]
    (output / "RUN_RECEIPT.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return receipt["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
