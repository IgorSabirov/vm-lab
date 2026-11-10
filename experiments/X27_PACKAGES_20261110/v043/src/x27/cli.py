"""Command-line smoke and exact diagnostic runner for X27 v0.4.3."""
from __future__ import annotations

import argparse
import json
import hashlib
import platform
import sys
from pathlib import Path
from typing import Any

from .analysis import (
    g0_report,
    hq_partition,
    run_apparatus_factorial,
    run_memory_apparatus_interaction,
    run_x27a_matrix,
    deterministic_law,
    total_variation,
)
from .controls import run_e2_checks, run_pc_nc_controls
from .engine import run_b_lite
from .model import Arm, Disturbance, MemoryRecord, ModelConfig, RepairRecord, SubstituteCalibration


def _calibration() -> SubstituteCalibration:
    return SubstituteCalibration(True, True, True, True, True)



def _hash_project_sources() -> tuple[str, dict[str, str], str]:
    root = Path(__file__).resolve().parents[2]
    source_root = root / "src" / "x27"
    source_hashes: dict[str, str] = {}
    digest = hashlib.sha256()
    for path in sorted(source_root.glob("*.py")):
        raw = path.read_bytes()
        rel = path.relative_to(root).as_posix()
        file_hash = hashlib.sha256(raw).hexdigest()
        source_hashes[rel] = file_hash
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(raw)
        digest.update(b"\0")
    spec_path = root / "spec" / "model_manifest.json"
    spec_hash = hashlib.sha256(spec_path.read_bytes()).hexdigest() if spec_path.exists() else "MISSING"
    return digest.hexdigest(), source_hashes, spec_hash

def build_smoke_report(*, include_hq: bool = True) -> dict[str, Any]:
    config = ModelConfig()
    x27a = run_x27a_matrix(config=config)
    apparatus = run_apparatus_factorial(calibration=_calibration(), config=config)
    hma = run_memory_apparatus_interaction(config=config)

    r0 = run_b_lite(arm=Arm.R0, config=config)
    r_ext = run_b_lite(arm=Arm.R_EXT, config=config, causal_prod_read=False)
    r_int = run_b_lite(arm=Arm.R_INT, config=config, causal_prod_read=False)
    r2_r0 = run_b_lite(arm=Arm.R_INT, config=config, prod_memory=RepairRecord.make("r0"), causal_prod_read=True)
    r2_r1 = run_b_lite(arm=Arm.R_INT, config=config, prod_memory=RepairRecord.make("r1"), causal_prod_read=True)

    g0_a = g0_report(module="A", config=config)
    g0_b = g0_report(module="B-LITE", config=config)
    hq_a = hq_partition(module="A", config=config) if include_hq else {"status": "NOT_RUN"}
    hq_b = hq_partition(module="B-LITE", config=config) if include_hq else {"status": "NOT_RUN"}

    e2 = run_e2_checks()
    controls = run_pc_nc_controls()
    kernel_hash, source_hashes, spec_hash = _hash_project_sources()

    def b_profile(result):
        return (
            result.task2_success,
            result.state_final.task2_status,
            result.state_final.time,
            result.state_final.resources.as_tuple(),
            result.readiness.v_nom,
            result.readiness.v_rob,
        )

    r2_full_profile_tv = total_variation(
        deterministic_law(b_profile(r2_r0)),
        deterministic_law(b_profile(r2_r1)),
    )

    # The output is a software smoke/diagnostic artefact. It is not a scientific
    # main run, not a frozen preregistration, and not an empirical physical test.
    return {
        "experiment": "X27_U010_V03_CAUSAL_CONTINUITY",
        "version": "0.4.3-regression-repair-candidate",
        "status": "SOFTWARE_REGRESSION_VALIDATION_ONLY / DESIGN_DRAFT / NOT_FROZEN / MAIN_RUN_NOT_EXECUTED",
        "scientific_scope": "finite deterministic reference model only",
        "reproducibility": {
            "kernel_sha256": kernel_hash,
            "source_file_sha256": source_hashes,
            "spec_manifest_sha256": spec_hash,
            "python": sys.version,
            "platform": platform.platform(),
            "test_command": "PYTHONPATH=src python -m unittest discover -s tests -v",
            "smoke_command": "PYTHONPATH=src python -m x27.cli smoke --output validation/smoke_report.json",
        },
        "x27_a": x27a,
        "apparatus": apparatus,
        "memory_apparatus_interaction": hma,
        "x27_b_lite": {
            "R0": r0.as_dict(),
            "R_ext": r_ext.as_dict(),
            "R_int_R1_fixed_protocol": r_int.as_dict(),
            "R2_causal_r0": r2_r0.as_dict(),
            "R2_causal_r1": r2_r1.as_dict(),
            "R2_delta_U": r2_r1.state_final.resources.unavailable - r2_r0.state_final.resources.unavailable,
            "R2_TV_deterministic_profiles": float(r2_full_profile_tv),
        },
        "G0": {"X27-A": g0_a, "X27-B-LITE": g0_b},
        "H_Q": {"X27-A": hq_a, "X27-B-LITE": hq_b},
        "E2": e2,
        "PC_NC": controls,
        "freeze_status": "NOT_FROZEN",
        "main_run_status": "NOT_EXECUTED",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="X27 v0.4.3 finite reference kernel")
    sub = parser.add_subparsers(dest="command", required=True)
    smoke = sub.add_parser("smoke", help="run deterministic software smoke checks and exact finite diagnostics")
    smoke.add_argument("--output", type=Path, default=Path("x27_smoke_report.json"))
    smoke.add_argument("--skip-hq", action="store_true", help="skip exact H-Q partition enumeration")
    args = parser.parse_args()

    if args.command == "smoke":
        report = build_smoke_report(include_hq=not args.skip_hq)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        sidecars = {
            "G0_X27A_REACHABLE_CLOSURE.json": report["G0"]["X27-A"],
            "G0_X27BL_REACHABLE_CLOSURE.json": report["G0"]["X27-B-LITE"],
            "HQ_X27A_PARTITION.json": report["H_Q"]["X27-A"],
            "HQ_X27BL_PARTITION.json": report["H_Q"]["X27-B-LITE"],
            "E2_VALIDATION.json": report["E2"],
            "PC_NC_CONTROLS.json": report["PC_NC"],
        }
        for filename, payload in sidecars.items():
            (args.output.parent / filename).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({
            "output": str(args.output),
            "status": report["status"],
            "G0_A": report["G0"]["X27-A"]["status"],
            "G0_B": report["G0"]["X27-B-LITE"]["status"],
            "E2_all_pass": report["E2"]["all_pass"],
            "PC_NC_all_pass": report["PC_NC"]["summary"]["all_pass"],
            "main_run": "NOT_EXECUTED",
        }, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
