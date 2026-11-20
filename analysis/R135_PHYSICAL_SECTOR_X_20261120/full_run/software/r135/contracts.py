"""Stage requests, content-addressed inputs and atomic, verifiable results.

This contract concerns numerical reproducibility, not launch permission or
scientific acceptance. It does not change infra/run_contract.py.
"""
from __future__ import annotations

import importlib
import os
import platform
import re
import subprocess
import tempfile
import time
import traceback
from pathlib import Path

from .common import (InputError, OpenInput, canonical_hash, file_record, read_json,
                     sha256, write_json)

HERE = Path(__file__).resolve().parents[1]
REPO = HERE.parents[3]
STAGES = {
    "P1": "thermodynamics", "P2": "graph", "P3": "lattice",
    "P4": "response", "P5": "nucleation", "P6": "collisions",
    "P7": "history", "P8": "observations", "P9": "backends", "P10": "audit",
}
KEY_FIELDS = ("claim_id", "model_id", "point_id", "thermal_path")
PATHS = ("isolated_during_transition", "exchange_during_transition")


def source_inventory() -> dict:
    paths = list((HERE / "r135").rglob("*.py")) + [HERE / "p0_register.py"]
    paths += list((HERE / "planck_pr3").glob("*.py"))
    paths += [HERE / "r135_stage.py"] if (HERE / "r135_stage.py").exists() else []
    paths += [HERE / "register_inputs.json", HERE.parent / "PLAN.json"]
    paths += list(HERE.glob("*_sources.lock.json"))
    paths += [p for p in (HERE/"cascade_requirements.lock",HERE/"neutrino_reference/sources.json",
                          HERE/"perturbations_reference/SOURCES.lock.json") if p.is_file()]
    paths += list((HERE / "planck_pr3").glob("*.json")) + list((HERE / "planck_pr3").glob("*.lock"))
    paths += list((HERE / "xb_reference").glob("*.json"))
    paths += [HERE.parent.parent / "run_design" / name for name in
              ("measure_field.py", "cumulants.py", "PROTOCOL.json")]
    paths += [REPO / "analysis/ADD_NEIGHBOR_SYNTHESIS_20261117/verify.py"]
    paths += [REPO / "analysis/PRIMAT_LINX_BBN_BRIDGE_20261117" / name for name in
              ("validate_contract.py", "BBN_HISTORY.schema.json", "NETWORK_MAP.json")]
    records = [file_record(p.resolve(), REPO) for p in sorted(set(paths))]
    return {"sha256": canonical_hash(records), "files": records, "source_root": "repository"}


def source_matches_commit(inventory: dict, commit: str) -> bool:
    """A source SHA is attribution only when every executed local module agrees."""
    for record in inventory["files"]:
        path = record["path"]
        blob = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=REPO,
                              capture_output=True)
        if blob.returncode or __import__("hashlib").sha256(blob.stdout).hexdigest() != record["sha256"]:
            return False
    return True


def _commit() -> str | None:
    p = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE,
                       text=True, capture_output=True)
    return p.stdout.strip() if p.returncode == 0 else None


def _key(request: dict) -> dict:
    key = request.get("key", {})
    if set(key) != set(KEY_FIELDS) or any(not isinstance(key[k], str) or not key[k]
                                          for k in KEY_FIELDS):
        raise InputError(f"key must contain exactly {KEY_FIELDS}")
    if key["thermal_path"] not in PATHS:
        raise InputError("unknown thermal_path")
    if key["claim_id"] not in {"XA_carrier", "XB_SU3_cosmology", "graph_as_XB_marker"}:
        raise InputError("unknown registered claim")
    return key


