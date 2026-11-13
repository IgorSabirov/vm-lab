"""Conditional ADD -> Phi -> R040 spectrum -> Psi loading -> transfer/resource run.

This is an optional full-pipeline layer.  It does not modify the inherited
spectral-only runner.  Every new Phi/Psi/transport/resource rule is an explicit
MODEL_ASSUMPTION; unaccepted or missing inputs block execution.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Mapping

import numpy as np

from .add_mapping import (EXPECTED_CARRIER_BLOB, load_verified_carrier,
                          combinatorial_invariants, local_motif_features,
                          map_local_motifs_to_r040, advance_one_add_step)
from .bic import check_direct_bic
from .loading import simulate_controlled_loading
from .model import R040Parameters
from .resource_ledger import evaluate_resource_ledger
from .runner import run_spectral
from .provenance import preflight as spectral_preflight
from .thermal_loading import simulate_davies_loading
from .transfer import check_moving_projector_transport, projector_from_dark_vector


def _complex_vector(value, name: str) -> np.ndarray:
    arr = np.asarray(value)
    if arr.ndim != 2 or arr.shape[1] != 2:
        raise ValueError(f"{name} must be encoded as [[real,imag], ...]")
    out = arr[:, 0].astype(float) + 1j * arr[:, 1].astype(float)
    if not np.all(np.isfinite(out.real)) or not np.all(np.isfinite(out.imag)):
        raise ValueError(f"{name} must be finite")
    return out


def _complex_matrix(value, name: str) -> np.ndarray:
    arr = np.asarray(value, dtype=float)
    if arr.ndim != 3 or arr.shape[-1] != 2:
        raise ValueError(f"{name} must be encoded as [rows][cols][real,imag]")
    out = arr[..., 0] + 1j * arr[..., 1]
    if not np.all(np.isfinite(out.real)) or not np.all(np.isfinite(out.imag)):
        raise ValueError(f"{name} must be finite")
    return out


def _feature_vector(word, anchors: Mapping[str, int], radius: int) -> np.ndarray:
    features = [local_motif_features(word, int(anchors[role]), radius)
                for role in ("V", "1", "2")]
    return np.asarray([x["feature_vector"] for x in features], dtype=float)


def local_transition_activity(word_before, anchors_before, word_after, anchors_after,
                              radius: int, activity_scale: float) -> dict:
    """Prospective local transition score used by the explicitly imported Psi law."""
    if not math.isfinite(activity_scale) or activity_scale <= 0:
        raise ValueError("activity_scale must be finite and positive")
    f0 = _feature_vector(word_before, anchors_before, radius)
    f1 = _feature_vector(word_after, anchors_after, radius)
    delta = f1 - f0
    norm_l1 = float(np.sum(np.abs(delta)))
    score = min(1.0, norm_l1 / float(activity_scale))
    return {
        "feature_matrix_before": f0.tolist(),
        "feature_matrix_after": f1.tolist(),
        "local_feature_delta": delta.tolist(),
        "local_activity_l1": norm_l1,
        "activity_scale": float(activity_scale),
        "activity_score": float(score),
        "future_history_used": False,
        "status": "LOCAL_TRANSITION_FEATURE_EVALUATED_MODEL_ASSUMPTION",
    }


def _coherent_psi(p: R040Parameters, activity: float, cfg: dict) -> dict:
    if cfg.get("source") != "MODEL_ASSUMPTION" or cfg.get("accepted") is not True:
        raise ValueError("coherent Psi must be an explicitly accepted MODEL_ASSUMPTION")
    omega = float(cfg["coupling_strength"])
    if not math.isfinite(omega) or omega <= 0:
        raise ValueError("coupling_strength must be finite and positive")
    if activity <= 0:
        raise ValueError("local ADD transition has zero activity; Psi does not trigger")
    d = p.dark_vector
    b = p.bright_vector
    hc = omega * activity * (np.outer(d, b.conj()) + np.outer(b, d.conj()))
    herm_err = float(np.linalg.norm(hc - hc.conj().T, ord="fro"))
    if herm_err > 1e-12:
        raise ArithmeticError("constructed coherent loading control is not Hermitian")
    duration = float(cfg["duration"])
    peak = float(cfg.get("envelope_peak", 1.0))
    if not math.isfinite(duration) or duration <= 0 or not math.isfinite(peak) or peak <= 0:
        raise ValueError("duration and envelope_peak must be finite and positive")

    def envelope(t):
        x = float(t)
        if x < 0 or x > duration:
            return 0.0
        return peak * math.sin(math.pi * x / duration) ** 2

    def derivative(t):
        x = float(t)
        if x < 0 or x > duration:
            return 0.0
        return peak * (math.pi / duration) * math.sin(2.0 * math.pi * x / duration)

    return {"H_control": hc, "duration": duration, "envelope": envelope,
            "envelope_derivative": derivative, "coupling_strength_effective": omega * activity,
            "hermiticity_residual": herm_err,
            "status": "PSI_COHERENT_LOCAL_TRANSITION_POSTULATE_EVALUATED"}


def _loading_from_manifest(p: R040Parameters, word_before, anchors_before,
                           word_after, anchors_after, manifest: dict) -> dict:
    cfg = manifest["loading"]
    psi = cfg["psi"]
    activity = local_transition_activity(
        word_before, anchors_before, word_after, anchors_after,
        int(psi["radius"]), float(psi["activity_scale"]))
    score = float(activity["activity_score"])
    if score <= 0:
        return {"status": "NOT_TRIGGERED_NO_LOCAL_ADD_TRANSITION_ACTIVITY",
                "local_transition": activity,
                "resource_ledger": {"status": "NOT_EVALUABLE_NO_LOADING_EVENT"}}
    initial = _complex_vector(cfg["initial_state_real_imag"], "initial_state_real_imag")
    times = np.asarray(cfg["times"], dtype=float)
    mode = psi.get("mode")
    if mode == "COHERENT_EVENT_TRIGGERED":
        control = _coherent_psi(p, score, psi)
        result = simulate_controlled_loading(
            p.H3, control["H_control"], initial, projector_from_dark_vector(p.dark_vector),
            times, control["envelope"], control["envelope_derivative"],
            hbar=float(cfg.get("hbar", 1.0)))
        result["psi"] = {k: v for k, v in control.items() if k not in {"H_control", "envelope", "envelope_derivative"}}
        result["local_transition"] = activity
    elif mode == "THERMAL_DAVIES_EVENT_TRIGGERED":
        if not psi.get("loading_reservoir_id"):
            raise ValueError("thermal Psi requires loading_reservoir_id")
        duration = float(times[-1] - times[0])
        if duration <= 0:
            raise ValueError("invalid thermal loading duration")

        def gate(t):
            x = float(t - times[0])
            if x < 0 or x > duration:
                return 0.0
            return math.sin(math.pi * x / duration) ** 2

        result = simulate_davies_loading(
            p, initial, times, beta=float(psi["beta"]),
            gamma_down_base=float(psi["gamma_down_base"]),
            local_event_activity=score, gate_envelope=gate,
            bath_id=str(psi["loading_reservoir_id"]))
        result["psi"] = {"source": "MODEL_ASSUMPTION", "mode": mode,
                          "assumption": psi.get("assumption"),
                          "status": "PSI_THERMAL_DAVIES_LOCAL_TRANSITION_POSTULATE_EVALUATED"}
        result["local_transition"] = activity
    else:
        raise ValueError("loading Psi mode must be COHERENT_EVENT_TRIGGERED or THERMAL_DAVIES_EVENT_TRIGGERED")
    result["resource_ledger"] = evaluate_resource_ledger(
        result, cfg["resource_model"], activation_count=1)
    return result


def preflight_full_pipeline(manifest: dict) -> dict:
    blockers = []
    carrier = manifest.get("carrier", {})
    if not carrier.get("path"):
        blockers.append("carrier.path missing")
    if carrier.get("expected_git_blob_sha1") != EXPECTED_CARRIER_BLOB:
        blockers.append("carrier expected Git blob is not the pinned carrier.py blob")
    if not carrier.get("word") or not isinstance(carrier.get("anchors"), dict):
        blockers.append("carrier word/anchors missing")
    phi = manifest.get("phi", {})
    if phi.get("source") != "MODEL_ASSUMPTION" or phi.get("accepted") is not True:
        blockers.append("Phi must be explicitly accepted as MODEL_ASSUMPTION")
    if not isinstance(phi.get("assumption"), str) or not phi.get("assumption", "").strip():
        blockers.append("Phi assumption text missing")
    psi = manifest.get("loading", {}).get("psi", {})
    if manifest.get("loading", {}).get("enabled") is True:
        if psi.get("source") != "MODEL_ASSUMPTION" or psi.get("accepted") is not True:
            blockers.append("Psi must be explicitly accepted as MODEL_ASSUMPTION")
        if psi.get("mode") not in {"COHERENT_EVENT_TRIGGERED", "THERMAL_DAVIES_EVENT_TRIGGERED"}:
            blockers.append("Psi loading mode missing/unsupported")
        if manifest.get("loading", {}).get("resource_model", {}).get("accepted") is not True:
            blockers.append("resource model is not explicitly accepted")
        if manifest.get("loading", {}).get("resource_model", {}).get("source") != "MODEL_ASSUMPTION":
            blockers.append("resource model source must be MODEL_ASSUMPTION")
    transfer = manifest.get("transfer", {})
    if transfer.get("enabled") is True:
        if transfer.get("source") != "MODEL_ASSUMPTION" or transfer.get("accepted") is not True:
            blockers.append("T_X transport law must be explicitly accepted as MODEL_ASSUMPTION")
        if transfer.get("operator_real_imag") is None:
            blockers.append("T_X isometry matrix missing")
    if manifest.get("spectral") is None:
        blockers.append("spectral manifest missing")
    return {"status": "READY_FOR_INTEGRATED_LOCAL_RUN" if not blockers else "BLOCKED_MISSING_OR_UNACCEPTED_INPUTS",
            "blockers": blockers, "blocker_count": len(blockers),
            "submit_allowed": not blockers,
            "scientific_status": "CONDITIONAL_MAPPING_AND_LOADING_POSTULATES_NOT_ADD_DERIVED"}


def run_full_pipeline(manifest: dict) -> dict:
    gate = preflight_full_pipeline(manifest)
    if not gate["submit_allowed"]:
        raise ValueError("integrated X26 preflight blocked: " + "; ".join(gate["blockers"]))
    carrier = manifest["carrier"]
    module = load_verified_carrier(carrier["path"], carrier["expected_git_blob_sha1"])
    word = list(carrier["word"])
    anchors = {k: int(v) for k, v in carrier["anchors"].items()}
    mapping_before = map_local_motifs_to_r040(word, anchors, manifest["phi"])
    params_before = R040Parameters(**mapping_before["parameters"])
    step = advance_one_add_step(word, anchors, module.full_step,
                                interaction=bool(carrier.get("interaction", True)))
    mapping_after = map_local_motifs_to_r040(step["word_after"], step["anchors_after"], manifest["phi"])
    params_after = R040Parameters(**mapping_after["parameters"])
    bic_before = check_direct_bic(params_before)
    bic_after = check_direct_bic(params_after)

    spectral_manifest = dict(manifest["spectral"])
    spectral_manifest["model"] = mapping_before["parameters"]
    spectral_manifest["provenance"] = mapping_before["provenance"]
    spectral_manifest["model_assumptions_accepted"] = True
    spectral_gate = spectral_preflight(spectral_manifest)
    if not spectral_gate["submit_allowed"]:
        raise ValueError("derived spectral manifest preflight blocked: " +
                         "; ".join(x["id"] for x in spectral_gate["blockers"]))
    spectral_report = run_spectral(spectral_manifest)

    transfer_result = {"status": "NOT_REQUESTED"}
    transfer_cfg = manifest.get("transfer", {})
    if transfer_cfg.get("enabled") is True:
        if (bic_before["verdict"] == "BIC_IN_CONDITIONAL_R040_TIGHT_BINDING_MODEL"
                and bic_after["verdict"] == "BIC_IN_CONDITIONAL_R040_TIGHT_BINDING_MODEL"):
            tx = _complex_matrix(transfer_cfg["operator_real_imag"], "T_X")
            transfer_result = check_moving_projector_transport(
                projector_from_dark_vector(params_before.dark_vector),
                projector_from_dark_vector(params_after.dark_vector), tx,
                tol=float(transfer_cfg.get("tolerance", 1e-9)),
                source="MODEL_ASSUMPTION")
        else:
            transfer_result = {"status": "NOT_EVALUABLE_BIC_SUBSPACE_NOT_PRESENT_AT_BOTH_STEPS",
                               "bic_before": bic_before["verdict"], "bic_after": bic_after["verdict"]}

    loading_result = {"status": "DISABLED_SEPARATE_PROTOCOL"}
    if manifest.get("loading", {}).get("enabled") is True:
        if bic_before["verdict"] != "BIC_IN_CONDITIONAL_R040_TIGHT_BINDING_MODEL":
            loading_result = {"status": "NOT_RUN_CURRENT_STATE_HAS_NO_DIRECT_BIC",
                              "bic_before": bic_before["verdict"]}
        else:
            loading_result = _loading_from_manifest(params_before, step["word_before"],
                                                     step["anchors_before"], step["word_after"],
                                                     step["anchors_after"], manifest)

    return {
        "schema": 1,
        "experiment": "X26_ADD_R040_LOADING_INTEGRATED",
        "epistemic_class": "CONDITIONAL_PHI_PSI_MODEL_NOT_ADD_DERIVED",
        "carrier": {
            "source_git_blob_sha1": carrier["expected_git_blob_sha1"],
            "initial_invariants": combinatorial_invariants(word),
            "one_step": step,
        },
        "phi": {"before": mapping_before, "after": mapping_after},
        "direct_bic": {"before": bic_before, "after": bic_after},
        "spectral_preflight": spectral_gate,
        "spectral_only": spectral_report,
        "moving_projector_transfer": transfer_result,
        "loading": loading_result,
        "non_claims": [
            "Phi and Psi are explicit model assumptions, not derived from K1/K2 or ADD topology",
            "the local permutation control is a sensitivity test, not proof of physical causality",
            "a one-step projector identity is not a global BIC on an infinite growing orbit",
            "resource ledger results are in declared model units, not laboratory joules",
        ],
    }
