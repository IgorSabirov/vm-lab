"""Pinned CAMB 1.6.5 / RECFAST 1.5.2 adapter for the R143 matched-background run.

Importing this file and creating parameter objects do not evolve a history.
Call build_background only after the common run contract has been frozen.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping

import camb
import numpy as np

CAMB_SOURCE_SHA = "53c1f1c0208f75223cf3da2b163187deb7310f42"
CAMB_VERSION = "1.6.5"
RECFAST_PARAMETERS = {
    "RECFAST_fudge": 1.125,
    "RECFAST_fudge_He": 0.86,
    "RECFAST_Heswitch": 6,
    "RECFAST_Hswitch": True,
    "AGauss1": -0.14,
    "AGauss2": 0.079,
    "zGauss1": 7.28,
    "zGauss2": 6.73,
    "wGauss1": 0.18,
    "wGauss2": 0.33,
}


def params_from_cosmology(
    *, H0: float, Omega_b: float, Omega_c: float, Omega_k: float,
    Yp: float, Tcmb: float, Neff: float,
    accuracy_boost: float = 1.0,
    background_timestep_boost: float = 1.0,
    integration_tolerance_boost: float = 1.0,
):
    """Every abundance, curvature and neutrino input is explicit.

    Omega_b/c are density fractions today; Yp is the helium mass fraction.
    Dark energy is a cosmological constant, and closure is performed by CAMB.
    The three boost controls do not change RECFAST's compile-time Nz/tol.
    """
    if camb.__version__ != CAMB_VERSION:
        raise RuntimeError(f"Expected CAMB {CAMB_VERSION}, found {camb.__version__}")
    h = H0 / 100.0
    p = camb.CAMBparams()
    p.set_cosmology(
        H0=H0, ombh2=Omega_b * h*h, omch2=Omega_c * h*h,
        omk=Omega_k, YHe=Yp, TCMB=Tcmb,
        mnu=0.0, num_massive_neutrinos=0, nnu=Neff,
        standard_neutrino_neff=Neff, meffsterile=0.0,
        neutrino_hierarchy="degenerate",
    )
    p.set_dark_energy(w=-1.0, wa=0.0, dark_energy_model="fluid")
    p.Recomb = camb.recombination.Recfast(**RECFAST_PARAMETERS)
    p.Reion.Reionization = False
    p.WantCls = False
    p.WantTransfer = False
    p.WantDerivedParameters = False
    p.DoLensing = False
    p.NonLinear = camb.model.NonLinear_none
    p.Accuracy.AccuracyBoost = accuracy_boost
    p.Accuracy.BackgroundTimeStepBoost = background_timestep_boost
    p.Accuracy.IntTolBoost = integration_tolerance_boost
    assert p.YHe == Yp and p.num_nu_massive == 0 and p.omnuh2 == 0.0
    assert p.num_nu_massless == Neff and not p.Reion.Reionization
    return p


def abundance_normalization(params) -> dict:
    """Use exactly the mass and gravitational constants in CAMB 1.6.5."""
    c = camb.constants
    ratio = c.m_He4 / c.m_H
    nH_coefficient_cm3 = 3.0 * (1e5 / c.Mpc)**2 / (8*np.pi*c.G*c.m_H) / 1e6
    return {
        "Yp_mass_fraction": float(params.YHe),
        "m_H_kg": float(c.m_H),
        "m_He4_kg": float(c.m_He4),
        "mHe_over_mH": float(ratio),
        "G_SI": float(c.G),
        "Mpc_m": float(c.Mpc),
        "c_m_s": float(c.c),
        "nH_coefficient_cm3": float(nH_coefficient_cm3),
        "nH0_cm3": float(nH_coefficient_cm3 * params.ombh2 * (1-params.YHe)),
        "fHe": float(params.YHe / (ratio * (1-params.YHe))),
        "xe_definition": "n_e/n_H (hydrogen nuclei)",
    }


def build_background(params):
    """Run RECFAST and construct the CAMB thermodynamic background."""
    return camb.get_background(params, no_thermo=False)


def hubble_s(data, z):
    """Exact CAMB H(z), converted from km/s/Mpc to s^-1; no H interpolation."""
    return data.hubble_parameter(z) / (camb.constants.Mpc / 1000.0)


def sample_history(data, z) -> dict:
    z = np.asarray(z, dtype=np.float64)
    if z.ndim != 1 or not np.all(np.isfinite(z)) or np.any(z < 0):
        raise ValueError("z must be a finite nonnegative 1D array")
    thermal = data.get_background_redshift_evolution(z, vars=["x_e", "T_b"], format="dict")
    return {
        "z": z,
        "a": 1.0/(1.0+z),
        "xe": np.asarray(thermal["x_e"]),
        "Tm_K": np.asarray(thermal["T_b"]),
        "H_s": np.asarray(hubble_s(data, z)),
    }


def installation_metadata() -> dict:
    root = Path(camb.__file__).resolve().parent
    lib = root / "camblib.so"
    result = {
        "camb_version": camb.__version__,
        "camb_source_sha": CAMB_SOURCE_SHA,
        "recfast_version": "Recfast_1.5.2",
        "module_path": str(root),
        "library_sha256": hashlib.sha256(lib.read_bytes()).hexdigest(),
        "recfast_parameters": RECFAST_PARAMETERS,
        "base_RECFAST_Nz": 10000,
        "base_RECFAST_zinitial": 10000.0,
        "base_RECFAST_delta_z": 1.0,
        "base_RECFAST_DVERK_tolerance": 1e-5,
    }
    profile = root / "R143_BUILD.json"
    if profile.is_file():
        result["compiled_build"] = json.loads(profile.read_text())
    else:
        result["compiled_build"] = {
            "profile": "published_wheel",
            "RECFAST_Nz": 10000,
            "RECFAST_delta_z": 1.0,
            "RECFAST_DVERK_tolerance": 1e-5,
        }
    return result
