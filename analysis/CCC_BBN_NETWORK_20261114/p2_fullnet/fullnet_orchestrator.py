"""Stateful, approval-gated orchestration for P2_FULLNET.

Commands: prepare -> probe -> forecast -> publish -> approve -> publish -> run -> publish.
No automatic retry, no solver resume, no S1/S2 mode.
"""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import resource
import shutil
import signal
import subprocess
import sys
import time

PACKAGE = Path(__file__).resolve().parent
REPO = PACKAGE.parents[2]
PROFILE_PATH = PACKAGE / "PROFILE.json"
PARENT_COMMIT = "900a67f879621b501f74f8b1da561494fa3c4ae6"
UPSTREAM_PIN = "6f7e5680614fb119d65a6c9c65a292240b27c61e"
DEFAULT_RUN_ROOT = PACKAGE / "results" / "P2_FULLNET"
FROZEN_INPUTS = [
    "analysis/CCC_BBN_NETWORK_20261114/p2_fullnet/PROFILE.json",
    "analysis/CCC_BBN_NETWORK_20261114/p2_fullnet/PROVENANCE.json",
    "analysis/CCC_BBN_NETWORK_20261114/p2_fullnet/fullnet_worker.py",
    "analysis/CCC_BBN_NETWORK_20261114/p2_fullnet/fullnet_orchestrator.py",
    "analysis/CCC_BBN_NETWORK_20261114/p2_fullnet/run_fullnet.sh",
    "analysis/CCC_BBN_NETWORK_20261114/p2_fullnet/cloud_run.py",
    ".github/workflows/p2-fullnet-execute.yml",
    "analysis/CCC_BBN_NETWORK_20261114/p2_fullnet/RUN_REQUEST.json",
    "analysis/CCC_BBN_NETWORK_20261114/prelaunch/audit.py",
    "analysis/CCC_BBN_NETWORK_20261114/prelaunch/run.py",
    "analysis/CCC_BBN_NETWORK_20261114/prelaunch/s1_adapter.py",
]


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def digest(path):
    return sha256_bytes(Path(path).read_bytes())


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def git(*args, check=True, text=True):
    result = subprocess.run(
        ["git", "-C", str(REPO), *map(str, args)],
        check=check, text=text, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return result.stdout.strip() if text else result.stdout


def run_root_arg(value):
    root = Path(value).expanduser().resolve() if value else DEFAULT_RUN_ROOT.resolve()
    try:
        root.relative_to(REPO)
    except ValueError:
        raise RuntimeError("run_root must remain inside this checkout so evidence can be committed to the draft PR")
    return root


def append_ledger(root, event):
    path = root / "LEDGER.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.write(fd, line.encode("utf-8"))
        os.fsync(fd)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def ledger_events(root):
    path = root / "LEDGER.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def check_branch():
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    if branch != "s0-fullnet":
        raise RuntimeError(f"Expected branch s0-fullnet, found {branch!r}")
    head = git("rev-parse", "HEAD")
    git("merge-base", "--is-ancestor", PARENT_COMMIT, head)
    return head


def check_upstream(upstream):
    root = Path(upstream).expanduser().resolve()
    if not (root / ".git").exists():
        raise RuntimeError("upstream path is not a PRIMAT git checkout")
    head = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    tree = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD^{tree}"], text=True
    ).strip()
    dirty = subprocess.check_output(
        ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
        text=True,
    ).strip()
    if head != UPSTREAM_PIN or dirty:
        raise RuntimeError(
            f"PRIMAT checkout must be clean at {UPSTREAM_PIN}; got {head}, dirty={bool(dirty)}"
        )
    return root, head, tree


def verify_frozen(root):
    freeze = read_json(root / "FREEZE.json")
    frozen_commit = freeze["source_commit"]
    current = git("rev-parse", "HEAD")
    git("merge-base", "--is-ancestor", frozen_commit, current)
    for path, expected in freeze["source_files"].items():
        local = REPO / path
        actual = digest(local)
        if actual != expected["sha256"]:
            raise RuntimeError(f"Frozen source changed after prepare: {path}")
        frozen = git("show", f"{frozen_commit}:{path}", check=False, text=False)
        if not frozen or sha256_bytes(frozen) != expected["sha256"]:
            raise RuntimeError(f"Git object does not match frozen file: {path}")
    for filename, field in (("PRODUCTION_CONFIG.json","production_config_sha256"),("PROBE_CONFIG.json","probe_config_sha256")):
        if digest(root/filename)!=freeze[field]:
            raise RuntimeError("Frozen configuration changed: "+filename)
    return freeze


