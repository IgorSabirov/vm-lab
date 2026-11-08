"""Offline launch helpers. No network, job submission, authorization or scientific verdict.

The assistant performs connector calls described in LAUNCH_RUNBOOK.md. This helper
packages attested bytes, recomputes a measured forecast and reconciles live evidence.
"""
import argparse
import base64
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import statistics
import sys
import zlib


def unwrap(value):
    """Accept a plain JSON object or a captured MCP response; errors stay errors."""
    if not isinstance(value, dict):
        raise ValueError("expected JSON object")
    if value.get("isError"):
        raise ValueError("connector returned an error; no state inferred")
    if "structuredContent" in value or isinstance(value.get("content"), list):
        data = value.get("structuredContent")
        if data is None:
            texts = [x["text"] for x in value.get("content", []) if x.get("type") == "text"]
            if len(texts) != 1:
                raise ValueError("ambiguous connector response")
            data = texts[0]
        if isinstance(data, dict) and isinstance(data.get("content"), str):
            data = data["content"]
        value = json.loads(data) if isinstance(data, str) else data
    if not isinstance(value, dict):
        raise ValueError("expected JSON object in connector response")
    return value


def json_file(value):
    value = unwrap(value)
    if "text" in value and "path" in value:
        if value.get("next_offset") is not None:
            raise ValueError("file is incomplete; collect all chunks before parsing JSON")
        return json.loads(value["text"])
    return value


def checkpoint_cursor(value):
    value = unwrap(value)
    if "text" not in value:
        cursor = value.get("cursor")
    elif value.get("offset", 0) != 0:
        cursor = None
    else:
        try:
            cursor = json.loads(value["text"]).get("cursor")
        except json.JSONDecodeError:
            # Only an unambiguous top-level prefix, never a cursor inside active state.
            match = re.match(r'^\s*\{\s*"active"\s*:\s*null\s*,\s*"cursor"\s*:\s*(\d+)\s*,', value["text"])
            cursor = int(match[1]) if match else None
    return cursor if type(cursor) is int and cursor >= 0 else None


def observe(record, job, checkpoint=None, process=None, observed_at=None):
    """Produce a dated observation. A retry always retains the recorded job ID."""
    job = unwrap(job)
    if job.get("job_id") != record["job_id"]:
        raise ValueError("job identity mismatch")
    launcher_sha = record.get("launcher_sha256")
    if launcher_sha and job.get("source_sha256") != launcher_sha:
        raise ValueError("launcher hash mismatch (distinct from scientific source commit)")
    state = str(job.get("state", "unknown")).lower()
    cursor = checkpoint_cursor(checkpoint) if checkpoint is not None else None
    if cursor is not None and cursor > record["planned_tasks"]:
        raise ValueError("checkpoint exceeds planned task count")
    result = dict(observed_at_utc=observed_at,
                  interpreted_at_utc=datetime.now(timezone.utc).isoformat(),
                  job_id=record["job_id"], source_commit=record["source_commit"],
                  process_state=state, completed_tasks=cursor,
                  planned_tasks=record["planned_tasks"], progress_is_snapshot=True,
                  scientific_confirmation=False, automatic_resubmit=False)
    if checkpoint is not None:
        result["checkpoint_sha256"] = unwrap(checkpoint).get("sha256")
    if state in ("queued", "pending", "running"):
        result["next_action"] = "OBSERVE_EXISTING_JOB"
        result["execution_observed"] = state == "running" and cursor is not None and cursor > 0
        return result
    if state not in ("completed", "finished", "succeeded", "failed", "cancelled", "canceled", "interrupted"):
        result["next_action"] = "RESTORE_STATUS_ACCESS_WITHOUT_RESUBMIT"
        return result
    if process is None:
        result["next_action"] = "READ_PROCESS_AND_LOGS"
        return result
    proc = json_file(process)
    run = proc.get("run", {})
    if proc.get("source_commit") != record["source_commit"] or run.get("source_commit") != record["source_commit"]:
        raise ValueError("result source mismatch")
    for key in ("source_digest", "config_digest", "environment_fingerprint"):
        if record.get(key) and run.get(key) != record[key]:
            raise ValueError("result identity mismatch: " + key)
    result.update(process_wall_seconds=proc.get("process_wall_seconds"),
                  child_cpu_seconds=proc.get("child_cpu_seconds"),
                  process_exit_code=proc.get("exit_code"), executed_tasks=run.get("task_count"))
    complete = (state in ("completed", "finished", "succeeded") and proc.get("exit_code") == 0
                and job.get("exit_code", 0) == 0 and run.get("complete") is True
                and run.get("technical_pass") is True and run.get("task_count") == record["planned_tasks"])
    actual = proc.get("process_wall_seconds")
    limits = [record.get(k) for k in ("lower_seconds", "expected_seconds", "upper_seconds")]
    valid_time = (type(actual) in (int, float) and math.isfinite(actual) and actual > 0
                  and all(type(x) in (int, float) and math.isfinite(x) and x > 0 for x in limits)
                  and limits[0] <= limits[1] <= limits[2])
    result["time_and_workload_check"] = (
        "NOT_EVALUABLE" if not valid_time else
        "WITHIN_RANGE" if complete and limits[0] <= actual <= limits[2] else "REVIEW_REQUIRED")
    result["next_action"] = "READ_DECLARED_REPORT_AND_RECONCILE_TIME" if complete else "DIAGNOSE_AND_PRESERVE_OUTPUT"
    return result


