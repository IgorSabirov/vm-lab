"""Strict validator for the canonical PRIMAT/LINX BBN bridge input.

No solver is imported or executed here. Hashes are SHA-256 of canonical JSON
(UTF-8, sorted keys, compact separators, ensure_ascii=False) for history/rates.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from typing import Any


class ContractError(ValueError):
    pass


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{label}: expected numeric value")
    number = float(value)
    if not math.isfinite(number):
        raise ContractError(f"{label}: value must be finite")
    return number


def _series(value: Any, label: str, n: int | None = None) -> list[float]:
    if not isinstance(value, list) or len(value) < 2:
        raise ContractError(f"{label}: expected array with at least two values")
    out = [_finite_number(v, f"{label}[{i}]") for i, v in enumerate(value)]
    if n is not None and len(out) != n:
        raise ContractError(f"{label}: length {len(out)} != history length {n}")
    return out


def validate_input(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ContractError("payload must be an object")
    if payload.get("schema_version") != "vm-lab-canonical-bbn-input-v1":
        raise ContractError("unsupported schema_version")
    for key in ("history", "rates", "provenance"):
        if not isinstance(payload.get(key), dict):
            raise ContractError(f"{key}: expected object")

    history = payload["history"]
    required = ("time_s", "scale_factor", "H_s_inv", "T_gamma_MeV", "n_b_cm3")
    arrays = {key: _series(history.get(key), f"history.{key}") for key in required}
    n = len(arrays["time_s"])
    for key, values in arrays.items():
        if len(values) != n:
            raise ContractError(f"history.{key}: length {len(values)} != {n}")
    if any(b <= a for a, b in zip(arrays["time_s"], arrays["time_s"][1:])):
        raise ContractError("history.time_s must be strictly increasing")
    for key in ("scale_factor", "H_s_inv", "T_gamma_MeV", "n_b_cm3"):
        if any(v <= 0 for v in arrays[key]):
            raise ContractError(f"history.{key} must be strictly positive")

    for key in ("T_nu_MeV", "rho_X_MeV_cm3", "p_X_MeV_cm3",
                "Q_Xem_MeV_cm3_s", "Q_Xnu_MeV_cm3_s", "Q_emnu_MeV_cm3_s"):
        if key in history:
            _series(history[key], f"history.{key}", n)

    for key in ("f_nu_e", "f_antinu_e"):
        if key in history:
            spec = history[key]
            if not isinstance(spec, dict):
                raise ContractError(f"history.{key}: expected object")
            energy = _series(spec.get("energy_MeV"), f"history.{key}.energy_MeV")
            values = spec.get("values")
            if not isinstance(values, list) or len(values) != n:
                raise ContractError(f"history.{key}.values must have {n} time rows")
            for i, row in enumerate(values):
                row_values = _series(row, f"history.{key}.values[{i}]",
                                     len(energy))
                if any(v < 0 for v in row_values):
                    raise ContractError(f"history.{key}.values[{i}] must be nonnegative")
            if any(b <= a for a, b in zip(energy, energy[1:])):
                raise ContractError(f"history.{key}.energy_MeV must be strictly increasing")

    phase = history.get("phase_state")
    if phase is not None and (not isinstance(phase, list) or len(phase) != n):
        raise ContractError("history.phase_state must match history length")

    rates = payload["rates"]
    for key in ("network_id", "temperature_unit", "rate_units",
                "interpolation", "extrapolation", "detailed_balance_policy"):
        if not isinstance(rates.get(key), str) or not rates[key]:
            raise ContractError(f"rates.{key}: required nonempty string")
    if rates["temperature_unit"] != "T9":
        raise ContractError("rates.temperature_unit must be T9")
    if rates["interpolation"] not in ("linear", "log"):
        raise ContractError("unsupported interpolation")
    if rates["extrapolation"] not in ("reject", "upstream-zero-linear", "declared-model"):
        raise ContractError("unsupported extrapolation")
    species = rates.get("species")
    if (not isinstance(species, list) or not species
            or any(not isinstance(item, str) or not item for item in species)
            or len(set(species)) != len(species)):
        raise ContractError("rates.species must be a nonempty unique string list")
    reactions = rates.get("reactions")
    if not isinstance(reactions, list) or not reactions:
        raise ContractError("rates.reactions must be a nonempty list")
    reaction_ids = set()
    for i, reaction in enumerate(reactions):
        label = f"rates.reactions[{i}]"
        if not isinstance(reaction, dict):
            raise ContractError(f"{label}: expected object")
        rid = reaction.get("id")
        if not isinstance(rid, str) or not rid or rid in reaction_ids:
            raise ContractError(f"{label}.id: missing or duplicate")
        reaction_ids.add(rid)
        for side in ("reactants", "products"):
            mapping = reaction.get(side)
            if not isinstance(mapping, dict) or not mapping:
                raise ContractError(f"{label}.{side}: expected nonempty stoichiometry")
            for name, count in mapping.items():
                if name not in species:
                    raise ContractError(f"{label}.{side}: unknown species {name}")
                if isinstance(count, bool) or not isinstance(count, int) or count < 1:
                    raise ContractError(f"{label}.{side}.{name}: invalid multiplicity")
        t9 = _series(reaction.get("T9"), f"{label}.T9")
        vals = _series(reaction.get("values"), f"{label}.values", len(t9))
        if any(b <= a for a, b in zip(t9, t9[1:])):
            raise ContractError(f"{label}.T9 must be strictly increasing")
        if any(v < 0 for v in vals):
            raise ContractError(f"{label}.values must be nonnegative")
        if rates["interpolation"] == "log" and any(v <= 0 for v in vals):
            raise ContractError(f"{label}.values must be positive for log interpolation")

    provenance = payload["provenance"]
    for key in ("history_sha256", "rates_sha256", "producer", "created_utc"):
        if key not in provenance:
            raise ContractError(f"provenance.{key}: required")
    if provenance["history_sha256"] != canonical_sha256(history):
        raise ContractError("history SHA-256 mismatch")
    if provenance["rates_sha256"] != canonical_sha256(rates):
        raise ContractError("rates SHA-256 mismatch")
    if not isinstance(provenance["producer"], str) or not provenance["producer"]:
        raise ContractError("provenance.producer must be nonempty")
    try:
        datetime.fromisoformat(provenance["created_utc"].replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise ContractError("provenance.created_utc must be ISO-8601") from None

    return {
        "valid": True,
        "history_points": n,
        "species": len(species),
        "reactions": len(reactions),
        "history_sha256": provenance["history_sha256"],
        "rates_sha256": provenance["rates_sha256"],
    }
