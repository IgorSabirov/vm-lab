import hashlib
import math
import json
import os
from pathlib import Path
import platform
import sys
import time
import shutil

IO_BUDGET = None


def configure_io_budget(root, limit_bytes, reserve_bytes=0):
    global IO_BUDGET
    IO_BUDGET = (Path(root).resolve(), limit_bytes, reserve_bytes)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",",":"), allow_nan=False).encode()).hexdigest()


def source_manifest(root):
    # Receipts bind this complete manifest after GitHub publication, avoiding a self-hash.
    paths = sorted(list((root/"nowexp").glob("*.py")) + list((root/"preregistration").glob("*.json")) + list((root/"tests").glob("*.py")))
    paths += [root/"run.py", root/"requirements.txt"] + sorted(root.glob("*.md")) + sorted((root/"tools").glob("*.py"))
    repo = root.parents[1]
    paths += [repo/name for name in ("AGENTS.md", "RESEARCH_LINEAGE.md", "RUNTIME_GATE.md",
        "analysis/INTEGRATED_EXPERIMENT_20261107/EXPERIMENT_DESIGN.md",
        "analysis/INTEGRATED_EXPERIMENT_20261107/EXPERIMENT_GRAPH.json",
        "analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.json",
        "analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.md",
        "analysis/VM_ENVIRONMENT_20261107/ENVIRONMENT_CONSTRAINTS.json")]
    paths += [repo/'tools/piecewise_flat_qg/signature_kernel.py']
    return {str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(paths))}


def verify_source(root, commit, receipt_path):
    receipt = read_json(receipt_path)
    files = source_manifest(root)
    if receipt.get("source_commit") != commit or receipt.get("files") != files:
        raise ValueError("source commit/manifest does not match published source")
    if receipt.get("source_digest") != digest(files) or not receipt.get("github_tree_sha"):
        raise ValueError("invalid source attestation")
    repo = root.parents[1]
    for name, expected in receipt.get("git_blobs", {}).items():
        content = (repo/name).read_bytes()
        actual = hashlib.sha1(b"blob "+str(len(content)).encode()+b"\0"+content).hexdigest()
        if actual != expected:
            raise ValueError("Git blob mismatch: "+name)
    if set(receipt.get("git_blobs", {})) != set(files):
        raise ValueError("incomplete Git blob attestation")
    return files


def environment():
    import numpy as np
    def optional(path):
        try:
            return Path(path).read_text().strip()
        except OSError:
            return None
    cpuinfo = optional("/proc/cpuinfo") or ""
    cpu_model = next((line.split(":",1)[1].strip() for line in cpuinfo.splitlines()
                      if line.startswith("model name")), None)
    group = optional("/proc/self/cgroup") or ""
    cgroup = Path("/sys/fs/cgroup")
    for line in group.splitlines():
        if line.startswith("0::") and ".." not in Path(line[3:]).parts:
            candidate = cgroup/line[3:].lstrip("/")
            if (candidate/"cpu.max").exists():
                cgroup = candidate
    return dict(python=sys.version, platform=platform.platform(), numpy=np.__version__,
        cpu_count=os.cpu_count(), affinity=sorted(os.sched_getaffinity(0)) if hasattr(os,"sched_getaffinity") else None,
        cpu_max=optional(cgroup/"cpu.max"), memory_max=optional(cgroup/"memory.max"),
        threads={k:os.environ.get(k) for k in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS")},
        cpu_model=cpu_model, blas=np.__config__.CONFIG if hasattr(np.__config__,"CONFIG") else None)


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix+".tmp")
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)+"\n"
    size = len(encoded.encode())
    if IO_BUDGET and path.resolve().is_relative_to(IO_BUDGET[0]):
        root, cap, reserve = IO_BUDGET
        used = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
        if used+size > cap or shutil.disk_usage(root).free-size < reserve:
            raise RuntimeError("prospective atomic write exceeds disk budget/reserve")
    with tmp.open("w") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def read_json(path):
    return json.loads(Path(path).read_text())


