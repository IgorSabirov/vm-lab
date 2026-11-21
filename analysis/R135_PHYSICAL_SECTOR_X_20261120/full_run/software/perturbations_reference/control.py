#!/usr/bin/env python3
"""Synthetic analytic ETHOS controls; these are not calibrated R135 points.

Run the pinned real CLASS executable and retain its inputs, raw spectra and
parameter-consumption record. This developer control does not run P0--P10.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import os
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from r135.common import HBARC_MEV_CM, InputError, canonical_hash, sha256, write_json
from r135.perturbations import (CLASS_COMMIT, KB_MEV_K, MODEL_KIND, MPC_OVER_C_S, ONE_NEUTRINO_FACTOR,
                                REQUIRED_DOMAIN, match_ethos_history, photon_omega, validate_ethos_input)


def control_fixture(a_idm_dr=.1, idr_nature="fluid", n_index=0):
    """Exact FLRW cold+massless background with an analytic elastic opacity.

    Every number is a software-test preparation. No matching to the BBN energy
    budget, literature benchmark likelihood, or cosmological sector X is claimed.
    """
    pars = {"H0": 67.4, "omega_b": .02242, "omega_cdm": .108, "T_cmb": 2.7255,
            "tau_reio": .054, "n_s": .965, "A_s": 2.1e-9, "N_ur": 3.044}
    model = {"kind": MODEL_KIND, "source": "synthetic analytic ETHOS development control",
             "domain_proof_source": "exact same stable species and elastic power law continued to early times; diagnostic only",
             **dict.fromkeys(REQUIRED_DOMAIN, True), "fluid_limit_validated": True,
             "fluid_limit_source": "analytic large self-scattering opacity (b_idr=1e12/Mpc) over the tested modes; no R135 identification",
             "microphysics": {"source": "diagnostic coefficients, ETHOS convention arXiv:1512.05344v4",
                              "m_idm_eV": 1e10, "n_index_idm_dr": n_index, "idr_nature": idr_nature,
                              "stat_f_idr": 1., "alpha_idm_dr": [1.5], "beta_idr": [1.5]}}
    config = {"perturbation_model": model, "parameters": pars,
              "matching": {"source": "analytic cold+massless FLRW diagnostic, not P7 physical R135 output",
                           "homogeneous_transfer_finished": True, "electron_annihilation_finished": True,
                           "relevant_k_max_Mpc_inv": 1., "maximum_k_over_aH": .05,
                           "start_index": 0, "index": -1}}
    tg = np.array([.009, .007, .005])
    a = pars["T_cmb"] * KB_MEV_K / tg
    omega_g, omega_m, n_idr = photon_omega(pars["T_cmb"]), .012, .2
    rg = np.pi ** 2 * tg ** 4 / 15
    rn = rg * ONE_NEUTRINO_FACTOR * pars["N_ur"]
    rr = rg * ONE_NEUTRINO_FACTOR * n_idr
    rm = rg * (omega_m / omega_g) * a
    wr = omega_g * (1 + ONE_NEUTRINO_FACTOR * (pars["N_ur"] + n_idr))
    wm = omega_m + pars["omega_cdm"] + pars["omega_b"]
    h100 = 1e5 / 3.085677581282e22
    hubble = h100 * np.sqrt(wr / a ** 4 + wm / a ** 3 + (pars["H0"] / 100) ** 2 - wr - wm)
    # The radiation+matter age formula is exact for those components; the tiny
    # vacuum term at this early epoch is below double-precision sensitivity.
    from scipy.integrate import quad
    times = np.array([quad(lambda x: x / np.sqrt(wr + wm * x), 0., ai,
                           epsabs=1e-30)[0] / h100 for ai in a])
    rate = omega_m * a_idm_dr * (1 / a / 1e7) ** n_index / (a * MPC_OVER_C_S)
    self_rate = (n_idr * ONE_NEUTRINO_FACTOR * omega_g * 1e12 * (1 / a / 1e7) ** n_index /
                 (a * MPC_OVER_C_S)) if idr_nature == "fluid" else np.zeros_like(a)
    zeros = np.zeros_like(a)
    history = {"time_s": times.tolist(), "scale_factor": (a / a[0]).tolist(), "H_s_inv": hubble.tolist(),
               "T_gamma_MeV": tg.tolist(),
               "n_b_cm3": (6.1e-10 * 2 * 1.2020569031595942 / np.pi ** 2 * (tg / HBARC_MEV_CM) ** 3).tolist(),
               "rho_gamma_MeV4": rg.tolist(), "rho_nu_MeV4": rn.tolist(),
               "rho_idm_MeV4": rm.tolist(), "p_idm_MeV4": zeros.tolist(),
               "rho_idr_MeV4": rr.tolist(), "p_idr_MeV4": (rr / 3).tolist(),
               "rho_extra_MeV4": (rm + rr).tolist(), "p_extra_MeV4": (rr / 3).tolist(),
               "Gamma_idr_idm_s_inv": rate.tolist(),
               "Gamma_idm_idr_s_inv": (4 * rr / (3 * rm) * rate).tolist(),
               "Gamma_idr_self_s_inv": self_rate.tolist()}
    return history, config


def _native_case(source, out, name, parameters, precision=None):
    work = out / name
    work.mkdir()
    root = work / "native_"
    pars = deepcopy(parameters)
    pars.update(precision or {})
    pars.update(YHe=.245, N_ncdm=0, output="tCl,pCl,lCl,mPk", lensing="yes", l_max_scalars=512,
                root=str(root), headers="yes", format="camb")
    pars.update({"P_k_max_1/Mpc": 1., "write parameters": "yes"})
    ini = work / "input.ini"
    ini.write_text("\n".join(f"{key} = {value}" for key, value in pars.items()) + "\n")
    started = time.monotonic()
    with (work / "stdout.txt").open("w") as stdout:
        result = subprocess.run([str(source / "class"), str(ini)], cwd=source, stdout=stdout,
                                stderr=subprocess.STDOUT, env={**os.environ, "OMP_NUM_THREADS": "1"})
    elapsed = time.monotonic() - started
    if result.returncode:
        raise RuntimeError(f"real CLASS control {name} failed; inspect {work / 'stdout.txt'}")
    cl_path, pk_path = work / "native_00_cl_lensed.dat", work / "native_00_pk.dat"
    cl, pk = np.loadtxt(cl_path), np.loadtxt(pk_path)
    if not np.isfinite(cl).all() or not np.isfinite(pk).all() or np.any(cl[:, 1:4] < 0) or np.any(pk[:, 1] <= 0):
        raise RuntimeError("native CLASS emitted nonfinite/nonpositive auto power")
    if not np.array_equal(cl[:, 0], np.arange(2, 513)):
        raise RuntimeError("missing CLASS multipoles")
    used = (work / "native_00_parameters.ini").read_text()
    actual = {line.split("=", 1)[0].strip(): line.split("=", 1)[1].strip()
              for line in used.splitlines() if "=" in line and not line.startswith("#")}
    for name in parameters:
        if name not in actual:
            raise RuntimeError(f"CLASS did not consume requested parameter {name}")
    return {"time_s": elapsed, "parameters_read": actual,
            "files": {p.name: sha256(p) for p in work.iterdir() if p.is_file()}}, cl, pk


def run_native_controls(source, output):
    from r135.backends import verify_checkout
    source, output = Path(source).resolve(), Path(output).resolve()
    verified = verify_checkout(source, CLASS_COMMIT)
    if output.exists() and any(output.iterdir()):
        raise InputError("use a new isolated perturbation-control output directory")
    output.mkdir(parents=True, exist_ok=True)
    adapter_digest = sha256(Path(__file__).parents[1] / "r135" / "perturbations.py")
    control_digest = sha256(Path(__file__))
    cases, results, cls, pks = {}, {}, {}, {}
    for name, amp, nature in (("zero_free", 0., "free_streaming"), ("zero_fluid", 0., "fluid"),
                             ("coupled_fluid", 1., "fluid"), ("coupled_free", 1., "free_streaming")):
        h, cfg = control_fixture(amp, nature)
        doc = match_ethos_history(h, cfg)
        validate_ethos_input(doc)
        cases[name] = doc["parameters"]
        write_json(output / (name + "_handoff.json"), doc)
    # Same total matter and radiation, represented as ordinary CDM + free ur.
    standard = {k: v for k, v in cases["zero_free"].items() if k in
                ("H0", "omega_b", "omega_cdm", "T_cmb", "tau_reio", "n_s", "A_s", "N_ur")}
    standard["omega_cdm"] += cases["zero_free"]["omega_idm"]
    standard["N_ur"] += cases["zero_free"]["N_idr"]
    cases["equivalent_cdm_ur"] = standard
    cases["coupled_fluid_refined"] = cases["coupled_fluid"]
    refinement = {"tol_perturbations_integration": 1e-7, "tol_background_integration": 1e-11,
                  "tol_thermo_integration": 1e-7, "l_linstep": 10, "l_logstep": 1.026}
    for name, parameters in cases.items():
        results[name], cls[name], pks[name] = _native_case(source, output, name, parameters,
                                                        refinement if name.endswith("refined") else None)
    def cl_difference(one, two):
        # TT is positive; unlike TE, this ratio has no zero-crossing singularity.
        return float(np.max(np.abs(cls[one][:, 1] / cls[two][:, 1] - 1)))
    def pk_at(name, wavenumber=.2):
        return float(np.exp(np.interp(np.log(wavenumber), np.log(pks[name][:, 0]), np.log(pks[name][:, 1]))))
    stats = {"zero_coupling_vs_cdm_ur_max_relative_TT": cl_difference("zero_free", "equivalent_cdm_ur"),
             "coupled_vs_uncoupled_fluid_max_relative_TT": cl_difference("coupled_fluid", "zero_fluid"),
             "coupled_vs_uncoupled_free_max_relative_TT": cl_difference("coupled_free", "zero_free"),
             "fluid_vs_free_zero_coupling_max_relative_TT": cl_difference("zero_fluid", "zero_free"),
             "refinement_max_relative_TT": cl_difference("coupled_fluid", "coupled_fluid_refined"),
             "coupled_to_uncoupled_fluid_Pk_ratio_at_k_h_Mpc_0.2": pk_at("coupled_fluid") / pk_at("zero_fluid"),
             "all_spectra_finite": True, "ell_range": [2, 512], "Pk_query_unit": "k in h/Mpc; P in (Mpc/h)^3"}
    gates = {"uncoupled_equivalence": stats["zero_coupling_vs_cdm_ur_max_relative_TT"] < .003,
             "interaction_resolved": stats["coupled_vs_uncoupled_fluid_max_relative_TT"] > .001,
             "free_hierarchy_interaction_resolved": stats["coupled_vs_uncoupled_free_max_relative_TT"] > .001,
             "fluid_shear_response_resolved": stats["fluid_vs_free_zero_coupling_max_relative_TT"] > .001,
             "interaction_exceeds_5x_refinement": stats["coupled_vs_uncoupled_fluid_max_relative_TT"] >
                                                     5 * stats["refinement_max_relative_TT"],
             "precision_control": stats["refinement_max_relative_TT"] < .003}
    report = {"schema": "R135-ETHOS-native-development-control-v1", "status": "PASS" if all(gates.values()) else "FAIL",
              "purpose": "native equation/consumption/unit control; not a calibrated X point or observational inference",
              "class_source": verified, "class_binary_sha256": sha256(source / "class"),
              "adapter_sha256": adapter_digest, "control_code_sha256": control_digest,
              "statistics": stats, "gates": gates, "cases": results}
    write_json(output / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--class-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = run_native_controls(args.class_root, args.output)
    print(report["status"], report["statistics"])
    raise SystemExit(0 if report["status"] == "PASS" else 1)
