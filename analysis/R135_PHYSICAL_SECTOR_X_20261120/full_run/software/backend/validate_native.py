"""Optional P8/P9 wiring test using genuine backends and a manufactured history.

THIS IS NOT AN R135 PHYSICAL RUN. Nuclear rates are explicitly zero and initial
D/He are assigned to test the adapters, mixed-response gate and likelihood I/O.
No calculated abundance from this control may be used as a physical prediction.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
import sys
import time

import numpy as np

SOFTWARE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOFTWARE))
from r135 import observations, backends
from r135.common import HBARC_MEV_CM, read_json, sha256, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--class-source", type=Path, required=True)
    parser.add_argument("--planck-root", type=Path, required=True)
    parser.add_argument("--planck-python", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("use a new output directory; previous evidence is preserved")
    args.out.mkdir(parents=True)
    started = time.monotonic()
    rates, reverse = backends.prepare_native_rates()
    for reaction in rates["reactions"]:
        reaction["values"] = [0.] * len(reaction["values"])
    tg = np.linspace(.008, .004, 9)
    times = np.linspace(0., 2., len(tg))
    a = tg[0] / tg
    rg = np.pi ** 2 / 15 * tg ** 4
    w = {"time_s": times.tolist(), "lambda_n_to_p_s_inv": (.2 + .2 * times).tolist(),
         "lambda_p_to_n_s_inv": [0.] * len(tg), "unit": "s^-1",
         "source": "SYNTHETIC_SOFTWARE_CONTROL: prescribed n->p decay for adapter verification"}
    history = {"time_s": times.tolist(), "scale_factor": a.tolist(),
               "H_s_inv": np.gradient(np.log(a), times).tolist(), "T_gamma_MeV": tg.tolist(),
               "T_nu_MeV": (tg * (4 / 11) ** (1 / 3)).tolist(),
               "n_b_cm3": (6e-10 * 2 * 1.2020569031595942 / np.pi ** 2 * (tg / HBARC_MEV_CM) ** 3).tolist(),
               "rho_gamma_MeV4": rg.tolist(), "rho_nu_MeV4": (3.044 * (7 / 8) * (4 / 11) ** (4 / 3) * rg).tolist(),
               "rho_extra_MeV4": [0.] * len(tg), "p_extra_MeV4": [0.] * len(tg), "weak_rates": w}
    bundle = {"schema": "R135-channel-history-v1", "scope": "SYNTHETIC_SOFTWARE_CONTROL",
              "units": {"time": "s", "temperature": "MeV", "density": "MeV^4", "rate": "s^-1"},
              "histories": {corner: deepcopy(history) for corner in observations.CORNERS}}
    write_json(args.out / "manufactured_channel_history.json", bundle)
    write_json(args.out / "manufactured_nuclear_rates.json", {"rates": rates, "reverse_alpha_beta_gamma": reverse})
    p8_config = {"_mode": "validation", "created_utc": "2026-11-20T00:00:00Z",
        "common_initial_abundances": [.1, .65998, .00001, 0., 0., .06, 0., 0.],
        "applicability": {"scope": "SYNTHETIC_SOFTWARE_CONTROL", "photodisintegration_or_nonthermal_nuclear_sources": False},
        "class": {"perturbation_model": {"kind": "standard_free_streaming_after_matching",
                "source": "Manufactured radiation-only solver control",
                "domain_proof_source": "No extra sector exists in this artificial fixture",
                "all_transfer_finished_before_relevant_modes_enter": True, "adiabatic_initial_perturbations": True,
                "massless_collisionless_extra_radiation": True, "no_surviving_interacting_relic": True},
            "matching": {"source": "Synthetic post-annihilation density relation",
                         "transfer_finished": True, "electron_annihilation_finished": True},
            "parameters": {"H0": 67.4, "omega_b": .02242, "omega_cdm": .120, "N_ur": 3.044,
                           "T_cmb": 2.7255, "tau_reio": .054, "n_s": .965, "A_s": 2.1e-9}}}
    write_json(args.out / "P8_config.json", p8_config)
    p8 = observations.run(p8_config, {"channel_history": args.out / "manufactured_channel_history.json",
                                     "nuclear_rates": args.out / "manufactured_nuclear_rates.json"}, args.out / "P8")
    p9_config = {"_mode": "validation", "relative_floor": 1e-6,
        "refinement": [{"rtol": 1e-8, "atol": 1e-11}, {"rtol": 1e-10, "atol": 1e-13}, {"rtol": 1e-12, "atol": 1e-15}],
        "class_source_root": str(args.class_source.resolve()), "planck_data_root": str(args.planck_root.resolve()),
        "planck_python": str(args.planck_python.absolute()), "planck_python_sha256": sha256(args.planck_python),
        "theory_covariance_logD_Yp": [[0., 0.], [0., 0.]], "profile_nuisance": False}
    write_json(args.out / "P9_config.json", p9_config)
    p9 = backends.run(p9_config, {"bbn_inputs": args.out / "P8/bbn_inputs.json",
                                  "class_inputs": args.out / "P8/class_inputs.json",
                                  "data_release_lock": SOFTWARE / "p0_snapshot/data_release_lock.json"}, args.out / "P9")
    if p9["software_status"] != "PASS":
        raise RuntimeError(f"synthetic orchestration failed: {p9}")
    gates = read_json(args.out / "P9/convergence.json")
    summary = {"scope": "SYNTHETIC_SOFTWARE_CONTROL", "physical_R135_run": False,
               "P8": p8, "P9": p9, "elapsed_seconds": time.monotonic() - started,
               "convergence": {k: v["status"] for k, v in gates.items()},
               "primary_artifact_sha256": {str(p.relative_to(args.out)): sha256(p) for p in
                    (args.out / "P9/abundances.csv", args.out / "P9/mixed_response.csv", args.out / "P9/likelihood_grid.csv",
                     args.out / "P9/backend_consumption.json", args.out / "P9/cmb_spectra_manifest.json")}}
    write_json(args.out / "VALIDATION.json", summary)
    print(summary)


if __name__ == "__main__":
    main()
