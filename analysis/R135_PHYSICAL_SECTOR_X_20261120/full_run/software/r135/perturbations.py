"""History-bound ETHOS matching to the *existing*, pinned CLASS equations.

This is an adapter for one cold stable species elastically scattering on thermal
massless dark radiation, not a generic X perturbation solver. It never substitutes
an independent X density or opacity for the calculated P7 history. Equations,
positive-opacity convention and the deliberately limited domain are documented
in NUMERICS_PERTURBATIONS.md. Native CLASS evolves the metric and all species.
"""
from __future__ import annotations

from copy import deepcopy
import math
import re

import numpy as np

from .common import HBARC_MEV_CM, InputError, OpenInput, canonical_hash, finite, require_source

MODEL_KIND = "class_ethos_idm_idr"
CLASS_COMMIT = "e85808324f51fc694d12e3ed7439552a3c3f9540"
MPC_OVER_C_S = 3.085677581282e22 / 2.99792458e8
KB_MEV_K = 8.617333262145e-11
ONE_NEUTRINO_FACTOR = (7 / 8) * (4 / 11) ** (4 / 3)
BASE_PARAMETERS = {"H0", "omega_b", "omega_cdm", "T_cmb", "tau_reio", "n_s", "A_s", "N_ur", "YHe"}
HISTORY_FIELDS = ("time_s", "scale_factor", "H_s_inv", "T_gamma_MeV", "n_b_cm3",
                  "rho_gamma_MeV4", "rho_nu_MeV4", "rho_extra_MeV4", "p_extra_MeV4",
                  "rho_idm_MeV4", "p_idm_MeV4", "rho_idr_MeV4", "p_idr_MeV4",
                  "Gamma_idr_idm_s_inv", "Gamma_idm_idr_s_inv", "Gamma_idr_self_s_inv")
REQUIRED_DOMAIN = ("cold_nonrelativistic_idm", "thermal_massless_idr", "elastic_scattering_only",
                   "adiabatic_initial_perturbations", "no_late_particle_production_or_decay",
                   "early_background_continuation_validated", "cold_pressure_negligible_on_requested_scales",
                   "massless_neutrino_background")


def photon_omega(T_cmb_K):
    """omega_gamma using the constants of pinned CLASS input.c/background.h.

    Using the same declared normalization avoids a hidden rounding mismatch in
    the R135-to-CLASS density conversion. These are the donor's CODATA constants,
    not a new fit to an observed energy budget.
    """
    temperature = finite(T_cmb_K, "T_cmb", positive=True)
    c, g, kb, hp, mpc = 2.99792458e8, 6.67428e-11, 1.3806504e-23, 6.62606896e-34, 3.085677581282e22
    sigma = 2 * math.pi ** 5 * kb ** 4 / (15 * hp ** 3 * c ** 2)
    return (4 * sigma / c * temperature ** 4) / (3 * c ** 2 * 1e10 / mpc ** 2 / (8 * math.pi * g))


def conformal_opacity_Mpc_inv(physical_rate_s_inv, a_today):
    """Positive physical momentum-transfer rate -> CLASS conformal opacity."""
    return (finite(physical_rate_s_inv, "physical momentum rate", nonnegative=True)
            * finite(a_today, "a/a_today", positive=True) * MPC_OVER_C_S)


def ethos_opacity_Mpc_inv(z, omega_idm, a_idm_dr, n_index):
    """CLASS convention, dmu = omega_idm*a_idm_dr*((1+z)/1e7)**n."""
    redshift = finite(z, "redshift", nonnegative=True)
    density = finite(omega_idm, "omega_idm", positive=True)
    amplitude = finite(a_idm_dr, "a_idm_dr", nonnegative=True)
    power = finite(n_index, "n_index", nonnegative=True)
    return density * amplitude * ((1 + redshift) / 1e7) ** power


def collision_drag(theta_idm, theta_idr, rho_idm, rho_idr, opacity_Mpc_inv):
    """The two Euler collision terms; rho_m*C_m + 4*rho_r*C_r/3 = 0.

    Density units may be any common unit, theta is in inverse conformal-length
    units and the returned derivatives use inverse conformal length squared.
    Gravity, Hubble drag, pressure and hierarchy streaming are evolved by CLASS.
    """
    tm, tr = finite(theta_idm, "theta_idm"), finite(theta_idr, "theta_idr")
    rm = finite(rho_idm, "rho_idm", positive=True)
    rr = finite(rho_idr, "rho_idr", nonnegative=True)
    rate = finite(opacity_Mpc_inv, "conformal opacity", nonnegative=True)
    radiation = rate * (tm - tr)
    return {"idm": -(4 * rr / (3 * rm)) * radiation, "idr": radiation}


