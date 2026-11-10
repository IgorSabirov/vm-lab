"""Command-line smoke and artifact generation for X27 v0.5.1."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import platform
import sys
from pathlib import Path
from typing import Any

from .audit import calibrate_a2, run_nc13, run_nc15, run_nc16, static_policy_audit
from .controls import run_e2_exact_controls, run_negative_controls, run_positive_controls
from .engine import functional_repair_contrast, run_b_lite, run_dose_sweep
from .evaluation import (
    capability_matrix, capability_factorial_contrasts, legacy_policy_baseline,
    run_apparatus_class_contrast, score_b_lite_run,
)
from .hq import generate_intervention_sequences, hq_observable_contract
from .model import MemoryRecord, RepairRecord
from .resources import saturation_probe


def _json_default(value: Any) -> Any:
    if hasattr(value, "as_dict"):
        return value.as_dict()
    if isinstance(value, (set, frozenset, tuple)):
        return list(value)
    if hasattr(value, "value"):
        return value.value
    raise TypeError(f"cannot JSON-serialize {type(value).__name__}")


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True, default=_json_default) + "\n", encoding="utf-8")


def _hash_files(paths: list[Path], root: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(paths):
        h.update(str(path.relative_to(root)).encode("utf-8"))
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def run_smoke(output_dir: str | Path) -> dict[str, object]:
    root = Path(__file__).resolve().parents[2]
    out = Path(output_dir)
    if not out.is_absolute():
        out = (Path.cwd() / out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    src_files = list((root / "src").rglob("*.py"))
    spec_files = [p for p in (root / "spec").rglob("*") if p.is_file()]
    kernel_hash = _hash_files(src_files, root)
    manifest_hash = _hash_files(spec_files, root)

    matrix = capability_matrix()
    factorial_contrasts = capability_factorial_contrasts(matrix)
    apparatus_class = run_apparatus_class_contrast()
    legacy = legacy_policy_baseline()
    dose = run_dose_sweep()
    r2 = functional_repair_contrast()
    nc13 = run_nc13()
    nc15 = run_nc15()
    nc16 = run_nc16()
    calibration = calibrate_a2()
    e2 = run_e2_exact_controls()
    pc = run_positive_controls()
    nc = run_negative_controls()
    static_audit = static_policy_audit()
    saturation = saturation_probe()

    r0 = score_b_lite_run(run_b_lite("R0", 3, load=1), "eval_case_opaque_A")
    rint = score_b_lite_run(run_b_lite("R_int", 3, load=1), "eval_case_opaque_A")
    r_ext = score_b_lite_run(run_b_lite("R_ext", 3, load=1), "eval_case_opaque_A")

    seq_a = generate_intervention_sequences("A", 2)
    seq_b = generate_intervention_sequences("B-LITE", 2)
    hq_contract = hq_observable_contract()

    fields = list(matrix[0].keys())
    with (out / "CAPABILITY_MATRIX.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in matrix:
            writer.writerow({k: json.dumps(v, sort_keys=True, default=_json_default)
                             if isinstance(v, (tuple, list, dict)) else v for k, v in row.items()})
    with (out / "PI0_LEGACY_BASELINE.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(legacy[0].keys()))
        writer.writeheader()
        for row in legacy:
            writer.writerow({k: json.dumps(v, sort_keys=True, default=_json_default)
                             if isinstance(v, (tuple, list, dict)) else v for k, v in row.items()})

    _write_json(out / "CAPABILITY_FACTORIAL_CONTRASTS.json", factorial_contrasts)
    _write_json(out / "APPARATUS_CLASS_CONTRAST.json", apparatus_class)
    _write_json(out / "NC13_RESULTS.json", nc13)
    _write_json(out / "NC15_RESULTS.json", nc15)
    _write_json(out / "NC16_RESULTS.json", nc16)
    _write_json(out / "A2_CALIBRATION_RESULTS.json", calibration)
    _write_json(out / "DOSE_SWEEP.json", dose)
    _write_json(out / "R2_FUNCTIONAL_CONTRAST.json", r2)
    _write_json(out / "E2_EXACT_VALIDATION.json", e2)
    _write_json(out / "POSITIVE_CONTROLS.json", pc)
    _write_json(out / "NEGATIVE_CONTROLS.json", nc)
    _write_json(out / "HQ_INTERVENTION_SEQUENCES.json", {"A": seq_a, "B_LITE": seq_b})
    _write_json(out / "HQ_OBSERVABLES.json", hq_contract)
    _write_json(out / "STATIC_POLICY_AUDIT.json", static_audit)
    _write_json(out / "RESOURCE_SATURATION_CONTROL.json", saturation)

    policy_summary = {}
    for policy in sorted({str(r["policy"]) for r in matrix}):
        rows = [r for r in matrix if r["policy"] == policy]
        scored = [r for r in rows if r["Y_correct"] is not None]
        summary = {
            "cells": len(rows), "scored_cells": len(scored),
            "correct_cells": sum(bool(r["Y_correct"]) for r in scored),
            "accuracy_over_scored_cells": (f"{sum(bool(r['Y_correct']) for r in scored)}/{len(scored)}"
                                           if scored else None),
            "read_sources": sorted({r["read_source"] for r in rows if r["read_source"] is not None}),
        }
        alignment_field = {"pi_M": "M_matches_oracle", "pi_P": "P_matches_oracle"}.get(policy)
        if alignment_field is not None:
            aligned = [r for r in scored if r[alignment_field]]
            misaligned = [r for r in scored if not r[alignment_field]]
            summary["source_alignment_accuracy"] = {
                "alignment_field": alignment_field,
                "aligned_correct": sum(bool(r["Y_correct"]) for r in aligned),
                "aligned_total": len(aligned),
                "misaligned_correct": sum(bool(r["Y_correct"]) for r in misaligned),
                "misaligned_total": len(misaligned),
                "aligned_accuracy": (f"{sum(bool(r['Y_correct']) for r in aligned)}/{len(aligned)}"
                                     if aligned else None),
                "misaligned_accuracy": (f"{sum(bool(r['Y_correct']) for r in misaligned)}/{len(misaligned)}"
                                        if misaligned else None),
            }
        policy_summary[policy] = summary

    # R1 diagnostic: under h2 -> Task1 h1, fixed r0 maps h1 -> h1.
    r1_diagnostic = {
        "R0_no_repair": r0.as_dict(),
        "R_int_fixed_r0": rint.as_dict(),
        "R_ext": r_ext.as_dict(),
        "R0_vs_Rint_nominal_same_task_success": r0.execution.executed.success == rint.execution.executed.success,
        "R0_vs_Rint_robust": {"R0": r0.execution.readiness.v_rob if r0.execution.readiness else None,
                              "R_int_r0": rint.execution.readiness.v_rob if rint.execution.readiness else None},
        "r0_health_gain": rint.execution.repair_health_gain,
        "interpretation": "Because Task1 changes h:2->1 and r0 sets h'=1, r0 has zero health gain. At load=1, R0 without repair also succeeds. The model therefore does not show that r0 repair is functionally necessary; this is a design limitation, not a PASS.",
    }
    _write_json(out / "R1_FUNCTIONAL_LIMITATION.json", r1_diagnostic)

    report: dict[str, object] = {
        "experiment": "X27_U010_V03_CAUSAL_CONTINUITY",
        "implementation": "v0.5.1-oracle-policy-repair-dose-reference",
        "status": "DESIGN_DRAFT / NOT_FROZEN / MAIN_RUN_NOT_EXECUTED",
        "validation_type": "SOFTWARE_SMOKE_ONLY",
        "kernel_hash_sha256": kernel_hash,
        "spec_manifest_hash_sha256": manifest_hash,
        "source_file_count": len(src_files),
        "spec_file_count": len(spec_files),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "capability_matrix": {"rows": len(matrix), "expected_rows": 40,
                               "policy_summary": policy_summary,
                               "full_matrix_pass": len(matrix) == 40},
        "capability_factorial_contrasts": factorial_contrasts,
        "apparatus_class_contrast": apparatus_class,
        "legacy_pi0": {"rows": len(legacy), "kept_separate": True},
        "dose_sweep": dose,
        "R2_functional_contrast": r2,
        "R1_functional_benefit": "NOT_DEMONSTRATED_FOR_r0_UNDER_D3_RULES",
        "R1_limitation": r1_diagnostic,
        "NC13": nc13,
        "NC15": {k: v for k, v in nc15.items() if k != "rows"},
        "NC16": {k: v for k, v in nc16.items() if k != "runtime_attempts"},
        "A2_calibration": calibration,
        "E2": e2,
        "positive_controls": {k: v for k, v in pc.items() if k != "details"},
        "negative_controls": {k: v for k, v in nc.items() if k != "details"},
        "HQ": {"contract": hq_contract, "sequence_count_A": seq_a["sequence_count"],
               "sequence_count_B_LITE": seq_b["sequence_count"],
               "full_model_partition_status": "NOT_EVALUATED_ADAPTER_PENDING"},
        "G0_reachable_closure": "NOT_EVALUATED_FOR_V0_5_1_FULL_INTERVENTION_KERNEL",
        "software_checks": {
            "capability_matrix_40": len(matrix) == 40,
            "factorial_contrast_patterns": factorial_contrasts["source_factor_patterns_match_policy_contract"],
            "H_A_class": apparatus_class["H_A_class"] == "PASS",
            "NC13": nc13["pass"], "NC15": nc15["pass"], "NC16": nc16["pass"],
            "A2_calibration": calibration["valid"], "E2": e2["pass"],
            "PC": pc["pass"], "NC": nc["pass"], "saturation": saturation["pass"],
        },
        "software_smoke_pass": (len(matrix) == 40 and factorial_contrasts["source_factor_patterns_match_policy_contract"]
                                and apparatus_class["H_A_class"] == "PASS"
                                and nc13["pass"] and nc15["pass"] and nc16["pass"]
                                and calibration["valid"] and e2["pass"] and pc["pass"] and nc["pass"]
                                and saturation["pass"]),
        "freeze_authorized": False,
        "G7_main_run_authorized": False,
        "physical_mechanism": "NOT_ESTABLISHED",
    }
    _write_json(out / "SMOKE_REPORT.json", report)
    # Hashes are generated after all reports are written; self-hash is intentionally excluded.
    files = sorted(p for p in out.rglob("*") if p.is_file() and p.name != "SHA256SUMS.txt")
    sums = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out).as_posix()}" for p in files]
    (out / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="x27v051")
    sub = parser.add_subparsers(dest="command", required=True)
    smoke = sub.add_parser("smoke", help="run exact software diagnostics and write artifacts")
    smoke.add_argument("--output", default="validation", help="output directory")
    args = parser.parse_args(argv)
    if args.command == "smoke":
        report = run_smoke(args.output)
        print(json.dumps({"software_smoke_pass": report["software_smoke_pass"],
                          "capability_rows": report["capability_matrix"]["rows"],
                          "factorial_contrasts_pass": report["software_checks"]["factorial_contrast_patterns"],
                          "H_A_class": report["apparatus_class_contrast"]["H_A_class"],
                          "E_star_nominal": report["dose_sweep"]["E_star_nominal"],
                          "E_star_robust": report["dose_sweep"]["E_star_robust"],
                          "R2_PASS": report["R2_functional_contrast"]["R2_PASS"],
                          "R1_functional_benefit": report["R1_functional_benefit"],
                          "G0": report["G0_reachable_closure"],
                          "H_Q": report["HQ"]["full_model_partition_status"],
                          "G7": report["G7_main_run_authorized"]}, indent=2))
        return 0 if report["software_smoke_pass"] else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
