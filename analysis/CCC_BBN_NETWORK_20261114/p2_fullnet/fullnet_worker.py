"""Isolated P2_FULLNET PRIMAT worker.

The parent orchestrator owns wall/RSS limits and records process receipts.
This worker runs standard S0 only; it never applies the S1 clock adapter.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pickle
import platform
import resource
import subprocess
import sys
import time

PIN = "6f7e5680614fb119d65a6c9c65a292240b27c61e"
WEAK = {
    "nTOp_7e3af87bd0404e0a.txt": "f5111a85112e94a237ed73f28ef860876ee0f8ed",
    "nTOp_thermal_cfdb4d324bb5651f.txt": "e3a8b6782393df73a9140e05bd3941ff135af2c9",
}


def digest(path):
    data = Path(path).read_bytes()
    return {
        "sha256": hashlib.sha256(data).hexdigest(),
        "git_blob_sha": hashlib.sha1(
            b"blob " + str(len(data)).encode() + b"\0" + data
        ).hexdigest(),
        "bytes": len(data),
    }


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False,
                   default=lambda x: x.item() if hasattr(x, "item") else str(x))
        + "\n",
        encoding="utf-8",
    )


def cache_snapshot(root):
    root = Path(root)
    return {
        str(p.relative_to(root)): digest(p)
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--upstream", required=True, type=Path)
    ap.add_argument("--config", required=True, type=Path)
    ap.add_argument("--cache", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--run-id", required=True)
    args = ap.parse_args()

    started = time.monotonic()
    upstream = args.upstream.resolve()
    config_path = args.config.resolve()
    cache = args.cache.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    cache.mkdir(parents=True, exist_ok=True)

    head = subprocess.check_output(
        ["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True
    ).strip()
    tree = subprocess.check_output(
        ["git", "-C", str(upstream), "rev-parse", "HEAD^{tree}"], text=True
    ).strip()
    dirty = subprocess.check_output(
        ["git", "-C", str(upstream), "status", "--porcelain", "--untracked-files=no"],
        text=True,
    ).strip()
    if head != PIN or dirty:
        raise RuntimeError("PRIMAT upstream pin mismatch or tracked source modifications")

    sys.path.insert(0, str(upstream))
    import numpy as np
    import scipy
    from threadpoolctl import threadpool_info
    from primat.config import PRIMATConfig, DEFAULT_PARAMS
    from primat.cache_utils import fingerprint_hash, resolve_cache_file
    from primat.weak_rates.cache import weak_rate_fingerprint, thermal_fingerprint
    import primat.weak_rates.api as weak_api
    import primat.weak_rates.corrections as corrections
    import primat.nuclear_network as nuclear_module
    from primat.main import PRIMAT

    params = json.loads(config_path.read_text(encoding="utf-8"))
    if params.get("network") != "large" or params.get("amax") not in (None, 0):
        raise RuntimeError("P2 profile must resolve to network=large with no amax filter")
    params.pop("amax", None)
    params.update({
        "cache_dir": str(cache),
        "data_dir": None,
        "user_nuclear_dir": None,
        "weak_rate_cache": True,
        "decay_era": False,
        "verbose": True,
        "output_time_evolution": False,
        "output_final_result": False,
        "output_decay_evolution": False,
    })
    cfg = PRIMATConfig(params)

    weak_hash = fingerprint_hash(weak_rate_fingerprint(cfg))
    thermal_hash = fingerprint_hash(thermal_fingerprint(cfg))
    cache_names = [
        "nTOp_" + weak_hash + ".txt",
        "nTOp_thermal_" + thermal_hash + ".txt",
    ]
    cache_sources = {}
    for name in cache_names:
        resolved = Path(resolve_cache_file(cfg, "weak", name)).resolve()
        if name not in WEAK:
            dump(out / "REJECTION.json", {
                "status": "CACHE_FINGERPRINT_MISMATCH",
                "computed_name": name,
                "expected_names": sorted(WEAK),
                "weak_hash": weak_hash,
                "thermal_hash": thermal_hash,
            })
            raise RuntimeError("P2 config changed frozen weak-cache fingerprint")
        if not resolved.is_file():
            dump(out / "REJECTION.json", {
                "status": "FROZEN_CACHE_MISSING",
                "name": name,
                "resolved_path": str(resolved),
            })
            raise RuntimeError("Required frozen upstream weak cache is unavailable")
        info = digest(resolved)
        if info["git_blob_sha"] != WEAK[name]:
            dump(out / "REJECTION.json", {
                "status": "FROZEN_CACHE_CONTENT_MISMATCH",
                "name": name,
                "resolved_path": str(resolved),
                "actual": info,
                "expected_git_blob_sha": WEAK[name],
            })
            raise RuntimeError("Frozen weak cache content differs from approved upstream")
        cache_sources[name] = {"resolved_path": str(resolved), **info}

    def forbid_weak_recompute(*_a, **_kw):
        raise RuntimeError("P2_FULLNET strictly forbids weak-cache regeneration")

    weak_api.ComputeWeakRates = forbid_weak_recompute
    corrections._L_CCRTh_compute = forbid_weak_recompute

    load_events = []
    original_loadtxt = np.loadtxt

    def traced_loadtxt(fname, *a, **kw):
        if isinstance(fname, (str, Path)):
            candidate = Path(fname).resolve()
            if candidate.is_file() and (
                "cache_plasma_weak" in str(candidate) or str(cache) in str(candidate)
            ):
                load_events.append({"path": str(candidate), **digest(candidate)})
        return original_loadtxt(fname, *a, **kw)

    np.loadtxt = traced_loadtxt
    cache_before = cache_snapshot(cache)

    source_dir = Path(__file__).resolve().parent
    frozen_files = [
        source_dir / "PROFILE.json",
        source_dir / "PROVENANCE.json",
        source_dir / "fullnet_worker.py",
        source_dir / "fullnet_orchestrator.py",
        source_dir / "run_fullnet.sh",
        config_path,
    ]
    manifest = {
        "schema": "vm-lab-p2-execution-manifest-v1",
        "run_id": args.run_id,
        "upstream_commit": head,
        "upstream_tree": tree,
        "network": {
            "launcher_profile": "full_59_427",
            "primat_network": cfg.network,
            "amax": None,
            "expected_LT_species": 59,
            "expected_LT_total_channels_including_weak": 428,
        },
        "mode": "S0_STANDARD_BBN",
        "config": params,
        "resolved_defaults": {k: getattr(cfg, k) for k in DEFAULT_PARAMS},
        "cache_fingerprints": {
            "weak": weak_hash,
            "thermal": thermal_hash,
            "resolved_files": cache_sources,
        },
        "cache_before": cache_before,
        "cache_overlay": str(cache),
        "frozen_vm_lab_files": {
            str(p.relative_to(source_dir)): digest(p)
            for p in frozen_files if p.is_file()
        },
        "environment": {
            "python": sys.version,
            "python_executable": sys.executable,
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "platform": platform.platform(),
            "affinity": sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
            "threadpools": threadpool_info(),
            "pid": os.getpid(),
        },
        "reference_comparison": "NOT_APPLICABLE_P1_REFERENCE_IS_LARGE_AMAX_8",
        "scientific_acceptance": False,
    }
    dump(out / "S0_EXECUTION_MANIFEST.json", manifest)

    solver_objects = []
    original_solve_ivp = nuclear_module.solve_ivp

    def capture_solve_ivp(fun, t_span, y0, *a, **kw):
        kw["dense_output"] = True
        sol = original_solve_ivp(fun, t_span, y0, *a, **kw)
        solver_objects.append(sol)
        return sol

    nuclear_module.solve_ivp = capture_solve_ivp
    init_started = time.monotonic()
    run = PRIMAT(params)
    init_seconds = time.monotonic() - init_started

    solve_started = time.monotonic()
    result = run.solve(progress=False)
    solve_seconds = time.monotonic() - solve_started

    if len(solver_objects) != 3:
        raise RuntimeError("Expected exactly HT/MT/LT solver integrations")
    if not all(sol.success for sol in solver_objects):
        raise RuntimeError("One or more PRIMAT era integrations did not succeed")

    lt_species = list(run.nucl._lt_net.species)
    lt_channels = len(run.nucl._lt_net.names)
    if len(lt_species) != 59 or len(set(lt_species)) != 59 or lt_channels != 428:
        raise RuntimeError(
            f"Loaded network mismatch: species={len(lt_species)}, channels={lt_channels}"
        )

    loaded_paths = {event["path"] for event in load_events}
    expected_paths = {v["resolved_path"] for v in cache_sources.values()}
    if not expected_paths.issubset(loaded_paths):
        raise RuntimeError("Expected frozen weak tables were not observed being loaded")

    phase_species = [
        ["n", "p"],
        list(run.nucl._mt_net.species),
        lt_species,
    ]
    eras, traces = [], []
    for era, sol, species in zip(("HT", "MT", "LT"), solver_objects, phase_species):
        temperatures = np.geomspace(
            float(run.background.T_of_t(sol.t[0])),
            float(run.background.T_of_t(sol.t[-1])),
            401,
        )
        times = np.asarray(run.background.t_of_T(temperatures))
        times[0], times[-1] = sol.t[0], sol.t[-1]
        values = np.asarray(sol.sol(times))
        weights = np.asarray([sum(cfg.Nuclides[name]) for name in species])
        eras.append({
            "era": era,
            "success": bool(sol.success),
            "status": int(sol.status),
            "message": str(sol.message),
            "nfev": int(sol.nfev),
            "njev": int(sol.njev),
            "nlu": int(sol.nlu),
            "steps": int(len(sol.t)),
            "raw_min": float(np.min(sol.y)),
            "max_baryon_residual": float(np.max(np.abs(weights @ sol.y - 1.0))),
            "species_count": len(species),
            "species": species,
        })
        traces.append({
            "era": era,
            "species": species,
            "T_MeV": temperatures.tolist(),
            "t_seconds": times.tolist(),
            "Y": values.T.tolist(),
        })

    final = {str(k): float(v) for k, v in dict(run.nuclear.Y_final).items()}
    final_finite = all(np.isfinite(float(v)) for v in final.values())
    lt_raw_final = np.asarray(solver_objects[-1].y[:, -1], dtype=float)
    if len(lt_raw_final) != len(lt_species) or set(final) != set(lt_species):
        raise RuntimeError("LT raw solver state and Y_final species do not align")
    raw_final_by_species = {
        name: float(value) for name, value in zip(lt_species, lt_raw_final)
    }
    clamp_delta = {
        name: float(final[name] - raw_final_by_species[name]) for name in lt_species
    }
    changed_by_postprocessing = [
        name for name, delta in clamp_delta.items() if delta != 0.0
    ]
    clamp_checks = {
        "raw_global_min": float(min(np.min(sol.y) for sol in solver_objects)),
        "raw_LT_final_min": float(np.min(lt_raw_final)),
        "postprocessed_Y_final_min": float(min(final.values())),
        "max_abs_Y_final_minus_raw_LT": float(max(abs(v) for v in clamp_delta.values())),
        "postprocessed_species_changed": changed_by_postprocessing,
        "postprocess_delta_by_species": clamp_delta,
        "final_abundances_finite": final_finite,
        "final_abundances_nonnegative": all(v >= 0.0 for v in final.values()),
        "interpretation": "diagnostic only; raw values are preserved, no local clamp is applied by this worker",
    }
    final_mass_residual = abs(sum(
        sum(cfg.Nuclides[name]) * float(value) for name, value in final.items()
    ) - 1.0)
    result_clean = {}
    for key, value in result.items():
        if isinstance(value, np.generic):
            value = value.item()
        if isinstance(value, (str, int, float, bool)) or value is None:
            result_clean[key] = value
        elif isinstance(value, dict):
            result_clean[key] = {
                str(k): (v.item() if isinstance(v, np.generic) else v)
                for k, v in value.items()
            }
        else:
            result_clean[key] = str(value)
    result_clean["Y_final"] = {str(k): float(v) for k, v in final.items()}

    cache_after = cache_snapshot(cache)
    changed_weak = []
    for name, old in cache_sources.items():
        if digest(old["resolved_path"])["sha256"] != old["sha256"]:
            changed_weak.append(name)
    new_cache_files = sorted(set(cache_after) - set(cache_before))
    unexpected_new = [
        name for name in new_cache_files
        if not (
            name.startswith("plasma/electron_thermo_")
            and name.endswith(".txt")
        )
    ]

    checks = {
        "three_eras_present": [e["era"] for e in eras] == ["HT", "MT", "LT"],
        "three_solver_successes": len(solver_objects) == 3 and all(s.success for s in solver_objects),
        "LT_has_59_distinct_species": len(lt_species) == 59 and len(set(lt_species)) == 59,
        "LT_has_428_channels_including_weak": lt_channels == 428,
        "all_final_abundances_finite": final_finite,
        "final_baryon_residual": final_mass_residual,
        "final_baryon_pass": final_mass_residual <= 1e-10,
        "raw_baryon_pass": all(e["max_baryon_residual"] <= 1e-10 for e in eras),
        "raw_positivity_pass": all(e["raw_min"] >= -1e-12 for e in eras),
        "two_frozen_weak_cache_files_loaded": expected_paths.issubset(loaded_paths),
        "weak_cache_unchanged": not changed_weak,
        "no_unexpected_new_cache_files": not unexpected_new,
    }
    engineering_pass = all(
        value is True
        for key, value in checks.items()
        if key not in ("final_baryon_residual",)
    )
    engineering_pass = engineering_pass and checks["final_baryon_pass"]

    report = {
        "schema": "vm-lab-p2-result-v1",
        "run_id": args.run_id,
        "status": "ENGINEERING_PASS" if engineering_pass else "ENGINEERING_GATE_FAILED",
        "result": result_clean,
        "checks": checks,
        "eras": eras,
        "cache_load_events": load_events,
        "cache_before": cache_before,
        "cache_after": cache_after,
        "new_cache_files": new_cache_files,
        "unexpected_new_cache_files": unexpected_new,
        "timing": {
            "initialization_seconds": init_seconds,
            "solve_seconds": solve_seconds,
            "worker_wall_seconds": time.monotonic() - started,
            "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0,
        },
        "scientific_acceptance": False,
        "physics_failure_inference": "NOT_MADE",
    }

    # This snapshot is written only after the solver has completed all eras.
    # It is not a resumable checkpoint for a killed/incomplete solve.
    with (out / "SOLVER_CHECKPOINT.pkl").open("wb") as stream:
        pickle.dump({
            "solver_objects": solver_objects,
            "result": result_clean,
            "Y_final": final,
            "Nuclides": cfg.Nuclides,
            "cache_load_events": load_events,
        }, stream, protocol=pickle.HIGHEST_PROTOCOL)

    raw_arrays = {}
    for era, sol, species in zip(("HT", "MT", "LT"), solver_objects, phase_species):
        raw_arrays[f"{era}_t_seconds"] = np.asarray(sol.t, dtype=float)
        raw_arrays[f"{era}_Y"] = np.asarray(sol.y, dtype=float)
        raw_arrays[f"{era}_species"] = np.asarray(species, dtype="U")
    np.savez_compressed(out / "RAW_SOLVER.npz", **raw_arrays)
    report["clamp_checks"] = clamp_checks
    dump(out / "RESULT.json", report)
    dump(out / "TRACE.json", {
        "convention": "HT/MT/LT dense traces; no interpolation across era boundaries",
        "eras": traces,
    })
    print(json.dumps({
        "run_id": args.run_id,
        "status": report["status"],
        "YPBBN": result_clean.get("YPBBN"),
        "DoH": result_clean.get("DoH"),
        **report["timing"],
    }), flush=True)

    if not engineering_pass:
        raise RuntimeError("P2 engineering gate failed; evidence retained")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
