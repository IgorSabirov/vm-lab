"""P8: convert a *computed* history to explicit, traceable solver inputs.

Time is the independent variable throughout. In particular, sorting a reheating
history by photon temperature is forbidden: its weak rates need not be a
single-valued function of that temperature. The native network adapters consume
these time-indexed rates directly (see :mod:`backends`).
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import re

import numpy as np

from .common import (HBARC_MEV_CM, InputError, OpenInput, canonical_hash, finite, read_json,
                     require_input, require_source, sha256, write_json)

SOFTWARE = Path(__file__).resolve().parents[1]
REPO = SOFTWARE.parents[3]
BRIDGE = REPO / "analysis/PRIMAT_LINX_BBN_BRIDGE_20261117"
CORNERS = ("00", "10", "01", "11full", "11add")
SPECIES = ("n", "p", "d", "t", "He3", "a", "Li7", "Be7")
MASSES = np.array([1., 1., 2., 3., 3., 4., 7., 7.])
BASE_FIELDS = ("time_s", "scale_factor", "H_s_inv", "T_gamma_MeV", "n_b_cm3")
CLASS_PRECISION_DIRECTION = {"tol_background_integration": -1, "tol_thermo_integration": -1,
    "tol_perturbations_integration": -1, "tol_tau_approx": -1, "perturbations_sampling_stepsize": -1,
    "l_linstep": -1, "l_logstep": -1, "k_max_tau0_over_l_max": 1, "accurate_lensing": 1}


def validate_class_lmax(value):
    if type(value) is not int or value < 2508:
        raise InputError("native CMB output must declare an integer l_max_scalars >= 2508")
    return value


def validate_gw_scalar_mapping(history, config):
    """A tensor radiation background alone does not fix scalar CMB initial data."""
    from .gravitationalwaves import has_gw_energy
    if not has_gw_energy(history):
        return None
    proof=config.get("gw_scalar_mapping")
    if (not isinstance(proof,dict) or not proof.get("source")
            or proof.get("source_P7_history_sha256")!=bridge_hash(history)
            or proof.get("native_model")!=config.get("perturbation_model",{}).get("kind")
            or proof.get("adiabatic_free_scalar_reduction") is not True):
        raise OpenInput("GW background is already in H; its native scalar CMB reduction needs a separate history-bound applicability calculation")
    return deepcopy(proof)


def validate_class_precision(values):
    if not isinstance(values, dict) or set(values) - set(CLASS_PRECISION_DIRECTION):
        raise InputError("unsupported CLASS precision parameter")
    result = {}
    for name, value in values.items():
        if name == "accurate_lensing":
            if type(value) is not int or value not in (0, 1):
                raise InputError("accurate_lensing must be integer 0 or 1")
        elif name == "l_linstep":
            if type(value) is not int or value < 1:
                raise InputError("l_linstep must be a positive integer")
        else:
            finite(value, name, positive=True)
            if name == "l_logstep" and value <= 1:
                raise InputError("l_logstep must be greater than one")
        result[name] = value
    return result


def bridge_hash(value):
    """The pre-existing bridge uses compact JSON, unlike stage-file hashes."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _array(value, name, n=None, *, positive=False, nonnegative=False):
    a = np.asarray(value, dtype=float)
    if a.ndim != 1 or len(a) < 2 or (n is not None and len(a) != n):
        raise InputError(f"{name}: expected a one-dimensional time series")
    if not np.isfinite(a).all() or (positive and np.any(a <= 0)) or (
            nonnegative and np.any(a < 0)):
        raise InputError(f"{name}: invalid finite/positivity domain")
    return a


