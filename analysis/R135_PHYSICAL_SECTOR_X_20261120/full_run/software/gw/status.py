"""Check GW coverage of the frozen P0 matrix. Missing evidence is an explicit scientific output."""

import argparse
import hashlib
import json
from pathlib import Path


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
            row.update(
                status="CONDITIONAL",
                response=entry["response"],
                history=entry["history"],
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
