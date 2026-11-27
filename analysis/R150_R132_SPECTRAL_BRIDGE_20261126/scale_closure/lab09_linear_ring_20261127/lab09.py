"""Acceptance for the linear 6+1 ring in 09-LAB.

The prediction is the exact locked operator
H = A ⊕ ν_p + g|0><p| + g*|p><0|.
Port weights and frequencies are compared with that spectrum.
Ideal weights 0, 1/2 and 1 are a rejected predicate: at σ = 5e-6 they fail
the known-answer kits even though the exact residuals are numerical noise.

A synthetic pass does not trace a frequency unit and does not close
09-LAB-SCALE, 09-LAB-OP, SCALE-09…12 or scientific acceptance.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import hf_recovery

LINES_MHZ = np.array([6588.8172, 6627.8914, 6713.2201, 6791.6168])
Z_MAX = 5.0
WEIGHT_SIGMA = 5e-6
FREQ_SIGMA_MHZ = 1e-6
# Published digitized window for the neighbour element, not an instrument budget.
NEIGHBOUR_WINDOW_MHZ = (48.004, 48.032)

# Multisets printed with the known-answer run. Locked so a basis change that
# still represents the same observable still has to match these weights.
PUBLISHED_WEIGHTS = {
    "detuned": np.array([
        0.0013302900994615816, 0.998211250348446, 3.686708844281637e-24,
        0.00042791715658770243, 1.5522474298747216e-23,
        2.6002896799517862e-05, 4.5394987055991794e-06]),
    "resonant_one_doublet": np.array([
        4.366500962638102e-06, 0.5000538428669501, 2.092202133122534e-22,
        0.4999397106820886, 4.82916433294447e-22, 1.83124884144884e-06,
        2.4870115681247343e-07]),
}


def jsonable(value):
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return jsonable(value.tolist())
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def circulant_coefficients(nu=LINES_MHZ):
    """Inverse Fourier map used by SCALE09_LAB_PLAN for the symmetric ring."""
    nu0, nu1, nu2, nu3 = [float(x) for x in nu]
    return np.array([
        (nu3 + 2 * nu2 + 2 * nu1 + nu0) / 6,
        (-nu0 - nu1 + nu2 + nu3) / 6,
        (nu0 - nu1 - nu2 + nu3) / 6,
        (-nu0 + 2 * nu1 - 2 * nu2 + nu3) / 6,
    ])


def circulant(c):
    row = np.array([c[0], c[1], c[2], c[3], c[2], c[1]], dtype=float)
    return np.stack([np.roll(row, i) for i in range(6)])


def hamiltonian(A, nup, g, phase=0.0):
    matrix = np.zeros((7, 7), dtype=complex)
    matrix[:6, :6] = A
    matrix[6, 6] = nup
    coupling = g * np.exp(1j * phase)
    matrix[0, 6] = coupling
    matrix[6, 0] = np.conjugate(coupling)
    return matrix


def diagonalize(matrix):
    values, vectors = np.linalg.eigh(matrix)
    return values.real.copy(), vectors


def port_weights(vectors):
    return np.abs(vectors[6, :]) ** 2


def sorted_observable(values, weights):
    order = np.argsort(values)
    return values[order].copy(), weights[order].copy()


def nn_sum_residual(nu=LINES_MHZ):
    nu0, nu1, nu2, nu3 = [float(x) for x in nu]
    residual = (nu0 + nu3) - (nu1 + nu2)
    return residual, abs(residual) / 4


def mode_groups(A, atol=1e-7):
    values, vectors = diagonalize(A)
    used = np.zeros(len(values), dtype=bool)
    groups = []
    for index in np.argsort(values):
        if used[index]:
            continue
        members = [j for j, energy in enumerate(values)
                   if not used[j] and abs(energy - values[index]) <= atol]
        for member in members:
            used[member] = True
        subspace = vectors[:, members]
        coords = np.conjugate(subspace[0, :])
        weight = float(np.real(np.vdot(coords, coords)))
        bright = dark = None
        if weight > 1e-12:
            bright = subspace @ (coords / np.sqrt(weight))
            bright = bright / np.linalg.norm(bright)
        if len(members) == 2:
            direction = coords / np.sqrt(weight) if weight > 1e-12 else np.array([1, 0])
            orthogonal = np.array([-np.conjugate(direction[1]), np.conjugate(direction[0])])
            dark = subspace @ orthogonal
            dark = dark / np.linalg.norm(dark)
        groups.append({
            "energy": float(np.mean(values[members])),
            "degeneracy": len(members),
            "site0_weight": weight,
            "bright": bright,
            "dark": dark,
        })
    return groups


def partner_shifts(A, nup, g, phase=0.0):
    """Shift of each unperturbed bright/dark ring vector after the port is on."""
    values, vectors = diagonalize(hamiltonian(A, nup, g, phase))
    rows = []
    for group in mode_groups(A):
        for kind, bare in (("bright", group["bright"]), ("dark", group["dark"])):
            if bare is None:
                continue
            overlap = np.abs(np.conjugate(bare) @ vectors[:6, :]) ** 2
            index = int(np.argmax(overlap))
            rows.append({
                "kind": kind,
                "degeneracy": group["degeneracy"],
                "site0_weight": group["site0_weight"],
                "bare_mhz": group["energy"],
                "full_mhz": float(values[index]),
                "shift_khz": float((values[index] - group["energy"]) * 1000),
                "overlap": float(overlap[index]),
                "port_weight": float(port_weights(vectors)[index]),
            })
    return rows


def leading_shift_mhz(g, energy, nup, site_weight):
    detuning = energy - nup
    if abs(detuning) < 1e-15:
        return None
    return (g * g) * site_weight / detuning


def leading_gap_mhz(g, site_weight):
    return 2 * abs(g) * np.sqrt(site_weight)


def hybrid_gap(values, weights):
    order = np.argsort(-weights)
    left, right = int(order[0]), int(order[1])
    return abs(float(values[left] - values[right])), left, right


def nearest_gap(values, target):
    order = np.argsort(np.abs(values - target))[:2]
    return abs(float(values[order[0]] - values[order[1]])), order


def reference_ring():
    coefficients = circulant_coefficients()
    matrix = circulant(coefficients)
    values, vectors = diagonalize(matrix)
    residual, bound = nn_sum_residual()
    c0, c1, c2, c3 = [float(x) for x in coefficients]
    return {
        "source": "SCALE09_LAB_PLAN.md digitized Barkhofen Fig. 10 lines; not a new digitization",
        "lines_mhz": LINES_MHZ.tolist(),
        "coefficients_mhz": {
            "c0": c0, "c1": c1, "c2": c2, "c3": c3,
            "opposite_matrix_element": c3,
            "prefactor_S3_plus_Sinv3": c3 / 2,
        },
        "neighbour_window_mhz": list(NEIGHBOUR_WINDOW_MHZ),
        "nn_sum_residual_mhz": residual,
        "nn_min_line_error_mhz": bound,
        "nn_model": "REJECTED_BY_FOUR_LINES",
        "eigenvalues_mhz": values.tolist(),
        "site0_weights": (np.abs(vectors[0, :]) ** 2).tolist(),
        "distinct_lines_recovered": True,
    }


def reference_controls():
    """Numeric controls quoted by the measurement plan. Not a physical kit."""
    coefficients = circulant_coefficients()
    matrix = circulant(coefficients)
    out = {"ring": reference_ring(), "cases": {}}
    detuned = partner_shifts(matrix, 6600.0, 1.0)
    bright = [row for row in detuned if row["kind"] == "bright" and row["degeneracy"] == 2]
    bright.sort(key=lambda row: row["bare_mhz"])
    out["cases"]["detuned_g1_nup6600"] = {
        "bright_shifts_khz": [row["shift_khz"] for row in bright],
        "leading_shifts_khz": [
            leading_shift_mhz(1.0, row["bare_mhz"], 6600.0, row["site0_weight"]) * 1000
            for row in bright
        ],
        "dark_shifts_khz": [row["shift_khz"] for row in detuned if row["kind"] == "dark"],
        "dark_port_weights": [row["port_weight"] for row in detuned if row["kind"] == "dark"],
    }
    gaps = {}
    for label, target in (("lower", 6627.8914), ("upper", 6713.2201)):
        values, vectors = diagonalize(hamiltonian(matrix, target, 0.2))
        weights = port_weights(vectors)
        full, _, _ = hybrid_gap(values, weights)
        near, _ = nearest_gap(values, target)
        gaps[label] = {
            "full_gap_mhz": full,
            "nearest_gap_mhz": near,
            "leading_gap_mhz": float(leading_gap_mhz(0.2, 1 / 3)),
            "hybrid_port_weights": [float(x) for x in weights[np.argsort(-weights)[:2]]],
        }
    out["cases"]["resonant_g0.2"] = gaps
    return out


def _base_locked(nup, g):
    coefficients = circulant_coefficients()
    return {
        "nu_lines_mhz": LINES_MHZ.tolist(),
        "coefficients_mhz": coefficients.tolist(),
        "nu_p_mhz": float(nup),
        "g_mhz": float(g),
        "phase_rad": 0.0,
        "contact_site": 0,
    }


def _observe(locked, freq_sigma, weight_sigma, rng=None, g_data=None):
    matrix = circulant(np.array(locked["coefficients_mhz"], dtype=float))
    values, vectors = diagonalize(hamiltonian(
        matrix, locked["nu_p_mhz"], locked["g_mhz"] if g_data is None else g_data,
        locked["phase_rad"]))
    weights = port_weights(vectors)
    if rng is not None:
        values = values + rng.normal(0.0, freq_sigma, size=7)
        weights = weights + rng.normal(0.0, weight_sigma, size=7)
    values, weights = sorted_observable(values, weights)
    bare, _ = diagonalize(matrix)
    return np.sort(bare.real), values, weights


def _record(name, *, nup, g, protocol, synthetic=True, g_data=None, independent=True,
            readout="calibrated_projector", gap_definition=None, claimed_gap=None,
            residual_upper=1e-8, freq_sigma=FREQ_SIGMA_MHZ, weight_sigma=WEIGHT_SIGMA,
            seed=None, traceable=False, assembly="synthetic-barkhofen-symmetric"):
    locked = _base_locked(nup, g)
    rng = None if seed is None else np.random.default_rng(seed)
    bare, frequencies, weights = _observe(
        locked, freq_sigma, weight_sigma, rng=rng, g_data=g_data)
    calibration_id = f"{name}-calibration"
    port_on_id = calibration_id if not independent else f"{name}-port-on"
    kit = {
        "name": name,
        "synthetic": synthetic,
        "assembly_id": assembly,
        "frequency_unit": {
            "name": "MHz",
            "traceable_to_assembly": traceable,
            "source": "declared synthetic unit" if synthetic else "unspecified",
        },
        "locked": locked,
        "port_off": {
            "assembly_id": assembly,
            "source_id": f"{name}-port-off",
            "frequencies_mhz": bare.tolist(),
            "sigma_mhz": [freq_sigma] * 6,
            "nu_p_mhz": float(nup),
            "sigma_nu_p_mhz": freq_sigma,
            "residual_coupling_upper_mhz": float(residual_upper),
            "same_frequency_reference": True,
        },
        "calibration": {
            "assembly_id": assembly,
            "source_id": calibration_id,
            "g_mhz": float(g),
            "sigma_g_mhz": freq_sigma,
            "nu_p_mhz": float(nup),
            "independent_of_port_on": independent,
            "readout": readout,
            "fit_uses_holdout": False,
        },
        "port_on": {
            "assembly_id": assembly,
            "source_id": port_on_id,
            "protocol": protocol,
            "frequencies_mhz": frequencies.tolist(),
            "sigma_freq_mhz": [freq_sigma] * 7,
            "port_weights": weights.tolist(),
            "sigma_weight": [weight_sigma] * 7,
            "gap_definition": gap_definition,
        },
        "tolerances": {"z_max": Z_MAX},
        "holdout_used_for_fit": False,
    }
    if claimed_gap is not None:
        kit["port_on"]["claimed_gap_mhz"] = float(claimed_gap)
    return jsonable(kit)


def published_ring_extract():
    """Four Fig. 10 lines only. This is not a same-assembly 6+1 kit."""
    return jsonable({
        "name": "barkhofen_fig10_ring_only",
        "synthetic": False,
        "assembly_id": "barkhofen-2012-fig10-digitized",
        "frequency_unit": {
            "name": "MHz",
            "traceable_to_assembly": False,
            "source": "digitized figure in SCALE09_LAB_PLAN.md; no instrument certificate in this scope",
        },
        "locked": {
            "nu_lines_mhz": LINES_MHZ.tolist(),
            "coefficients_mhz": circulant_coefficients().tolist(),
            "nu_p_mhz": None,
            "g_mhz": None,
            "phase_rad": 0.0,
            "contact_site": 0,
        },
        "port_off": None,
        "calibration": None,
        "port_on": None,
        "searched_scope": [
            "analysis/R150_R132_SPECTRAL_BRIDGE_20261126/scale_closure at a490b05",
            "SCALE09_LAB_PLAN.md extracted lines and cited Fig. 10 / Kuhl figures",
        ],
    })


def synthetic_kit(name):
    if name.startswith("hf_"):
        import hf_port
        if name not in hf_port.HF_LIMITS:
            raise KeyError(name)
        kit = _record(name, nup=6600., g=1., protocol="detuned", readout="spectral_derivative")
        on = kit["port_on"]
        del on["port_weights"], on["sigma_weight"]
        on["branch_ids"] = list(range(7))
        on["spectral_sweep"] = hf_port.make_sweep(name, on["source_id"])
        return jsonable(kit)
    if name == "detuned":
        return _record("detuned", nup=6600.0, g=1.0, protocol="detuned")
    if name == "resonant_one_doublet":
        return _record(
            "resonant_one_doublet", nup=6627.8914, g=0.2, protocol="resonant",
            gap_definition="two_largest_port_weights")
    if name == "resonant_other_doublet":
        return _record(
            "resonant_other_doublet", nup=6713.2201, g=0.2, protocol="resonant",
            gap_definition="two_largest_port_weights")
    if name == "detuned_within_noise":
        return _record(
            "detuned_within_noise", nup=6600.0, g=1.0, protocol="detuned",
            seed=11, freq_sigma=FREQ_SIGMA_MHZ, weight_sigma=WEIGHT_SIGMA)
    if name == "wrong_g":
        # Spectrum generated at the resonant g, locked claim uses another g.
        kit = _record(
            "wrong_g", nup=6627.8914, g=0.5, protocol="resonant", g_data=0.2,
            gap_definition="two_largest_port_weights")
        return kit
    if name == "dependent_calibration":
        return _record(
            "dependent_calibration", nup=6627.8914, g=0.2, protocol="resonant",
            independent=False, gap_definition="two_largest_port_weights")
    if name == "peak_height":
        return _record(
            "peak_height", nup=6627.8914, g=0.2, protocol="resonant",
            readout="peak_height", gap_definition="two_largest_port_weights")
    if name == "loose_residual":
        return _record(
            "loose_residual", nup=6600.0, g=1.0, protocol="detuned",
            residual_upper=5.0)
    if name == "half_gap":
        matrix = circulant(circulant_coefficients())
        values, vectors = diagonalize(hamiltonian(matrix, 6627.8914, 0.2))
        near, _ = nearest_gap(values, 6627.8914)
        return _record(
            "half_gap", nup=6627.8914, g=0.2, protocol="resonant",
            gap_definition="two_nearest_to_bare", claimed_gap=near)
    raise KeyError(name)


def _check(identifier, passed, detail, kind):
    return {"id": identifier, "passed": bool(passed), "class": kind, "detail": detail}


def _max_z(residual, sigma):
    residual = np.abs(np.asarray(residual, dtype=float))
    sigma = np.asarray(sigma, dtype=float)
    if np.any(sigma <= 0):
        raise ValueError("sigma must be positive")
    return float(np.max(residual / sigma))


def idealized_weight_gate(kit):
    """Rejected rule. Reproduces FAIL on the known-answer weights at σ=5e-6."""
    port_on = kit.get("port_on") or {}
    weights = np.asarray(port_on.get("port_weights", []), dtype=float)
    sigma = np.asarray(port_on.get("sigma_weight", []), dtype=float)
    protocol = port_on.get("protocol")
    if len(weights) != 7 or len(sigma) != 7 or protocol not in {"detuned", "resonant"}:
        return {"linear_decision": "METHOD_FAIL_SYNTHETIC", "limit": "IDEALIZED_WEIGHT_INCOMPLETE",
                "max_z": None}
    target = np.zeros(7)
    if protocol == "detuned":
        target[int(np.argmax(weights))] = 1.0
        limit = "IDEAL_DETUNED_UNDRESSED_WEIGHT"
    else:
        order = np.argsort(-weights)
        target[int(order[0])] = 0.5
        target[int(order[1])] = 0.5
        limit = "IDEAL_RESONANT_HALF_WEIGHT"
    score = _max_z(weights - target, sigma)
    passed = score <= kit.get("tolerances", {}).get("z_max", Z_MAX)
    return {
        "linear_decision": "METHOD_PASS_SYNTHETIC" if passed else "METHOD_FAIL_SYNTHETIC",
        "limit": None if passed else limit,
        "max_z": score,
        "rule": "compare port weights with 0, 1/2 or 1; not the acceptance rule",
    }


def _induced_shift_upper(matrix, nup, g_upper):
    """Largest bright-level displacement still allowed by the port-off coupling bound."""
    if g_upper < 0:
        raise ValueError("residual coupling bound must be non-negative")
    displacements = []
    for group in mode_groups(matrix):
        if group["bright"] is None:
            continue
        coupling = g_upper * np.sqrt(group["site0_weight"])
        detuning = group["energy"] - nup
        # Exact two-level displacement from the bare energy, reducing to g_eff^2/|Δ| far away.
        displacements.append(0.5 * (np.hypot(detuning, 2 * coupling) - abs(detuning)))
    return float(max(displacements))


def evaluate_kit(kit):
    """Predeclared 6+1 comparison. Returns the failing check instead of a bare FAIL."""
    checks = []
    diagnostics = {}
    synthetic = bool(kit.get("synthetic"))
    port_off = kit.get("port_off")
    calibration = kit.get("calibration")
    port_on = kit.get("port_on")
    locked = kit.get("locked") or {}
    tolerances = kit.get("tolerances") or {"z_max": Z_MAX}
    z_max = float(tolerances.get("z_max", Z_MAX))

    def finish(extra_comparison=None):
        failed = [item for item in checks if item["class"] == "method" and not item["passed"]]
        incomplete = any(item["id"] == "KIT_COMPLETE" and not item["passed"] for item in failed)
        if incomplete and not synthetic:
            decision = "INCOMPLETE_KIT"
            limit = "NO_ANCHOR_IN_SEARCHED_SCOPE"
        elif failed:
            decision = "METHOD_FAIL_SYNTHETIC" if synthetic else "METHOD_FAIL"
            limit = failed[0]["id"]
        elif synthetic:
            decision = "METHOD_PASS_SYNTHETIC"
            limit = "PHYSICAL_OPEN_NO_SAME_ASSEMBLY_PORT_KIT"
        elif kit.get("frequency_unit", {}).get("traceable_to_assembly"):
            decision = "CANDIDATE_READY_FOR_REVIEW"
            limit = "SCIENTIFIC_ACCEPTANCE_UNCHANGED"
        else:
            decision = "INCOMPLETE_KIT"
            limit = "NO_ANCHOR_IN_SEARCHED_SCOPE"
        comparison = {
            "rule": "exact spectrum of the locked A, nu_p and g; idealized 0/1/2 weights are not used",
            "failed_checks": [item["id"] for item in failed],
            "passed_method_checks": [item["id"] for item in checks
                                      if item["class"] == "method" and item["passed"]],
        }
        if extra_comparison:
            comparison.update(extra_comparison)
        return jsonable({
            "name": kit.get("name"),
            "linear_decision": decision,
            "limit": limit,
            "method_decision": decision,
            "physical_decision": "OPEN",
            "scale_gate": "OPEN",
            "operator_gate": "PARTIAL",
            "scientific_acceptance": False,
            "promotes_scale_09_to_12": False,
            "holdout_consumed": False,
            "bbn_used_for_calibration": False,
            "checks": checks,
            "diagnostics": diagnostics,
            "comparison": comparison,
            "rejected_predicates": {
                "idealized_weight_gate": idealized_weight_gate(kit),
            } if port_on and "port_weights" in port_on else {},
        })

    present = port_off is not None and calibration is not None and port_on is not None
    checks.append(_check(
        "KIT_COMPLETE", present,
        "need port-off, an independent readout calibration, and port-on on one assembly",
        "method"))
    if not present:
        return finish()

    same = (port_off.get("assembly_id") == calibration.get("assembly_id")
            == port_on.get("assembly_id") == kit.get("assembly_id"))
    checks.append(_check("SAME_ASSEMBLY", same, "port-off, calibration and port-on assembly ids", "method"))
    independent = bool(calibration.get("independent_of_port_on")) and (
        calibration.get("source_id") != port_on.get("source_id")) and not kit.get("holdout_used_for_fit") \
        and not calibration.get("fit_uses_holdout")
    checks.append(_check(
        "INDEPENDENT_CALIBRATION", independent,
        "g and the port-weight map are not taken from the port-on record or the holdout",
        "method"))
    spectral = ("spectral_sweep" in port_on or calibration.get("readout") == "spectral_derivative")
    readout_ok = calibration.get("readout") == ("spectral_derivative" if spectral else "calibrated_projector")
    checks.append(_check(
        "CALIBRATED_READOUT", readout_ok,
        "peak height is not a port weight; readout must be a calibrated projector",
        "method"))
    reference = bool(port_off.get("same_frequency_reference"))
    checks.append(_check("COMMON_FREQUENCY_REFERENCE", reference, "one frequency origin for ring and port", "method"))

    coefficients = np.array(locked["coefficients_mhz"], dtype=float)
    matrix = circulant(coefficients)
    bare, vectors_bare = diagonalize(matrix)
    bare = np.sort(bare.real)
    off = np.asarray(port_off["frequencies_mhz"], dtype=float)
    off_order = np.argsort(off)
    off_z = _max_z(off[off_order] - bare, np.asarray(port_off["sigma_mhz"])[off_order])
    checks.append(_check(
        "PORT_OFF_MATCHES_A", off_z <= z_max,
        f"max z of port-off frequencies against locked A is {off_z:.3e}",
        "method"))

    g = float(calibration["g_mhz"])
    nup = float(port_off["nu_p_mhz"])
    if abs(g - float(locked["g_mhz"])) > z_max * float(calibration["sigma_g_mhz"]):
        checks.append(_check("LOCKED_G", False, "calibration g disagrees with the locked input", "method"))
    else:
        checks.append(_check("LOCKED_G", True, "prediction uses the calibration value of g", "method"))
    phase = float(locked.get("phase_rad", 0.0))
    predicted_values, predicted_vectors = diagonalize(hamiltonian(matrix, nup, g, phase))
    predicted_weights = port_weights(predicted_vectors)
    predicted_values, predicted_weights = sorted_observable(predicted_values, predicted_weights)
    observed_values = np.asarray(port_on.get("frequencies_mhz", []), dtype=float)
    if observed_values.shape != (7,) or np.shape(port_on.get("sigma_freq_mhz")) != (7,):
        checks.append(_check("SPECTRUM_COMPLETE", False, "seven central lines and errors required", "method"))
        return finish()
    order = np.argsort(observed_values)
    observed_values = observed_values[order]
    freq_sigma = np.asarray(port_on["sigma_freq_mhz"], float)[order]
    frequency_z = _max_z(observed_values - predicted_values, freq_sigma)
    if spectral:
        try:
            fit = hf_recovery.from_records(kit)
            mode = port_on["spectral_sweep"]["normalization"]
            weight_z, sum_z = hf_recovery.slope_scores(fit, mode, predicted_weights, order, z_max)
        except hf_recovery.SweepError as exc:
            checks.append(_check(exc.gate, False, str(exc), "method"))
            return finish()
        observed_weights = fit["weights"][order]
        weight_sigma = np.sqrt(np.maximum(0., np.diag(fit["covariance"])))[order]
        diagnostics["spectral_recovery"] = {
            "normalization": mode, "step": fit["step"], "confidence": fit["confidence"],
            "branch_ids": [port_on["branch_ids"][j] for j in order],
            "intervals": fit["intervals"][order], "covariance": fit["covariance"][np.ix_(order, order)],
            "denominator": fit["denominator"], "denominator_sigma": fit["denominator_sigma"],
            "denominator_bias_bound": fit["denominator_bias_bound"],
        }
        if mode == "both":
            diagnostics["spectral_recovery"]["trace_weights"] = fit["trace_estimate"]["weights"][order]
    else:
        observed_weights = np.asarray(port_on["port_weights"], dtype=float)[order]
        weight_sigma = np.asarray(port_on["sigma_weight"], dtype=float)[order]
        weight_z = _max_z(observed_weights - predicted_weights, weight_sigma)
        sum_z = abs(float(np.sum(observed_weights) - 1.0)) / np.linalg.norm(weight_sigma)
    checks.append(_check(
        "FORWARD_SPECTRUM", frequency_z <= z_max and weight_z <= z_max,
        f"frequency z {frequency_z:.3e}, port-weight z {weight_z:.3e}",
        "method"))
    if sum_z is None:
        checks.append(_check("TRACE_SUM_IDENTITY", True, "trace-normalized weights sum to one by construction", "control"))
    else:
        checks.append(_check(
            "PORT_WEIGHT_SUM", sum_z <= z_max,
            f"sum of port weights differs from 1 by z {sum_z:.3e}",
            "method"))

    tolerance = z_max * float(np.median(port_on["sigma_freq_mhz"]))
    residual_upper = float(port_off["residual_coupling_upper_mhz"])
    induced = _induced_shift_upper(matrix, nup, residual_upper)
    checks.append(_check(
        "RESIDUAL_COUPLING", induced <= tolerance,
        f"port-off coupling bound can still move a bright line by {induced:.3e} MHz; "
        f"frequency tolerance is {tolerance:.3e} MHz",
        "method"))

    gap_payload = {}
    if port_on.get("protocol") == "resonant":
        definition = port_on.get("gap_definition")
        definition_ok = definition == "two_largest_port_weights"
        checks.append(_check(
            "GAP_DEFINITION", definition_ok,
            "the resonant gap is the split of the two largest port weights, "
            "not the two levels nearest the bare frequency",
            "method"))
        full_obs, _, _ = hybrid_gap(observed_values, observed_weights)
        full_pred, _, _ = hybrid_gap(predicted_values, predicted_weights)
        gap_z = abs(full_obs - full_pred) / float(np.median(port_on["sigma_freq_mhz"]))
        checks.append(_check(
            "HYBRID_GAP", gap_z <= z_max,
            f"hybrid gap {full_obs:.10f} MHz against locked gap {full_pred:.10f} MHz",
            "method"))
        near_obs, _ = nearest_gap(observed_values, nup)
        tuned = min(mode_groups(matrix), key=lambda group: abs(group["energy"] - nup))
        gap_payload = {
            "hybrid_gap_mhz": full_obs,
            "predicted_hybrid_gap_mhz": full_pred,
            "nearest_to_bare_gap_mhz": near_obs,
            "nearest_over_hybrid": near_obs / full_obs if full_obs else None,
            "leading_gap_mhz": float(leading_gap_mhz(g, tuned["site0_weight"])),
        }
        diagnostics["gap"] = gap_payload
        if "claimed_gap_mhz" in port_on:
            claimed = float(port_on["claimed_gap_mhz"])
            claimed_z = abs(claimed - full_pred) / float(np.median(port_on["sigma_freq_mhz"]))
            checks.append(_check(
                "CLAIMED_GAP", claimed_z <= z_max,
                f"claimed gap {claimed:.10f} MHz is not the locked hybrid gap {full_pred:.10f} MHz",
                "method"))
    elif port_on.get("protocol") == "detuned":
        shifts = [row for row in partner_shifts(matrix, nup, g, phase)
                  if row["kind"] == "bright" and row["degeneracy"] == 2]
        shifts.sort(key=lambda row: row["bare_mhz"])
        diagnostics["bright_doublet_shifts_khz"] = [row["shift_khz"] for row in shifts]
        if len(shifts) >= 2:
            distinct = abs(shifts[0]["shift_khz"] - shifts[1]["shift_khz"]) > 1000 * tolerance
            diagnostics["bright_shifts_are_distinct"] = bool(distinct)
            checks.append(_check(
                "DISTINCT_BRIGHT_SHIFTS", distinct,
                "reported control for a single-site contact at unequal detuning: "
                f"{shifts[0]['shift_khz']:.6f} and {shifts[1]['shift_khz']:.6f} kHz. "
                "Equal detuning is not itself a method failure; the spectrum still has to match H",
                "control"))
    else:
        checks.append(_check("PROTOCOL", False, "protocol must be detuned or resonant", "method"))

    bare_site_weights = np.abs(vectors_bare[0, :]) ** 2
    diagnostics["unperturbed_site0_weights"] = bare_site_weights.tolist()
    extra = {
        "max_abs_frequency_residual_mhz": float(np.max(np.abs(observed_values - predicted_values))),
        "max_abs_weight_residual": float(np.max(np.abs(observed_weights - predicted_weights))),
        "frequency_z": frequency_z,
        "weight_z": weight_z,
        "weights": {
            "values": observed_weights.tolist(),
            "prediction": predicted_weights.tolist(),
            "residual": (observed_weights - predicted_weights).tolist(),
            "sigma": list(weight_sigma),
        },
        "frequencies_mhz": {
            "values": observed_values.tolist(),
            "prediction": predicted_values.tolist(),
            "residual": (observed_values - predicted_values).tolist(),
            "sigma": list(freq_sigma),
        },
    }
    extra.update(gap_payload)
    return finish(extra)


def catalog_names():
    import hf_port
    return [
        "detuned", "resonant_one_doublet", "resonant_other_doublet",
        "detuned_within_noise", "wrong_g", "dependent_calibration",
        "peak_height", "loose_residual", "half_gap", *hf_port.HF_LIMITS,
    ]


def build_results():
    import hf_port
    controls = reference_controls()
    kits = {}
    for name in catalog_names():
        decision = evaluate_kit(synthetic_kit(name))
        kits[name] = {
            "linear_decision": decision["linear_decision"],
            "limit": decision["limit"],
            "failed_checks": decision["comparison"]["failed_checks"],
            "max_abs_weight_residual": decision["comparison"].get("max_abs_weight_residual"),
            "max_abs_frequency_residual_mhz": decision["comparison"].get("max_abs_frequency_residual_mhz"),
            "weight_z": decision["comparison"].get("weight_z"),
            "idealized_weight_gate": decision["rejected_predicates"].get("idealized_weight_gate"),
            "diagnostics": decision["diagnostics"],
        }
    extract = evaluate_kit(published_ring_extract())
    kits["barkhofen_fig10_ring_only"] = {
        "linear_decision": extract["linear_decision"],
        "limit": extract["limit"],
        "failed_checks": extract["comparison"]["failed_checks"],
    }
    positive = ["detuned", "resonant_one_doublet", "resonant_other_doublet", "detuned_within_noise"]
    positive.extend(name for name, limit in hf_port.HF_LIMITS.items() if limit is None)
    spectral = hf_port.campaign()
    hf_port.assert_spectral(spectral)
    return jsonable({
        "spectral_recovery": spectral,
        "scope": "method acceptance for one linear 6+1 ring; synthetic known answers are not a measured anchor",
        "scientific_acceptance": False,
        "physical_anchor": "OPEN",
        "gates": {
            "09-LAB-LINEAR-RING": "METHOD_PASS_SYNTHETIC",
            "09-LAB-SCALE": "OPEN",
            "09-LAB-OP": "PARTIAL",
            "SCALE-09": "OPEN",
            "SCALE-10": "OPEN",
            "SCALE-11": "OPEN",
            "SCALE-12": "OPEN",
        },
        "bbn_used_for_calibration": False,
        "target_contrast_used": False,
        "holdout_consumed": False,
        "acceptance_rule": "exact locked Hamiltonian; z<=5 on frequencies and calibrated port weights",
        "rejected_rule": "ideal port weights 0, 1/2 and 1 at the same sigma",
        "reference": controls,
        "kits": kits,
        "positive_kits": positive,
        "searched_scope": {
            "result": "NO_ANCHOR_IN_SEARCHED_SCOPE",
            "found": "four digitized symmetric-ring lines and their circulant",
            "missing": "one assembly with port-off, independently calibrated g and port weights, and port-on",
            "not_claimed": "a search of every archive or a statement that no such experiment exists",
        },
    })


def assert_reference(controls=None):
    controls = controls or reference_controls()
    coefficients = circulant_coefficients()
    c0, c1, c2, c3 = coefficients
    if abs(c0 - 6677.1095) > 1e-9 or abs(c1 - 48.02138333333293) > 1e-9:
        raise AssertionError("circulant coefficients drifted")
    if abs(c2 - 6.55375) > 1e-9 or abs(c3 - 5.357033333333523) > 1e-9:
        raise AssertionError("longer-range coefficients drifted")
    if abs(c3 / 2 - 2.6785166666667615) > 1e-12:
        raise AssertionError("opposite-bond prefactor drifted")
    residual, bound = nn_sum_residual()
    if abs(residual - 39.3225) > 1e-9 or abs(bound - 9.830625) > 1e-9:
        raise AssertionError("nearest-neighbour sum rule drifted")
    values = np.array(controls["ring"]["eigenvalues_mhz"])
    if np.max(np.abs(np.sort(values) - np.sort(np.repeat(LINES_MHZ, [1, 2, 2, 1])))) > 1e-8:
        raise AssertionError("ring spectrum does not recover the four lines")
    shifts = controls["cases"]["detuned_g1_nup6600"]["bright_shifts_khz"]
    if abs(shifts[0] - 11.945715795) > 1e-6 or abs(shifts[1] - 2.944122563) > 1e-6:
        raise AssertionError(f"bright shifts {shifts} are not the plan's 11.946 and 2.944 kHz")
    gaps = controls["cases"]["resonant_g0.2"]
    if abs(gaps["lower"]["full_gap_mhz"] - 0.2309393648) > 1e-9:
        raise AssertionError("lower hybrid gap drifted")
    if abs(gaps["upper"]["full_gap_mhz"] - 0.2309397550) > 1e-9:
        raise AssertionError("upper hybrid gap drifted")
    leading = 2 * 0.2 / np.sqrt(3)
    if abs(gaps["lower"]["leading_gap_mhz"] - leading) > 1e-12:
        raise AssertionError("leading gap is not 2|g|/sqrt(3)")
    for name, published in PUBLISHED_WEIGHTS.items():
        kit = synthetic_kit(name)
        weights = np.asarray(kit["port_on"]["port_weights"])
        if np.max(np.abs(np.sort(weights) - np.sort(published))) > 1e-11:
            raise AssertionError(f"{name} port weights do not match the known-answer print")
    expected = {
        "detuned": ("METHOD_PASS_SYNTHETIC", "PHYSICAL_OPEN_NO_SAME_ASSEMBLY_PORT_KIT"),
        "resonant_one_doublet": ("METHOD_PASS_SYNTHETIC", "PHYSICAL_OPEN_NO_SAME_ASSEMBLY_PORT_KIT"),
        "resonant_other_doublet": ("METHOD_PASS_SYNTHETIC", "PHYSICAL_OPEN_NO_SAME_ASSEMBLY_PORT_KIT"),
        "detuned_within_noise": ("METHOD_PASS_SYNTHETIC", "PHYSICAL_OPEN_NO_SAME_ASSEMBLY_PORT_KIT"),
        "wrong_g": ("METHOD_FAIL_SYNTHETIC", "FORWARD_SPECTRUM"),
        "dependent_calibration": ("METHOD_FAIL_SYNTHETIC", "INDEPENDENT_CALIBRATION"),
        "peak_height": ("METHOD_FAIL_SYNTHETIC", "CALIBRATED_READOUT"),
        "loose_residual": ("METHOD_FAIL_SYNTHETIC", "RESIDUAL_COUPLING"),
        "half_gap": ("METHOD_FAIL_SYNTHETIC", "GAP_DEFINITION"),
    }
    import hf_port
    for name, limit in hf_port.HF_LIMITS.items():
        expected[name] = (("METHOD_FAIL_SYNTHETIC", limit) if limit else
                          ("METHOD_PASS_SYNTHETIC", "PHYSICAL_OPEN_NO_SAME_ASSEMBLY_PORT_KIT"))
    for name, (decision, limit) in expected.items():
        result = evaluate_kit(synthetic_kit(name))
        if result["linear_decision"] != decision or result["limit"] != limit:
            raise AssertionError(f"{name}: {result['linear_decision']} {result['limit']}")
        if result["scientific_acceptance"] or result["holdout_consumed"]:
            raise AssertionError("synthetic evaluation promoted acceptance or consumed a holdout")
        gate = result["rejected_predicates"].get("idealized_weight_gate", {})
        if name in {"detuned", "resonant_one_doublet"} and gate["linear_decision"] != "METHOD_FAIL_SYNTHETIC":
            raise AssertionError("idealized weights unexpectedly pass at sigma 5e-6")
        if name == "detuned" and (result["comparison"]["max_abs_weight_residual"] > 1e-12
                                   or gate["max_z"] < 100):
            raise AssertionError("detuned exact residual or undressed z is inconsistent")
        if name == "dependent_calibration" and result["comparison"]["max_abs_weight_residual"] > 1e-12:
            raise AssertionError("a dependent calibration can reproduce the weights and must still fail")
        if name == "resonant_one_doublet" and gate["max_z"] < 5:
            raise AssertionError("resonant half-weight gate should fail at this sigma")
    extract = evaluate_kit(published_ring_extract())
    if extract["linear_decision"] != "INCOMPLETE_KIT" or extract["limit"] != "NO_ANCHOR_IN_SEARCHED_SCOPE":
        raise AssertionError("Fig. 10 extract must stay an incomplete physical kit")
    candidate = synthetic_kit("detuned")
    candidate["synthetic"] = False
    candidate["frequency_unit"]["traceable_to_assembly"] = True
    candidate["frequency_unit"]["source"] = "code-path certificate, not a measurement"
    reviewed = evaluate_kit(candidate)
    if reviewed["linear_decision"] != "CANDIDATE_READY_FOR_REVIEW":
        raise AssertionError(reviewed["linear_decision"])
    if reviewed["limit"] != "SCIENTIFIC_ACCEPTANCE_UNCHANGED" or reviewed["scientific_acceptance"]:
        raise AssertionError("a complete traced kit must stay unpromoted")
    return True


def load_kit(path):
    return json.loads(Path(path).read_text())