def _p0_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("r135_existing_p0", HERE / "p0_register.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def verified_registry(inputs: dict) -> tuple[dict, dict]:
    """Verify all P0 records against their source, not merely one copied file."""
    folder = inputs["model_register"].parent
    mod = _p0_module()
    expected = mod.build(inputs.get("registry", HERE / "register_inputs.json"))
    for name in mod.FILES:
        path = folder / name
        if not path.is_file() or path.read_bytes() != mod.encoded(expected[name]):
            raise InputError(f"P0 snapshot does not match its registered source: {name}")
    if (folder / "MANIFEST.json").exists():
        parent = verify_result(folder)
        if parent["stage"] != "P0" or parent["result"]["software_status"] != "PASS":
            raise InputError("P0 stage did not verify its records")
    elif (folder / "P0_SHA256.json").exists():
        mod.verify(folder, expected)
    else:
        raise OpenInput("P0 records need their frozen snapshot or verified stage manifest")
    return expected["model_register.json"], expected["decision_rules.json"]


def validate_request(request: dict, stage: str, base: Path) -> tuple[dict, dict]:
    if request.get("schema") != "r135-stage-request-v1":
        raise InputError("unsupported stage request schema")
    if request.get("stage") != stage or stage not in {"P0", *STAGES}:
        raise InputError("stage mismatch")
    _key(request)
    if not re.fullmatch("[0-9a-f]{40}", request.get("execution_sha", "")):
        raise InputError("execution_sha must be the exact 40-hex source commit")
    actual_commit = _commit()
    if actual_commit is not None and request["execution_sha"] != actual_commit:
        raise InputError("execution_sha differs from checked-out HEAD")
    config = request.get("config")
    if not isinstance(config, dict) or canonical_hash(config) != request.get("config_sha256"):
        raise InputError("configuration checksum mismatch")
    if config.get("thermal_path", request["key"]["thermal_path"]) != request["key"]["thermal_path"]:
        raise InputError("configuration thermal path differs from the request key")
    if any(k.startswith("_") for k in config):
        raise InputError("configuration keys beginning '_' are reserved")
    mode = request.get("mode")
    if mode not in {"validation", "conditional", "physical"}:
        raise InputError("mode must be validation, conditional or physical")
    applicability = request.get("applicability")
    if not isinstance(applicability, dict) or not applicability.get("description"):
        raise InputError("explicit applicability description is required")
    inv = source_inventory()
    if request.get("source_sha256") != inv["sha256"]:
        raise InputError("source content checksum mismatch; seal the current code")
    if mode != "validation" and not source_matches_commit(inv, request["execution_sha"]):
        raise InputError("non-validation execution requires source bytes committed at execution_sha")
    inputs = {}
    records = request.get("inputs")
    if not isinstance(records, list):
        raise InputError("inputs must be a list, including for a self-contained request")
    for rec in records:
        name = rec.get("name")
        if not isinstance(name, str) or not name or name in inputs:
            raise InputError("missing or duplicate input name")
        given = Path(rec.get("path", ""))
        path = given if given.is_absolute() else base / given
        if not path.is_file() or path.is_symlink():
            raise OpenInput(f"input {name} is not an available regular file")
        if sha256(path) != rec.get("sha256"):
            raise InputError(f"input {name}: checksum mismatch")
        parent_stages = {"channel_history": "P7", "bbn_inputs": "P8", "class_inputs": "P8"}
        if stage == "P7":
            parent_stages["initial_history"] = "P1"
        if name in parent_stages:
            parent = path.parent / "MANIFEST.json"
            if parent.exists():
                previous = verify_result(path.parent)
                if previous["stage"] != parent_stages[name] or previous["key"] != request["key"]:
                    raise InputError(f"input {name} belongs to another stage/model/point/path/claim")
                if previous["result"]["software_status"] != "PASS" or previous["result"]["evidence_status"] in {"OPEN_INPUT", "TECHNICAL_FAILURE", "INCONCLUSIVE", "NECESSARY_CONDITION_FAILED"}:
                    raise OpenInput(f"input {name}: parent did not produce an admissible calculation")
                if mode != "validation" and (previous["mode"] == "validation" or previous["result"]["evidence_status"] == "DIAGNOSTIC"):
                    raise InputError(f"input {name}: a diagnostic history cannot be promoted to physical evidence")
                if mode == "physical" and previous["mode"] != "physical":
                    raise OpenInput(f"input {name}: physical mode requires a physical parent preparation")
            elif mode != "validation":
                raise OpenInput(f"input {name} requires its verified parent stage bundle")
        inputs[name] = path.resolve()
    if mode != "validation":
        if "model_register" not in inputs:
            raise OpenInput("non-validation stages require the frozen P0 model_register")
        registry, rules = verified_registry(inputs)
        rule = next((r for r in rules["rules"] if r["claim"] == request["key"]["claim_id"]), None)
        if rule is None or request["key"]["model_id"] not in rule["models"]:
            raise InputError("claim/model pairing is absent from the frozen P0 rules")
        # P0 file deliberately retains its design scope and origin distinctions.
        points = registry.get("points", [])
        point = next((p for p in points if p.get("id", p.get("point_id")) ==
                      request["key"]["point_id"]), None)
        if point is None or point.get("model_id") != request["key"]["model_id"]:
            raise InputError("point/model is absent from the frozen P0 register")
        if point.get("thermal_path") != request["key"]["thermal_path"]:
            raise InputError("point thermal path differs from P0")
        if mode == "physical" and point.get("role") != "physical_candidate":
            raise OpenInput("physical mode requires an independently calibrated P0 physical_candidate")
        if point.get("role") == "diagnostic":
            raise OpenInput("diagnostic P0 points require validation mode")
    config = dict(config, _mode=mode, _key=request["key"],
                  _applicability=applicability, _request=request)
    return config, inputs


def verify_result(folder: Path, request: dict | None = None) -> dict:
    folder = Path(folder)
    manifest = read_json(folder / "MANIFEST.json")
    if manifest.get("schema") != "r135-stage-manifest-v1":
        raise InputError("invalid result manifest schema")
    paths = set()
    for rec in manifest["files"]:
        relative = Path(rec["path"])
        if relative.is_absolute() or ".." in relative.parts or str(relative) in paths:
            raise InputError("unsafe or duplicate result path")
        p = folder / relative
        if (not p.is_file() or p.is_symlink() or not p.resolve().is_relative_to(folder.resolve())
                or any(q.is_symlink() for q in p.parents if q != folder)
                or p.stat().st_size != rec["bytes"] or sha256(p) != rec["sha256"]):
            raise InputError(f"modified or missing result artifact: {relative}")
        paths.add(relative.as_posix())
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}
    if actual != paths | {"MANIFEST.json"}:
        raise InputError("unlisted files in result")
    saved = read_json(folder / "REQUEST.json")
    receipt = read_json(folder / "EXECUTION_RECEIPT.json")
    digest = canonical_hash(saved)
    if receipt["request_sha256"] != digest or manifest["request_sha256"] != digest:
        raise InputError("request/receipt/manifest binding mismatch")
    if request is not None and canonical_hash(request) != digest:
        raise InputError("output belongs to another request; use a new output directory")
    for name in ("stage", "key", "mode", "execution_sha", "config_sha256", "source_sha256", "inputs"):
        if receipt.get(name) != saved.get(name):
            raise InputError(f"receipt/request semantic binding mismatch: {name}")
    if canonical_hash(saved.get("config")) != saved.get("config_sha256"):
        raise InputError("stored configuration checksum mismatch")
    source = read_json(folder / "SOURCE.json")
    if canonical_hash(source.get("files")) != source.get("sha256") or source.get("sha256") != saved.get("source_sha256"):
        raise InputError("stored source inventory binding mismatch")
    if receipt.get("scientific_acceptance") != "owner_review":
        raise InputError("scientific acceptance must remain separate")
    if receipt.get("result", {}).get("software_status") == "PASS":
        plan = read_json(HERE.parent / "PLAN.json")
        expected = next((s["deliverables"] for s in plan["stages"] if s["id"] == saved["stage"]), None)
        if expected is None or not set(expected).issubset(actual):
            raise InputError("successful stage is missing its declared artifacts")
    return receipt


