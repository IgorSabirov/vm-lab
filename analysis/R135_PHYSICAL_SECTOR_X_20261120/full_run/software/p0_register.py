"""Freeze and verify the design records of R135 P0. This command starts no scientific jobs."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile


HERE = Path(__file__).resolve().parent
PLAN = HERE.parent / "PLAN.json"
FILES = ("model_register.json", "data_release_lock.json", "decision_rules.json")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def indexed(rows, key):
    require(isinstance(rows, list) and len(rows) > 0, f"Empty table: {key}")
    result = {}
    for row in rows:
        label = row[key]
        require(isinstance(label, str) and label.strip() and label not in result,
                f"Missing or duplicate {key}: {label}")
        result[label] = row
    return result


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate_release_file(item, root):
    relative = Path(item["path"])
    require(not relative.is_absolute() and ".." not in relative.parts, "Invalid release file path")
    path = (root / relative).resolve()
    require(path.is_relative_to(root) and path.is_file(), f"Missing release file: {relative}")
    with path.open("rb") as stream:
        actual_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    require(actual_hash == item["sha256"], f"Release SHA-256 mismatch: {relative}")
    require(type(item["bytes"]) is int and path.stat().st_size == item["bytes"] > 0,
            f"Release size mismatch: {relative}")


def build(source):
    reg = load(source)
    plan = load(PLAN)
    models = reg["models"]
    points = reg["points"]
    releases = reg["data_releases"]
    rules = reg["rules"]
    model_ids = indexed(models, "model_id")
    point_ids = indexed(points, "point_id")
    data_ids = indexed(releases, "data_id")
    rule_ids = indexed(rules, "claim")
    require(set(rule_ids) == set(plan["claims"]), "Claim coverage differs from PLAN")
    require({r["architecture"] for r in models} == set(plan["architectures"]), "Architecture coverage")
    require(all(set(rule["models"]) and set(rule["models"]) <= model_ids.keys() for rule in rules),
            "Unknown model in decision rules")
    required_data = rule_ids["XB_SU3_cosmology"]["required_data_ids"]
    require(isinstance(required_data, list) and len(required_data) == len(set(required_data)) and
            bool(required_data) and set(required_data) <= data_ids.keys(), "Missing required observational dataset")
    for model in models:
        require(set(model["thermal_paths"]) == set(plan["thermal_paths"]), "Thermal paths")
        require(model["required_inputs"] and all(isinstance(s, str) and s for s in model["required_inputs"]),
                "Missing physical input declarations")
    reference = reg.get("xb_reference")
    if reference:
        for item in (reference["inputs"], reference["coordinates"]):
            validate_release_file(item, source.resolve().parent)
        xb = load(source.parent / reference["inputs"]["path"])
        preparations = indexed(xb["preparations"], "point_id")
        coordinates = indexed(load(source.parent / reference["coordinates"]["path"])["points"], "point_id")
        require(preparations.keys() == coordinates.keys() ==
                {p["point_id"] for p in points if p["role"] == "literature_benchmark"},
                "Incomplete published benchmark coverage")
    for point in points:
        require(point["role"] in {"diagnostic", "physical_candidate", "literature_benchmark"}, "Unknown point role")
        require(point["model_id"] in model_ids, "Unknown point model")
        require(point["thermal_path"] in model_ids[point["model_id"]]["thermal_paths"], "Unknown thermal path")
        require(isinstance(point["origin"], str) and point["origin"].strip(), "Missing point provenance")
        if point["role"] == "physical_candidate":
            require(point.get("initial_history_id"), "Physical candidate needs an initial-history reference")
            for key in ("history_file", "calibration_file"):
                require(key in point, f"Missing physical point evidence: {key}")
                validate_release_file(point[key], source.resolve().parent)
            history = load(source.parent / point["history_file"]["path"])
            calibration = load(source.parent / point["calibration_file"]["path"])
            require(history["history_id"] == point["initial_history_id"] and
                    history["model_id"] == point["model_id"] and
                    history["thermal_path"] == point["thermal_path"] and
                    history["epoch"] and history["initial_conditions"], "Physical preparation mismatch")
            require(calibration["model_id"] == point["model_id"] and
                    calibration["kind"] in {"independent_measurement", "independent_model_prediction"} and
                    calibration["independent_of_R135_BBN_CMB"] is True and
                    number(calibration["scale_MeV"]) and calibration["scale_MeV"] > 0 and
                    calibration["source_locator"] and calibration["uncertainty_budget"],
                    "No independent scale evidence")
            require(point["independent_parameters"] == calibration["parameters"],
                    "Calibration values differ from cited evidence")
            for param in indexed(point["independent_parameters"], "name").values():
                require(number(param["value"]) and param["unit"] and param["source"],
                        "Physical parameter needs value, unit and source")
        elif point["role"] == "literature_benchmark":
            require(reference and point["point_id"] in preparations, "Missing published preparation")
            prep = preparations[point["point_id"]]
            coord = coordinates[point["point_id"]]
            history = xb["initial_history"]
            require(point["model_id"] == history["model_id"] and
                    point["thermal_path"] == history["thermal_path"] and
                    point["initial_history_id"] == history["history_id"] == prep["history_id"] and
                    point["origin"] == xb["sources"][prep["source"]]["url"] and
                    point["m0_GeV"] == prep["m0_GeV"] == coord["m0_GeV"] > 0 and
                    point["R_post"] == prep["R_post"] == coord["R_post"] > 0,
                    "Published preparation differs from source inputs")
            require(math.isclose(coord["xi"], coord["T_X_MeV"] / coord["T_gamma_MeV"],
                                 rel_tol=1e-12), "Boundary temperature mismatch")
        else:
            require(number(point["T_gamma_event_MeV"]) and point["T_gamma_event_MeV"] > 0, "Invalid T_gamma")
            require(number(point["xi_event"]) and point["xi_event"] > 0, "Invalid xi")
    for release in data_ids.values():
        require(release["source"] and release["version"], "Missing release provenance")
        if release["state"] == "published_statistic":
            require(number(release["value"]) and number(release["sigma"]) and release["sigma"] > 0,
                    "Invalid reported statistic")
            require(release["observable"] and release["units"], "Missing observable")
        elif release["state"] == "artifact_required":
            require(release["missing"], "Missing artifact requirements")
        elif release["state"] in {"verified_files", "verified_external_bundle"}:
            for item in indexed(release["files"], "path").values():
                validate_release_file(item, source.resolve().parent)
            if release["state"] == "verified_external_bundle":
                require(release["bundle_manifest"] in {item["path"] for item in release["files"]},
                        "External manifest itself must be locked")
                manifest = load(source.parent / release["bundle_manifest"])
                require(manifest["data_id"] == release["data_id"] and manifest["members"] and
                        set(manifest["components"]) == {"Plik", "Commander", "SimAll"} and
                        manifest["archive"]["bytes"] > 0 and len(manifest["archive"]["sha256"]) == 64,
                        "Invalid Planck external bundle")
        else:
            raise ValueError("Unsupported release state: "+release["state"])
    require({p["model_id"] for p in point_ids.values()} == set(model_ids), "Point coverage")
    require({(p["model_id"],p["thermal_path"]) for p in points} ==
            {(m["model_id"],t) for m in models for t in m["thermal_paths"]}, "Point coverage by thermal path")
    meta = dict(schema="R135-P0-design-v2", plan_sha256=sha(PLAN.read_bytes()),
                register_sha256=sha(encoded(reg)), freeze_scope="design_records")
    counts = {role: sum(p["role"] == role for p in points)
              for role in ("diagnostic", "literature_benchmark", "physical_candidate")}
    return {
        FILES[0]: dict(**meta, models=models, points=points, point_counts=counts, xb_reference=reference),
        FILES[1]: dict(**meta, data_releases=releases),
        FILES[2]: dict(**meta, rules=rules, physical_launch_authorized=False),
    }


def verify(dest, expected):
    require(dest.is_dir(), f"Missing output directory: {dest}")
    actual_files = {f.name for f in dest.iterdir()}
    require(actual_files == set(FILES) | {"P0_SHA256.json"}, "Unexpected or missing files")
    hashes = {}
    for name in FILES:
        data = (dest / name).read_bytes()
        require(data == encoded(expected[name]), f"Mismatch against declared input: {name}")
        hashes[name] = sha(data)
    require((dest / "P0_SHA256.json").read_bytes() == encoded(hashes), "Digest manifest mismatch")
    return hashes


def freeze(dest, expected):
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix=".p0-", dir=dest.parent))
        try:
            hashes = {}
            for name in FILES:
                data = encoded(expected[name])
                (tmp / name).write_bytes(data)
                hashes[name] = sha(data)
            (tmp / "P0_SHA256.json").write_bytes(encoded(hashes))
            verify(tmp, expected)
            try:
                os.rename(tmp, dest)
            except OSError:
                if not dest.exists():
                    raise
        finally:
            if tmp.exists():
                shutil.rmtree(tmp)
    return verify(dest, expected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=["freeze","verify"])
    parser.add_argument("--registry",type=Path,default=HERE/"register_inputs.json")
    parser.add_argument("--out",type=Path,required=True)
    args = parser.parse_args()
    expected = build(args.registry)
    hashes = (freeze if args.action=="freeze" else verify)(args.out,expected)
    print(json.dumps({"status":"DESIGN_RECORDS_VERIFIED","artifacts":hashes},indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, ValueError, TypeError) as error:
        sys.exit(str(error))