def _array(h, name, n):
    if name not in h:
        raise OpenInput(f"ETHOS matching requires calculated P7 {name}")
    values = np.asarray(h[name], dtype=float)
    if values.shape != (n,) or not np.isfinite(values).all() or np.any(values < 0):
        raise InputError(f"{name}: expected a finite nonnegative history of length {n}")
    return values


def _constant(values, name, tolerance, *, zero_allowed=False):
    values = np.asarray(values)
    reference = float(np.median(values))
    if reference == 0:
        if not zero_allowed or np.any(values != 0):
            raise OpenInput(f"{name}: zero or changing support is not a single ETHOS power law")
        return 0., 0.
    error = float(np.max(np.abs(values / reference - 1)))
    if error > tolerance:
        raise OpenInput(f"{name}: P7 matching residual {error:.6g} exceeds {tolerance:.6g}")
    return reference, error


def _model(config):
    model = deepcopy(config.get("perturbation_model", {}))
    require_source(model, "ETHOS perturbation model")
    if model.get("kind") != MODEL_KIND:
        raise InputError("wrong interacting perturbation model")
    if not isinstance(model.get("domain_proof_source"), str) or not model["domain_proof_source"].strip():
        raise OpenInput("ETHOS needs a model-specific early continuation/domain proof")
    missing = [name for name in REQUIRED_DOMAIN if model.get(name) is not True]
    if missing:
        raise OpenInput("ETHOS applicability is not established: " + ", ".join(missing))
    micro = deepcopy(model.get("microphysics", {}))
    require_source(micro, "ETHOS angular/mass coefficients")
    mass = finite(micro.get("m_idm_eV"), "m_idm_eV", positive=True)
    if mass < 1e6:
        raise OpenInput("pinned CLASS has only tested its cold IDM formalism for m_idm >= 1 MeV")
    power = finite(micro.get("n_index_idm_dr"), "n_index_idm_dr", nonnegative=True)
    if power not in (0., 2., 4.):
        raise OpenInput("this tested ETHOS adapter admits only n_index_idm_dr = 0, 2, 4")
    nature = micro.get("idr_nature")
    if nature not in ("fluid", "free_streaming"):
        raise InputError("idr_nature must be fluid or free_streaming")
    if nature == "fluid" and (model.get("fluid_limit_validated") is not True or
                               not model.get("fluid_limit_source")):
        raise OpenInput("perfect-fluid DR requires a sourced self-scattering/fluid-limit proof")
    stat = finite(micro.get("stat_f_idr"), "stat_f_idr", positive=True)
    if stat not in (1., 7 / 8):
        raise OpenInput("stat_f_idr must be 1 (bosonic) or 7/8 (fermionic), with two reference degrees of freedom")
    angular = {}
    for name in ("alpha_idm_dr", "beta_idr"):
        values = micro.get(name)
        if not isinstance(values, list) or not 1 <= len(values) <= 16:
            raise OpenInput(f"{name}: supply 1..16 sourced multipole coefficients, last value repeats")
        angular[name] = ",".join(format(finite(v, name, positive=True), ".17g") for v in values)
    return model, {"m_idm": mass, "n_index_idm_dr": power, "idr_nature": nature,
                   "stat_f_idr": stat, "idm_soundspeed": "no", **angular}


def _base_parameters(config):
    p = deepcopy(config.get("parameters", {}))
    if set(p) - BASE_PARAMETERS:
        raise InputError("X density/opacities and unrestricted CLASS controls cannot override P7 matching")
    for name in ("H0", "omega_b", "omega_cdm", "T_cmb", "tau_reio", "n_s", "A_s"):
        if name not in p:
            raise OpenInput(f"missing registered cosmological parameter {name}")
        p[name] = finite(p[name], name, nonnegative=name in ("omega_cdm", "tau_reio"),
                         positive=name not in ("omega_cdm", "tau_reio"))
    if "N_ur" in p:
        finite(p["N_ur"], "N_ur", nonnegative=True)
    if "YHe" in p and not 0 < finite(p["YHe"], "YHe") < 1:
        raise InputError("YHe must be in (0,1)")
    return p


