"""Check GW coverage of the frozen P0 matrix. Missing evidence is an explicit scientific output."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np


def load(path):
    return json.loads(path.read_text())


def linked(root, ref):
    p = (root / ref["file"]).resolve()
    if (
        not p.is_relative_to(root.resolve())
        or hashlib.sha256(p.read_bytes()).hexdigest() != ref["sha256"]
    ):
        raise ValueError("Invalid GW evidence path or digest")
    return load(p)


def coverage(points, submissions, root):
    known = {p["point_id"] for p in points}
    if len(known) != len(points):
        raise ValueError("Duplicate GW point in the frozen matrix")
    if submissions.keys() - known:
        raise ValueError("Unknown GW point")
    rows = []
    for point in points:
        pid = point["point_id"]
        entry = submissions.get(pid, {})
        row = {k: point[k] for k in ("point_id", "model_id", "thermal_path", "role")}
        if not entry:
            row.update(
                status="OPEN_INPUT",
                missing=[
                    "P5 spectrum or source law",
                    "common P7 history and uncertainty",
                ],
            )
        elif "response" in entry:
            if "inapplicability_evidence" in entry:
                raise ValueError("GW response and inapplicability cannot replace each other implicitly")
            history = linked(root, entry["history"])
            response = linked(root, entry["response"])
            if (
                any(
                    history.get(k) != row[k]
                    for k in ("point_id", "model_id", "thermal_path")
                )
                or response.get("history_id") != history.get("history_id")
                or response.get("point_id") != pid
                or response.get("input_sha256") != entry["history"]["sha256"]
                or not response.get("bbn_budget")
                or not response.get("detectors")
            ):
                raise ValueError(
                    "GW response belongs to a different history or lacks outputs"
                )
            # A hash only identifies bytes. Reconstruct the actual transfer and
            # epoch budget before treating the supplied response as computed.
            spec = importlib.util.spec_from_file_location("r135_legacy_gw_transfer",Path(__file__).with_name("response.py"))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            frequency, omega, budget = module.transfer(history)
            if (not np.array_equal(np.asarray(response.get("f_today_Hz")),frequency)
                    or not np.allclose(np.asarray(response.get("Omega_GW_today")),omega,rtol=1e-12,atol=0)
                    or budget != response["bbn_budget"]):
                raise ValueError("GW transfer or BBN budget failed independent reconstruction")
            row.update(
                status="CONDITIONAL",
                response=entry["response"],
                history=entry["history"],
                physical_completion=False,
                remaining=["legacy end-spectrum input does not reconstruct coupled P7 energy debit",
                           "PTA full likelihood and LVK foreground/systematics remain open"],
            )
        else:
            # Scientific exclusion needs an identified, inspectable upstream result.
            proof = linked(root, entry["inapplicability_evidence"])
            if any(
                proof.get(k) != row[k] for k in ("point_id", "model_id", "thermal_path")
            ) or not proof.get("physical_argument"):
                raise ValueError(
                    "Inapplicability evidence missing or assigned to a different branch"
                )
            row.update(
                status="INAPPLICABILITY_FOR_REVIEW",
                evidence=entry["inapplicability_evidence"],
            )
        rows.append(row)
    return rows


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--p0", type=Path, required=True)
    p.add_argument("--evidence", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    root = args.evidence.parent if args.evidence else Path.cwd()
    rows = coverage(
        load(args.p0)["points"], load(args.evidence) if args.evidence else {}, root
    )
    args.output.write_text(json.dumps(rows, indent=2) + "\n")