def _p0(config, inputs, out):
    mod = _p0_module()
    source = inputs.get("registry", HERE / "register_inputs.json")
    built = mod.build(source)
    # Reuse the exact P0 encoder; do not alter the frozen design facts.
    for name in mod.FILES:
        (out / name).write_bytes(mod.encoded(built[name]))
    return {"software_status": "PASS", "evidence_status": "DESIGN_RECORDS",
            "metrics": {}, "limitations": ["P0 is a design register, not physical calibration"]}


def execute(stage: str, request_path: Path, out: Path) -> dict:
    request_path, out = Path(request_path), Path(out)
    request = read_json(request_path)
    config, inputs = validate_request(request, stage, request_path.resolve().parent)
    if out.exists():
        return verify_result(out, request)
    out.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{out.name}.partial-", dir=out.parent))
    started = time.time()
    try:
        write_json(temp / "REQUEST.json", request)
        source = source_inventory()
        write_json(temp / "SOURCE.json", source)
        try:
            module = importlib.import_module("r135." + STAGES[stage]) if stage != "P0" else None
            result = module.run(config, inputs, temp) if module else _p0(config, inputs, temp)
            result = dict(result)
            result.setdefault("software_status", "PASS")
            result.setdefault("evidence_status", "CONDITIONAL")
            result.setdefault("limitations", [])
        except OpenInput as exc:
            result = {"software_status": "NOT_EVALUATED", "evidence_status": "OPEN_INPUT",
                      "limitations": [str(exc)], "error_type": type(exc).__name__}
        except Exception as exc:
            result = {"software_status": "FAIL", "evidence_status": "TECHNICAL_FAILURE",
                      "limitations": [str(exc)], "error_type": type(exc).__name__}
            (temp / "ERROR.txt").write_text(traceback.format_exc(), encoding="utf-8")
        mutated = []
        if source_inventory()["sha256"] != source["sha256"]:
            mutated.append("executed source changed during computation")
        for rec in request["inputs"]:
            p = inputs[rec["name"]]
            if not p.is_file() or sha256(p) != rec["sha256"]:
                mutated.append(f"input changed during computation: {rec['name']}")
        if mutated:
            result.update(software_status="FAIL", evidence_status="TECHNICAL_FAILURE")
            result["limitations"].extend(mutated)
        if result["software_status"] == "PASS":
            plan = read_json(HERE.parent / "PLAN.json")
            expected = next(s["deliverables"] for s in plan["stages"] if s["id"] == stage)
            # The receipt and line manifest are finalized by this wrapper for P10.
            missing = [x for x in expected if x not in {"EXECUTION_RECEIPT.json", "MANIFEST.sha256"}
                       and not (temp / x).is_file()]
            if missing:
                result.update(software_status="FAIL", evidence_status="TECHNICAL_FAILURE")
                result["limitations"].append("missing declared artifacts: " + ", ".join(missing))
        receipt = {
            "schema": "r135-stage-receipt-v1", "stage": stage, "key": request["key"],
            "mode": request["mode"], "execution_sha": request["execution_sha"],
            "source_sha256": source["sha256"], "request_sha256": canonical_hash(request),
            "source_bytes_match_commit": source_matches_commit(source, request["execution_sha"]),
            "config_sha256": request["config_sha256"], "inputs": request["inputs"],
            "elapsed_seconds": time.time() - started,
            "environment": {"python": platform.python_version(), "platform": platform.platform()},
            "scientific_acceptance": "owner_review", "result": result,
        }
        write_json(temp / "EXECUTION_RECEIPT.json", receipt)
        if stage == "P10":
            entries = [file_record(p, temp) for p in sorted(temp.rglob("*")) if p.is_file()]
            (temp / "MANIFEST.sha256").write_text("".join(f"{p['sha256']}  {p['path']}\n" for p in entries))
        write_json(temp / "MANIFEST.json", {
            "schema": "r135-stage-manifest-v1", "request_sha256": canonical_hash(request),
            "files": [file_record(p, temp) for p in sorted(temp.rglob("*")) if p.is_file()],
        })
        verify_result(temp, request)
        os.rename(temp, out)
        return receipt
    except BaseException:
        # Preserve partial products for diagnosis. Never overwrite another run.
        raise


def seal(stage: str, config_path: Path, template_path: Path, out: Path) -> dict:
    """Freeze explicit inputs; no guessing model, preparation or physical units."""
    template = read_json(template_path)
    config = read_json(config_path)
    request = dict(template, schema="r135-stage-request-v1", stage=stage,
                   execution_sha=_commit(), config=config, config_sha256=canonical_hash(config),
                   source_sha256=source_inventory()["sha256"])
    for rec in request.get("inputs", []):
        path = Path(rec["path"])
        path = path if path.is_absolute() else Path(template_path).resolve().parent / path
        rec["sha256"] = sha256(path)
        rec["path"] = str(path.resolve())
    validate_request(request, stage, Path(out).resolve().parent)
    write_json(out, request)
    return request
