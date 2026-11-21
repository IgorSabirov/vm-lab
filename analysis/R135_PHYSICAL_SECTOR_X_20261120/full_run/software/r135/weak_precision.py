"""Scope nonthermal weak-rate validation to the actual rates, spectra and BBN run."""
from __future__ import annotations

import re
import numpy as np

from .common import InputError, canonical_hash, finite
from .neutrino_rates import APPROXIMATION, OMITTED_CORRECTIONS


def compare(item, reference, policy):
    weak = item["weak_rates"]
    if "f_nu_e" not in item["canonical"]["history"]:
        return {"status": "THERMAL_DOMAIN"}
    if weak.get("approximation") == APPROXIMATION or weak.get("production_precision_validated") is False:
        return {"status": "OPEN_INPUT", "reason": "uncertified or Born-only nonthermal rates"}
    if not reference or not policy:
        return {"status": "OPEN_INPUT", "reason": "independent nonthermal benchmark or registered tolerance missing"}
    if reference.get("input_sha256") != canonical_hash(item):
        raise InputError("weak benchmark refers to another BBN input")
    if not reference.get("source") or not re.fullmatch(r"[0-9a-f]{64}", str(reference.get("solver_sha256", ""))):
        raise InputError("weak benchmark needs a versioned independent calculation")
    candidate = weak.get("solver_sha256")
    if not re.fullmatch(r"[0-9a-f]{64}", str(candidate)) or candidate == reference["solver_sha256"]:
        raise InputError("weak benchmark and candidate need distinct solver identities")
    # Flavour evolution belongs to the history producer. Here both rate kernels
    # integrate the identical already supplied electron-flavour distributions.
    required = set(OMITTED_CORRECTIONS) - {"flavour_density_matrix_evolution"}
    if any((not required.issubset(set(r.get("included_corrections", []))) or required.intersection(r.get("omitted_corrections", []))) for r in (weak, reference)):
        return {"status": "OPEN_INPUT", "reason": "nonthermal weak correction budget incomplete"}
    if not np.array_equal(weak["time_s"], reference.get("time_s")) or reference.get("unit") != "s^-1":
        raise InputError("weak benchmark grid or units differ")
    atol = finite(policy.get("atol_s_inv"), "registered weak absolute tolerance", positive=True)
    rtol = finite(policy.get("rtol"), "registered weak relative tolerance", nonnegative=True)
    yp_tol = finite(policy.get("max_abs_delta_Yp"), "registered absolute helium error", positive=True)
    if yp_tol >= 1:
        raise InputError("helium tolerance outside the physical observable range")
    deviations = []
    for key in ("lambda_n_to_p_s_inv", "lambda_p_to_n_s_inv"):
        x, y = np.asarray(weak[key], float), np.asarray(reference.get(key), float)
        if x.shape != y.shape or not np.isfinite(y).all() or np.any(y < 0):
            raise InputError("invalid independent weak rates")
        deviations.append(float(np.max(np.abs(x-y) / (atol + rtol*np.abs(y)))))
    yp = finite(reference.get("Yp"), "independent reference Yp", positive=True)
    err = finite(reference.get("Yp_abs_uncertainty"), "reference helium uncertainty", nonnegative=True)
    if yp >= 1:
        raise InputError("benchmark Yp outside (0,1)")
    return {"status": "RATES_REPRODUCED" if max(deviations) <= 1 else "FAIL_RATE_PRECISION",
            "max_normalized_rate_error": max(deviations), "reference_Yp": yp,
            "reference_Yp_abs_uncertainty": err, "max_abs_delta_Yp": yp_tol,
            "input_sha256": canonical_hash(item), "reference_sha256": canonical_hash(reference)}


def helium_check(comparison, abundances):
    if comparison["status"] != "RATES_REPRODUCED" or set(abundances) != {"linx", "primat"}:
        return {"status": "OPEN_INPUT"}
    errors = {engine: abs(finite(yp, "native Yp") - comparison["reference_Yp"])
              + comparison["reference_Yp_abs_uncertainty"] for engine, yp in abundances.items()}
    return {"status": "PRECISION_VALIDATED" if max(errors.values()) <= comparison["max_abs_delta_Yp"]
            else "FAIL_HELIUM_PRECISION", "absolute_error_bounds": errors,
            "reference_sha256": comparison["reference_sha256"]}