def bundle(repo, receipt, tree):
    """One deterministic compressed upload, verified against the pinned Git tree."""
    repo = Path(repo).resolve()
    tree = unwrap(tree)
    if tree.get("truncated") or tree.get("sha") != receipt["github_tree_sha"]:
        raise ValueError("need complete pinned Git tree")
    git_files = {x["path"]: x["sha"] for x in tree["tree"] if x["type"] == "blob"}
    if set(receipt["files"]) != set(receipt["git_blobs"]):
        raise ValueError("incomplete source receipt")
    files = {}
    for name, sha256 in sorted(receipt["files"].items()):
        rel = PurePosixPath(name)
        if rel.is_absolute() or ".." in rel.parts or not rel.parts:
            raise ValueError("unsafe source path")
        path = repo.joinpath(*rel.parts)
        if not path.resolve().is_relative_to(repo):
            raise ValueError("source escapes repository")
        raw = path.read_bytes()
        git_sha = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        if (hashlib.sha256(raw).hexdigest() != sha256 or git_sha != receipt["git_blobs"][name]
                or git_files.get(name) != git_sha):
            raise ValueError("published source mismatch: " + name)
        files[name] = raw.decode("utf-8")
    encoded = json.dumps(files, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return dict(source_commit=receipt["source_commit"], github_tree_sha=receipt["github_tree_sha"],
                git_blobs=receipt["git_blobs"], zlib_base64=base64.b64encode(zlib.compress(encoded, 9)).decode())


def forecast(tasks, case_strata, calibration, base):
    """Measured stratified cost, for the existing NOW long-run design.

    The caller must justify strata applicability and unchanged base dynamics. This
    arithmetic helper does not grant admission or invent an uncertainty interval.
    """
    calibration = json_file(calibration)
    run = calibration["run"]
    rows = calibration["rows"]
    if (calibration.get("exit_code") != 0 or not run.get("complete") or not run.get("technical_pass")
            or run.get("phase") != "calibrate" or len(rows) != run.get("task_count") or not rows):
        raise ValueError("incomplete or failed target calibration")
    measurements = defaultdict(list)
    for row in rows:
        t = row["task_compute_seconds"]
        if type(t) not in (int, float) or not math.isfinite(t) or t < 0:
            raise ValueError("invalid measured task time")
        if row.get("stratum"):
            measurements[row["stratum"]].append(t)
    counts = Counter(case_strata.get(t["case_id"]) for t in tasks)
    base_count = counts.pop(None, 0)
    if base_count != base["tasks"] or not base.get("reference"):
        raise ValueError("unmeasured base workload or missing base reference")
    base_seconds = base["seconds"]
    if not math.isfinite(base_seconds) or base_seconds < 0:
        raise ValueError("invalid measured base time")
    if set(counts) - set(measurements):
        raise ValueError("uncalibrated strata: " + str(sorted(set(counts) - set(measurements))))
    wall = calibration["process_wall_seconds"]
    residual = wall - sum(x["task_compute_seconds"] for x in rows)
    if not math.isfinite(wall) or residual < -1e-8:
        raise ValueError("invalid serial timing decomposition; do not use for parallel task timers")
    extension = sum(n * statistics.mean(measurements[s]) for s, n in counts.items())
    estimate = extension + base_seconds + max(0, residual) * len(tasks) / len(rows)
    return dict(status="ARITHMETIC_ONLY", source_commit=calibration["source_commit"],
                source_digest=run["source_digest"], config_digest=run["config_digest"],
                environment_fingerprint=run["environment_fingerprint"],
                expected_seconds=estimate, task_count=len(tasks), base_tasks=base_count,
                base_reference=base["reference"], strata=dict(sorted(counts.items())),
                extension_compute_seconds=extension, cal_noncompute_seconds=residual,
                scientific_confirmation=False, admission_granted=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    ob = sub.add_parser("observe")
    for arg in ("record", "job", "output"):
        ob.add_argument("--" + arg, required=True)
    ob.add_argument("--checkpoint"); ob.add_argument("--process")
    ob.add_argument("--observed-at", help="UTC timestamp of the live connector read, not of this offline command")
    bu = sub.add_parser("bundle")
    for arg in ("repo", "receipt", "tree", "output"):
        bu.add_argument("--" + arg, required=True)
    fc = sub.add_parser("forecast")
    for arg in ("repo", "calibration", "base", "output"):
        fc.add_argument("--" + arg, required=True)
    args = parser.parse_args()
    read = lambda path: json.loads(Path(path).read_text())
    if args.command == "observe":
        value = observe(read(args.record), read(args.job),
                        read(args.checkpoint) if args.checkpoint else None,
                        read(args.process) if args.process else None, args.observed_at)
    elif args.command == "bundle":
        value = bundle(args.repo, read(args.receipt), read(args.tree))
    else:
        root = Path(args.repo).resolve() / "experiments/now_integrated_v1"
        sys.path.insert(0, str(root))
        from nowexp.runner import make_tasks, validate_workload
        from nowexp.provenance import digest, source_manifest
        plan = read(root / "preregistration/PROTOCOL.json")
        cases = read(root / "preregistration/CASES.json")
        validate_workload(plan, cases, read(root / "preregistration/FOUR_CANDIDATE_AMENDMENT.json"))
        calibration = json_file(read(args.calibration))
        if (calibration["run"]["config_digest"] != digest(cases)
                or calibration["run"]["source_digest"] != digest(source_manifest(root))):
            raise ValueError("use the exact calibrated source checkout")
        _, tasks = make_tasks(plan, cases, "main")
        value = forecast(tasks, {c["id"]: c.get("cost_stratum") for c in cases["cases"]}, calibration, read(args.base))
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    temp.replace(path)
    print(json.dumps({"output": str(path), "command": args.command}, ensure_ascii=False))


if __name__ == "__main__":
    main()
