import hashlib
import math
import json
import os
from pathlib import Path
import platform
import sys
import time


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",",":"), allow_nan=False).encode()).hexdigest()


def source_manifest(root):
    # Exclude reports/receipts: acceptance is tied to code + scientific configuration.
    paths = sorted(list((root/"nowexp").glob("*.py")) + list((root/"preregistration").glob("*.json")) + list((root/"tests").glob("*.py")))
    paths += [root/"run.py", root/"requirements.txt"]
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


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
    return dict(python=sys.version, platform=platform.platform(), numpy=np.__version__,
        cpu_count=os.cpu_count(), affinity=sorted(os.sched_getaffinity(0)) if hasattr(os,"sched_getaffinity") else None,
        cpu_max=optional("/sys/fs/cgroup/cpu.max"), memory_max=optional("/sys/fs/cgroup/memory.max"),
        threads={k:os.environ.get(k) for k in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS")},
        cpu_model=cpu_model, blas=np.__config__.CONFIG if hasattr(np.__config__,"CONFIG") else None)


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix+".tmp")
    with tmp.open("w") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


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
    if phase == "smoke":
        return {"stage":"REVIEWED_SMOKE", "main_allowed":False}
    if not smoke:
        raise ValueError("matching successful smoke report required")
    s = read_json(smoke)
    if not (s.get("source_digest") == code_digest and s.get("phase") == "smoke" and s.get("complete") and s.get("technical_pass")):
        raise ValueError("invalid smoke evidence")
    if phase == "calibrate":
        return {"stage":"VM_CALIBRATION", "main_allowed":False}
    protocol = read_json(root/"preregistration"/"PROTOCOL.json")
    if protocol["freeze_state"] != "FROZEN_AFTER_REVIEW":
        raise ValueError("scientific protocol is not frozen")
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
