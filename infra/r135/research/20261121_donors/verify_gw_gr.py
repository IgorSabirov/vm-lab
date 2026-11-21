"""Research replay for PR #185. Inputs are the immutable archived histories of PR #159."""
import argparse
import hashlib
import json
import math
import urllib.request
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp

BASE = ("https://raw.githubusercontent.com/IgorSabirov/vm-lab/"
        "c3bc771d1daa292d5d9fd3e1d17bf4d3d6d01c92/"
        "analysis/R135_PHYSICAL_SECTOR_X_20261120/full_run/software/gw/integrated_reference/")
HASHES = {
    "source_on_refined_P7_history.json": "701e44ee50414848ec0de83dc9d35d9b3f1bcbdb24678a70d71bdd7e0824526e",
    "zero_source_P7_history.json": "e70277a924f43d74f2bbfd59ef224bb3046e0d3dc30ffcbfcf65290bca45e519",
    "gw_response.json": "60a129ac631c632c6b3216b446416bbffbc887ada324ca76afb66983c8c54582",
    "gw_channel_status.json": "a688ecc3645af013bf8ff63cda94803b19d4bc37bdee6cf653839d760f3a56fb",
}


def read(cache, name, offline):
    path = cache / name
    if path.is_file():
        raw = path.read_bytes()
    elif offline:
        raise FileNotFoundError(name)
    else:
        with urllib.request.urlopen(BASE + name, timeout=60) as response:
            raw = response.read()
    if hashlib.sha256(raw).hexdigest() != HASHES[name]:
        raise ValueError(f"Changed source {name}")
    if not path.exists():
        path.write_bytes(raw)
    return json.loads(raw)


def arithmetic():
    latent, enthalpy, g = 1.175, 1.471, 16
    beta_h, speed, fluid = 5e5, 0.5, 0.1
    alpha = latent / (math.pi**2 * g / 30)
    trace = latent / (3 * enthalpy)
    x = (8 * math.pi)**(1/3) * speed / (beta_h * fluid)
    xi = 0.441189
    rho_rad = math.pi**2 / 30 * 10.75
    hot = (1.471 - 0.01768) * xi**4
    ideal = math.pi**2 / 30 * 16 * xi**4
    return {
        "hybrid_assumptions": {"Tc_GeV": 1, "beta_over_H": beta_h, "g": g, "kappa": 0.05},
        "alpha_rad_free_gluon_convention": alpha, "alpha_trace_Tc": trace,
        "hybrid_h2Omega": 1.67e-5 / beta_h**2 * (0.05*alpha/(1+alpha))**2 * (100/g)**(1/3),
        "hybrid_frequency_Hz": 1.9e-5 * beta_h / 100 * (g/100)**(1/6),
        "trace_to_one_third_amplitude_fixed_others": (4 * trace / (1+trace))**2,
        "cold_enthalpy_from_combined_latent_over_hot": (enthalpy-latent)/enthalpy,
        "cold_enthalpy_from_phase_entropies_over_hot": 0.2928/enthalpy,
        "H_times_Rstar_over_Uf": x, "Upsilon": -math.expm1(-0.5 * math.log1p(2*x)),
        "xi_for_fraction_example": xi, "hot_EOS_fraction_of_total": hot/(rho_rad+hot),
        "ideal_gas_fraction_of_total": ideal/(rho_rad+ideal)}