def _prepare(history, config, source_history_sha256):
    from .observations import validate_history, validate_class_precision
    h = validate_history(history)
    model, species_parameters = _model(config)
    parameters = _base_parameters(config)
    policy = deepcopy(config.get("matching", {}))
    require_source(policy, "ETHOS matching")
    for name in ("homogeneous_transfer_finished", "electron_annihilation_finished"):
        if policy.get(name) is not True:
            raise OpenInput(f"ETHOS matching requires {name}; elastic momentum drag remains allowed")
    n = len(h["time_s"])
    start, stop = policy.get("start_index", n - 3), policy.get("index", n - 1)
    if type(start) is not int or type(stop) is not int or not -n <= start < n or not -n <= stop < n:
        raise InputError("ETHOS matching indices are invalid")
    start, stop = start % n, stop % n
    if stop - start < 2:
        raise OpenInput("ETHOS matching requires at least three samples across expansion")
    sl = slice(start, stop + 1)
    series = {name: _array(h, name, n)[sl] for name in HISTORY_FIELDS}
    tolerance = finite(policy.get("relative_closure_tolerance", 1e-6), "ETHOS closure tolerance", positive=True)
    if tolerance > 1e-3:
        raise InputError("ETHOS matching closure tolerance cannot exceed 1e-3")
    tg, scale = series["T_gamma_MeV"], series["scale_factor"]
    if np.max(tg) > .01 or np.min(tg) <= 0:
        raise OpenInput("ETHOS matching must be after e+/- annihilation, T_gamma <= .01 MeV")
    if scale[-1] / scale[0] < 1.1:
        raise OpenInput("a single nearly static slice does not test the background power laws; need a span >= 1.1")
    residuals = {}
    _, residuals["photon_entropy"] = _constant(tg * scale, "T_gamma*a", tolerance)
    a_today = parameters["T_cmb"] * KB_MEV_K / tg
    if np.any(a_today >= 1):
        raise OpenInput("ETHOS matching belongs to the pre-present cosmology")
    rg, rn = series["rho_gamma_MeV4"], series["rho_nu_MeV4"]
    rm, rr = series["rho_idm_MeV4"], series["rho_idr_MeV4"]
    pm, pr = series["p_idm_MeV4"], series["p_idr_MeV4"]
    if np.any(rg <= 0) or np.any(rm <= 0) or np.any(rr <= 0):
        raise OpenInput("this interacting family requires positive photon, IDM and IDR densities")
    residuals["photon_density"] = float(np.max(np.abs(rg / (math.pi ** 2 * tg ** 4 / 15) - 1)))
    residuals["extra_density_partition"] = float(np.max(np.abs(series["rho_extra_MeV4"] / (rm + rr) - 1)))
    residuals["extra_pressure_partition"] = float(np.max(np.abs(series["p_extra_MeV4"] - pm - pr) / (rm + rr)))
    residuals["idr_equation_of_state"] = float(np.max(np.abs(3 * pr / rr - 1)))
    pressure_limit = finite(policy.get("maximum_idm_w", 1e-6), "maximum_idm_w", positive=True)
    if pressure_limit > 1e-5:
        raise InputError("pressureless CLASS matching cannot admit maximum_idm_w > 1e-5")
    if np.max(pm / rm) > pressure_limit:
        raise OpenInput("P7 IDM pressure is outside the declared pressureless perturbation limit")
    for name, error in residuals.items():
        if error > tolerance:
            raise OpenInput(f"{name}: background is incompatible with ETHOS ({error:.6g})")
    omega_g = photon_omega(parameters["T_cmb"])
    om, residuals["omega_idm_constancy"] = _constant(rm / rg * omega_g / a_today, "rho_idm*a^3", tolerance)
    nr, residuals["N_idr_constancy"] = _constant(rr / (ONE_NEUTRINO_FACTOR * rg), "rho_idr*a^4", tolerance)
    nu, residuals["N_ur_constancy"] = _constant(rn / (ONE_NEUTRINO_FACTOR * rg), "rho_nu*a^4", tolerance, zero_allowed=True)
    tidr = (rr / rg / species_parameters["stat_f_idr"]) ** .25 * tg
    if np.max(tidr / (species_parameters["m_idm"] * 1e-6)) > 1e-3:
        raise OpenInput("the thermal DR momentum is not small compared with the IDM mass")
    # The native solver uses ordinary flat FLRW, not an arbitrary H(t). Check
    # that matching this density history actually reproduces the supplied clock.
    # A 1e-3 ceiling covers the donor's old constants and the still provisional
    # baryonic mass normalization; it is not an observational precision claim.
    wr = omega_g * (1 + ONE_NEUTRINO_FACTOR * (nr + nu))
    wm = parameters["omega_b"] + parameters["omega_cdm"] + om
    vacuum = (parameters["H0"] / 100) ** 2 - wr - wm
    h_class = (1e5 / 3.085677581282e22) * np.sqrt(wr / a_today ** 4 + wm / a_today ** 3 + vacuum)
    residuals["flat_FLRW_clock"] = float(np.max(np.abs(series["H_s_inv"] / h_class - 1)))
    if residuals["flat_FLRW_clock"] > 1e-3:
        raise OpenInput("P7 H(t) differs from the matched CLASS flat-FLRW density history")
    power = species_parameters["n_index_idm_dr"]
    shape = (1 / a_today / 1e7) ** power
    dr_rate, dm_rate = series["Gamma_idr_idm_s_inv"], series["Gamma_idm_idr_s_inv"]
    reciprocal = 4 * rr / (3 * rm) * dr_rate
    denom = np.maximum(np.maximum(dm_rate, reciprocal), 1e-300)
    residuals["momentum_action_reaction"] = float(np.max(np.abs(dm_rate - reciprocal) / denom))
    if residuals["momentum_action_reaction"] > tolerance:
        raise OpenInput("the P6/P7 drag rates do not conserve the summed IDM/IDR momentum")
    amp, residuals["idm_idr_power_law"] = _constant(dr_rate * a_today * MPC_OVER_C_S / (om * shape),
                                                   "a_idm_dr", tolerance, zero_allowed=True)
    omega_idr = nr * ONE_NEUTRINO_FACTOR * omega_g
    bamp, residuals["idr_self_power_law"] = _constant(series["Gamma_idr_self_s_inv"] * a_today * MPC_OVER_C_S /
                                                       (omega_idr * shape), "b_idr", tolerance, zero_allowed=True)
    if amp == 0 and bamp > 0 and species_parameters["idr_nature"] == "free_streaming":
        raise OpenInput("zero IDM opacity with finite IDR self opacity is not in the tested pinned CLASS branch")
    kmax = finite(policy.get("relevant_k_max_Mpc_inv"), "relevant_k_max_Mpc_inv", positive=True)
    if kmax < 1:
        raise InputError("the l<=2508 CMB adapter requires a declared relevant k range covering at least 1/Mpc")
    max_kah = finite(policy.get("maximum_k_over_aH", .05), "maximum_k_over_aH", positive=True)
    if max_kah > .1:
        raise InputError("ETHOS adiabatic early continuation must be tested outside the horizon (k/aH <= .1)")
    kah = kmax / (a_today * series["H_s_inv"] * MPC_OVER_C_S)
    if np.max(kah) > max_kah:
        raise OpenInput("P7 matching is too late for the registered adiabatic superhorizon continuation")
    if species_parameters["idr_nature"] == "fluid":
        self_opacity = series["Gamma_idr_self_s_inv"] * a_today * MPC_OVER_C_S
        fluid_ratio = self_opacity / np.maximum(kmax, a_today * series["H_s_inv"] * MPC_OVER_C_S)
        if np.min(fluid_ratio) < 100:
            raise OpenInput("fluid DR needs an actual self-scattering opacity >=100*max(k_max,aH), plus the sourced late-time proof")
    ng = 2 * 1.2020569031595942 / math.pi ** 2 * (tg / HBARC_MEV_CM) ** 3
    eta, residuals["eta_constancy"] = _constant(series["n_b_cm3"] / ng, "eta", tolerance)
    parameters.update(species_parameters)
    parameters.update(omega_idm=om, N_idr=nr, N_ur=nu, a_idm_dr=amp, b_idr=bamp)
    matching = {"source": policy["source"], "source_history_sha256": source_history_sha256,
                "indices": [start, stop], "time_s": float(series["time_s"][-1]),
                "T_gamma_MeV": float(tg[-1]), "eta": eta, "N_ur": nu, "N_idr": nr,
                "omega_idm": om, "a_idm_dr_Mpc_inv": amp, "b_idr_Mpc_inv": bamp,
                "maximum_k_over_aH_measured": float(np.max(kah)), "maximum_idm_w_measured": float(np.max(pm / rm)),
                "residuals": residuals, "source_policy": policy,
                "rho_nu_convention": "total_all_massless_standard_species; IDR separate",
                "omega_b_rule": "derived from eta, measured Tcmb and final nuclear composition in P9",
                "scope": "conditional stable cold IDM + thermal massless IDR with sourced ETHOS continuation"}
    if species_parameters["idr_nature"] == "fluid":
        matching["minimum_fluid_self_scattering_over_k_or_aH"] = float(np.min(fluid_ratio))
    return {"perturbation_model": model, "parameters": parameters,
            "precision": validate_class_precision(config.get("precision", {})),
            "l_max_scalars": 2508, "spectra": "lensed TT,TE,EE,BB", "Cl_unit": "microK^2",
            "matching": matching, "class_source_commit": CLASS_COMMIT}