def gate(root, phase, code_digest, config_digest, acceptance=None, smoke=None, calibration=None):
    if phase == "reviewer":
        return {"stage":"UNREVIEWED_REVIEWER_DIAGNOSTIC", "main_allowed":False}
    if not acceptance:
        raise ValueError("review acceptance required before author smoke/calibration/main")
    receipt = read_json(acceptance)
    if receipt.get("status") != "accepted" or receipt.get("source_digest") != code_digest:
        raise ValueError("review acceptance does not match current source")
    if not receipt.get("user_decision_reference") or not receipt.get("review_reference"):
        raise ValueError("review source and user's decision must be recorded")
    if phase not in receipt.get("authorized_phases", ["smoke", "calibrate", "main"]):
        raise ValueError("phase outside recorded current user authorization")
    if phase == "smoke":
        return {"stage":"REVIEWED_SMOKE", "main_allowed":False}
    if not smoke:
        raise ValueError("matching successful smoke report required")
    s = read_json(smoke)
    if not (s.get("source_digest") == code_digest and s.get("phase") == "smoke" and s.get("complete") and s.get("technical_pass")):
        raise ValueError("invalid smoke evidence")
    required_checks = {"after_row_scientific_equality", "after_checkpoint_scientific_equality",
                       "finalization_scientific_equality", "user_stop_scientific_equality",
                       "external_watchdog_killed_hang", "tampered_row_rejected", "wrong_commit_rejected"}
    if not required_checks <= {x["name"] for x in s.get("checks", []) if x.get("passed")}:
        raise ValueError("full recovery smoke suite required, not only trajectory smoke")
    if phase == "calibrate":
        return {"stage":"VM_CALIBRATION", "main_allowed":False}
    protocol = read_json(root/"preregistration"/"PROTOCOL.json")
    frozen_by_review = protocol.get("freeze_state") == "FROZEN_AFTER_REVIEW"
    authorization = protocol.get("execution_authorization", {})
    frozen_by_user = (protocol.get("freeze_state") == "FROZEN_AFTER_USER_DIRECTIVE"
        and authorization.get("technical_audit_waived") is True
        and authorization.get("runtime_gate_required") is True
        and receipt.get("audit_waived_by_user") is True
        and receipt.get("user_decision_reference"))
    if not (frozen_by_review or frozen_by_user):
        raise ValueError("protocol needs technical review or an explicit user waiver with runtime gate")
    if not calibration:
        raise ValueError("VM calibration/forecast required")
    c = read_json(calibration)
    if c.get("source_digest") != code_digest or c.get("config_digest") != config_digest:
        raise ValueError("calibration fingerprint mismatch")
    if c.get("environment_fingerprint") != digest(environment()):
        raise ValueError("target environment changed")
    if not c.get("measured_on_target_vm") or not c.get("complete"):
        raise ValueError("unverified target calibration")
    required = ("expected_seconds", "lower_seconds", "upper_seconds", "hard_wall_seconds",
                "memory_limit_mib", "disk_limit_mib", "task_count")
    if any(not isinstance(c.get(k),(int,float)) or not math.isfinite(c[k]) or c[k] <= 0 for k in required):
        raise ValueError("incomplete numeric VM forecast")
    if not c["lower_seconds"] <= c["expected_seconds"] <= c["upper_seconds"] <= c["hard_wall_seconds"]:
        raise ValueError("invalid forecast interval")
    envelope = protocol["phase_limits"]["main"]
    for key in ("hard_wall_seconds", "memory_limit_mib", "disk_limit_mib"):
        if c[key] > envelope[key]:
            raise ValueError("forecast exceeds preregistered envelope: " + key)
    return {"stage":"VM_MAIN", "main_allowed":True, "forecast":c}
