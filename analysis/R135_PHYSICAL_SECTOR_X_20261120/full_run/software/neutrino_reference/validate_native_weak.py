#!/usr/bin/env python3
"""Small independent weak-rate comparison, not a BBN or physical-X run.

Use the already pinned LINX environment; --linx-source identifies its checkout.
No source fetching or dependency installation is hidden in this command.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--linx-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    lock = json.loads((Path(__file__).parent/"sources.json").read_text())
    donor = next(row for row in lock["donors"] if row["id"] == "LINX")
    source = args.linx_source.resolve()
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    if revision != donor["commit"]:
        raise RuntimeError("LINX source revision differs from the registered donor")
    for relative, expected in donor["files"].items():
        if hashlib.sha256((source/relative).read_bytes()).hexdigest() != expected:
            raise RuntimeError("LINX source file hash mismatch: "+relative)
    sys.path.insert(0, str(source))
    import numpy as np
    import jax
    jax.config.update("jax_enable_x64", True)
    import jax.numpy as jnp
    from linx.weak_rates import WeakRates
    from linx import const
    from r135.common import write_json
    from r135.neutrino_rates import nucleon_rates, ThermalSpectrum

    temperatures = jnp.array([.3, 1., 3.])
    reference = (jnp.array([.1, 5.]), jnp.array([.1, 5.]))
    born = WeakRates(RC_corr=False, FM_corr=False, weak_mag_corr=False, thermal_corr=False)
    corrected = WeakRates(RC_corr=True, FM_corr=True, weak_mag_corr=True, thermal_corr=False)
    native_born = np.asarray(born.nTOp_rates(temperatures, reference, const.me, jnp.asarray(0.)))/float(const.tau_n)
    native_corrected = np.asarray(corrected.nTOp_rates(temperatures, reference, const.me, jnp.asarray(0.)))/float(const.tau_n)
    rows = []
    for index, temperature in enumerate(np.asarray(temperatures)):
        result = nucleon_rates(float(temperature), ThermalSpectrum(float(temperature)), ThermalSpectrum(float(temperature)),
            neutron_lifetime_s=float(const.tau_n), electron_mass_MeV=float(const.me),
            neutron_proton_gap_MeV=float(const.mn-const.mp))
        ours = np.array([result["lambda_n_to_p_s_inv"], result["lambda_p_to_n_s_inv"]])
        rows.append({"T_gamma_MeV": float(temperature), "T_nu_MeV": float(temperature),
            "R135_Born_s_inv": ours.tolist(), "LINX_Born_s_inv": native_born[:, index].tolist(),
            "relative_Born_difference": (ours/native_born[:, index]-1).tolist(),
            "LINX_Coulomb_RC_FM_WM_no_thermal_s_inv": native_corrected[:, index].tolist(),
            "selected_correction_fraction": (native_corrected[:, index]/ours-1).tolist(),
            "R135_quadrature_abs_error_s_inv": result["quadrature_abs_error_s_inv"]})
    maximum = max(abs(value) for row in rows for value in row["relative_Born_difference"])
    if maximum > 5e-5:
        raise RuntimeError(f"Born cross-check failed: relative discrepancy {maximum}")
    output = {"schema": "r135-native-born-comparison-v1", "donor_commit": revision,
        "r135_source_sha256": {"r135/neutrino_rates.py": hashlib.sha256((ROOT/"r135/neutrino_rates.py").read_bytes()).hexdigest()},
        "donor_file_sha256": donor["files"], "python": platform.python_version(),
        "versions": {name: importlib.metadata.version(name) for name in ("numpy", "scipy", "jax", "jaxlib", "equinox")},
        "constants": {"electron_mass_MeV": float(const.me),
                      "neutron_proton_gap_MeV": float(const.mn-const.mp), "neutron_lifetime_s": float(const.tau_n)},
        "rate_order": ["n_to_p", "p_to_n"], "rows": rows,
        "maximum_Born_relative_difference": maximum, "Born_comparison_threshold": 5e-5,
        "status": "PASS_BORN_COMPARISON", "production_precision_validated": False,
        "interpretation": "Independent 1000-point LINX Born quadrature compared with adaptive six-process integration. Selected correction differences are a diagnostic, not an uncertainty bound for arbitrary spectra. Thermal radiative corrections are off in both donor runs."}
    write_json(args.output, output)
    print(json.dumps({"status": output["status"], "maximum_Born_relative_difference": maximum,
                      "selected_correction_fraction": [row["selected_correction_fraction"] for row in rows],
                      "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
