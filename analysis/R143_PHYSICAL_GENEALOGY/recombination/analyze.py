#!/usr/bin/env python3
"""Summarize existing R143 histories without running either physical solver."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def residual(z, lhs, rhs, mask=None):
    if mask is None:
        mask = np.ones(len(z), dtype=bool)
    zz, difference = z[mask], (lhs-rhs)[mask]
    relative = difference / rhs[mask]
    i, j = int(np.argmax(np.abs(difference))), int(np.argmax(np.abs(relative)))
    return {
        "points": len(zz),
        "max_abs": float(abs(difference[i])), "z_max_abs": float(zz[i]),
        "max_abs_relative": float(abs(relative[j])), "z_max_abs_relative": float(zz[j]),
        "min_signed_relative": float(np.min(relative)),
        "max_signed_relative": float(np.max(relative)),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).parent)
    parser.add_argument("--lock", type=Path, default=Path(__file__).with_name("LOCK.json"))
    args = parser.parse_args()
    p = args.data_dir
    lock = json.loads(args.lock.read_text())
    data = np.genfromtxt(p/"histories.csv", names=True, delimiter=",")
    fine = np.genfromtxt(p/"recfast_internal_refined.csv", names=True, delimiter=",")
    z, a = data["z"], data["a"]
    if not np.array_equal(z, fine["z"]):
        raise ValueError("Numerical controls must have exactly the same output nodes")
    main_receipt = json.loads((p/"RUN_RECEIPT.json").read_text())
    fine_receipt = json.loads((p/"recfast_internal_refined_receipt.json").read_text())
    assert main_receipt["lock_sha256"] == fine_receipt["lock_sha256"] == sha256(args.lock)
    assert main_receipt["histories_sha256"] == sha256(p/"histories.csv")
    assert main_receipt["inputs"] == fine_receipt["inputs"]
    assert main_receipt["composition"] == fine_receipt["composition"]
    assert np.max(np.abs(fine["H_s_inv"]/data["H_s_inv"]-1)) < 2e-14
    if not np.all(np.isfinite(fine.view(float))) or not np.all(fine["xe"] > 0) or not np.all(fine["Tgas_K"] > 0):
        raise ValueError("Invalid refined RECFAST output")
    index = int(np.flatnonzero(z == 49)[0])
    lumina_formula = lock["cosmology"]["Tcmb0_K"]*50**2/125.8
    boundary = {name: float(data[name][index]) for name in data.dtype.names}
    boundary.update(
        xe_RECFAST_internal_refined=float(fine["xe"][index]),
        Tgas_RECFAST_internal_refined_K=float(fine["Tgas_K"][index]),
        Tgas_Lumina_formula_K=lumina_formula,
        Tgas_Lumina_printed_K=54.17,
    )
    boundary["primary_residual"] = {
        "xe_abs": boundary["xe_HYREC2"]-boundary["xe_RECFAST"],
        "xe_relative": boundary["xe_HYREC2"]/boundary["xe_RECFAST"]-1,
        "Tgas_abs_K": boundary["Tgas_HYREC2_K"]-boundary["Tgas_RECFAST_K"],
        "Tgas_relative": boundary["Tgas_HYREC2_K"]/boundary["Tgas_RECFAST_K"]-1,
    }
    boundary["refined_pair_residual"] = {
        "xe_abs": boundary["xe_HYREC2_halfstep"]-boundary["xe_RECFAST_internal_refined"],
        "xe_relative": boundary["xe_HYREC2_halfstep"]/boundary["xe_RECFAST_internal_refined"]-1,
        "Tgas_abs_K": boundary["Tgas_HYREC2_halfstep_K"]-boundary["Tgas_RECFAST_internal_refined_K"],
        "Tgas_relative": boundary["Tgas_HYREC2_halfstep_K"]/boundary["Tgas_RECFAST_internal_refined_K"]-1,
    }
    boundary["vs_Lumina_formula"] = {
        key: {"difference_K": boundary[key]-lumina_formula,
              "relative": boundary[key]/lumina_formula-1}
        for key in ["Tgas_RECFAST_K", "Tgas_HYREC2_K",
                    "Tgas_RECFAST_internal_refined_K", "Tgas_HYREC2_halfstep_K"]
    }
    epochs = []
    for epoch in lock["epochs"]:
        mask = (z >= epoch["z_min"]) & (z <= epoch["z_max"])
        epochs.append({**epoch,
                       "xe": residual(z, data["xe_HYREC2"], data["xe_RECFAST"], mask),
                       "Tgas_K": residual(z, data["Tgas_HYREC2_K"], data["Tgas_RECFAST_K"], mask),
                       "refined_xe": residual(z, data["xe_HYREC2_halfstep"], fine["xe"], mask),
                       "refined_Tgas_K": residual(z, data["Tgas_HYREC2_halfstep_K"], fine["Tgas_K"], mask)})
    controls = {}
    pairs = [
        ("HYREC_half_step", data["xe_HYREC2_halfstep"], data["Tgas_HYREC2_halfstep_K"], data["xe_HYREC2"], data["Tgas_HYREC2_K"]),
        ("RECFAST_internal_refinement", fine["xe"], fine["Tgas_K"], data["xe_RECFAST"], data["Tgas_RECFAST_K"]),
        ("CAMB_external_sampling", data["xe_RECFAST_external_sampling"], data["Tgas_RECFAST_external_sampling_K"], data["xe_RECFAST"], data["Tgas_RECFAST_K"]),
        ("HYREC_native_composition", data["xe_HYREC2_native_composition"], data["Tgas_HYREC2_native_composition_K"], data["xe_HYREC2"], data["Tgas_HYREC2_K"]),
    ]
    for name, xx, tt, xr, tr in pairs:
        controls[name] = {"xe": residual(z, xx, xr), "Tgas_K": residual(z, tt, tr),
                          "boundary": {"xe_abs": float(xx[index]-xr[index]),
                                       "xe_relative": float(xx[index]/xr[index]-1),
                                       "Tgas_abs_K": float(tt[index]-tr[index]),
                                       "Tgas_relative": float(tt[index]/tr[index]-1)}}
    summary = {
        "id": lock["id"], "status": "EXECUTED_AND_COMPARED",
        "scientific_acceptance": False, "U014_status": "OPEN",
        "lock_sha256": sha256(args.lock), "grid_points": len(z),
        "normalization": main_receipt["composition"],
        "background_Omega": main_receipt["CAMB_background_Omega"],
        "boundary_z49": boundary, "epochs": epochs, "controls": controls,
        "checks": {"identical_grid": True, "identical_frozen_input": True,
                   "common_nH0_fHe": True, "finite_positive": True,
                   "HYREC_H_callback_max_relative_error": max(
                       main_receipt["HYREC"][key]["H_callback_max_relative_roundtrip"]
                       for key in ["main", "half_step", "native_composition"]),
                   "RECFAST_refinement_H_max_relative_change": float(np.max(np.abs(fine["H_s_inv"]/data["H_s_inv"]-1)))},
        "timing_seconds": {
            "RECFAST_main_and_sampling": main_receipt["RECFAST_seconds"],
            "HYREC_main": main_receipt["HYREC"]["main"]["elapsed_seconds"],
            "HYREC_half_step": main_receipt["HYREC"]["half_step"]["elapsed_seconds"],
            "HYREC_native_composition": main_receipt["HYREC"]["native_composition"]["elapsed_seconds"],
            "RECFAST_external_sampling_control": main_receipt["CAMB_external_sampling_control_seconds"],
            "RECFAST_internal_refinement": fine_receipt["RECFAST_seconds"]},
        "artifact_sha256": {name: sha256(p/name) for name in
                             ["histories.csv", "RUN_RECEIPT.json", "recfast_internal_refined.csv",
                              "recfast_internal_refined_receipt.json", "hyrec_input.dat"]},
        "limitations": [
            "Homogeneous no-reionization histories only; not a full reproduction of Lumina initial conditions.",
            "No density/velocity/potential perturbations or relative-streaming evolution in this run.",
            "No CCC+TL recombination or altered-background model is computed.",
            "RECFAST is a fitted approximation with common calibration ancestry; solver agreement is not independent experimental validation.",
            "Residual differences include native atomic/radiative approximations and constants, after matching H and abundance conventions.",
        ],
    }
    (p/"SUMMARY.json").write_text(json.dumps(summary, indent=2, allow_nan=False)+"\n")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False})
    fig, axs = plt.subplots(2, 2, figsize=(12, 8.2), sharex=True, constrained_layout=True)
    x = a[::-1]
    for ax in axs.flat:
        ax.set_xscale("log")
        ax.grid(alpha=0.2)
        ax.axvline(0.02, color="#626b79", lw=1, ls=":")
    for column, ylabel, ax in [("xe", r"$x_e=n_e/n_H$", axs[0, 0]),
                                ("Tgas", "Gas temperature [K]", axs[0, 1])]:
        suffix = "_K" if column == "Tgas" else ""
        ax.plot(x, data[f"{column}_HYREC2{suffix}"][::-1], label="HYREC-2", color="#194d73", lw=2)
        ax.plot(x, data[f"{column}_RECFAST{suffix}"][::-1], label="RECFAST 1.5.2", color="#c36728", lw=1.3, ls="--")
        ax.set_yscale("log")
        ax.set_ylabel(ylabel)
    cold = z <= 124.8
    axs[0, 1].plot(a[cold][::-1], (lock["cosmology"]["Tcmb0_K"]*(1+z[cold])**2/125.8)[::-1],
                   color="#7b4f90", lw=1.4, label="Lumina Eq. (27)")
    axs[0, 0].legend(frameon=False)
    axs[0, 1].legend(frameon=False)
    axs[1, 0].plot(x, (100*(data["xe_HYREC2"]/data["xe_RECFAST"]-1))[::-1], color="#194d73")
    axs[1, 1].plot(x, (100*(data["Tgas_HYREC2_K"]/data["Tgas_RECFAST_K"]-1))[::-1], color="#194d73")
    axs[1, 0].set_ylabel(r"$100\,(x_e^{H}/x_e^{R}-1)$ [%]")
    axs[1, 1].set_ylabel(r"$100\,(T_m^{H}/T_m^{R}-1)$ [%]")
    for ax in axs[1]:
        ax.axhline(0, color="#626b79", lw=0.6)
        ax.set_xlabel(r"Scale factor $a=1/(1+z)$")
    fig.suptitle("R143 | Matched recombination histories\nYp = 0.24; common H(a), hydrogen density and helium number fraction", fontsize=15)
    fig.savefig(p/"comparison.png", dpi=180)
    fig.savefig(p/"comparison.svg")
    plt.close(fig)
    print(json.dumps({"boundary": boundary, "controls_at_49": {k: v["boundary"] for k, v in controls.items()},
                      "timing_seconds": summary["timing_seconds"], "checks": summary["checks"]}, allow_nan=False))


if __name__ == "__main__":
    main()
