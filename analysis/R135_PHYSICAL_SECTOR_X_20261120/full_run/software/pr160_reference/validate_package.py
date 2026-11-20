"""Verify the integrated PR160 package without launching a physical X scan.

The donor tests read actual pinned bytes. Separate native/GW controls keep
their original execution records; this command links rather than reruns them.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
import time

SOFTWARE = Path(__file__).resolve().parents[1]
REPO = SOFTWARE.parents[3]
sys.path.insert(0, str(SOFTWARE))
from r135.common import file_record, read_json, sha256, write_json
from r135.contracts import source_inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--native-cmb-python", type=Path,
                        help="optional already pinned ACT/SPT environment for the native regression tests")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    output = args.out.resolve()
    if output.exists():
        parser.error("choose a new output directory")
    output.mkdir(parents=True)
    before = source_inventory()
    test_before = [file_record(p, REPO) for folder in ("tests", "donors", "gw")
                   for p in sorted((SOFTWARE / folder).glob("test_*.py"))]
    test_before += [file_record(SOFTWARE / "test_p0_register.py", REPO), file_record(Path(__file__), REPO)]
    started = time.monotonic()
    commands = []
    env = os.environ.copy()
    env["R135_DONOR_CACHE"] = str(args.cache.resolve())

    def run(label, command, cwd=SOFTWARE, extra_env=None):
        start = time.monotonic()
        result = subprocess.run(command, cwd=cwd, env={**env, **(extra_env or {})}, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)
        log = output / (label + ".log")
        log.write_text(result.stdout)
        count = re.search(r"Ran (\d+) tests?", result.stdout)
        skipped = re.search(r"OK \(skipped=(\d+)\)", result.stdout)
        commands.append({"label": label, "command": [str(x) for x in command],
                         "cwd": str(cwd.relative_to(REPO)), "exit_code": result.returncode,
                         "elapsed_seconds": time.monotonic() - start, "log_sha256": sha256(log),
                         "tests": int(count[1]) if count else None, "skipped": int(skipped[1]) if skipped else 0})
        if result.returncode:
            write_json(output / "FAILED.json", {"commands": commands})
            raise RuntimeError(f"{label} failed; see {log}")

    run("core", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
    run("p0", [sys.executable, "-m", "unittest", "discover", "-s", ".", "-p", "test_p0_register.py", "-v"])
    run("donors", [sys.executable, "-m", "unittest", "discover", "-s", "donors", "-v"])
    run("gw", [sys.executable, "-m", "unittest", "discover", "-s", "gw", "-v"])
    if args.native_cmb_python:
        run("native_cmb", [str(args.native_cmb_python.absolute()), "-m", "unittest", "discover",
                           "-s", "tests", "-p", "test_external_cmb*.py", "-v"],
            extra_env={"R135_EXTERNAL_CMB_NATIVE": "1", "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "2"})
    run("registry", [sys.executable, "tools/registry_links.py", "--summary", str(output / "registry.json")], REPO)
    with tempfile.TemporaryDirectory(prefix="r135-pr160-p0-") as directory:
        work = Path(directory)
        write_json(work / "config.json", {"donor_cache": str(args.cache.resolve()), "offline": True})
        cli = str(SOFTWARE / "r135_stage.py")
        run("p0_seal_with_donors", [sys.executable, cli, "--seal", "--stage", "P0", "--config",
            str(work / "config.json"), "--template", str(SOFTWARE / "examples/request.validation.json"),
            "--out", str(work / "request.json")])
        run("p0_run_with_donors", [sys.executable, cli, "--stage", "P0", "--request",
            str(work / "request.json"), "--out", str(work / "result")])
        run("p0_verify_with_donors", [sys.executable, cli, "--verify", str(work / "result")])
        write_json(output / "P0_donor_consumption.json", read_json(work / "result/donor_acquisition.json"))
        write_json(output / "P0_execution_receipt.json", read_json(work / "result/EXECUTION_RECEIPT.json"))
    if before != source_inventory():
        raise RuntimeError("source files changed during the validation series")
    test_after = [file_record(p, REPO) for folder in ("tests", "donors", "gw")
                  for p in sorted((SOFTWARE / folder).glob("test_*.py"))]
    test_after += [file_record(SOFTWARE / "test_p0_register.py", REPO), file_record(Path(__file__), REPO)]
    if test_before != test_after:
        raise RuntimeError("test files changed during the validation series")
    refs = ["donor_reference/control/VALIDATION.json", "gw/integrated_reference/VALIDATION.json",
            "external_cmb_reference/native_control/VALIDATION.json",
            "external_cmb_reference/audit_control/VALIDATION.json"]
    for name in refs:
        result = read_json(SOFTWARE / name)
        if result.get("status") != "PASS" or result.get("physical_R135_run") is not False:
            raise RuntimeError("invalid scope/status for the saved control " + name)
    import numpy, scipy
    result = {"schema": "R135-PR160-integration-validation-v1", "status": "PASS",
              "scope": "DEVELOPMENT_TESTS_AND_CONDITIONAL_NUMERICAL_CONTROLS", "physical_R135_run": False,
              "scientific_acceptance": "owner_review", "integrated_PR160_sha": "cfbf4cbcb0529078d42c0d104dcf2e9f26e4ccc8",
              "base_executable_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
              "recorded_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "execution_identity": "exact source bytes and tests; changes uncommitted during this series",
              "source_sha256": before["sha256"], "source_files": before["files"],
              "source_unchanged_during_validation": True, "test_sources": test_before,
              "environment": {"python": platform.python_version(), "numpy": numpy.__version__, "scipy": scipy.__version__},
              "commands": commands, "elapsed_seconds": time.monotonic() - started,
              "saved_native_controls": [file_record(SOFTWARE / p, SOFTWARE) for p in refs],
              "native_controls_reexecuted_by_this_command": False,
              "native_CMB_tests_executed": bool(args.native_cmb_python),
              "native_CMB_interpreter_sha256": sha256(args.native_cmb_python) if args.native_cmb_python else None,
              "full_physical_runtime_gate": "NOT_EVALUABLE",
              "limitations": ["Optional native tests require their independently pinned environments.",
                              "Dedicated native/GW controls have their own executors, source hashes and scope.",
                              "These development measurements do not forecast a full physical R135 scan."]}
    write_json(output / "VALIDATION.json", result)
    print(json.dumps({k: result[k] for k in ("status", "elapsed_seconds", "commands")}, indent=2))


if __name__ == "__main__":
    main()
