#!/usr/bin/env python3
"""Bounded infrastructure probe, not a scientific experiment or model smoke.

No package installs, network, credentials, host-home access or existing-file edits.
Run through VM Compute from a fixed GitHub source, outputs in a fresh job directory.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import resource
import shutil
import signal
import statistics
import subprocess
import sys
import threading
import time

THREAD_KEYS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
               "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "BLIS_NUM_THREADS")


def read_optional(path):
    try:
        return Path(path).read_text().strip()
    except (OSError, PermissionError) as exc:
        return {"unavailable": type(exc).__name__}


def dump(path, data):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def timer(call, repeats):
    values = []
    result = None
    for _ in range(repeats):
        start = time.perf_counter()
        result = call()
        values.append(time.perf_counter() - start)
    return {"samples_s": values, "median_s": statistics.median(values)}, result


def numerical_worker():
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (35, 36))
    started = time.perf_counter()
    import numpy as np
    import_seconds = time.perf_counter() - started
    result = {"numpy_import_s": import_seconds,
              "requested_threads": {key: os.environ.get(key) for key in THREAD_KEYS},
              "numpy_version": np.__version__, "kernels": {}}
    try:
        from threadpoolctl import threadpool_info
        result["threadpools"] = threadpool_info()
    except ImportError:
        import contextlib
        import io
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            np.show_config()
        result["threadpools"] = {"unavailable": "threadpoolctl not installed",
                               "numpy_build_config": buffer.getvalue()}
    rng = np.random.default_rng(20261107)
    for size in (69, 133):
        # 69 = largest current candidate matrix; 133 = declared scaling probe.
        raw = rng.normal(size=(size, size)) + 1j*rng.normal(size=(size, size))
        h = (raw + raw.conj().T) / (2*np.sqrt(size))
        values, vectors = np.linalg.eigh(h)  # warm-up, explicitly outside timings
        eig_time, eig_result = timer(lambda: np.linalg.eigh(h), 5)
        values, vectors = eig_result
        residual = np.linalg.norm(h@vectors - vectors*values) / np.linalg.norm(h)
        psi = rng.normal(size=size) + 1j*rng.normal(size=size)
        psi /= np.linalg.norm(psi)
        rho = np.outer(psi, psi.conj())

        def evolve_and_check():
            u = (vectors*np.exp(-1j*values*0.2)) @ vectors.conj().T
            evolved = u @ rho @ u.conj().T
            minimum = float(np.linalg.eigvalsh(evolved).min())
            return float(abs(np.trace(evolved)-1)), minimum

        evolve_and_check()
        kernel_time, validity = timer(evolve_and_check, 10)
        if residual > 1e-10 or validity[0] > 1e-10 or validity[1] < -1e-10:
            raise ArithmeticError("numerical residual failed")
        result["kernels"][str(size)] = {
            "dtype": "complex128", "eigh": eig_time,
            "evolution_plus_psd_check": kernel_time,
            "relative_eigen_residual": float(residual),
            "trace_error": validity[0], "minimum_eigenvalue": validity[1]}
    source = np.ones(8*1024*1024, dtype=np.float64)
    destination = np.empty_like(source)
    np.copyto(destination, source)
    copy_time, _ = timer(lambda: np.copyto(destination, source), 5)
    result["warm_copy_64_mib"] = dict(copy_time,
        useful_gib_per_s=(source.nbytes/1024**3)/copy_time["median_s"],
        interpretation="warm NumPy copy, not a physical DRAM bandwidth claim")
    if not np.array_equal(source, destination):
        raise ArithmeticError("copy mismatch")
    record = {"real": rho.real.tolist(), "imag": rho.imag.tolist()}
    json_time, encoded = timer(lambda: json.dumps(record, separators=(",", ":")), 10)
    decode_time, _ = timer(lambda: json.loads(encoded), 10)
    result["matrix_json"] = {"dimension": 133, "bytes": len(encoded.encode()),
                             "encode": json_time, "decode": decode_time}
    result["process_status"] = {line.split(":", 1)[0]: line.split(":", 1)[1].strip()
        for line in Path("/proc/self/status").read_text().splitlines()
        if line.startswith(("Threads:", "VmRSS:", "VmHWM:", "Cpus_allowed_list:"))}
    result["peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    result["total_s"] = time.perf_counter() - started
    print(json.dumps(result, allow_nan=False), flush=True)


def environment():
    versions = {}
    for name in ("numpy", "scipy", "sympy", "matplotlib", "threadpoolctl"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    cpuinfo = read_optional("/proc/cpuinfo")
    cpu_model = next((line.split(":", 1)[1].strip() for line in cpuinfo.splitlines()
                      if line.startswith("model name")), None) if isinstance(cpuinfo, str) else cpuinfo
    cgroups = {}
    # Job-visible root plus its own v2 group, never enumerate the host hierarchy.
    own_group = read_optional("/proc/self/cgroup")
    roots = [Path("/sys/fs/cgroup")]
    if isinstance(own_group, str):
        for line in own_group.splitlines():
            if line.startswith("0::") and ".." not in Path(line[3:]).parts:
                group = Path("/sys/fs/cgroup") / line[3:].lstrip("/")
                if group not in roots:
                    roots.append(group)
    for root in roots:
        cgroups[str(root)] = {name: read_optional(root/name) for name in
            ("cpu.max", "cpu.stat", "cpuset.cpus.effective", "memory.max", "memory.current", "pids.max")}
    meminfo = read_optional("/proc/meminfo")
    selected_memory = {line.split(":", 1)[0]: line.split(":", 1)[1].strip()
        for line in meminfo.splitlines() if line.startswith(("MemTotal:", "MemAvailable:", "SwapTotal:", "SwapFree:"))} if isinstance(meminfo, str) else meminfo
    return {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "platform": platform.platform(), "architecture": platform.machine(),
        "python": sys.version, "cpu_model": cpu_model, "cpu_count": os.cpu_count(),
        "affinity": sorted(os.sched_getaffinity(0)), "load_average": os.getloadavg(),
        "visible_memory": selected_memory, "cgroups": cgroups,
        "inherited_rlimits": {name: resource.getrlimit(getattr(resource, name)) for name in
            ("RLIMIT_AS", "RLIMIT_CPU", "RLIMIT_FSIZE", "RLIMIT_NOFILE")},
        "packages": versions, "thread_environment": {key: os.environ.get(key) for key in THREAD_KEYS},
        "disk": dict(zip(("total_bytes", "used_bytes", "free_bytes"), shutil.disk_usage(".")))}


def io_probe():
    start = time.perf_counter()
    root = Path("io_probe_owned")
    root.mkdir(exist_ok=False)
    block = os.urandom(1024**2)
    path = root/"stream.bin"
    expected = hashlib.sha256()
    write_start = time.perf_counter()
    with path.open("wb") as stream:
        for _ in range(32):
            stream.write(block)
            expected.update(block)
        stream.flush()
        os.fsync(stream.fileno())
    write_s = time.perf_counter() - write_start
    read_start = time.perf_counter()
    observed = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024**2):
            observed.update(chunk)
    read_s = time.perf_counter() - read_start
    if observed.digest() != expected.digest():
        raise ArithmeticError("disk checksum mismatch")
    times = []
    for i in range(100):
        before = time.perf_counter()
        dump(root/"checkpoint.json", {"cursor": i, "padding": "x"*32768})
        times.append(time.perf_counter()-before)
    # Uncommitted replacement must leave the last complete snapshot readable.
    (root/"checkpoint.json.tmp").write_text('{"cursor":100')
    preserved = json.loads((root/"checkpoint.json").read_text())["cursor"] == 99
    if not preserved:
        raise ArithmeticError("uncommitted checkpoint replaced the durable file")
    result = {"bytes": 32*1024**2, "write_fsync_sha256_s": write_s,
        "write_mib_per_s": 32/write_s, "warm_read_sha256_s": read_s,
        "warm_read_mib_per_s": 32/read_s, "checksum_ok": True,
        "atomic_checkpoint_32k_100_replacements": {"median_s": statistics.median(times),
            "max_s": max(times), "total_s": sum(times)},
        "uncommitted_snapshot_preserves_previous": preserved,
        "power_loss_durability": "not tested", "total_s": time.perf_counter()-start}
    shutil.rmtree(root)  # only this job's newly created probe data
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--source-commit")
    args = parser.parse_args()
    if args.worker:
        numerical_worker()
        return
    if not args.source_commit or len(args.source_commit) != 40:
        raise ValueError("fixed source commit required")
    started = time.perf_counter()
    # Process-group watchdog remains active even while NumPy is blocked in a child.
    active = []
    def deadline():
        for process in active:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        os._exit(124)
    watchdog = threading.Timer(120, deadline)
    watchdog.daemon = True
    watchdog.start()
    report = {"schema": 1, "kind": "ENVIRONMENT_PROBE_NOT_SCIENTIFIC_RUN",
              "source_commit": args.source_commit,
              "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "environment_before": environment(), "workers": {}, "status": "RUNNING"}
    dump("ENVIRONMENT.json", report)
    try:
        for threads in (1, 7):
            env = dict(os.environ)
            env.update({key: str(threads) for key in THREAD_KEYS})
            before = time.perf_counter()
            process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--worker"],
                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
            active.append(process)
            try:
                stdout, stderr = process.communicate(timeout=40)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate()
                raise TimeoutError(f"{threads}-thread numerical worker exceeded 40s")
            if process.returncode:
                raise RuntimeError(f"worker {threads}, returncode {process.returncode}: {stderr[-2000:]}")
            report["workers"][str(threads)] = json.loads(stdout)
            report["workers"][str(threads)]["startup_inclusive_wall_s"] = time.perf_counter()-before
            dump("ENVIRONMENT.json", report)
        cpu_start = time.perf_counter()
        for i in range(100000):
            hashlib.sha256(f"20261107:{i}:node:instrument".encode()).digest()
        report["event_hash_100000_s"] = time.perf_counter()-cpu_start
        report["io"] = io_probe()
        report["status"] = "COMPLETED"
    except Exception as exc:
        report["status"] = "FAILED"
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
    report["environment_after"] = environment()
    report["wall_s"] = time.perf_counter()-started
    report["parent_peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    dump("ENVIRONMENT.json", report)
    watchdog.cancel()
    print(json.dumps({key: report[key] for key in ("status", "wall_s", "source_commit", "source_sha256")}), flush=True)
    if report["status"] != "COMPLETED":
        sys.exit(1)


if __name__ == "__main__":
    main()
