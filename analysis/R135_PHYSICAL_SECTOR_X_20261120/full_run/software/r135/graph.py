"""P2: execute the named R130 law with an explicitly supplied energy and map.

No label is reduced modulo three. A map or a Hamiltonian is a model input,
never inferred from success of the graph dynamics or a BBN energy budget.
"""
from __future__ import annotations

import importlib.util
import itertools
import math
from pathlib import Path

import numpy as np
from scipy.special import logsumexp

from .common import (InputError, OpenInput, canonical_hash, finite, read_json,
                     require_source, sha256, write_json)

ENGINE_PATH = Path(__file__).resolve().parents[5] / "analysis/ADD_NEIGHBOR_SYNTHESIS_20261117/verify.py"
ENGINE_SHA = "d46a47443e610ffe42a0160aaae0487e6c0a9be9e6b96bf72ce39962cf7cf9a1"


def engine():
    if sha256(ENGINE_PATH) != ENGINE_SHA:
        raise InputError("named R130 engine differs from its registered source")
    spec = importlib.util.spec_from_file_location("r135_r130_named", ENGINE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def labels(word):
    vals = tuple(word)
    if not vals or any(type(s) is not int or s < 0 or s > 15 for s in vals):
        raise InputError("a graph word is a nonempty list of integer labels 0..15")
    return vals


def motif_count(word, motif):
    word, motif = tuple(word), tuple(motif)
    if not word or not motif:
        raise InputError("empty motif or word")
    return sum(all(word[(i+j) % len(word)] == s for j, s in enumerate(motif))
               for i in range(len(word)))


class Hamiltonian:
    """Finite-range cyclic energy, with explicit coefficients in MeV.

    Terms may be onsite, oriented nearest-neighbor and named cyclic motifs.
    The energy law is invariant under choice of starting vertex; reflection
    invariance is not silently imposed on oriented interactions.
    """
    def __init__(self, definition):
        self.definition = definition
        require_source(definition, "graph Hamiltonian")
        if definition.get("unit") != "MeV":
            raise InputError("Hamiltonian must state unit MeV")
        self.onsite = {int(k): finite(v, f"onsite[{k}]")
                       for k, v in definition.get("onsite", {}).items()}
        self.pairs = {}
        for k, v in definition.get("pairs", {}).items():
            pair = tuple(int(x) for x in k.split(","))
            if len(pair) != 2:
                raise InputError("pair key must contain two comma-separated labels")
            labels(pair)
            self.pairs[pair] = finite(v, f"pair[{k}]")
        self.motifs = [(labels(rec["labels"]), finite(rec["coefficient_MeV"], "motif coefficient"))
                       for rec in definition.get("motifs", [])]
        self.constant = finite(definition.get("constant_MeV", 0), "energy constant")

    def __call__(self, word):
        word = labels(word)
        missing = sorted(set(word) - set(self.onsite))
        if missing:
            raise OpenInput(f"Hamiltonian lacks explicit onsite energies for labels {missing}")
        return self.constant + sum(self.onsite[s] for s in word) + sum(
            self.pairs.get((word[i], word[(i+1) % len(word)]), 0.) for i in range(len(word))) + sum(
            c * motif_count(word, motif) for motif, c in self.motifs)


def su3_map(definition):
    require_source(definition, "state map")
    if definition.get("representation") != "SU3-fundamental":
        raise OpenInput("state map must explicitly define the SU3-fundamental representation")
    result = {}
    for label, rec in definition.get("operators", {}).items():
        key = int(label)
        labels([key])
        a = np.asarray(rec["real"], dtype=float) + 1j*np.asarray(rec["imag"], dtype=float)
        if a.shape != (3, 3) or not np.isfinite(a).all():
            raise InputError(f"label {key}: expected finite complex 3x3 operator")
        if np.max(np.abs(a.conj().T @ a - np.eye(3))) > 1e-10 or abs(np.linalg.det(a)-1) > 1e-10:
            raise InputError(f"label {key}: operator is not in SU(3)")
        result[key] = a
    return result


def orbit(initial, steps, eps=(1,)):
    mod = engine()
    if type(steps) is not int or steps < 0:
        raise InputError("steps must be a nonnegative integer")
    if not eps or len(eps) > 2 or any(x not in {-1, 1} for x in eps):
        raise InputError("R130 interaction eps must contain one or two signs")
    initial = labels(initial)
    if max(initial) >= 4**len(eps):
        raise InputError("initial labels exceed the selected R130 channel count")
    state = mod.named(initial)
    result = []
    for step in range(steps + 1):
        word = mod.word(state)
        nxt = mod.forward(state, tuple(eps))
        if not mod.equal(mod.backward(nxt, tuple(eps)), state):
            raise RuntimeError("named transition inverse check failed")
        # Rotating the list preserves names, directed adjacency and the law.
        rotated = state[1:] + state[:1]
        if not mod.equal(mod.forward(rotated, tuple(eps)), nxt):
            raise RuntimeError("named transition depends on list starting vertex")
        result.append({"step": step, "word": list(word), "length": len(word),
                       "named_state_sha256": canonical_hash(state)})
        state = nxt
    return result


def canonical_ensemble(states, hamiltonian, temperature_MeV, weights=None):
    """Exact finite declared ensemble. No claim about an omitted state space."""
    t = finite(temperature_MeV, "temperature", positive=True)
    words = [labels(w) for w in states]
    if len(set(words)) != len(words) or not words:
        raise InputError("ensemble contains duplicate or no states")
    w = np.ones(len(words)) if weights is None else np.asarray(weights, float)
    if w.shape != (len(words),) or not np.isfinite(w).all() or np.any(w <= 0):
        raise InputError("statistical measure must be explicit positive weights")
    energies = np.array([hamiltonian(s) for s in words])
    logw = np.log(w) - energies/t
    logz = logsumexp(logw)
    probabilities = np.exp(logw-logz)
    mean = float(probabilities@energies)
    return {"log_partition_function": float(logz), "mean_energy_MeV": mean,
            "heat_capacity": float(probabilities@((energies-mean)**2)/t**2),
            "entropy": float(logz+mean/t), "probabilities": probabilities.tolist(),
            "ensemble_sha256": canonical_hash({"states": states, "weights": w.tolist()})}


def run(config, inputs, out):
    definition = read_json(inputs["graph_law"]) if "graph_law" in inputs else config.get("law")
    mapping = read_json(inputs["state_map"]) if "state_map" in inputs else config.get("state_map")
    if not definition:
        raise OpenInput("P2 requires a declared physical graph law")
    require_source(definition, "graph law")
    if not definition.get("version"):
        raise InputError("graph law version is required")
    energy = Hamiltonian(definition["hamiltonian"])
    preparations = config.get("preparations", [])
    ids = [x["id"] for x in preparations]
    if not ids or len(set(ids)) != len(ids):
        raise InputError("unique independent preparation ids are required")
    calibration_ids = set(definition.get("calibration_ids", []))
    heldout = [p for p in preparations if p.get("role") == "heldout"]
    if not heldout:
        raise OpenInput("P2 requires heldout preparations registered before their outcomes")
    if calibration_ids & {p["id"] for p in heldout}:
        raise InputError("heldout preparations overlap Hamiltonian calibration")
    if any("outcome" in p or "observed" in p for p in heldout):
        raise InputError("prediction registration must not consume heldout outcomes")
    mapping_ops = su3_map(mapping) if mapping else {}
    histories, reached, predictions, residuals = {}, set(), [], []
    tolerance = finite(config.get("energy_atol_MeV", 1e-12), "energy tolerance", positive=True)
    balance = definition.get("balance", {})
    if balance.get("kind") not in {"isolated", "measured_reservoir"}:
        raise OpenInput("declare isolated energy conservation or independently measured reservoir transfers")
    for p in preparations:
        require_source(p, f"preparation {p['id']}")
        hist = orbit(p["word"], config.get("steps", 8), definition.get("eps", [1]))
        for row in hist:
            reached.update(row["word"])
            row["energy_MeV"] = energy(row["word"])
            for shift in range(len(row["word"])):
                w = row["word"][shift:] + row["word"][:shift]
                if abs(energy(w)-row["energy_MeV"]) > tolerance:
                    raise RuntimeError("Hamiltonian failed cyclic representation invariance")
            defined = [s for s in row["word"] if s in mapping_ops]
            row["map_coverage"] = len(defined)/len(row["word"])
            row["missing_labels"] = sorted(set(row["word"])-set(mapping_ops))
            if len(defined) == len(row["word"]):
                ell = np.array([np.trace(mapping_ops[s])/3 for s in row["word"]])
                row["mean_trace_real"] = float(ell.mean().real)
                row["mean_trace_imag"] = float(ell.mean().imag)
            else:
                row["mean_trace_real"] = row["mean_trace_imag"] = None
        transfers = balance.get("transfers_MeV", {}).get(p["id"], [])
        if balance["kind"] == "measured_reservoir" and len(transfers) != len(hist)-1:
            raise OpenInput(f"missing independent event heat/work for {p['id']}")
        for i, (a, b) in enumerate(zip(hist, hist[1:])):
            q = 0 if balance["kind"] == "isolated" else finite(transfers[i], "measured event heat")
            residuals.append({"preparation_id": p["id"], "step": i+1,
                              "delta_energy_MeV": b["energy_MeV"]-a["energy_MeV"],
                              "input_heat_work_MeV": q,
                              "residual_MeV": b["energy_MeV"]-a["energy_MeV"]-q})
        histories[p["id"]] = hist
        if p.get("role") == "heldout":
            predictions.append({"preparation_id": p["id"], "trajectory": hist,
                                "parameter_uncertainty": definition.get("parameter_uncertainty"),
                                "prediction_scope": "declared finite preparation and step interval"})
    failed_balance = any(abs(r["residual_MeV"]) > tolerance for r in residuals)
    missing = sorted(reached-set(mapping_ops))
    write_json(out / "graph_law.json", {"definition": definition,
               "source_engine_sha256": ENGINE_SHA, "balance": residuals,
               "necessary_condition": {"energy_balance": not failed_balance,
                                       "scope": "only this declared graph energy and preparations"}})
    write_json(out / "state_map.json", {"definition": mapping, "reachable_labels": sorted(reached),
               "missing_labels": missing, "complete_for_tested_orbits": not missing,
               "unbounded_reachability_proved": False})
    write_json(out / "heldout_prediction.json", {
        "schema": "R135-graph-prediction-v1", "law_sha256": canonical_hash(definition),
        "predictions": predictions, "outcomes_read": False, "all_orbits": histories})
    limitations = ["A finite numerical prediction does not establish a physical carrier or a clock"]
    if missing:
        limitations.append(f"State map has no operators for reachable labels {missing}")
    if failed_balance:
        limitations.append("The declared energy fails its own necessary balance condition on saved events")
    if definition.get("parameter_uncertainty") is None:
        limitations.append("Physical parameter uncertainty has not been supplied")
    evidence = "NECESSARY_CONDITION_FAILED" if failed_balance else ("OPEN_INPUT" if missing else "CONDITIONAL")
    return {"software_status": "PASS", "evidence_status": evidence,
            "metrics": {"reached_labels": sorted(reached), "energy_balance": not failed_balance,
                        "heldout_predictions": len(predictions)}, "limitations": limitations}
