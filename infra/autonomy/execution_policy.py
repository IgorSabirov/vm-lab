"""Validate a frozen execution plan; do not submit jobs or accept science."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re

SHA = re.compile(r"[0-9a-f]{40}")
DIGEST = re.compile(r"[0-9a-f]{64}")
IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,100}")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def number(value, name, *, zero=False):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0 or (not zero and value == 0)):
        raise ValueError("Invalid budget: " + name)
    return value


def evidence(ref, root):
    path = ref.get("path", "")
    if not path or Path(path).is_absolute() or ".." in Path(path).parts or "\\" in path:
        raise ValueError("Unsafe evidence path")
    if not DIGEST.fullmatch(ref.get("sha256", "")):
        raise ValueError("Evidence requires SHA-256")
    if root is not None:
        root = Path(root).resolve()
        file = (root / path).resolve()
        if not file.is_relative_to(root) or not file.is_file():
            raise ValueError("Missing evidence: " + path)
        if hashlib.sha256(file.read_bytes()).hexdigest() != ref["sha256"]:
            raise ValueError("Changed evidence: " + path)


def validate(plan, limits, *, root=None):
    """Validate provenance, coverage, calibration and non-time resources.

    The owner selects placement; forecasts never become execution deadlines.
    Historical numeric time fields may be read without altering their bytes.
    """
    if plan.get("schema") != "vm-lab-execution-plan-v1":
        raise ValueError("Unknown execution plan schema")
    if not IDENTIFIER.fullmatch(plan.get("package_id", "")):
        raise ValueError("Invalid package_id")
    if not SHA.fullmatch(plan.get("source_commit", "")):
        raise ValueError("Freeze a full source commit before execution")
    branch = plan.get("publication_branch", "")
    if not branch.startswith("science/autonomous-") or any(c in branch for c in " ~^:?*[\\"):
        raise ValueError("Invalid autonomous publication branch")
    if plan.get("scientific_acceptance") is not False or plan.get("automatic_retry") is not False:
        raise ValueError("Science acceptance/retry must remain disabled")
    kind = plan.get("workload_kind")
    if kind not in {"independent_realizations", "continuous"}:
        raise ValueError("Declare scientific divisibility")
    for key in ("input_manifest", "acceptance", "calibration"):
        evidence(plan[key], root)
    if not plan["calibration"].get("environment_reference"):
        raise ValueError("Calibration must identify the measured environment")
    number(plan["calibration"].get("measured_seconds"), "calibration.measured_seconds")
    if plan.get("checkpoint_policy") not in {"not_required", "method_defined"}:
        raise ValueError("Declare checkpoint semantics without assuming resumability")
    if plan["checkpoint_policy"] == "method_defined":
        evidence(plan["checkpoint_contract"], root)

    tasks = plan["tasks"]
    sections = plan["sections"]
    if not tasks or not sections:
        raise ValueError("Empty task/section matrix")
    ids = [task["id"] for task in tasks]
    section_ids = [section["id"] for section in sections]
    if any(not isinstance(i, str) or not IDENTIFIER.fullmatch(i) for i in ids + section_ids):
        raise ValueError("Invalid task/section identifier")
    if len(set(ids)) != len(ids) or len(set(section_ids)) != len(section_ids):
        raise ValueError("Duplicate task/section identifier")
    matrix = {task["id"]: task for task in tasks}
    for task in tasks:
        forecast = number(task["forecast_seconds"], "task.forecast_seconds")
        # Seeds may repeat intentionally across A/B pairs; task IDs may not.
        if "seed" in task and (type(task["seed"]) is not int or task["seed"] < 0):
            raise ValueError("Invalid preregistered seed")
    assignments = [i for section in sections for i in section["task_ids"]]
    if sorted(assignments) != sorted(ids):
        raise ValueError("Sections must cover every whole task exactly once")
    if kind == "continuous" and (len(tasks) != 1 or len(sections) != 1):
        raise ValueError("A continuous integration cannot be split into sections")

    b = plan["budget"]
    for key in ("memory_bytes", "output_bytes"):
        number(b[key], key)
    if b["memory_bytes"] > limits["memory_bytes"] or b["output_bytes"] > limits["output_bytes"]:
        raise ValueError("Package exceeds authorized memory/output budget")
    parallelism = plan.get("parallel_sections", 1)
    if type(parallelism) is not int or not 1 <= parallelism <= len(sections):
        raise ValueError("Invalid section parallelism")
    if kind == "continuous" and parallelism != 1:
        raise ValueError("Continuous integration requires one process")
    peak_mem = []
    forecast_total = 0
    for section in sections:
        if not section["task_ids"]:
            raise ValueError("Empty section")
        overhead = sum(number(section[key], key, zero=(key == "setup_seconds"))
                       for key in ("setup_seconds", "verification_seconds", "publication_seconds"))
        mem = number(section["memory_bytes"], "section.memory_bytes")
        peak_mem.append(mem)
        forecast_total += overhead + sum(matrix[i]["forecast_seconds"] for i in section["task_ids"])
    if sum(sorted(peak_mem, reverse=True)[:parallelism]) > b["memory_bytes"]:
        raise ValueError("Concurrent sections exceed aggregate memory budget")
    # The owner chooses placement. Calibration must describe that same executor.
    # Legacy time-budget fields are retained in receipts, never used as deadlines.
    route = plan.get("executor")
    if route not in {"local", "github_actions", "vm"}:
        raise ValueError("Declare the executor selected by the owner")
    if plan["calibration"].get("executor") != route:
        raise ValueError("Calibration must match the owner-selected executor")
    if route == "vm":
        worker = plan["verified_vm_limits"]
        evidence(worker["evidence"], root)
        if (number(worker["memory_bytes"], "worker.memory_bytes") < b["memory_bytes"]
                or number(worker["output_bytes"], "worker.output_bytes") < b["output_bytes"]):
            raise ValueError("Verified VM resources do not support this package")
        if not worker.get("executor_id"):
            raise ValueError("Identify the verified VM worker")
    return {"package_id": plan["package_id"], "source_commit": plan["source_commit"],
            "plan_sha256": digest(plan), "executor": route,
            "forecast_seconds": forecast_total, "budget": b,
            "parallel_sections": parallelism, "placement_authority": "user",
            "duration_limit_seconds": None,
            "sections": [{"id": s["id"], "task_ids": s["task_ids"],
                          "timeout_minutes": None} for s in sections],
            "scientific_acceptance": False, "automatic_retry": False}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plan", type=Path)
    ap.add_argument("--control", type=Path, default=Path("infra/autonomy/CONTROL.json"))
    ap.add_argument("--root", type=Path, default=Path.cwd())
    args = ap.parse_args()
    result = validate(json.loads(args.plan.read_text()), json.loads(args.control.read_text())["limits"], root=args.root)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