def match_ethos_history(history, config):
    """Derive all X densities/opacities from the supplied, conserved P7 history.

    The source/domain proof is still a model-specific physical input; checking
    numerical consistency is not proof that a particular X has this microphysics.
    """
    from .observations import bridge_hash
    digest = bridge_hash(history)
    result = _prepare(history, config, digest)
    evidence_history = {name: deepcopy(history[name]) for name in HISTORY_FIELDS}
    evidence_config = {name: deepcopy(config[name]) for name in ("perturbation_model", "parameters", "matching")}
    evidence = {"history": evidence_history, "config": evidence_config, "source_P7_history_sha256": digest}
    result["ethos_matching_evidence"] = evidence
    result["ethos_matching_evidence_sha256"] = canonical_hash(evidence)
    result["source_P7_history_sha256"] = digest
    return result


def validate_ethos_input(doc):
    """Recompute the handoff from saved evidence, rejecting independent overrides.

    P9 is allowed to update omega_b from BBN and YHe from computed abundances;
    every X, primordial and expansion input remains bound to the matching record.
    """
    from .observations import validate_class_precision
    evidence = doc.get("ethos_matching_evidence")
    if not isinstance(evidence, dict) or canonical_hash(evidence) != doc.get("ethos_matching_evidence_sha256"):
        raise OpenInput("ETHOS native input lacks intact P7 matching evidence")
    digest = evidence.get("source_P7_history_sha256", "")
    if not re.fullmatch(r"[0-9a-f]{64}", digest) or doc.get("source_P7_history_sha256") != digest:
        raise InputError("ETHOS input and P7 history provenance differ")
    expected = _prepare(evidence["history"], evidence["config"], digest)
    parameters = doc.get("parameters", {})
    permitted = set(expected["parameters"]) | {"YHe"}
    if set(parameters) - permitted or set(expected["parameters"]) - set(parameters):
        raise InputError("unsupported or missing CLASS ETHOS parameters")
    for name, value in expected["parameters"].items():
        if name not in ("omega_b", "YHe") and parameters[name] != value:
            raise InputError(f"CLASS {name} was changed independently of its P7/model evidence")
    finite(parameters["omega_b"], "BBN omega_b", positive=True)
    if "YHe" in parameters and not 0 < finite(parameters["YHe"], "YHe") < 1:
        raise InputError("YHe must be in (0,1)")
    matching = deepcopy(doc.get("matching", {}))
    bbn_fields = {"omega_b", "late_isotope_masses_g", "abundances_sha256"}
    present = set(matching) & bbn_fields
    if present:
        if present != bbn_fields:
            raise InputError("incomplete BBN baryon-mass provenance in ETHOS handoff")
        if matching["omega_b"] != parameters["omega_b"]:
            raise InputError("CLASS omega_b differs from the BBN-matched value")
        masses = np.asarray(matching["late_isotope_masses_g"], dtype=float)
        if masses.shape != (8,) or not np.isfinite(masses).all() or np.any(masses <= 0):
            raise InputError("invalid BBN isotope mass record")
        if not re.fullmatch(r"[0-9a-f]{64}", str(matching["abundances_sha256"])):
            raise InputError("missing BBN abundance hash for updated omega_b")
        for name in bbn_fields:
            matching.pop(name)
    elif parameters["omega_b"] != expected["parameters"]["omega_b"]:
        raise InputError("omega_b changed without the computed BBN mass/provenance record")
    if matching != expected["matching"]:
        raise InputError("ETHOS matching does not match its independently reconstructed evidence")
    for key in ("perturbation_model", "class_source_commit"):
        if doc.get(key) != expected[key]:
            raise InputError(f"ETHOS {key} does not match its independently reconstructed evidence")
    result = deepcopy(doc)
    result["precision"] = validate_class_precision(doc.get("precision", {}))
    return result