def tensor_control():
    # Fourier vector along z, symmetric orthonormal spatial components.
    n = np.array([0., 0., 1.])
    projector = np.eye(3) - np.outer(n, n)
    plus = np.diag([1., -1., 0.])
    def project(stress):
        transverse = projector @ stress @ projector
        return transverse - 0.5 * projector * np.trace(transverse)
    np.testing.assert_allclose(project(np.eye(3)), np.zeros((3, 3)), atol=1e-15)
    np.testing.assert_allclose(project(plus), plus)
    # Radiation era a=eta/10. With mu=a*h, mu''+k^2 mu=1 for the plus polarization.
    k, start = 4., 10.
    end = start + math.pi / (2*k)
    def evolve(t0, t1, y, forcing):
        return solve_ivp(lambda t, z: [z[1], forcing - k*k*z[0]],
                         (t0, t1), y, rtol=1e-11, atol=1e-13, method="DOP853").y[:, -1]
    mu, prime = evolve(start, end, [0., 0.], project(plus)[0, 0])
    np.testing.assert_allclose([mu, prime], [1/k**2, 1/k], rtol=5e-10)
    free = evolve(end, end + math.pi/(2*k), [mu, prime], 0.)
    energy = 0.5 * (prime**2 + (k*mu)**2)
    np.testing.assert_allclose(0.5*(free[1]**2+(k*free[0])**2), energy, rtol=5e-10)
    return {"dimensionless_single_mode": True, "isotropic_TT_norm": 0.,
            "mu_end": round(mu, 10), "mu_prime_end": round(prime, 10),
            "h_plus_end": round(mu/(end/10), 10), "canonical_oscillator_energy": round(energy, 10)}


def indistinguishable_final_spectra():
    # a(t)=sqrt(t); equal comoving injection in disjoint unit-width windows.
    def density(t, start):
        deposited = min(max(t - start, 0.), 1.)
        return deposited / t**2
    early = [density(t, 1.) for t in (2.5, 5.)]
    late = [density(t, 3.) for t in (2.5, 5.)]
    assert early[0] > late[0] and early[-1] == late[-1]
    return {"time": [2.5, 5.], "early_density": early, "late_density": late,
            "scope": "one frequency cell, dimensionless; final spectrum does not identify emission history"}


def archived(files):
    h = files["source_on_refined_P7_history.json"]
    g, a, t = h["gw"], np.array(h["scale_factor"]), np.array(h["time_s"])
    power = np.array(g["power_MeV4_s_per_logq"])
    density = np.array(g["rho_MeV4_per_logq"])
    widths = np.diff(np.log(g["q_frequency_edges_Hz"]))
    np.testing.assert_allclose(density @ widths, g["rho_GW_MeV4"], rtol=2e-13, atol=0)
    # Integrate (linear a)^4 (linear power) exactly on each stored interval (degree 5).
    nodes, weights = np.polynomial.legendre.leggauss(3)
    integral = np.zeros(len(widths))
    for u, w in zip((nodes+1)/2, weights/2):
        au = (1-u)*a[:-1] + u*a[1:]
        pu = (1-u)*power[:-1] + u*power[1:]
        integral += np.sum((w*np.diff(t)*au**4)[:, None]*pu, axis=0)
    change = a[-1]**4*density[-1] - a[0]**4*density[0]
    residual = float(np.max(np.abs(integral-change)/np.maximum(integral, change)))
    if residual > 1e-3:
        raise ValueError("Archived energy balance exceeds its registered tolerance")
    response = files["gw_response.json"]
    H0 = response["H0_s_inv"]
    critical = 3 * (H0 * 6.582119569e-22)**2 / (8*math.pi*6.70883e-45)
    predicted = density[-1]*(a[-1]/response["a_today_in_P7_convention"])**4 / critical
    np.testing.assert_allclose(predicted, response["Omega_GW_today_per_logf"], rtol=2e-13, atol=0)
    zero = files["zero_source_P7_history.json"]
    assert np.count_nonzero(zero["gw"]["rho_MeV4_per_logq"]) == 0
    statuses = files["gw_channel_status.json"]["rows"]
    assert len({r["point_id"] for r in statuses}) == 52
    return {"scope": "archived diagnostic P7 transfer, no new X run",
            "rerendered_integral_Omega_today": float(predicted @ widths),
            "max_relative_cell_energy_residual": residual, "zero_history_max_GW": 0.,
            "open_rows": sum(r["status"] == "OPEN_INPUT" for r in statuses),
            "total_rows": len(statuses)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    files = {name: read(args.cache, name, args.offline) for name in HASHES}
    print(json.dumps({"archive_base": BASE, "sha256": HASHES, "arithmetic": arithmetic(),
                      "tensor_control": tensor_control(), "time_profile": indistinguishable_final_spectra(),
                      "P7": archived(files)}, ensure_ascii=False, indent=2, allow_nan=False))
