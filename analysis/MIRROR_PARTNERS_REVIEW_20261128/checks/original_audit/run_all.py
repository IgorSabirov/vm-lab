#!/usr/bin/env python3
"""Reproduce the attachment and run the corrected bounded checks locally."""
from pathlib import Path
import json
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
LOGS = ROOT / "logs"
SCRIPTS = (
    "replay_original_cells.py",
    "dynamics/check.py",
    "charges/reproduce.py",
    "graphs/verify_graphs.py",
)

def main():
    LOGS.mkdir(exist_ok=True)
    receipts = []
    for script in SCRIPTS:
        tick = time.perf_counter()
        completed = subprocess.run(
            [sys.executable, str(ROOT / script)],
            cwd=ROOT, text=True, capture_output=True,
        )
        log_name = script.replace("/", "_").removesuffix(".py")
        (LOGS / (log_name + ".stdout.txt")).write_text(completed.stdout, encoding="utf-8")
        (LOGS / (log_name + ".stderr.txt")).write_text(completed.stderr, encoding="utf-8")
        row = dict(script=script, exit_code=completed.returncode,
                   elapsed_seconds=time.perf_counter()-tick)
        receipts.append(row)
        print(f"{script}: exit={completed.returncode}", flush=True)
    (ROOT / "run_receipt.json").write_text(
        json.dumps(receipts, indent=2) + "\n", encoding="utf-8")
    if any(row["exit_code"] != 0 for row in receipts):
        return 1
    original = json.loads((ROOT / "original_cells_replay.json").read_text())
    print("Original captured exceptions:",
          [(r["cell"], r.get("exception_type")) for r in original["cells"]
           if r["status"] == "error"])
    print("Expected failed original cells: 2, 3, 12. See JSON for the scientific results.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
