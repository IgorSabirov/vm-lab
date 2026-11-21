"""Reproduce nonzero donor controls; this is not a physical R135 run."""
import argparse
import copy
import resource
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from r135.cascades import linear_spectrum_moment, run_electromagnetic_cascade
from r135.common import read_json, sha256, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--donor-path", type=Path)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "results")
    parser.add_argument("--no-fetch", action="store_true")
    args = parser.parse_args()
    input_path = Path(__file__).resolve().parent / "control_input.json"
    base = read_json(input_path)
    configs = {"photon_120": base}
    fine = copy.deepcopy(base)
    fine["numerics"]["energy_points_per_decade"] = 150
    configs["photon_150"] = fine
    half = copy.deepcopy(base)
    half["injection"]["lines"][0]["dN_dVdt_MeV3_s"] = (np.array(base["injection"]["lines"][0]["dN_dVdt_MeV3_s"])/2).tolist()
    half["injection"]["power_MeV4_s"] = (np.array(base["injection"]["power_MeV4_s"])/2).tolist()
    configs["photon_half"] = half
    zero = copy.deepcopy(base)
    zero["injection"]["lines"][0]["dN_dVdt_MeV3_s"] = [0.]*len(base["background"]["time_s"])
    zero["injection"]["power_MeV4_s"] = [0.]*len(base["background"]["time_s"])
    configs["zero"] = zero
    pair = copy.deepcopy(base)
    pair["injection"]["lines"] = [
        {"species": particle, "energy_MeV": 20,
         "dN_dVdt_MeV3_s": (np.array(base["injection"]["power_MeV4_s"])/40).tolist()}
        for particle in ("electron", "positron")]
    pair["injection"]["source"] = "diagnostic charge-neutral 20MeV e-/e+ pairs, same total injected EM power as photon control"
    configs["electron_positron"] = pair
    continuous = copy.deepcopy(base)
    continuous["injection"]["lines"] = []
    continuous["injection"]["energy_MeV"] = [1.5, 2., 4., 5.]
    shape = np.array([0., 1., 1., 0.])
    norm = linear_spectrum_moment(continuous["injection"]["energy_MeV"], shape)
    continuous["injection"]["photon_dN_dVdt_dE_MeV2_s"] = (np.outer(base["injection"]["power_MeV4_s"], shape)/norm).tolist()
    continuous["injection"]["source"] = "diagnostic continuous photons, same total injected power as line control"
    configs["continuous_photons"] = continuous
    dense = copy.deepcopy(base)
    bg = dense["background"]
    t = np.linspace(bg["time_s"][0], bg["time_s"][-1], 9)
    a = np.sqrt(t/t[0])
    bg.update(time_s=t.tolist(), a=a.tolist(), H_s=(.5/t).tolist(),
              T_gamma_MeV=(bg["T_gamma_MeV"][0]/a).tolist(),
              n_b_MeV3=(bg["n_b_MeV3"][0]/a**3).tolist())
    rate = base["injection"]["lines"][0]["dN_dVdt_MeV3_s"][0]/a**3
    dense["injection"]["lines"][0]["dN_dVdt_MeV3_s"] = rate.tolist()
    dense["injection"]["power_MeV4_s"] = (5*rate).tolist()
    configs["photon_time9"] = dense
    summary = {"scope": "DEVELOPMENT_DONOR_VALIDATION_NOT_PHYSICAL_R135",
               "input_file_sha256": sha256(input_path), "controls": {}}
    results = {}
    for name, config in configs.items():
        start = time.perf_counter()
        result = run_electromagnetic_cascade(config, donor_path=args.donor_path, fetch=not args.no_fetch)
        elapsed = time.perf_counter()-start
        results[name] = result
        write_json(args.output / (name + "_input.json"), config)
        write_json(args.output / (name + ".json"), result)
        summary["controls"][name] = {"D_over_H": result["D_over_H"], "Y_p": result["Y_p"],
            "deuterium_Y_final": result["final_Y"][2], "baryon_residual": result["baryon_residual"],
            "wall_seconds": elapsed, "input_sha256": result["input_sha256"],
            "output_sha256": sha256(args.output / (name + ".json")),
            "nonthermal_radiation_fraction": result["energy_ledger"]["nonthermal_density_fraction_max"],
            "composition_change": result["domain_checks"]["max_fractional_p_He4_change"]}
        print(name, f"{elapsed:.3f}s", result["D_over_H"], flush=True)
    effect = results["zero"]["final_Y"][2]-results["photon_150"]["final_Y"][2]
    summary["refinement"] = {
        "energy120_to150_relative_error_in_D_destruction": float(abs(results["photon_120"]["final_Y"][2]-results["photon_150"]["final_Y"][2])/effect),
        "time5_to9_relative_error_in_D_destruction": float(abs(results["photon_120"]["final_Y"][2]-results["photon_time9"]["final_Y"][2])/effect)}
    summary["process_peak_RSS_MiB"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
    summary["donor"] = results["photon_120"]["donor"]
    write_json(args.output / "summary.json", summary)


if __name__ == "__main__":
    main()
