"""Explicit resource accounting for conditional loading protocols.

The ledger never translates ADD particle counts into fuel by itself.  The
resource exchange rates and available local stock are separate MODEL_ASSUMPTION
inputs.  Work, reservoir heat, entropy flow and controller reset are reported
as distinct terms to prevent double counting.
"""
from __future__ import annotations

import math


def evaluate_resource_ledger(loading_result: dict, model: dict,
                             activation_count: int = 1) -> dict:
    if model.get("source") != "MODEL_ASSUMPTION" or model.get("accepted") is not True:
        return {"status": "NOT_EVALUABLE_RESOURCE_MODEL_NOT_ACCEPTED",
                "blockers": ["resource model must be an explicitly accepted MODEL_ASSUMPTION"]}
    if type(activation_count) is not int or activation_count < 0:
        raise ValueError("activation_count must be a non-negative integer")
    required = (
        "fuel_units_available", "energy_per_fuel_unit_model_units",
        "drive_efficiency", "actuator_switch_energy_model_units",
        "controller_reset_bits", "k_B_model_units_per_temperature",
        "temperature_model_units", "precursor_units_available",
        "precursor_units_per_activation",
        "initial_packet_preparation_energy_model_units",
    )
    missing = [key for key in required if model.get(key) is None]
    if missing:
        return {"status": "NOT_EVALUABLE_RESOURCE_INPUTS_MISSING", "blockers": missing}

    vals = {k: float(model[k]) for k in required}
    if not all(math.isfinite(v) for v in vals.values()):
        raise ValueError("resource inputs must be finite")
    if vals["fuel_units_available"] < 0 or vals["precursor_units_available"] < 0:
        raise ValueError("available resources cannot be negative")
    if vals["energy_per_fuel_unit_model_units"] <= 0:
        raise ValueError("energy_per_fuel_unit must be positive")
    if not 0 < vals["drive_efficiency"] <= 1:
        raise ValueError("drive_efficiency must be in (0,1]")
    if vals["actuator_switch_energy_model_units"] < 0 or vals["controller_reset_bits"] < 0:
        raise ValueError("switch energy and reset bits cannot be negative")
    if vals["k_B_model_units_per_temperature"] <= 0 or vals["temperature_model_units"] <= 0:
        raise ValueError("k_B and temperature must be positive")
    if vals["precursor_units_per_activation"] < 0 or vals["initial_packet_preparation_energy_model_units"] < 0:
        raise ValueError("precursor and initial preparation costs cannot be negative")

    protocol = loading_result.get("status", "")
    work_input = loading_result.get("external_work_input_model_units")
    if work_input is None:
        # Thermal channel coupling gate is an additional actuator. Its switching
        # work is not supplied by the thermal heat term and must be explicit.
        work_input = model.get("loading_gate_actuator_work_model_units")
    if work_input is None:
        return {"status": "NOT_EVALUABLE_ACTUATOR_WORK_MISSING",
                "blockers": ["loading work/gate actuator work is not supplied"]}
    work_input = float(work_input)
    if not math.isfinite(work_input) or work_input < 0:
        raise ValueError("gross actuator input work must be finite and non-negative")

    drive_energy = work_input / vals["drive_efficiency"]
    switch_energy = vals["actuator_switch_energy_model_units"]
    reset_energy = (vals["k_B_model_units_per_temperature"]
                    * vals["temperature_model_units"] * math.log(2.0)
                    * vals["controller_reset_bits"])
    initial_energy = vals["initial_packet_preparation_energy_model_units"]
    # These are distinct supplied terms; reservoir heat is deliberately not added
    # again to fuel demand.  If the initial packet is already included in another
    # source, the model author must set its preparation cost to zero and state why.
    total_energy = drive_energy + switch_energy + reset_energy + initial_energy
    fuel_required = total_energy / vals["energy_per_fuel_unit_model_units"]
    precursor_required = vals["precursor_units_per_activation"] * activation_count

    bath_heat = loading_result.get("reservoir_heat_gained_model_units")
    bath_entropy = loading_result.get("reservoir_entropy_flow_kB_units")
    bath_energy_capacity = model.get("reservoir_energy_capacity_model_units")
    bath_entropy_capacity = model.get("reservoir_entropy_capacity_kB")
    reservoir_checks = {"energy_capacity": "NOT_APPLICABLE", "entropy_capacity": "NOT_APPLICABLE"}
    reservoir_missing = []
    if bath_heat is not None:
        if bath_energy_capacity is None:
            reservoir_missing.append("reservoir_energy_capacity_model_units")
        else:
            reservoir_checks["energy_capacity"] = bool(float(bath_energy_capacity) >= max(0.0, float(bath_heat)))
    if bath_entropy is not None:
        if bath_entropy_capacity is None:
            reservoir_missing.append("reservoir_entropy_capacity_kB")
        else:
            reservoir_checks["entropy_capacity"] = bool(float(bath_entropy_capacity) >= max(0.0, float(bath_entropy)))

    fuel_ok = vals["fuel_units_available"] + 1e-12 >= fuel_required
    precursor_ok = vals["precursor_units_available"] + 1e-12 >= precursor_required
    reservoir_ok = all(v is not False for v in reservoir_checks.values())
    if reservoir_missing:
        status = "NOT_EVALUABLE_RESERVOIR_CAPACITY_MISSING"
    elif not fuel_ok or not precursor_ok or not reservoir_ok:
        status = "RESOURCE_INFEASIBLE_UNDER_DECLARED_BUDGET"
    else:
        status = "LOWER_BOUND_WITHIN_BUDGET_ACTUAL_RESET_PROTOCOL_NOT_MODELLED"
    return {
        "status": status,
        "source": "MODEL_ASSUMPTION",
        "protocol": protocol,
        "activation_count": activation_count,
        "energy_terms_model_units": {
            "gross_control_work_input": drive_energy,
            "actuator_switching": switch_energy,
            "controller_reset_minimum_Landauer_bound": reset_energy,
            "initial_packet_preparation": initial_energy,
            "fuel_demand_total": total_energy,
            "reservoir_heat_gained_not_double_counted_as_actuator_work": bath_heat,
        },
        "entropy_terms": {
            "reservoir_entropy_flow_kB_units": bath_entropy,
            "controller_reset_bits": vals["controller_reset_bits"],
            "ideal_reset_entropy_lower_bound_kB": vals["controller_reset_bits"] * math.log(2.0),
        },
        "fuel_units_required": fuel_required,
        "fuel_units_available": vals["fuel_units_available"],
        "precursor_units_required": precursor_required,
        "precursor_units_available": vals["precursor_units_available"],
        "fuel_feasible": bool(fuel_ok),
        "precursor_feasible": bool(precursor_ok),
        "reservoir_capacity_checks": reservoir_checks,
        "reservoir_capacity_missing": reservoir_missing,
        "double_counting_rule": "Q_bath is reported separately and is not added to actuator/fuel demand; reset lower bound is a separate controller term.",
        "interpretation": "Model-unit resource result only; no laboratory energy conversion or measured actuator cost is asserted.",
    }
