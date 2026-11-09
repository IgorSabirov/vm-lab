"""Conditional R040 spectral run; no VM submit or ADD-derived claims."""
from __future__ import annotations
import json
import numpy as np
from .model import R040Parameters
from .feshbach import determinant_identity_residual, projected_resolvent_residual, discrete_measure_atoms, bath_density_eff, reduced_measure_sum_rule
from .bic import check_direct_bic, static_loading_invariant
from .continuum import ring_limit_scan, moment_checks
from .poles import solve_second_sheet_pole


def run_spectral(manifest: dict) -> dict:
    m = manifest["model"]
    p = R040Parameters(E_V=float(m["E_V"]), E_1=float(m["E_1"]), E_2=float(m["E_2"]),
                       t_1=float(m["t_1"]), t_2=float(m["t_2"]), gamma_d=float(m["gamma_d"]),
                       kappa=float(m["kappa"]), g=float(m["g"]),
                       bath_onsite=float(m.get("bath_onsite", 0.0)))
    checks_z = [complex(x,y) for x,y in manifest["numerics"]["feshbach_test_points"]]
    determinant_errors = [determinant_identity_residual(z,p) for z in checks_z]
    resolvent_errors = [projected_resolvent_residual(z,p) for z in checks_z]
    bath = p.bath()
    zpoints = [complex(x, y) for x,y in manifest["continuum_scan"]["resolvent_test_points"]]
    nscan = ring_limit_scan(bath, manifest["continuum_scan"]["ring_sizes"], zpoints,
                            reference_energy=p.dark_energy)
    pole_tol = float(manifest["numerics"]["pole_residual_tolerance"])
    poles = [solve_second_sheet_pole(p, complex(*seed), residual_tol=pole_tol)
             for seed in manifest.get("pole_search", {}).get("seeds", [])]
    resolution_by_pole = []
    for index, pole in enumerate(poles):
        if pole.get("width") is not None:
            resolution_by_pole.append({
                "pole_index": index,
                "pole_z": pole["z"],
                "ring_scan": ring_limit_scan(bath, manifest["continuum_scan"]["ring_sizes"], zpoints,
                    reference_energy=complex(*pole["z"]).real,
                    gamma_infinite_chain=float(pole["width"]))
            })
    bic = check_direct_bic(p)
    static_cfg = manifest["loading"]["static_no_load_control"]
    if bic["verdict"] == "BIC_IN_CONDITIONAL_R040_TIGHT_BINDING_MODEL":
        psi_node_2 = np.array([0.0, 0.0, 1.0], dtype=complex)
        static_no_load = static_loading_invariant(
            p, psi_node_2, static_cfg["times"],
            n_bath_sites=int(static_cfg["bath_ring_sites"])
        )
        static_no_load_status = "EXECUTED"
        static_no_load_ok = bool(static_no_load["static_no_loading_pass"])
    else:
        static_no_load = {
            "status": "NOT_APPLICABLE_NO_DIRECT_BIC",
            "reason": "the candidate dark vector is not a direct embedded eigenstate for these inputs; do not test its projector as a protected sector",
            "bath_ring_sites": int(static_cfg["bath_ring_sites"]),
            "finite_bath_is_closed": True,
        }
        static_no_load_status = "NOT_APPLICABLE"
        static_no_load_ok = True
    sample_energies = manifest.get("diagnostics", {}).get("spectral_density_energies", [])
    numerics=manifest["numerics"]
    sum_rule=reduced_measure_sum_rule(p,epsabs=float(numerics["spectral_measure_quad_epsabs"]),
                                      epsrel=float(numerics["spectral_measure_quad_epsrel"]))
    feshbach_pass=(max(determinant_errors)<=float(numerics["determinant_relative_tolerance"])
                   and max(resolvent_errors)<=float(numerics["resolvent_relative_tolerance"]))
    continuum_pass=(nscan[-1]["max_abs_green_error_off_real_axis"]
                    <=float(numerics["off_axis_green_abs_tolerance"]))
    j_eff = [{"energy":float(e),"matrix":bath_density_eff(float(e),p).tolist()}
             for e in sample_energies]
    all_poles_ok = bool(poles) and all(x["status"] in {
        "SECOND_SHEET_RESONANCE", "SECOND_SHEET_POLE_OUTSIDE_BAND_CLASSIFY_SEPARATELY"
    } for x in poles)
    technical_pass = bool(feshbach_pass and sum_rule["continuous_plus_point_sum_rule_pass"]
                          and continuum_pass and all_poles_ok and static_no_load_ok)
    return {
        "schema": 1,
        "experiment": "X26_R040_ANALYTIC_BATH",
        "epistemic_class": "CONDITIONAL_MODEL_RUN_NOT_ADD_DERIVED",
        "input_model": m,
        "direct_bic": bic,
        "feshbach": {
            "max_determinant_identity_relative_residual": max(determinant_errors),
            "max_projected_resolvent_relative_residual": max(resolvent_errors),
            "spectral_measure_sum_rule": sum_rule,
            "discrete_measure_atoms": [
                {"energy":a["energy"],"residue":a["residue"].tolist()}
                for a in discrete_measure_atoms(p)
            ],
            "continuous_density_samples": j_eff,
        },
        "continuum_limit": {
            "ring_scan": nscan,
            "off_axis_green_convergence_pass": bool(continuum_pass),
            "ring_resolution_by_infinite_chain_pole": resolution_by_pole,
            "moment_checks_at_largest_N": moment_checks(bath, max(manifest["continuum_scan"]["ring_sizes"])),
            "warning": "finite rings are closed; Gamma_N is null; no finite-ring irreversible width is inferred",
        },
        "second_sheet_poles": poles,
        "loading": {
            "status": "DYNAMIC_LOADING_NOT_RUN_SEPARATE_PROTOCOL_REQUIRED",
            "static_no_loading_control_status": static_no_load_status,
            "static_no_loading_control": static_no_load,
            "static_no_load_theorem": "for constant H, the exact dark spectral projector has constant population",
            "actuator_and_resource_cost": "NOT_EVALUABLE_UNTIL_CONTROL_AND_RESOURCE_MODEL_ARE_SPECIFIED",
        },
        "technical_checks": {
            "feshbach_identities_pass": bool(feshbach_pass),
            "spectral_measure_sum_rule_pass": bool(sum_rule["continuous_plus_point_sum_rule_pass"]),
            "off_axis_green_convergence_pass": bool(continuum_pass),
            "all_requested_pole_roots_converged": all_poles_ok,
            "static_no_loading_control_pass": (bool(static_no_load["static_no_loading_pass"])
                                                if static_no_load_status == "EXECUTED" else None),
            "static_no_loading_control_applicable": static_no_load_status == "EXECUTED",
            "overall_technical_pass": technical_pass,
        },
        "status": ("TECHNICAL_CHECKS_PASS_CONDITIONAL_R040_MODEL"
                   if technical_pass else "TECHNICAL_CHECKS_FAILED_CONDITIONAL_R040_MODEL"),
    }
