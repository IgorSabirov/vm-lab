#!/usr/bin/env python3
"""Execute the frozen R143 homogeneous recombination comparison.

Dependencies are explicit CLI inputs. This script never downloads software or
changes solver parameters in response to a numerical result.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time

os.environ.setdefault("OMP_NUM_THREADS", "1")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_csv(path, columns):
    names = list(columns)
    with Path(path).open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(names)
        writer.writerows(zip(*(columns[name] for name in names)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=Path(__file__).with_name("LOCK.json"))
    parser.add_argument("--camb-root", type=Path, help="Directory containing the pinned camb package")
    parser.add_argument("--hyrec-root", type=Path)
    parser.add_argument("--hyrec-library", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--mode", choices=["pair", "recfast-control"], default="pair")
    parser.add_argument("--control-name", default="recfast_internal_refined")
    parser.add_argument("--build-receipt", type=Path,
                        help="Source/build receipt for the explicitly selected CAMB library")
    args = parser.parse_args()
    if args.camb_root:
        sys.path.insert(0, str(args.camb_root.resolve()))
    import numpy as np
    import recfast_adapter as rf

    lock = json.loads(args.lock.read_text())
    c, grid = lock["cosmology"], lock["grid"]
    z = np.unique(np.r_[np.geomspace(1+grid["z_min"], 1+grid["z_max"],
                                    grid["log1pz_points"])-1,
                        grid["landmarks"]])
    z[0], z[-1] = grid["z_min"], grid["z_max"]
    assert np.count_nonzero(z == grid["boundary_z"]) == 1
    inputs = dict(H0=c["H0_km_s_Mpc"], Omega_b=c["Omega_b"],
                  Omega_c=c["Omega_c"], Omega_k=c["Omega_k"],
                  Yp=c["Yp_mass_fraction"], Tcmb=c["Tcmb0_K"], Neff=c["N_eff"])
    params = rf.params_from_cosmology(**inputs)
    abundance = rf.abundance_normalization(params)
    for key in ("nH0_cm3", "fHe"):
        assert np.isclose(abundance[key], lock["composition"][key], rtol=2e-14, atol=0)

    started_utc = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    data = rf.build_background(params)
    thermal = rf.sample_history(data, z)
    recfast_seconds = time.perf_counter() - started
    args.output_dir.mkdir(parents=True, exist_ok=True)
    receipt = {
        "started_UTC": started_utc,
        "lock_sha256": digest(args.lock),
        "python": sys.version, "platform": platform.platform(),
        "OMP_NUM_THREADS": os.environ["OMP_NUM_THREADS"],
        "CAMB": rf.installation_metadata(), "composition": abundance,
        "RECFAST_seconds": recfast_seconds,
        "grid_points": len(z), "z_range": [float(z[0]), float(z[-1])],
        "inputs": inputs,
        "CAMB_background_Omega": {name: float(data.get_Omega(name)) for name in
                                   ["baryon", "cdm", "photon", "neutrino", "de"]},
        "code_sha256": {name: digest(Path(__file__).with_name(name)) for name in
                        ["experiment.py", "recfast_adapter.py", "hyrec_adapter.py", "hyrec_adapter.c"]},
    }
    if args.build_receipt:
        receipt["build_receipt"] = json.loads(args.build_receipt.read_text())
        receipt["build_receipt_sha256"] = digest(args.build_receipt)
    (args.output_dir / (args.control_name + "_CAMB_params.txt"
                       if args.mode == "recfast-control" else "CAMB_params.txt")).write_text(str(params))
    if args.mode == "recfast-control":
        name = args.control_name
        write_csv(args.output_dir / f"{name}.csv", {
            "z": z, "a": thermal["a"], "xe": thermal["xe"],
            "Tgas_K": thermal["Tm_K"], "H_s_inv": thermal["H_s"],
        })
        (args.output_dir / f"{name}_receipt.json").write_text(
            json.dumps(receipt, indent=2, allow_nan=False)+"\n")
        print(json.dumps({"run": name, "seconds": recfast_seconds,
                          "grid_points": len(z)}, allow_nan=False))
        return

    if not args.hyrec_root or not args.hyrec_library:
        parser.error("pair mode requires --hyrec-root and --hyrec-library")
    from hyrec_adapter import HyrecRunner, write_input
    parameter_file = args.output_dir / "hyrec_input.dat"
    write_input(parameter_file, H0=c["H0_km_s_Mpc"], Tcmb0=c["Tcmb0_K"],
                Omega_b=c["Omega_b"], Omega_cb=c["Omega_m"], Omega_k=c["Omega_k"],
                Yp=c["Yp_mass_fraction"], Neff=c["N_eff"])
    solver = HyrecRunner(args.hyrec_root, args.hyrec_library)
    common_h = lambda value: rf.hubble_s(data, value)
    used = dict(nH0_override=abundance["nH0_cm3"], fHe_override=abundance["fHe"])
    hyrec = solver.run(parameter_file, z, common_h, dlna=0.004, **used)
    half = solver.run(parameter_file, z, common_h, dlna=0.002, **used)
    native = solver.run(parameter_file, z, common_h, dlna=0.004)
    receipt["HYREC"] = {"main": hyrec["metadata"], "half_step": half["metadata"],
                        "native_composition": native["metadata"],
                        "library_sha256": digest(args.hyrec_library)}
    for result in (hyrec, half):
        for key in ("nH0_cm3", "fHe"):
            assert result["metadata"]["used_" + key] == abundance[key]
        assert result["metadata"]["H_callback_max_relative_roundtrip"] < 2e-14

    started = time.perf_counter()
    finer_params = rf.params_from_cosmology(
        **inputs, accuracy_boost=2.0, background_timestep_boost=2.0)
    finer_data = rf.build_background(finer_params)
    external = rf.sample_history(finer_data, z)
    receipt["CAMB_external_sampling_control_seconds"] = time.perf_counter() - started
    receipt["CAMB_external_sampling_control"] = {
        "AccuracyBoost": 2.0, "BackgroundTimeStepBoost": 2.0,
        "description": "Changes the CAMB thermal sampling; native RECFAST Nz/tol unchanged.",
        "max_H_relative_change": float(np.max(np.abs(external["H_s"]/thermal["H_s"]-1))),
    }
    columns = {
        "z": z, "a": thermal["a"], "H_s_inv": thermal["H_s"],
        "Tgamma_K": c["Tcmb0_K"]*(1+z),
        "xe_RECFAST": thermal["xe"], "Tgas_RECFAST_K": thermal["Tm_K"],
        "xe_HYREC2": hyrec["xe"], "Tgas_HYREC2_K": hyrec["Tm_K"],
        "xe_HYREC2_halfstep": half["xe"], "Tgas_HYREC2_halfstep_K": half["Tm_K"],
        "xe_HYREC2_native_composition": native["xe"],
        "Tgas_HYREC2_native_composition_K": native["Tm_K"],
        "xe_RECFAST_external_sampling": external["xe"],
        "Tgas_RECFAST_external_sampling_K": external["Tm_K"],
    }
    for name, values in columns.items():
        if not np.all(np.isfinite(values)) or not np.all(values > 0):
            raise ValueError(f"Nonpositive/nonfinite history: {name}")
    for name in columns:
        if name.startswith("xe_") and np.max(columns[name]) > 1+2*max(
                abundance["fHe"], native["metadata"]["used_fHe"])+1e-6:
            raise ValueError("Electron fraction exceeds full HII/HeIII limit")
    output = args.output_dir / "histories.csv"
    write_csv(output, columns)
    receipt["histories_sha256"] = digest(output)
    receipt["hyrec_input_sha256"] = digest(parameter_file)
    receipt["finite_positive"] = True
    receipt["primary_H_callback_exact"] = True
    (args.output_dir / "RUN_RECEIPT.json").write_text(
        json.dumps(receipt, indent=2, allow_nan=False)+"\n")
    at = int(np.flatnonzero(z == 49)[0])
    print(json.dumps({"run": "matched_pair", "grid_points": len(z),
                      "boundary": {name: float(values[at]) for name, values in columns.items()},
                      "RECFAST_seconds": recfast_seconds,
                      "HYREC_seconds": {key: receipt["HYREC"][key]["elapsed_seconds"] for key in
                                        ["main", "half_step", "native_composition"]}}, allow_nan=False))


if __name__ == "__main__":
    main()
