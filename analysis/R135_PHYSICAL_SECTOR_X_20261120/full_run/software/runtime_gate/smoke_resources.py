#!/usr/bin/env python3
"""Measure a fixed diagnostic smoke; no physical R135 or ensemble mixing run.

Linux /proc is used to sample simultaneous process-group RSS/PSS. This is a
resource measurement of the running machine, not a remote-runner forecast.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import resource
import shutil
import subprocess
import sys
import time

SOFTWARE = Path(__file__).resolve().parents[1]
REPO = SOFTWARE.parents[3]


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def optional(path):
    try:
        return Path(path).read_text().strip()
    except (OSError, PermissionError):
        return None


def environment():
    mem = dict(line.split(":", 1) for line in (optional("/proc/meminfo") or "").splitlines())
    cpu = next((line.split(":", 1)[1].strip() for line in (optional("/proc/cpuinfo") or "").splitlines()
                if line.startswith("model name")), None)
    usage = shutil.disk_usage(Path.cwd())
    return {"platform": platform.platform(), "observer_python": platform.python_version(),
            "cpu_model": cpu, "visible_cpus": os.cpu_count(),
            "affinity": sorted(os.sched_getaffinity(0)),
            "mem_total_bytes": int(mem["MemTotal"].split()[0])*1024 if "MemTotal" in mem else None,
            "mem_available_bytes": int(mem["MemAvailable"].split()[0])*1024 if "MemAvailable" in mem else None,
            "cgroup_root_files": {key: optional("/sys/fs/cgroup/"+key)
                                  for key in ("cpu.max", "memory.max", "memory.current", "cpuset.cpus.effective")},
            "free_disk_bytes": usage.free,
            "limitation": "Visible resources are not a guaranteed CPU or memory quota; unavailable limits remain null."}


def group_memory(pgid):
    rss = pss = high = count = 0
    pss_complete = True
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            fields = (proc/"stat").read_text().rsplit(")", 1)[1].split()
            if int(fields[2]) != pgid:
                continue
            data = {}
            for line in (proc/"status").read_text().splitlines():
                if line.startswith(("VmRSS:", "VmHWM:")):
                    key, value = line.split(":", 1)
                    data[key] = int(value.split()[0])*1024
            rss += data.get("VmRSS", 0)
            high = max(high, data.get("VmHWM", 0))
            count += 1
            rollup = optional(proc/"smaps_rollup")
            match = next((line for line in (rollup or "").splitlines() if line.startswith("Pss:")), None)
            if match is None:
                pss_complete = False
            else:
                pss += int(match.split()[1])*1024
        except (OSError, ValueError, IndexError):
            continue  # A process may disappear between samples.
    return {"rss_bytes": rss, "pss_bytes": pss if pss_complete and count else None,
            "largest_process_hwm_bytes": high, "live_processes": count}


def measured_command(name, command, out, env, interval):
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    peak_rss = peak_pss = hwm = peak_processes = samples = pss_samples = 0
    start = time.monotonic()
    with (out/(name+".log")).open("w") as log, (out/(name+".memory.jsonl")).open("w") as trace:
        process = subprocess.Popen(command, cwd=REPO, env=env, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        while True:
            sample = group_memory(process.pid)
            sample["seconds"] = time.monotonic()-start
            trace.write(json.dumps(sample)+"\n")
            peak_rss = max(peak_rss, sample["rss_bytes"])
            hwm = max(hwm, sample["largest_process_hwm_bytes"])
            peak_processes = max(peak_processes, sample["live_processes"])
            samples += 1
            if sample["pss_bytes"] is not None:
                peak_pss = max(peak_pss, sample["pss_bytes"])
                pss_samples += 1
            if process.poll() is not None:
                break
            time.sleep(interval)
        code = process.wait()
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    return {"phase": name, "command": command, "exit_code": code,
            "wall_seconds": time.monotonic()-start,
            "cpu_user_seconds": after.ru_utime-before.ru_utime,
            "cpu_system_seconds": after.ru_stime-before.ru_stime,
            "sampled_group_peak_rss_bytes": peak_rss,
            "sampled_group_peak_pss_bytes": peak_pss if pss_samples else None,
            "largest_observed_process_hwm_bytes": hwm,
            "max_live_processes": peak_processes, "memory_samples": samples,
            "complete_pss_samples": pss_samples,
            "log_sha256": sha(out/(name+".log")),
            "memory_trace_sha256": sha(out/(name+".memory.jsonl"))}


def lattice_worker(out):
    sys.path.insert(0, str(SOFTWARE))
    import numpy as np
    from r135 import lattice
    out.mkdir(parents=True)
    started = time.monotonic()
    chain = lattice.WilsonChain((4, 8, 8, 8), 5.69275, 1359101, "cold")
    t = time.monotonic()
    chain.sweep(2)
    sweep_seconds = time.monotonic()-t
    t = time.monotonic()
    row = lattice.measure(chain.links, chain_id="resource-smoke", config_id="resource-smoke:2",
                          sweep=2, role="calibration", beta=chain.beta, seed=chain.seed,
                          start="cold", verify_gauge=True)
    measure_seconds = time.monotonic()-t
    t = time.monotonic()
    path = chain.checkpoint(out, "two-sweeps")
    checkpoint_seconds = time.monotonic()-t
    t = time.monotonic()
    resumed = lattice.WilsonChain.resume(path)
    assert np.array_equal(chain.links, resumed.links)
    assert chain.rng.bit_generator.state == resumed.rng.bit_generator.state
    restore_seconds = time.monotonic()-t
    write_json(out/"measurement.json", row)
    write_json(out/"LATTICE.json", {"scope": "DIAGNOSTIC_RESOURCE_SMOKE", "physical_ensemble": False,
               "geometry": list(chain.geometry), "sweeps": chain.sweeps, "updates": chain.attempted,
               "link_array_bytes": chain.links.nbytes, "sweep_seconds": sweep_seconds,
               "measure_seconds": measure_seconds, "checkpoint_seconds": checkpoint_seconds,
               "restore_seconds": restore_seconds, "elapsed_seconds": time.monotonic()-started,
               "exact_checkpoint_state_match": True, "mixing_or_autocorrelation_estimated": False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path)
    parser.add_argument("--linx-source", type=Path)
    parser.add_argument("--primat-source", type=Path)
    parser.add_argument("--class-source", type=Path)
    parser.add_argument("--planck-root", type=Path)
    parser.add_argument("--planck-python", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--sample-interval", type=float, default=.05)
    parser.add_argument("--lattice-worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.lattice_worker:
        lattice_worker(args.out)
        return 0
    if not 0 < args.sample_interval <= 1:
        parser.error("memory sample interval must be between 0 and 1 second")
    for key in ("python", "linx_source", "primat_source", "class_source", "planck_root", "planck_python"):
        if getattr(args, key) is None:
            parser.error("missing --"+key.replace("_", "-"))
    out = args.out.absolute()
    if out.exists():
        parser.error("use a new output directory; prior evidence is preserved")
    out.mkdir(parents=True)
    env = {**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "2",
           "JAX_PLATFORMS": "cpu", "JAX_ENABLE_X64": "true",
           "PYTHONPATH": os.pathsep.join((str(args.linx_source.absolute()), str(args.primat_source.absolute())))}
    py = str(args.python.absolute())
    version_cmd = [py, "-c", "import json,platform,importlib.metadata as m; print(json.dumps({'python':platform.python_version(),'packages':{p:m.version(p) for p in ['numpy','scipy','jax','jaxlib','diffrax']}}))"]
    numerical_environment = json.loads(subprocess.check_output(version_cmd, env=env, text=True))
    source_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    file_set = list((SOFTWARE/"r135").glob("*.py")) + [SOFTWARE/"p0_register.py", SOFTWARE/"r135_stage.py", SOFTWARE/"backend/validate_native.py", Path(__file__)]
    source = {str(p.relative_to(REPO)): sha(p) for p in file_set}
    result = {"schema": "R135-smoke-resources-v1", "scope": "DIAGNOSTIC_SOFTWARE_RESOURCE_SMOKE",
              "physical_R135_run": False, "production_ensemble_calibration": False,
              "timestamp_utc": datetime.now(timezone.utc).isoformat(),
              "base_execution_commit": source_sha, "source_sha256": source,
              "environment": environment(), "numerical_environment": numerical_environment,
              "thread_settings": {k:env[k] for k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "JAX_PLATFORMS", "JAX_ENABLE_X64")},
              "measurement": {"interval_seconds": args.sample_interval,
                  "group": "fresh process group per sequential phase, excluding the observer",
                  "rss": "sum of simultaneously live process RSS; shared pages can be counted more than once",
                  "pss": "sum of live process PSS when all smaps_rollup readings succeed",
                  "limitation": "Sampled peaks may miss shorter transients; HWM is the largest observed individual-process high-water mark, not summed process-group peak.",
                  "host_transfer": "No GitHub runner or production-lattice runtime is inferred from this host.",
                  "cache": "New result directories and processes; installed environments and OS file cache already present. No assertion of cold installation/cache."},
              "phases": []}
    write_json(out/"RESOURCES.json", result)
    cli = str(SOFTWARE/"r135_stage.py")
    phases = [
        ("p0_freeze", [py, str(SOFTWARE/"p0_register.py"), "freeze", "--out", str(out/"P0")]),
        ("p0_verify", [py, str(SOFTWARE/"p0_register.py"), "verify", "--out", str(out/"P0")]),
        ("lattice", [py, str(Path(__file__).resolve()), "--lattice-worker", "--out", str(out/"P3")]),
        ("p7_seal", [py, cli, "--seal", "--stage", "P7", "--config", str(SOFTWARE/"examples/coupled_control.json"), "--template", str(SOFTWARE/"examples/request.coupled.validation.json"), "--out", str(out/"P7.request.json")]),
        ("p7_run", [py, cli, "--stage", "P7", "--request", str(out/"P7.request.json"), "--out", str(out/"P7")]),
        ("p7_verify", [py, cli, "--verify", str(out/"P7")]),
        ("native", [py, str(SOFTWARE/"backend/validate_native.py"), "--class-source", str(args.class_source.absolute()), "--planck-root", str(args.planck_root.absolute()), "--planck-python", str(args.planck_python.absolute()), "--out", str(out/"native")]),
    ]
    started = time.monotonic()
    for label, command in phases:
        row = measured_command(label, command, out, env, args.sample_interval)
        result["phases"].append(row)
        write_json(out/"RESOURCES.json", result)
        print(json.dumps({k: row[k] for k in ("phase", "exit_code", "wall_seconds", "sampled_group_peak_rss_bytes")}), flush=True)
        if row["exit_code"]:
            break
    result["wall_seconds"] = time.monotonic()-started
    result["sampled_peak_rss_bytes"] = max(x["sampled_group_peak_rss_bytes"] for x in result["phases"])
    result["sampled_peak_pss_bytes"] = max((x["sampled_group_peak_pss_bytes"] or 0) for x in result["phases"]) or None
    result["source_unchanged"] = all(sha(REPO/p)==digest for p,digest in source.items())
    result["status"] = "PASS" if len(result["phases"])==len(phases) and all(x["exit_code"]==0 for x in result["phases"]) and result["source_unchanged"] else "FAIL"
    result["output_bytes_before_final_summary"] = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    write_json(out/"RESOURCES.json", result)
    print(json.dumps({k: result[k] for k in ("status", "wall_seconds", "sampled_peak_rss_bytes", "sampled_peak_pss_bytes", "output_bytes_before_final_summary")}), flush=True)
    return 0 if result["status"]=="PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