def _bridge_validate(doc):
    spec = importlib.util.spec_from_file_location("r135_bbn_contract", BRIDGE / "validate_contract.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.validate_input(doc)
    # Check the structural schema as well when jsonschema is installed; the
    # numerical validator remains mandatory in a minimal environment.
    try:
        import jsonschema
    except ImportError:
        return
    jsonschema.validate(doc, read_json(BRIDGE / "BBN_HISTORY.schema.json"))


def validate_history(history):
    """Validate ordering, units and baryon normalization without assuming cooling."""
    h = deepcopy(history)
    if "neutrino_distribution" in h or "neutrino_spectra" in h:
        raise InputError("supply nonthermal spectra explicitly as f_nu_e and f_antinu_e; opaque distributions cannot be discarded")
    arrays = {k: _array(h.get(k), k, positive=k != "time_s") for k in BASE_FIELDS}
    t = arrays["time_s"]
    if t[0] < 0 or np.any(np.diff(t) <= 0):
        raise InputError("history time_s must be nonnegative and strictly increasing")
    n = len(t)
    if any(len(a) != n for a in arrays.values()):
        raise InputError("history array lengths differ")
    if np.any(np.diff(arrays["scale_factor"]) < 0):
        raise InputError("the expanding BBN branch requires nondecreasing scale_factor")
    # The implemented network has no baryon-number injection. Do not merely
    # discard one when present in a new portal model.
    baryons = arrays["n_b_cm3"] * arrays["scale_factor"] ** 3
    if np.max(np.abs(baryons / baryons[0] - 1)) > 1e-6:
        raise OpenInput("baryon injection requires an explicit network source operator")
    if "T_nu_MeV" in h:
        _array(h["T_nu_MeV"], "T_nu_MeV", n, positive=True)
    for name in ("rho_gamma_MeV4", "rho_nu_MeV4", "rho_extra_MeV4", "p_extra_MeV4"):
        if name in h:
            _array(h[name], name, n, nonnegative=True)
    for name in ("f_nu_e", "f_antinu_e"):
        if name in h:
            spec = h[name]
            values = np.asarray(spec.get("values"), dtype=float)
            if "energy_edges_MeV" in spec:
                if "energy_MeV" in spec:
                    raise InputError("choose cell edges or node samples, not both spectral representations")
                e=np.asarray(spec["energy_edges_MeV"],float)
                if e.ndim==1:e=np.tile(e,(n,1))
                valid=e.ndim==2 and e.shape[0]==n and e.shape[1]>=2 and np.isfinite(e).all() and np.all(e[:,0]==0) and np.all(np.diff(e,axis=1)>0)
                expected=(n,e.shape[1]-1) if valid else None
            else:
                e = _array(spec.get("energy_MeV"), name + ".energy_MeV", positive=True)
                valid=np.all(np.diff(e)>0)
                expected=(n,len(e))
            if not valid or values.shape != expected or not np.isfinite(values).all():
                raise InputError(f"{name}: invalid momentum grid or time/momentum shape")
            if np.any(values < 0) or np.any(values > 1):
                raise InputError(f"{name}: fermion occupation must lie in [0, 1]")
    if ("f_nu_e" in h) != ("f_antinu_e" in h):
        raise OpenInput("both electron neutrino and antineutrino spectra are required")
    return h


def validate_weak_rates(weak, history):
    if not isinstance(weak, dict):
        raise OpenInput("P8 needs calculated weak rates or an explicit thermal closure")
    require_source(weak, "weak_rates")
    if weak.get("unit") != "s^-1":
        raise InputError("weak rates must explicitly use s^-1")
    t = _array(weak.get("time_s"), "weak_rates.time_s")
    if np.any(np.diff(t) <= 0):
        raise InputError("weak-rate time grid must be strictly increasing")
    target = np.asarray(history["time_s"])
    if t[0] > target[0] or t[-1] < target[-1]:
        raise OpenInput("weak-rate table does not cover the computed history")
    for name in ("lambda_n_to_p_s_inv", "lambda_p_to_n_s_inv"):
        _array(weak.get(name), "weak_rates." + name, len(t), nonnegative=True)
    # A derived rate table must identify the distribution it integrated. A
    # supplied temperature alone cannot certify a nonthermal weak calculation.
    if "f_nu_e" in history:
        expected = bridge_hash({name: history[name] for name in ("f_nu_e", "f_antinu_e")})
        if weak.get("neutrino_spectra_sha256") != expected:
            raise OpenInput("weak rates are not bound to the actual nonthermal neutrino spectra")
    return deepcopy(weak)


def adapt_history(history, rates, weak_rates, *, producer, created_utc,
                  source_commits=None, initial_abundances=None, applicability=None):
    """Build a canonical bridge document plus sidecars actually used by solvers."""
    h = validate_history(history)
    weak = validate_weak_rates(weak_rates, h)
    known = set(BASE_FIELDS) | {"T_nu_MeV", "f_nu_e", "f_antinu_e", "rho_X_MeV_cm3",
                              "p_X_MeV_cm3", "Q_Xem_MeV_cm3_s", "Q_Xnu_MeV_cm3_s",
                              "Q_emnu_MeV_cm3_s", "phase_state"}
    canonical_history = {k: deepcopy(v) for k, v in h.items() if k in known}
    doc = {"schema_version": "vm-lab-canonical-bbn-input-v1", "history": canonical_history,
           "rates": deepcopy(rates), "provenance": {
               "history_sha256": bridge_hash(canonical_history), "rates_sha256": bridge_hash(rates),
               "producer": producer, "created_utc": created_utc,
               "source_commits": source_commits or {}}}
    _bridge_validate(doc)
    if tuple(rates["species"]) != SPECIES:
        raise InputError("this adapter implements the registered eight-species network")
    if initial_abundances is None:
        raise OpenInput("initial abundances must come from the frozen preparation/native baseline")
    y0 = np.asarray(initial_abundances, dtype=float)
    if y0.shape != (8,) or not np.isfinite(y0).all() or np.any(y0 < 0) or abs(y0 @ MASSES - 1) > 1e-8:
        raise InputError("initial abundances violate positivity or baryon normalization")
    return {"canonical": doc, "weak_rates": weak, "initial_abundances": y0.tolist(),
            "applicability": applicability or {}, "source_history_sha256": bridge_hash(history),
            "interpolation": {"independent_variable": "physical_time_s", "positive_history": "log_linear_in_time",
                              "weak_rates": "linear_in_time", "outside_domain": "reject"}}


def validate_class_model(config):
    """Only declare CLASS support that is supplied by the actual native engine."""
    model = config.get("perturbation_model")
    if not isinstance(model, dict):
        raise OpenInput("CLASS needs a specified perturbation model, not background H(t) alone")
    require_source(model, "CLASS perturbation_model")
    if model.get("kind") != "standard_free_streaming_after_matching":
        raise OpenInput("custom interacting X perturbations require a separately implemented CLASS sector")
    required = ("all_transfer_finished_before_relevant_modes_enter",
                "adiabatic_initial_perturbations", "massless_collisionless_extra_radiation",
                "no_surviving_interacting_relic")
    if any(model.get(k) is not True for k in required):
        raise OpenInput("the standard CLASS free-streaming reduction is not established for this history")
    if not model.get("domain_proof_source"):
        raise OpenInput("the CLASS reduction needs its applicability argument and source")
    parameters = deepcopy(config.get("parameters", {}))
    for name in ("H0", "omega_b", "omega_cdm", "T_cmb", "tau_reio", "n_s", "A_s", "N_ur"):
        if name not in parameters:
            raise OpenInput(f"CLASS cosmological parameter is not fixed: {name}")
        finite(parameters[name], name, nonnegative=name in ("tau_reio", "N_ur"),
               positive=name not in ("tau_reio", "N_ur"))
    # A private adapter must not accidentally expose the binary's unrestricted
    # file-output or command-line options to a scientific input document.
    allowed = {"H0", "omega_b", "omega_cdm", "T_cmb", "tau_reio", "n_s", "A_s", "N_ur", "YHe"}
    if set(parameters) - allowed:
        raise InputError("unsupported CLASS parameter(s): " + ", ".join(sorted(set(parameters) - allowed)))
    if "YHe" in parameters and not 0 < parameters["YHe"] < 1:
        raise InputError("CLASS YHe must lie in (0,1)")
    return {"perturbation_model": deepcopy(model), "parameters": parameters,
            "precision": validate_class_precision(config.get("precision", {})),
            "l_max_scalars": validate_class_lmax(config.get("l_max_scalars",2508)),
            "spectra": "lensed TT,TE,EE,BB", "Cl_unit": "microK^2"}


def match_class_history(history, config):
    """Derive the radiation and baryon initial data from an actual late P7 slice.

    The record is valid only after e+/- annihilation and completion of all
    relevant energy transfer. A short transition-only history cannot supply it.
    Massive relics and interacting perturbations are explicitly outside this
    native CLASS reduction; their general perturbation equations must be added.
    """
    h = validate_history(history)
    result = validate_class_model(config)
    gw_mapping=validate_gw_scalar_mapping(history,config)
    policy = config.get("matching")
    if not isinstance(policy, dict):
        raise OpenInput("CLASS requires a late matching policy bound to the P7 history")
    require_source(policy, "CLASS matching")
    if policy.get("transfer_finished") is not True or policy.get("electron_annihilation_finished") is not True:
        raise OpenInput("late radiation matching is not established after transfer/electron annihilation")
    index = policy.get("index", -1)
    if isinstance(index, bool) or not isinstance(index, int) or not -len(h["time_s"]) <= index < len(h["time_s"]):
        raise InputError("invalid CLASS matching time index")
    if h["T_gamma_MeV"][index] > .01:
        raise OpenInput("history has not reached the declared late post-annihilation matching domain")
    for k in ("rho_gamma_MeV4", "rho_nu_MeV4", "rho_extra_MeV4", "p_extra_MeV4"):
        if k not in h:
            raise OpenInput(f"CLASS matching needs the calculated {k}")
    rg, rn, rx, px = [float(h[k][index]) for k in
                      ("rho_gamma_MeV4", "rho_nu_MeV4", "rho_extra_MeV4", "p_extra_MeV4")]
    tolerance = finite(policy.get("relative_closure_tolerance", 1e-6), "matching closure tolerance", positive=True)
    if abs(px - rx / 3) > tolerance * max(rg + rn + rx, 1e-300):
        raise OpenInput("P7 retains a nonradiation extra sector; native massless CLASS reduction is invalid")
    tg = h["T_gamma_MeV"][index]
    if abs(rg / (np.pi ** 2 * tg ** 4 / 15) - 1) > tolerance:
        raise InputError("matching photon density is inconsistent with T_gamma")
    n_gamma = 2 * 1.2020569031595942 / np.pi ** 2 * (tg / HBARC_MEV_CM) ** 3
    eta = float(h["n_b_cm3"][index] / n_gamma)
    neff = float((rn + rx) / ((7 / 8) * (4 / 11) ** (4 / 3) * rg))
    result["parameters"]["N_ur"] = neff
    result["matching"] = {"source": policy["source"], "source_history_sha256": bridge_hash(history),
                           "time_s": h["time_s"][index], "T_gamma_MeV": tg,
                           "eta": eta, "N_ur": neff, "rho_nu_convention": "total_all_species",
                           "omega_b_rule": "derived from eta, measured Tcmb and final nuclear composition in P9",
                           "source_policy": policy}
    if gw_mapping is not None:
        result["matching"]["gw_scalar_mapping"]=gw_mapping
    return result


def external_perturbation_input(history, config):
    """Register an external computed-perturbation interface without approximating X."""
    model = config.get("perturbation_model", {})
    require_source(model, "external perturbation model")
    if model.get("kind") != "external_computed_perturbations":
        raise InputError("unknown external perturbation interface")
    producer = config.get("external_solver", {})
    if (not producer.get("repository") or not re.fullmatch(r"[0-9a-f]{40}", str(producer.get("commit", "")))
            or not producer.get("equations_source")):
        raise OpenInput("external perturbation solver needs a registered repository, commit and equations source")
    return {"perturbation_model": deepcopy(model), "external_solver": deepcopy(producer),
            "source_P7_history_sha256": bridge_hash(history),
            "status": "AWAIT_COMPUTED_SPECTRA", "required_spectra": ["TT", "TE", "EE"],
            "lmax": validate_class_lmax(config.get("l_max_scalars",2508)),
            "unit": "microK^2", "convention": "Cl"}


def run(config, inputs, out):
    source_path = require_input(inputs, "channel_history")
    bundle = read_json(source_path)
    units = bundle.get("units", {})
    if any(units.get(k) != v for k, v in {"time": "s", "temperature": "MeV", "density": "MeV^4", "rate": "s^-1"}.items()):
        raise InputError("P7 channel history must declare s, MeV, MeV^4, s^-1 units")
    histories = bundle.get("histories")
    if bundle.get("key") and config.get("_key"):
        for field in ("point_id","model_id","thermal_path"):
            if bundle["key"].get(field)!=config["_key"].get(field):
                raise InputError("P8 received a P7 history from another "+field)
    if not isinstance(histories, dict) or not histories or set(histories) - set(CORNERS):
        raise InputError("P7 histories must be keyed by registered five-corner names")
    if config.get("require_five_corners", True) and set(histories) != set(CORNERS):
        raise OpenInput("the mixed-response experiment requires all five independently evolved histories")
    rate_path = inputs.get("nuclear_rates")
    if rate_path is None:
        from .backends import prepare_native_rates
        rates, reverse = prepare_native_rates(config.get("nuclear_rates_q"))
    else:
        rate_bundle = read_json(rate_path)
        rates, reverse = rate_bundle["rates"], rate_bundle["reverse_alpha_beta_gamma"]
    weak_bundle = read_json(inputs["weak_rates"]) if "weak_rates" in inputs else {}
    prepared, manifest = {}, {}
    for corner, hist in histories.items():
        if config.get("_mode") != "validation":
            # Extending a transition solution to BBN is physics. A 10 H0^-1
            # endpoint at high temperature cannot be relabelled as an abundance.
            if hist["T_gamma_MeV"][-1] > .01:
                raise OpenInput("P7 must cover the registered pre-freezeout through post-BBN temperature interval")
            if hist["T_gamma_MeV"][0] < .8:
                prehistory = config.get("prehistory_baseline", {})
                initial = config.get("initial_abundances", {}).get(corner, config.get("common_initial_abundances"))
                if not prehistory.get("source") or not prehistory.get("history_sha256") or prehistory.get("initial_abundances_sha256") != canonical_hash(initial):
                    raise OpenInput("a late-starting P7 history needs a verified hot-baseline preparation for its initial abundances")
        weak = weak_bundle.get("histories", weak_bundle).get(corner, hist.get("weak_rates"))
        if weak is None and config.get("weak_rates_mode") == "linx_thermal_pointwise":
            if "f_nu_e" in hist or "f_antinu_e" in hist:
                raise OpenInput("a thermal weak-rate closure cannot consume nonthermal spectra")
            from .backends import thermal_weak_rates
            weak = thermal_weak_rates(hist, config.get("thermal_weak", {}))
        if weak is None and config.get("weak_rates_mode") == "born_spectrum_integrals":
            from .neutrino_rates import weak_rates_from_history
            weak = weak_rates_from_history(hist, **config.get("born_weak", {}))
        item = adapt_history(hist, rates, weak, producer="R135 P7 -> P8",
                             created_utc=config.get("created_utc", "2026-11-20T00:00:00Z"),
                             source_commits=config.get("source_commits", {}),
                             initial_abundances=config.get("initial_abundances", {}).get(corner,
                                                  config.get("common_initial_abundances")),
                             applicability=config.get("applicability", {}))
        item["reverse_alpha_beta_gamma"] = reverse
        prepared[corner] = item
        manifest[corner] = {"weak_rates_sha256": canonical_hash(item["weak_rates"]),
                            "canonical_history_sha256": item["canonical"]["provenance"]["history_sha256"],
                            "neutrino_input": "spectra_bound_to_weak_rates" if "f_nu_e" in hist else "thermal",
                            "actual_backend_consumption": False, "status": "PREPARED"}
    class_inputs, limitations = {}, []
    for corner in histories:
        class_config = config.get("class", {})
        specification = deepcopy(class_config.get(corner, class_config))
        if config.get("external_cmb_variants"):
            from .external_cmb import required_lmax
            specification["l_max_scalars"]=max(specification.get("l_max_scalars",2508),
                required_lmax(config["external_cmb_variants"]))
        try:
            kind=specification.get("perturbation_model", {}).get("kind")
            from .gravitationalwaves import has_gw_energy
            if has_gw_energy(histories[corner]) and kind!="external_computed_perturbations":
                name=specification.get("gw_scalar_mapping_input")
                if name not in inputs:
                    raise OpenInput("native CMB for a nonzero GW history needs its verified gw_scalar_mapping_input artifact")
                proof=read_json(inputs[name])
                specification["gw_scalar_mapping"]={**proof,"artifact_sha256":sha256(inputs[name])}
                validate_gw_scalar_mapping(histories[corner],specification)
            if kind == "external_computed_perturbations":
                class_inputs[corner] = external_perturbation_input(histories[corner], specification)
                limitations.append("General X perturbations are supplied as an independently computed, hash-bound spectrum; native equations are not implemented here.")
            elif kind == "class_ethos_idm_idr":
                from .perturbations import match_ethos_history
                class_inputs[corner] = match_ethos_history(histories[corner], specification)
            else:
                class_inputs[corner] = match_class_history(histories[corner], specification)
        except OpenInput as exc:
            class_inputs[corner]={"status":"OPEN_INPUT","missing":[str(exc)]}
            limitations.append("CMB "+corner+": "+str(exc))
        class_inputs[corner]["source_P7_history_sha256"] = bridge_hash(histories[corner])
    payload = {"schema": "R135-bbn-inputs-v1", "source_P7_file_sha256": sha256(source_path),
               "histories": prepared, "applicability": config.get("applicability", {})}
    write_json(out / "bbn_inputs.json", payload)
    write_json(out / "weak_rates_manifest.json", {"schema": "R135-weak-rate-manifest-v1", "histories": manifest})
    write_json(out / "class_inputs.json", {"schema": "R135-class-inputs-v1", "histories": class_inputs})
    write_json(out / "gw_inputs.json", {"schema":"R135-GW-handoff-v1","key":config.get("_key"),
        "source_P7_file_sha256":sha256(source_path),
        "history_sha256":{c:canonical_hash(h) for c,h in histories.items()},
        "GW_history_supplied":{c:isinstance(h.get("gw"),dict) for c,h in histories.items()},
        "GW_energy_already_in_BBN_H":all(isinstance(h.get("gw"),dict) for h in histories.values()),
        "no_second_GW_BBN_density_addition":True,
        "P9_input":"channel_history must name the same saved P7 file; a missing spectrum is not zero"})
    if config.get("weak_rates_mode")=="born_spectrum_integrals":
        limitations.append("Computed nonthermal weak rates include all six Born/static-nucleon processes; radiative, recoil and finite-temperature corrections require a separate accuracy budget.")
    return {"software_status": "PASS", "evidence_status": "DIAGNOSTIC" if config.get("_mode") == "validation" else "CONDITIONAL",
            "metrics": {"prepared_histories": len(prepared), "actual_solver_calls": 0,
                        "open_CMB_histories":sum(x.get("status")=="OPEN_INPUT" for x in class_inputs.values())},
            "limitations": limitations + ["P8 prepares inputs; actual backend consumption is recorded by P9."]}
