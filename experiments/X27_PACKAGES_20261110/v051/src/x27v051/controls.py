"""Exact smoke controls and independent metric consistency checks."""
from __future__ import annotations
from fractions import Fraction
from typing import Any

from .audit import calibrate_a2, run_nc13, run_nc15, run_nc16
from .engine import functional_repair_contrast, run_b_lite, run_dose_sweep, validate_read_before_action
from .evaluation import capability_matrix, legacy_policy_baseline
from .hq import exact_partition
from .metrics import direct_total_variation, point_mass, total_variation, validate_distribution
from .model import MemoryRecord, RepairRecord, TraceEvent
from .resources import saturation_probe


def run_hq_algorithm_control() -> dict[str, object]:
    # Tiny exactly solvable finite deterministic graph. Terminal is an output leaf.
    states = (0, 1, 2)
    def transition(s: int, action: str):
        if action != "continue":
            raise ValueError(action)
        if s == 2:
            return ("output", ("TERMINAL", 1))
        return ("state", s + 1)
    result = exact_partition(states, ("continue",), transition, lambda _: ("same-current-observation",))
    return {**result, "expected_class_count": 3,
            "pass": result["class_count"] == 3,
            "scope": "Algorithm sanity control only; not the full X27 H-Q model partition."}


def run_e2_exact_controls() -> dict[str, object]:
    p = {"a": Fraction(1, 1)}
    q = {"b": Fraction(1, 1)}
    z = {"a": Fraction(1, 1)}
    tv_zero = total_variation(p, z)
    tv_disjoint = total_variation(p, q)
    tv_reverse = total_variation(q, p)
    checks = {
        "zero_distance": tv_zero == 0,
        "symmetry": tv_disjoint == tv_reverse,
        "upper_bound": Fraction(0) <= tv_disjoint <= Fraction(1),
        "disjoint_support": tv_disjoint == 1,
        "exact_rational": isinstance(tv_disjoint, Fraction),
    }
    rejected = {}
    for label, invalid in (
        ("negative", {"a": 2, "b": -1}),
        ("float", {"a": 0.5, "b": 0.5}),
        ("unnormalized", {"a": 2}),
        ("boolean", {"a": True}),
    ):
        try:
            validate_distribution(invalid)
            rejected[label] = False
        except (TypeError, ValueError):
            rejected[label] = True
    checks["invalid_laws_rejected"] = all(rejected.values())
    direct = direct_total_variation(p, q)
    checks["independent_direct_sum"] = direct == tv_disjoint
    return {"checks": checks, "rejected_invalid_examples": rejected,
            "TV_zero": str(tv_zero), "TV_disjoint": str(tv_disjoint),
            "TV_reverse": str(tv_reverse), "TV_independent": str(direct),
            "pass": all(checks.values())}


def run_positive_controls() -> dict[str, object]:
    matrix = capability_matrix()
    by_policy: dict[str, list[dict[str, object]]] = {}
    for row in matrix:
        by_policy.setdefault(str(row["policy"]), []).append(row)
    pc1 = all(r["read_source"] == "M_task" and r["readout_fidelity"] is True and r["causal_source_use"]
              for r in by_policy["pi_M"])
    pc2 = all(r["read_source"] == "P_res" and r["readout_fidelity"] is True and r["causal_source_use"]
              for r in by_policy["pi_P"])
    pc3 = all(r["read_source"] is None and r["causal_source_use"] is False for r in by_policy["pi_fixed"])
    pc4 = functional_repair_contrast()
    pc5 = run_dose_sweep()
    pc6 = calibrate_a2()
    pc7 = run_hq_algorithm_control()
    pc8 = saturation_probe()
    legacy = legacy_policy_baseline()
    pc9 = len(legacy) == 8 and all(r["read_source"] == "M_task" for r in legacy)
    checks = {
        "PC1_M_readout_causal_path": pc1,
        "PC2_P_readout_causal_path": pc2,
        "PC3_fixed_policy_has_no_read": pc3,
        "PC4_R2_functional_high_load_contrast": pc4["R2_PASS"],
        "PC5_nominal_and_robust_dose_thresholds": pc5["E_star_nominal"] == 3 and pc5["E_star_robust"] == 4,
        "PC6_A2_computed_calibration": pc6["valid"],
        "PC7_exact_HQ_algorithm_sanity": pc7["pass"],
        "PC8_component_capacity_overflow": pc8["pass"],
        "PC9_legacy_pi0_separate": pc9,
    }
    return {"checks": checks, "details": {"R2": pc4, "dose": pc5,
            "A2_calibration": pc6, "HQ_algorithm": pc7, "capacity": pc8,
            "legacy_policy_rows": len(legacy)},
            "pass_count": sum(checks.values()), "total": len(checks), "pass": all(checks.values())}


def run_negative_controls() -> dict[str, object]:
    nc13 = run_nc13()
    nc15 = run_nc15()
    nc16 = run_nc16()
    # Task-1 checksum failure must remain distinct from an absent read.
    corrupt = run_b_lite("R_int", 3, task_memory=MemoryRecord("M_task", 1, 0, 0, "C"))
    nc14 = {
        "pre_task2_terminal_cause": corrupt.pre_task2_terminal_cause,
        "task2_reached": corrupt.task2_reached,
        "integrity_event": any(e.event_type == "integrity_error_event" for e in corrupt.events),
        "task_read_event": any(e.event_type == "read_event" and dict(e.details).get("source") == "M_task"
                                and dict(e.details).get("task") == "Task1" for e in corrupt.events),
        "mprod_does_not_substitute": validate_read_before_action((
            TraceEvent("read_event", 3, 3, (("source", "M_prod"), ("task", "repair"))),
            TraceEvent("action_event", 2, 2, (("task", "Task1"), ("operand", 0)))),
            "M_task", "Task1") == "MISSING_READ_EVENT",
    }
    nc14["pass"] = (nc14["pre_task2_terminal_cause"] == "INTEGRITY_ERROR"
                     and not nc14["task2_reached"] and nc14["integrity_event"]
                     and not nc14["task_read_event"] and nc14["mprod_does_not_substitute"])
    checks = {"NC13_estimator_purity_nested_fields": nc13["pass"],
              "NC14_integrity_error_distinct": nc14["pass"],
              "NC15_opaque_identifier_channel": nc15["pass"],
              "NC16_oracle_and_service_field_whitelist": nc16["pass"]}
    return {"checks": checks, "details": {"NC13": nc13, "NC14": nc14,
            "NC15": nc15, "NC16": nc16},
            "pass_count": sum(checks.values()), "total": len(checks), "pass": all(checks.values())}
