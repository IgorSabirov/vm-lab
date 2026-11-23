#!/usr/bin/env python3
"""Execute exactly the two predeclared HYREC step refinements, then summarize.

The original histories, LOCK and SUMMARY are immutable inputs. No fit, physical
parameter change or further adaptive refinement is performed by this script.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time

os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compare(z, lhs, rhs, mask):
    zz, d = z[mask], (lhs - rhs)[mask]
    rel = d / rhs[mask]
    i, j = int(np.argmax(np.abs(d))), int(np.argmax(np.abs(rel)))
    return {
        "points": int(len(zz)),
        "max_abs": float(abs(d[i])), "z_max_abs": float(zz[i]),
        "signed_at_max_abs": float(d[i]),
        "max_abs_relative": float(abs(rel[j])), "z_max_abs_relative": float(zz[j]),
        "min_signed_relative": float(np.min(rel)),
        "max_signed_relative": float(np.max(rel)),
    }


def pair_summary(z, x, t, xref, tref, lock):
    boundary = int(np.flatnonzero(z == 49.0)[0])
    all_nodes = np.ones(len(z), dtype=bool)
    output = {
        "all_nodes": {"xe": compare(z, x, xref, all_nodes),
                      "Tgas_K": compare(z, t, tref, all_nodes)},
        "z_ge_49": {"xe": compare(z, x, xref, z >= 49.0),
                    "Tgas_K": compare(z, t, tref, z >= 49.0)},
        "boundary_z49": {
            "xe_abs": float(x[boundary]-xref[boundary]),
            "xe_relative": float(x[boundary]/xref[boundary]-1.0),
            "Tgas_abs_K": float(t[boundary]-tref[boundary]),
            "Tgas_relative": float(t[boundary]/tref[boundary]-1.0),
        },
        "epochs": [],
    }
    for epoch in lock["epochs"]:
        mask = (z >= epoch["z_min"]) & (z <= epoch["z_max"])
        record = {**epoch, "xe": compare(z, x, xref, mask),
                  "Tgas_K": compare(z, t, tref, mask)}
        clipped = mask & (z >= 49.0)
        if np.any(clipped):
            record["z_ge_49"] = {"xe": compare(z, x, xref, clipped),
                                 "Tgas_K": compare(z, t, tref, clipped)}
        output["epochs"].append(record)
    return output


def write_csv(path, columns):
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns.keys())
        writer.writerows(zip(*columns.values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path,
                        default=Path(__file__).with_name("NUMERICAL_FOLLOWUP.json"))
    parser.add_argument("--camb-root", type=Path, required=True)
    parser.add_argument("--hyrec-root", type=Path, required=True)
    parser.add_argument("--hyrec-library", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path,
                        default=Path(__file__).parent/"results")
    args = parser.parse_args()
    package = args.plan.resolve().parent
    plan = json.loads(args.plan.read_text())
    if plan["new_steps_dlna"] != [0.001, 0.0005] or plan["maximum_new_HYREC_runs"] != 2:
        raise ValueError("This follow-up allows exactly the two predeclared steps")
    if sha256(__file__) != plan["convergence_script_sha256"]:
        raise ValueError("Follow-up script differs from its pre-run declaration")
    for name, expected in plan["input_sha256"].items():
        if sha256(package/name) != expected:
            raise ValueError(f"Immutable input changed: {name}")
    if sha256(args.hyrec_library) != plan["HYREC_library_sha256"]:
        raise ValueError("HYREC library differs from original execution")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.output_dir/"hyrec_additional_steps.csv"
    result_path = args.output_dir/"CONVERGENCE.json"
    if csv_path.exists() or result_path.exists():
        raise FileExistsError("Preserve existing follow-up results; use a new output directory for reproduction")

    sys.path.insert(0, str(args.camb_root.resolve()))
    import recfast_adapter as rf
    from hyrec_adapter import HyrecRunner

    installation = rf.installation_metadata()
    if installation["library_sha256"] != plan["CAMB_baseline_library_sha256"]:
        raise ValueError("Expected the exact compiled_base CAMB library")
    lock = json.loads((package/"LOCK.json").read_text())
    prior = np.genfromtxt(package/"results/histories.csv", names=True, delimiter=",")
    fine = np.genfromtxt(package/"results/recfast_internal_refined.csv", names=True, delimiter=",")
    z = np.ascontiguousarray(prior["z"])
    if len(z) != plan["grid_points"] or not np.array_equal(z, fine["z"]):
        raise ValueError("Reference output grids differ")
    if np.count_nonzero(z == 49.0) != 1:
        raise ValueError("Expected exactly one z=49 output node")
    c = lock["cosmology"]
    params = rf.params_from_cosmology(
        H0=c["H0_km_s_Mpc"], Omega_b=c["Omega_b"], Omega_c=c["Omega_c"],
        Omega_k=c["Omega_k"], Yp=c["Yp_mass_fraction"], Tcmb=c["Tcmb0_K"], Neff=c["N_eff"],
    )
    abundance = rf.abundance_normalization(params)
    for key in ["nH0_cm3", "fHe"]:
        if abundance[key] != lock["composition"][key]:
            raise ValueError("Abundance normalization changed")

    start_utc = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    background = rf.build_background(params)
    background_seconds = time.perf_counter() - started
    h = np.asarray(rf.hubble_s(background, z))
    h_residual = float(np.max(np.abs(h/prior["H_s_inv"]-1)))
    if h_residual >= 2e-14:
        raise ValueError("Repeated CAMB background is not the original shared H(z)")

    solver = HyrecRunner(args.hyrec_root, args.hyrec_library)
    columns = {"z": z, "a": prior["a"], "H_s_inv": h}
    fresh = []
    for step, suffix in zip(plan["new_steps_dlna"], ["0p001", "0p0005"]):
        result = solver.run(
            package/"results/hyrec_input.dat", z, lambda zz: rf.hubble_s(background, zz),
            dlna=step, nH0_override=abundance["nH0_cm3"], fHe_override=abundance["fHe"],
        )
        if result["metadata"]["H_callback_max_relative_roundtrip"] >= 2e-14:
            raise ValueError("Hubble callback round-trip failed")
        for key in ["nH0_cm3", "fHe"]:
            if result["metadata"]["used_"+key] != abundance[key]:
                raise ValueError("HYREC normalization was not applied")
        columns[f"xe_HYREC2_step_{suffix}"] = result["xe"]
        columns[f"Tgas_HYREC2_step_{suffix}_K"] = result["Tm_K"]
        fresh.append((step, result))

    write_csv(csv_path, columns)
    sequence = [
        (0.004, prior["xe_HYREC2"], prior["Tgas_HYREC2_K"]),
        (0.002, prior["xe_HYREC2_halfstep"], prior["Tgas_HYREC2_halfstep_K"]),
        *[(step, result["xe"], result["Tm_K"]) for step, result in fresh],
    ]
    consecutive = []
    for previous, current in zip(sequence[:-1], sequence[1:]):
        consecutive.append({
            "previous_dlna": previous[0], "next_dlna": current[0],
            **pair_summary(z, current[1], current[2], previous[1], previous[2], lock),
        })
    fine_comparisons = [{
        "HYREC_dlna": step, "reference": "RECFAST internal refinement Nz=20000, tol=1e-6",
        **pair_summary(z, x, t, fine["xe"], fine["Tgas_K"], lock),
    } for step, x, t in sequence]
    at = int(np.flatnonzero(z == 49.0)[0])
    lumina = c["Tcmb0_K"] * 50.0**2 / 125.8
    boundary = [{"dlna": step, "xe": float(x[at]), "Tgas_K": float(t[at]),
                 "vs_Lumina_formula_K": float(t[at]-lumina),
                 "vs_Lumina_formula_relative": float(t[at]/lumina-1)}
                for step, x, t in sequence]
    for name, expected in plan["input_sha256"].items():
        if sha256(package/name) != expected:
            raise ValueError(f"Immutable input changed during execution: {name}")
    report = {
        "id": plan["id"], "status": "TWO_PREDECLARED_REFINEMENTS_EXECUTED",
        "scientific_acceptance": False,
        "started_UTC": start_utc, "finished_UTC": datetime.now(timezone.utc).isoformat(),
        "plan_sha256": sha256(args.plan), "input_sha256": plan["input_sha256"],
        "convergence_script_sha256": sha256(__file__),
        "CAMB": installation, "HYREC_library_sha256": sha256(args.hyrec_library),
        "background_repeat_seconds": background_seconds,
        "background_max_relative_change": h_residual,
        "new_HYREC_runs": [{"dlna": step, **result["metadata"]} for step, result in fresh],
        "total_new_HYREC_solver_seconds": sum(result["metadata"]["elapsed_seconds"] for _, result in fresh),
        "new_HYREC_run_count": len(fresh),
        "grid_points": int(len(z)), "same_exact_output_grid": True,
        "boundary_z49": boundary,
        "consecutive_step_changes": consecutive,
        "comparison_to_fine_RECFAST": fine_comparisons,
        "additional_histories_sha256": sha256(csv_path),
        "limitations": [
            "Only two additional step sizes were executed. No extrapolated zero-step limit is asserted.",
            "Changes under refinement measure numerical sensitivity, not a rigorous error bound.",
            "The original LOCK, primary histories and SUMMARY are preserved unchanged.",
        ],
    }
    result_path.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n")
    print(json.dumps({
        "run_count": len(fresh), "background_seconds": background_seconds,
        "new_HYREC_seconds": report["total_new_HYREC_solver_seconds"],
        "boundary_z49": boundary,
        "z_ge_49_step_changes": [{"from": v["previous_dlna"], "to": v["next_dlna"],
                                   **v["z_ge_49"]} for v in consecutive],
    }, allow_nan=False))


if __name__ == "__main__":
    main()
