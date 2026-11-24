#!/usr/bin/env python3
"""Record numerical development tests without launching physical R135."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time

from r135.common import canonical_hash, file_record, sha256, write_json
from r135.contracts import HERE, REPO, _commit, source_inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit("Use a new validation output directory; previous evidence is preserved")
    out.mkdir(parents=True, exist_ok=True)
    relative = HERE.relative_to(REPO).as_posix()
    tests = [("core", ["-m", "unittest", "discover", "-s", relative+"/tests", "-v"]),
             ("p0", ["-m", "unittest", "discover", "-s", relative, "-p", "test_p0_register.py", "-v"])]
    source = source_inventory()
    write_json(out / "SOURCE.json", source)
    result = {"schema": "R135-software-validation-v1", "scope": "DEVELOPMENT_TESTS",
        "physical_R135_run": False, "execution_sha": _commit(), "source_sha256": source["sha256"],
        "environment": {"python": platform.python_version(),
            **{name: importlib.metadata.version(name) for name in ("numpy", "scipy")}},
        "scientific_acceptance": "owner_review", "commands": []}
    env = {**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}
    start = time.monotonic()
    for label, command in tests:
        t = time.monotonic()
        completed = subprocess.run([sys.executable, *command], cwd=REPO, env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        (out / f"{label}.log").write_text(completed.stdout)
        count = re.search(r"Ran (\d+) tests? in", completed.stdout)
        skipped = re.search(r"skipped=(\d+)", completed.stdout)
        record = {"label": label, "command": ["python", *command], "exit_code": completed.returncode,
            "elapsed_seconds": time.monotonic()-t, "tests": int(count.group(1)) if count else None,
            "skipped": int(skipped.group(1)) if skipped else 0,
            "log_sha256": sha256(out / f"{label}.log")}
        result["commands"].append(record)
        print(json.dumps(record), flush=True)
    result["elapsed_seconds"] = time.monotonic()-start
    result["source_unchanged_during_validation"] = source_inventory()["sha256"] == source["sha256"]
    result["status"] = "PASS" if all(r["exit_code"] == 0 for r in result["commands"]) and result["source_unchanged_during_validation"] else "FAIL"
    result["test_sources"] = [file_record(p, REPO) for p in sorted((HERE / "tests").glob("test_*.py"))]
    result["native_backend_validation"] = {"path": "backend/VALIDATION.json",
                                           "sha256": sha256(HERE / "backend/VALIDATION.json")}
    write_json(out / "VALIDATION.json", result)
    print(json.dumps({"status": result["status"], "elapsed_seconds": result["elapsed_seconds"]}))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
