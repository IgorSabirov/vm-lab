#!/usr/bin/env python3
"""Check saved R143 data and provenance without executing a physical history."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Save CHECKS.json")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    load = lambda name: json.loads((root / name).read_text())
    digest = lambda name: hashlib.sha256((root / name).read_bytes()).hexdigest()
    passed = []

    def check(name, condition):
        if not bool(condition):
            raise AssertionError(name)
        passed.append(name)

    def close(name, actual, expected):
        check(name, np.isclose(actual, expected, rtol=3e-12, atol=2e-15))

    lock = load("LOCK.json")
    plan = load("NUMERICAL_FOLLOWUP.json")
    summary = load("results/SUMMARY.json")
    receipt = load("results/RUN_RECEIPT.json")
    convergence = load("results/CONVERGENCE.json")
    for group in ["code_sha256", "build_receipt_sha256"]:
        for name, expected in lock[group].items():
            check("frozen:" + name, digest(name) == expected)
    for name, expected in summary["artifact_sha256"].items():
        check("primary-data:" + name, digest("results/" + name) == expected)
    for name, expected in plan["input_sha256"].items():
        check("followup-input:" + name, digest(name) == expected)
    check("summary-lock", summary["lock_sha256"] == digest("LOCK.json"))
    check("run-lock", receipt["lock_sha256"] == digest("LOCK.json"))
    check("followup-plan", convergence["plan_sha256"] == digest("NUMERICAL_FOLLOWUP.json"))
    check("followup-script", plan["convergence_script_sha256"] == digest("convergence.py"))
    check("followup-csv", convergence["additional_histories_sha256"] ==
          digest("results/hyrec_additional_steps.csv"))
    check("followup-declared-before-run",
          datetime.fromisoformat(plan["declared_UTC"]) <
          datetime.fromisoformat(convergence["started_UTC"]))
    check("two-declared-additional-runs", convergence["new_HYREC_run_count"] == 2 and
          [v["dlna"] for v in convergence["new_HYREC_runs"]] == [0.001, 0.0005])
    check("same-explicit-Yp", lock["cosmology"]["Yp_mass_fraction"] == 0.24 and
          receipt["inputs"]["Yp"] == 0.24)
    check("scientific-acceptance-not-implied", not summary["scientific_acceptance"] and
          not convergence["scientific_acceptance"] and summary["U014_status"] == "OPEN")

    primary = np.genfromtxt(root / "results/histories.csv", names=True, delimiter=",")
    fine = np.genfromtxt(root / "results/recfast_internal_refined.csv", names=True, delimiter=",")
    extra = np.genfromtxt(root / "results/hyrec_additional_steps.csv", names=True, delimiter=",")
    z = primary["z"]
    check("6023-identical-nodes", len(z) == 6023 and
          np.array_equal(z, fine["z"]) and np.array_equal(z, extra["z"]))
    check("unique-increasing-redshifts", np.all(np.diff(z) > 0))
    check("exact-boundary-node", np.count_nonzero(z == 49) == 1)
    check("scale-factor", np.allclose(primary["a"], 1 / (1 + z), rtol=2e-15, atol=0))
    check("identical-H", np.array_equal(primary["H_s_inv"], fine["H_s_inv"]) and
          np.array_equal(primary["H_s_inv"], extra["H_s_inv"]))
    for label, array in [("primary", primary), ("fine", fine), ("extra", extra)]:
        check(label + "-finite-positive", all(np.all(np.isfinite(array[name])) and
              np.all(array[name] > 0) for name in array.dtype.names))
    for metadata in [receipt["HYREC"]["main"], receipt["HYREC"]["half_step"],
                     *convergence["new_HYREC_runs"]]:
        step = metadata["dlna"]
        check(f"common-composition-step-{step}", all(
            metadata["used_" + key] == lock["composition"][key]
            for key in ["nH0_cm3", "fHe"]))
        check(f"internal-size-step-{step}", metadata["internal_grid_size"] ==
              int(np.log(8001) / step) + 2)
        check(f"H-units-step-{step}", metadata["H_callback_max_relative_roundtrip"] < 2e-14)

    at = int(np.flatnonzero(z == 49)[0])
    boundary = summary["boundary_z49"]
    for name in primary.dtype.names:
        if name in boundary:
            close("boundary:" + name, primary[name][at], boundary[name])
    for quantity, left, right, key in [
        ("xe", "xe_HYREC2", "xe_RECFAST", "xe"),
        ("Tgas", "Tgas_HYREC2_K", "Tgas_RECFAST_K", "Tgas_K"),
    ]:
        residual = (primary[left] - primary[right]) / primary[right]
        metric = "xe_relative" if quantity == "xe" else "Tgas_relative"
        close("boundary-residual:" + quantity, residual[at],
              boundary["primary_residual"][metric])
        for epoch in summary["epochs"]:
            mask = (z >= epoch["z_min"]) & (z <= epoch["z_max"])
            close("epoch:" + quantity + ":" + epoch["label"],
                  np.max(np.abs(residual[mask])), epoch[key]["max_abs_relative"])
    lumina = lock["cosmology"]["Tcmb0_K"] * 50**2 / 125.8
    close("Lumina-formula-boundary", lumina, boundary["Tgas_Lumina_formula_K"])
    for suffix, step in [("0p001", 0.001), ("0p0005", 0.0005)]:
        recorded = next(v for v in convergence["boundary_z49"] if v["dlna"] == step)
        close(f"additional-boundary-xe-{step}", extra["xe_HYREC2_step_" + suffix][at], recorded["xe"])
        close(f"additional-boundary-T-{step}", extra["Tgas_HYREC2_step_" + suffix + "_K"][at], recorded["Tgas_K"])

    # Diagnose the saved counterexample; positivity alone does not certify convergence.
    half = primary["xe_HYREC2_halfstep"]
    medium, small = extra["xe_HYREC2_step_0p001"], extra["xe_HYREC2_step_0p0005"]
    over_one_percent = np.abs((medium - small) / small) > 0.01
    diagnostics = {}
    for label, low, high in [("helium", 1600, 4000), ("hydrogen", 500, 1600)]:
        mask = (z >= low) & (z <= high) & over_one_percent
        diagnostics[label] = {
            "nodes_with_relative_step_difference_over_1_percent": int(mask.sum()),
            "z_range": [float(z[mask].min()), float(z[mask].max())],
        }
    check("known-He-anomaly-retained", diagnostics["helium"]["nodes_with_relative_step_difference_over_1_percent"] == 392)
    check("known-H-anomaly-retained", diagnostics["hydrogen"]["nodes_with_relative_step_difference_over_1_percent"] == 11)
    curves = {"0.004": primary["xe_HYREC2"], "0.002": half,
              "0.001": medium, "0.0005": small}
    diagnostics["monotonicity"] = {}
    for label, low, high in [("helium_window", 2800, 2900), ("hydrogen_window", 1450, 1650)]:
        mask = (z >= low) & (z <= high)
        diagnostics["monotonicity"][label] = {
            step: int(np.count_nonzero(np.diff(x[mask]) < 0)) for step, x in curves.items()
        }
    result = {
        "id": "R143-HYREC2-RECFAST-SAVED-DATA-AUDIT",
        "status": "DATA_AND_PROVENANCE_CHECKS_PASS",
        "checks_passed": len(passed), "checks": passed,
        "physical_histories_executed_by_this_script": 0,
        "scientific_acceptance": False, "U014_status": "OPEN",
        "full_history_convergence": "NOT_ESTABLISHED",
        "boundary_statement": "z49 is stable across the four saved HYREC step sizes; consecutive changes are not rigorous error bounds.",
        "diagnostics_from_saved_arrays": diagnostics,
        "sha256": {name: digest(name) for name in [
            "LOCK.json", "NUMERICAL_FOLLOWUP.json", "results/SUMMARY.json",
            "results/CONVERGENCE.json", "verify.py"]},
    }
    if args.write:
        (root / "CHECKS.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": result["status"], "checks_passed": len(passed),
                      "full_history_convergence": result["full_history_convergence"],
                      "diagnostics": diagnostics}, ensure_ascii=False))


if __name__ == "__main__":
    main()