def spent_seconds(root):
    return sum(float(e.get("wall_seconds",0)) for e in ledger_events(root) if "run_id" in e and "exit_code" in e)


def executor_policy():
    if os.environ.get("GITHUB_ACTIONS")=="true":
        request=read_json(PACKAGE/"RUN_REQUEST.json")
        if os.environ.get("GITHUB_REPOSITORY")!="IgorSabirov/vm-lab" or request["executor"]!="GITHUB_ACTIONS_VM":
            raise RuntimeError("Wrong hosted executor/request")
        return {"id":"GITHUB_ACTIONS_VM","package_cap":int(request["package_wall_cap_seconds"]),"process_cap":int(request["process_wall_cap_seconds"])}
    return {"id":"LOCAL_SANDBOX","package_cap":600,"process_cap":600}


def prepare(args):
    head = check_branch()
    upstream, up_head, up_tree = check_upstream(args.upstream)
    root = run_root_arg(args.run_root)
    if root.exists() and any(root.iterdir()):
        raise RuntimeError(f"Refusing to overwrite non-empty run directory: {root}")
    root.mkdir(parents=True, exist_ok=True)

    profile = read_json(PROFILE_PATH)
    production = dict(profile["production_config"])
    production["network"] = "large"
    production.pop("amax", None)
    probe = dict(production)
    probe.update(profile["probe_overrides_only"])
    for key in (
        "sampling_temperature_per_decade", "sampling_nTOp_per_decade",
        "sampling_nTOp_thermal_per_decade", "T_start_cosmo_MeV", "T_end_MeV",
        "vegas_n_eval", "vegas_n_itn",
    ):
        if probe.get(key) != production.get(key):
            raise RuntimeError(f"Probe altered cache/background-sensitive field: {key}")

    sys.path.insert(0,str(upstream))
    from primat.config import PRIMATConfig
    from primat.weak_rates.cache import weak_rate_fingerprint, thermal_fingerprint
    from primat.cache_utils import fingerprint_hash
    actual_fingerprints={}
    for name, config in (("production",production),("probe",probe)):
        cfg=PRIMATConfig(config)
        hashes=[fingerprint_hash(weak_rate_fingerprint(cfg)), fingerprint_hash(thermal_fingerprint(cfg))]
        if hashes != ["7e3af87bd0404e0a","cfdb4d324bb5651f"]:
            raise RuntimeError("Typed weak cache fingerprint mismatch before any solver: "+name+str(hashes))
        actual_fingerprints[name]=hashes
    write_json(root/"CACHE_PREFLIGHT.json",actual_fingerprints)
    write_json(root / "PRODUCTION_CONFIG.json", production)
    write_json(root / "PROBE_CONFIG.json", probe)
    write_json(root / "SETUP.json", {
        "created_utc": now(),
        "repo": "<VM_LAB_CHECKOUT>",
        "source_commit": head,
        "source_parent_commit": PARENT_COMMIT,
        "upstream_checkout": "external pinned PRIMAT checkout; local absolute path intentionally omitted",
        "upstream_commit": up_head,
        "upstream_tree": up_tree,
        "run_root": "<VM_LAB_CHECKOUT>/" + str(root.relative_to(REPO)),
        "probe_overlay": "<P2_RUN_ROOT>/cache_probe",
        "main_overlay": "<P2_RUN_ROOT>/cache_main",
        "scientific_acceptance": False,
    })

    # Reuse the already-reviewed source-only inventory; it does not integrate BBN.
    inventory = root / "STATIC_INVENTORY"
    inventory.mkdir()
    audit = PACKAGE.parent / "prelaunch" / "audit.py"
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    audit_proc = subprocess.run(
        [sys.executable, str(audit), "--upstream", str(upstream), "--out", str(inventory)],
        cwd=str(audit.parent), env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    (root / "STATIC_INVENTORY.stdout.txt").write_text(audit_proc.stdout, encoding="utf-8")
    (root / "STATIC_INVENTORY.stderr.txt").write_text(audit_proc.stderr, encoding="utf-8")
    if audit_proc.returncode:
        raise RuntimeError("Static network inventory failed; no solver run was attempted")
    coverage = read_json(inventory / "RATE_COVERAGE.json")
    p2 = next((p for p in coverage["profiles"] if p["profile"] == "P2"), None)
    if p2 is None or len(p2["eras"][1]["species"]) != 59 or len(p2["eras"][1]["channels"]) != 428:
        raise RuntimeError("P2 static inventory does not match the expected full network")
    write_json(root / "PROFILE_RESOLVED.json", {
        "profile_id": profile["id"],
        "alias": profile["alias"],
        "primat_params": production,
        "probe_params": probe,
        "static_inventory_summary": {
            "P2_LT_species": len(p2["eras"][1]["species"]),
            "P2_LT_channels_including_weak": len(p2["eras"][1]["channels"]),
            "solver_executed": False,
        },
        "upstream_commit": up_head,
        "upstream_tree": up_tree,
    })

    source_files = {}
    for rel in FROZEN_INPUTS:
        file = REPO / rel
        if not file.is_file():
            raise RuntimeError(f"Missing frozen source input: {rel}")
        tracked = git("show", f"{head}:{rel}", check=False, text=False)
        if not tracked or sha256_bytes(tracked) != digest(file):
            raise RuntimeError(f"Working source differs from committed input: {rel}")
        source_files[rel] = {"sha256": digest(file)}
    freeze = {
        "schema": "vm-lab-p2-source-freeze-v1",
        "frozen_utc": now(),
        "source_commit": head,
        "source_parent_commit": PARENT_COMMIT,
        "source_files": source_files,
        "profile_sha256": digest(PROFILE_PATH),
        "production_config_sha256": digest(root / "PRODUCTION_CONFIG.json"),
        "probe_config_sha256": digest(root / "PROBE_CONFIG.json"),
        "upstream_commit": up_head,
        "upstream_tree": up_tree,
        "cache_identity": profile["cache_contract"],
        "scientific_acceptance": False,
    }
    write_json(root / "FREEZE.json", freeze)
    append_ledger(root, {
        "utc": now(), "stage": "PREPARE", "status": "PREPARED_STATIC_INVENTORY_PASS",
        "source_commit": head, "upstream_commit": up_head,
        "P2_LT_species": 59, "P2_LT_channels_including_weak": 428,
        "solver_executed": False,
    })
    print(json.dumps({
        "status": "PREPARED_STATIC_INVENTORY_PASS",
        "source_commit": head,
        "upstream_commit": up_head,
        "P2_LT_species": 59,
        "P2_LT_channels_including_weak": 428,
        "run_root": "<VM_LAB_CHECKOUT>/" + str(root.relative_to(REPO)),
        "next": "probe",
    }, ensure_ascii=False))
    return 0


def execute_worker(root, upstream, run_id, config, cache, out, cap, budget_scope):
    verify_frozen(root)
    if out.exists():
        raise RuntimeError(f"Refusing to overwrite existing run output: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    worker = PACKAGE / "fullnet_worker.py"
    process_dir = root / "process"
    process_dir.mkdir(exist_ok=True)
    before_path = process_dir / f"{run_id}.before.json"
    after_path = process_dir / f"{run_id}.after.json"
    stdout_path = process_dir / f"{run_id}.stdout.txt"
    stderr_path = process_dir / f"{run_id}.stderr.txt"
    env = os.environ.copy()
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env[name] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    command = [
        sys.executable, str(worker),
        "--upstream", str(upstream),
        "--config", str(config),
        "--cache", str(cache),
        "--out", str(out),
        "--run-id", run_id,
    ]

    def limits():
        resource.setrlimit(resource.RLIMIT_AS, (4 * 1024**3, 4 * 1024**3))
        resource.setrlimit(resource.RLIMIT_FSIZE, (128 * 1024**2, 128 * 1024**2))
        resource.setrlimit(resource.RLIMIT_CPU, (int(math.ceil(cap)), int(math.ceil(cap)) + 1))

    command_receipt = [
        Path(sys.executable).name, "fullnet_worker.py",
        "--upstream", "<PINNED_PRIMAT_CHECKOUT>",
        "--config", str(config.relative_to(REPO)),
        "--cache", "<P2_RUN_ROOT>/" + str(cache.relative_to(root)),
        "--out", "<P2_RUN_ROOT>/" + str(out.relative_to(root)),
        "--run-id", run_id,
    ]
    before = {
        "utc": now(), "run_id": run_id, "command": command_receipt,
        "frozen_source_commit": read_json(root / "FREEZE.json")["source_commit"],
        "upstream_commit": UPSTREAM_PIN, "budget_scope": budget_scope,
        "limits": {
            "wall_seconds": cap, "address_space_bytes": 4 * 1024**3,
            "individual_file_bytes": 128 * 1024**2,
            "output_tree_bytes": 512 * 1024**2,
        },
        "machine": {
            "platform": platform.platform(),
            "affinity": sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
            "loadavg": list(os.getloadavg()) if hasattr(os, "getloadavg") else None,
            "disk_free_bytes": shutil.disk_usage(out.parent).free,
            "cpuinfo":Path('/proc/cpuinfo').read_text().split('\n\n')[0],
            "meminfo":Path('/proc/meminfo').read_text(),
            "cgroup_quota":None,"cgroup_reason":"not exposed in this container",
        },
        "threads": {k: env[k] for k in (
            "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"
        )},
        "cache_before": {
            str(p.relative_to(cache)): digest(p)
            for p in sorted(cache.rglob("*")) if p.is_file()
        },
        "checkpoint": "each completed era has raw arrays and compressed raw/dense sample checkpoint; incomplete current era not resumable",
        "automatic_retry": False,
    }
    write_json(before_path, before)
    wall0 = time.monotonic()
    cpu0 = resource.getrusage(resource.RUSAGE_CHILDREN)
    reason = None
    peak_rss_kib = 0
    proc = None
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        proc = subprocess.Popen(
            command, cwd=str(REPO), env=env, stdout=stdout, stderr=stderr,
            start_new_session=True, preexec_fn=limits,
        )
        while proc.poll() is None:
            size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) if out.exists() else 0
            elapsed = time.monotonic() - wall0
            status_file = Path(f"/proc/{proc.pid}/status")
            if status_file.is_file():
                for line in status_file.read_text().splitlines():
                    if line.startswith(("VmHWM:", "VmRSS:")):
                        try:
                            peak_rss_kib = max(peak_rss_kib, int(line.split()[1]))
                        except (ValueError, IndexError):
                            pass
            if elapsed > cap:
                reason = "WALL_CAP"
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
                break
            if size > 512 * 1024**2:
                reason = "OUTPUT_CAP"
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
                break
            time.sleep(0.2)
    elapsed = time.monotonic() - wall0
    cpu1 = resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu = (cpu1.ru_utime + cpu1.ru_stime) - (cpu0.ru_utime + cpu0.ru_stime)
    peak_rss_mib = peak_rss_kib / 1024.0 if peak_rss_kib else None
    status = "COMPLETED" if proc.returncode == 0 else (
        "CENSORED_BY_WALL_CAP" if reason == "WALL_CAP" else
        "CENSORED_BY_OUTPUT_CAP" if reason == "OUTPUT_CAP" else
        "FAILED_TECHNICAL"
    )
    files = [p for p in out.rglob("*") if p.is_file()] if out.exists() else []
    after = {
        "utc": now(), "run_id": run_id, "exit_code": proc.returncode,
        "stop_reason": reason, "status": status,
        "wall_seconds": elapsed, "cpu_seconds": cpu, "sampled_peak_rss_mib": peak_rss_mib,
        "output_bytes": sum(p.stat().st_size for p in files),
        "result_present": (out / "RESULT.json").is_file(),
        "cache_after": {
            str(p.relative_to(cache)): digest(p)
            for p in sorted(cache.rglob("*")) if p.is_file()
        },
    }
    write_json(after_path, after)
    append_ledger(root, {
        "utc": now(), "stage": budget_scope, "run_id": run_id, "status": status,
        "exit_code": proc.returncode, "wall_seconds": elapsed,
        "cpu_seconds": cpu, "sampled_peak_rss_mib": peak_rss_mib,
        "stop_reason": reason,
    })
    return after


def probe(args):
    root = run_root_arg(args.run_root)
    verify_frozen(root)
    upstream, _, _ = check_upstream(args.upstream)
    if (root / "CALIBRATION.json").exists():
        raise RuntimeError("Probe already exists; no automatic rerun/retry")
    cap = min(60.0,executor_policy()["package_cap"]-spent_seconds(root))
    if cap<=0: raise RuntimeError("P2 package budget exhausted")
    receipt = execute_worker(
        root, upstream, "PROBE", root / "PROBE_CONFIG.json",
        root / "cache_probe", root / "runs" / "PROBE",
        cap, "P2_CALIBRATION_INCLUDED_IN_PACKAGE",
    )
    result_path = root / "runs" / "PROBE" / "RESULT.json"
    worker_result = read_json(result_path) if result_path.is_file() else None
    calibration = {
        "schema": "vm-lab-p2-calibration-v1",
        "created_utc": now(),
        "probe_status": receipt["status"],
        "probe_wall_seconds": receipt["wall_seconds"],
        "probe_cpu_seconds": receipt["cpu_seconds"],
        "probe_peak_rss_mib": receipt["sampled_peak_rss_mib"],
        "wall_cap_seconds": cap,
        "worker_timing": worker_result.get("timing") if worker_result else None,
        "worker_checks": worker_result.get("checks") if worker_result else None,
        "probe_result_sha256": digest(result_path) if result_path.is_file() else None,
        "probe_trace_sha256": digest(root / "runs" / "PROBE" / "TRACE.json")
            if (root / "runs" / "PROBE" / "TRACE.json").is_file() else None,
        "forecast_policy": "An explicitly documented operator engineering envelope with target-machine calibration is required.",
        "scientific_acceptance": False,
    }
    write_json(root / "CALIBRATION.json", calibration)
    append_ledger(root, {
        "utc": now(), "stage": "PROBE_SUMMARY", "status": receipt["status"],
        "probe_wall_seconds": receipt["wall_seconds"],
        "probe_cpu_seconds": receipt["cpu_seconds"],
        "probe_peak_rss_mib": receipt["sampled_peak_rss_mib"],
    })
    print(json.dumps({
        "status": receipt["status"],
        "wall_seconds": receipt["wall_seconds"],
        "cpu_seconds": receipt["cpu_seconds"],
        "sampled_peak_rss_mib": receipt["sampled_peak_rss_mib"],
        "next": "forecast (human-specified engineering envelope)",
    }, ensure_ascii=False))
    return 0 if receipt["status"] == "COMPLETED" else 2


def forecast(args):
    root = run_root_arg(args.run_root)
    verify_frozen(root)
    calibration_path = root / "CALIBRATION.json"
    if not calibration_path.is_file():
        raise RuntimeError("Run the P2 probe before forecasting")
    calibration = read_json(calibration_path)
    if calibration["probe_status"] not in (
        "COMPLETED", "CENSORED_BY_WALL_CAP", "CENSORED_BY_OUTPUT_CAP"
    ):
        raise RuntimeError("Probe technical failure does not support a runtime forecast")
    low, central, high = args.low, args.central, args.high
    if not (0 < low <= central <= high):
        raise RuntimeError("Forecast bounds must satisfy 0 < low <= central <= high")
    if not args.basis.strip():
        raise RuntimeError("Forecast basis is mandatory")
    forecast_obj = {
        "schema": "vm-lab-p2-runtime-forecast-v1",
        "created_utc": now(),
        "source_commit": read_json(root / "FREEZE.json")["source_commit"],
        "probe": {
            "status": calibration["probe_status"],
            "wall_seconds": calibration["probe_wall_seconds"],
            "cpu_seconds": calibration["probe_cpu_seconds"],
            "peak_rss_mib": calibration["probe_peak_rss_mib"],
            "result_sha256": calibration["probe_result_sha256"],
        },
        "production_profile": "P2_FULLNET",
        "production_config_sha256": digest(root / "PRODUCTION_CONFIG.json"),
        "seconds": {"low": low, "central": central, "high": high},
        "basis": args.basis,
        "forecast_method_status": "OPERATOR_ENGINEERING_WORK_COUNT_ENVELOPE",
        "forecast_scope":"COLD_PLUS_WARM",
        "calibration_seconds_already_used":spent_seconds(root),
        "package_seconds":{"low":low+spent_seconds(root),"central":central+spent_seconds(root),"high":high+spent_seconds(root)},
        "executor":executor_policy(),
        "native_route": "WITHIN_EXECUTOR_CAP" if high+spent_seconds(root) <= executor_policy()["package_cap"] else "FORECAST_EXCEEDS_EXECUTOR_CAP",
        "approval_required": True,
        "scientific_acceptance": False,
    }
    write_json(root / "FORECAST.json", forecast_obj)
    forecast_sha = digest(root / "FORECAST.json")
    write_json(root / "FORECAST_RECEIPT.json", {
        "forecast_sha256": forecast_sha,
        "forecast_file": "FORECAST.json",
        "created_utc": now(),
        "published_before_main_run": False,
    })
    print(json.dumps({
        "status": forecast_obj["native_route"],
        "forecast_sha256": forecast_sha,
        "seconds": forecast_obj["seconds"],
        "next": "publish, then explicit approve",
    }, ensure_ascii=False))
    if args.auto_approve:
        if not args.publish:
            raise RuntimeError("--auto-approve requires --publish; forecast must reach GitHub before main run")
        if args.max_upper_seconds is None or high+spent_seconds(root) > args.max_upper_seconds or high+spent_seconds(root) > executor_policy()["package_cap"]:
            raise RuntimeError("Auto-approval refused: explicit max-upper bound is absent or exceeded")
        publish(root)
        create_approval(root, forecast_sha, "AUTO_APPROVED_BY_EXPLICIT_FLAG", args.max_upper_seconds)
        publish(root)  # commit approval receipt before any main solver starts
        execute_main(root, args.upstream)
    elif args.publish:
        publish(root)
    return 0


def publish(root):
    root = Path(root).resolve()
    try:
        rel = root.relative_to(REPO)
    except ValueError:
        raise RuntimeError("Cannot publish run artifacts outside repository")
    if git("rev-parse", "--abbrev-ref", "HEAD") != "s0-fullnet":
        raise RuntimeError("Publishing allowed only from s0-fullnet branch")
    git("add", "--", str(rel))
    staged_paths = git("diff", "--cached", "--name-only").splitlines()
    allowed_prefix = str(rel) + "/"
    unrelated = [
        item for item in staged_paths
        if item != str(rel) and not item.startswith(allowed_prefix)
    ]
    if unrelated:
        raise RuntimeError(
            "Refusing to publish: unrelated staged files exist: " + ", ".join(unrelated)
        )
    staged = subprocess.run(
        ["git", "-C", str(REPO), "diff", "--cached", "--quiet"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if staged.returncode == 0:
        print("No new run artifacts to publish.")
        return
    if staged.returncode != 1:
        raise RuntimeError("Could not inspect git index")
    git("commit", "-m", "Record P2_FULLNET execution evidence")
    git("push", "-u", "origin", "s0-fullnet")
    print(json.dumps({
        "status": "PUBLISHED",
        "head": git("rev-parse", "HEAD"),
        "branch": "s0-fullnet",
        "path": str(rel),
    }, ensure_ascii=False))


def verify_forecast_published(root, forecast_sha):
    if digest(root / "FORECAST.json") != forecast_sha:
        raise RuntimeError("Forecast SHA mismatch; approval is tied to exact FORECAST.json")
    rel = (root / "FORECAST.json").relative_to(REPO)
    committed = git("show", f"HEAD:{rel}", check=False, text=False)
    if not committed or sha256_bytes(committed) != forecast_sha:
        raise RuntimeError("Forecast is not committed to current branch")
    remote = subprocess.check_output(
        ["git", "-C", str(REPO), "ls-remote", "origin", "refs/heads/s0-fullnet"],
        text=True,
    ).strip().split()
    local = git("rev-parse", "HEAD")
    if not remote or remote[0] != local:
        raise RuntimeError("Forecast commit is not pushed to GitHub; publish first")


def create_approval(root, forecast_sha, approver, max_upper):
    verify_forecast_published(root, forecast_sha)
    forecast_obj = read_json(root / "FORECAST.json")
    high = float(forecast_obj["seconds"]["high"])
    if high+spent_seconds(root) > max_upper or high+spent_seconds(root) > executor_policy()["package_cap"]:
        raise RuntimeError("Forecast upper bound exceeds the authorized execution budget")
    approval = {
        "schema": "vm-lab-p2-run-approval-v1",
        "approved_utc": now(),
        "approved_by": approver,
        "forecast_sha256": forecast_sha,
        "authorized_max_upper_seconds": max_upper,
        "authorized_per_run_wall_cap_seconds": executor_policy()["process_cap"],
        "authorized_total_wall_cap_seconds_including_calibration": executor_policy()["package_cap"],
        "executor":executor_policy()["id"],
        "runs": ["COLD", "WARM"],
        "scientific_acceptance": False,
    }
    write_json(root / "APPROVAL.json", approval)
    append_ledger(root, {
        "utc": now(), "stage": "APPROVAL", "status": "APPROVED_FOR_ENGINEERING_RUN",
        "approved_by": approver, "forecast_sha256": forecast_sha,
        "forecast_high_seconds": high, "authorized_max_upper_seconds": max_upper,
    })


def execute_main(root, upstream):
    upstream, _, _ = check_upstream(upstream)
    approval = read_json(root / "APPROVAL.json")
    forecast_obj = read_json(root / "FORECAST.json")
    if approval["forecast_sha256"] != digest(root / "FORECAST.json"):
        raise RuntimeError("Approval receipt does not match current forecast")
    high = float(forecast_obj["seconds"]["high"])
    if high+spent_seconds(root) > approval["authorized_max_upper_seconds"] or high+spent_seconds(root) > executor_policy()["package_cap"]:
        raise RuntimeError("Forecast exceeds approved budget")
    verify_frozen(root)
    verify_forecast_published(root, approval["forecast_sha256"])
    approval_rel=(root/"APPROVAL.json").relative_to(REPO)
    if git("show",f"HEAD:{approval_rel}",text=False)!= (root/"APPROVAL.json").read_bytes():
        raise RuntimeError("Approval receipt must be published before production")

    main_cache = root / "cache_main"
    if main_cache.exists() and any(main_cache.iterdir()):
        raise RuntimeError("Main cold/warm overlay is not empty; refusing to relabel it cold")
    main_cache.mkdir(parents=True, exist_ok=True)
    used = spent_seconds(root)
    if used>=executor_policy()["package_cap"]: raise RuntimeError("P2 aggregate executor cap exhausted")
    remaining=executor_policy()["package_cap"]-used

    cold = execute_worker(
        root, upstream, "COLD", root / "PRODUCTION_CONFIG.json",
        main_cache, root / "runs" / "COLD",
        min(executor_policy()["process_cap"], remaining), "P2_MAIN",
    )
    if cold["status"] != "COMPLETED" or not (root / "runs" / "COLD" / "RESULT.json").is_file():
        write_json(root / "SUMMARY.json", {
            "status": "ENGINEERING_TIMEOUT_OR_FAILURE",
            "failed_stage": "COLD",
            "process": cold,
            "physics_failure_inference": "NOT_MADE",
            "scientific_acceptance": False,
        })
        finalize_artifacts(root)
        raise RuntimeError("P2 main did not complete; evidence retained")

    used += float(cold["wall_seconds"])
    remaining = executor_policy()["package_cap"] - used
    if remaining <= 1:
        write_json(root / "SUMMARY.json", {
            "status": "ENGINEERING_BUDGET_EXHAUSTED_AFTER_COLD",
            "cold": cold,
            "warm": "NOT_STARTED",
            "physics_failure_inference": "NOT_MADE",
            "scientific_acceptance": False,
        })
        finalize_artifacts(root)
        raise RuntimeError("P2 main did not complete; evidence retained")

    warm = execute_worker(
        root, upstream, "WARM", root / "PRODUCTION_CONFIG.json",
        main_cache, root / "runs" / "WARM",
        min(executor_policy()["process_cap"], remaining), "P2_MAIN",
    )
    repeatability = {"compared": False, "exact_trace_match": None, "exact_Y_final_match": None}
    if warm["status"] == "COMPLETED":
        cold_result = read_json(root / "runs" / "COLD" / "RESULT.json")
        warm_result = read_json(root / "runs" / "WARM" / "RESULT.json")
        cold_trace = read_json(root / "runs" / "COLD" / "TRACE.json")
        warm_trace = read_json(root / "runs" / "WARM" / "TRACE.json")
        repeatability = {
            "compared": True,
            "exact_trace_match": cold_trace["eras"] == warm_trace["eras"],
            "exact_Y_final_match": (
                cold_result["result"]["Y_final"] == warm_result["result"]["Y_final"]
            ),
            "cold_status": cold_result["status"],
            "warm_status": warm_result["status"],
            "interpretation": "deterministic repeatability check, not cross-backend or independent-solver validation",
        }
        write_json(root / "REPEATABILITY.json", repeatability)

    success = (
        cold["status"] == "COMPLETED"
        and warm["status"] == "COMPLETED"
        and repeatability["exact_trace_match"] is True
        and repeatability["exact_Y_final_match"] is True
        and read_json(root / "runs" / "COLD" / "RESULT.json")["status"] == "ENGINEERING_PASS"
        and read_json(root / "runs" / "WARM" / "RESULT.json")["status"] == "ENGINEERING_PASS"
    )
    summary = {
        "schema": "vm-lab-p2-summary-v1",
        "status": "ENGINEERING_PASS" if success else "ENGINEERING_REVIEW_REQUIRED",
        "budget": {
            "scope": "P2 only; independent from P0/P1 cumulative prelaunch ledger",
            "hard_wall_cap_seconds_per_run": executor_policy()["process_cap"],
            "hard_total_wall_cap_seconds_including_calibration": executor_policy()["package_cap"],
            "executor":executor_policy()["id"],
            "total_package_wall_seconds":spent_seconds(root),
            "cold_wall_seconds": cold["wall_seconds"],
            "warm_wall_seconds": warm["wall_seconds"],
            "total_wall_seconds": cold["wall_seconds"] + warm["wall_seconds"],
            "forecast":forecast_obj,
            "runtime_status":"FORECAST_IN_RANGE" if forecast_obj["seconds"]["low"]<=cold["wall_seconds"]+warm["wall_seconds"]<=forecast_obj["seconds"]["high"] else "REVIEW_REQUIRED",
        },
        "cold": cold,
        "warm": warm,
        "repeatability": repeatability,
        "physics_failure_inference": "NOT_MADE",
        "scientific_acceptance": False,
        "scope": "standard S0 PRIMAT full network only; S1-v2/S2/S_eta/BH1/B07/S3 excluded",
    }
    write_json(root / "SUMMARY.json", summary)
    finalize_artifacts(root)
    print(json.dumps({"status": summary["status"], "summary": str(root / "SUMMARY.json")}, ensure_ascii=False))
    if not success: raise RuntimeError("P2 main validation failed; artifacts retained")
    return 0


def finalize_artifacts(root):
    files = sorted(
        p for p in root.rglob("*")
        if p.is_file() and p.name != "ARTIFACTS.json" and not any(x.startswith("cache_") for x in p.relative_to(root).parts) and not p.name.startswith("SOLVER_")
    )
    manifest = {
        "schema": "vm-lab-sha256-artifact-manifest-v1",
        "created_utc": now(),
        "algorithm": "SHA-256",
        "root_relative_paths": True,
        "files": {
            str(p.relative_to(root)): {
                "sha256": digest(p),
                "bytes": p.stat().st_size,
            }
            for p in files
        },
        "manifest_self_hash": "omitted by design",
    }
    write_json(root / "ARTIFACTS.json", manifest)


def approve(args):
    root = run_root_arg(args.run_root)
    verify_frozen(root)
    if args.max_upper_seconds > executor_policy()["package_cap"]:
        raise RuntimeError("Requested cap exceeds selected executor policy")
    create_approval(root, args.forecast_sha, args.approved_by, args.max_upper_seconds)
    print(json.dumps({"status": "APPROVAL_RECEIPT_READY_PUBLISH_THEN_RUN"}, ensure_ascii=False))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)

    def add_root(p):
        p.add_argument("--run-root", default=None)

    p = subs.add_parser("prepare")
    p.add_argument("--upstream", required=True)
    add_root(p)

    p = subs.add_parser("probe")
    p.add_argument("--upstream", required=True)
    add_root(p)

    p = subs.add_parser("forecast")
    add_root(p)
    p.add_argument("--low", type=float, required=True)
    p.add_argument("--central", type=float, required=True)
    p.add_argument("--high", type=float, required=True)
    p.add_argument("--basis", required=True)
    p.add_argument("--publish", action="store_true")
    p.add_argument("--auto-approve", action="store_true")
    p.add_argument("--max-upper-seconds", type=float)
    p.add_argument("--upstream")

    p = subs.add_parser("approve")
    add_root(p)
    p.add_argument("--upstream", required=True)
    p.add_argument("--forecast-sha", required=True)
    p.add_argument("--approved-by", required=True)
    p.add_argument("--max-upper-seconds", type=float, required=True)

    p = subs.add_parser("run")
    add_root(p)
    p.add_argument("--upstream",required=True)

    p = subs.add_parser("publish")
    add_root(p)

    args = parser.parse_args()
    if args.command == "prepare":
        return prepare(args)
    if args.command == "probe":
        return probe(args)
    if args.command == "forecast":
        if args.auto_approve and not args.upstream:
            parser.error("--auto-approve requires --upstream")
        return forecast(args)
    if args.command == "approve":
        return approve(args)
    if args.command == "run":
        return execute_main(run_root_arg(args.run_root),args.upstream)
    if args.command == "publish":
        publish(run_root_arg(args.run_root))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
