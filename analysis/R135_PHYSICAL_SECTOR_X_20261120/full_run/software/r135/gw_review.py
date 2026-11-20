"""P10 readback of point-specific external GW evidence and project scientific decisions."""
import hashlib
import math
from pathlib import Path
import re
import subprocess
import json

import numpy as np
from scipy.special import logsumexp

from .common import InputError, canonical_hash, finite, read_json, sha256

IDENTITY = ("model_id", "point_id", "thermal_path")
ROOT = Path(__file__).resolve().parents[5]


def linked(root, ref):
    if not isinstance(ref, dict) or not isinstance(ref.get("file"), str) or Path(ref["file"]).is_absolute():
        raise InputError("GW evidence needs a relative file and SHA-256")
    path = (root/ref["file"]).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file() or sha256(path) != ref.get("sha256"):
        raise InputError("GW review file or digest differs")
    return path


def read_decision(record, identity, digest, outcome):
    if not re.fullmatch(r"D[0-9]+", str(record)):
        raise InputError("unknown scientific decision ID")
    path = "decisions/" + record + ".json"
    raw = subprocess.run(["git","show","HEAD:"+path], cwd=ROOT, capture_output=True)
    if raw.returncode:
        raise InputError("GW decision is absent from the committed decisions register")
    decision = json.loads(raw.stdout)
    expected = {**identity, "evidence_sha256":digest, "outcome":outcome}
    if (decision.get("id") != record or decision.get("status") != "RATIFIED"
            or decision.get("domain") != "science" or "result:R135" not in decision.get("scope", [])
            or expected not in decision.get("gw_dispositions", [])):
        raise InputError("committed scientific decision does not ratify this GW disposition")
    return {"id":record, "sha256":hashlib.sha256(raw.stdout).hexdigest()}


def marginalize(record):
    """Integrate paired conditional log likelihoods over the published discrete prior."""
    for key in ("release","foreground_model","systematics","prior","solver_version","overlap_policy"):
        if not isinstance(record.get(key), str) or not record[key].strip():
            raise InputError("external GW likelihood lacks "+key)
    w = np.asarray(record.get("weights"), float)
    if (w.ndim != 1 or not len(w) or not np.isfinite(w).all() or
            (w <= 0).any() or not math.isclose(float(w.sum()), 1., abs_tol=1e-12, rel_tol=0)):
        raise InputError("invalid normalized GW marginalization weights")
    result = {}
    for field in ("logL_signal","logL_null"):
        v = np.asarray(record.get(field), float)
        if v.shape != w.shape or not np.isfinite(v).all():
            raise InputError("GW grid lacks signal or null likelihoods at the same prior nodes")
        result[field] = float(logsumexp(v, b=w))
    result["delta_logL"] = result["logL_signal"]-result["logL_null"]
    if not math.isclose(result["delta_logL"], finite(record.get("delta_logL"),"external delta logL"),
                        abs_tol=1e-8,rel_tol=1e-9):
        raise InputError("external GW likelihood failed numerical readback")
    return result


def review(row, entry, base, response, audit):
    identity = {k:row[k] for k in IDENTITY}
    if set(entry) == {"history", "response"}:
        from gw.status import coverage
        checked = coverage([row], {row["point_id"]:entry}, base)[0]
        return {"status":row["status"] if response else checked["status"],
                "legacy_transfer":checked, "full_physical_completion":False,
                "missing":row["missing"] if response else checked["remaining"]}
    kinds = set(entry) & {"inapplicability_evidence", "physical_evidence"}
    if len(kinds) != 1 or set(entry) - kinds - {"decision_id"}:
        raise InputError("GW submission must select exactly one evidence type")
    kind = next(iter(kinds))
    path = linked(base, entry[kind])
    proof = read_json(path)
    if any(proof.get(k) != v for k,v in identity.items()) or not isinstance(proof.get("physical_argument"), str) or not proof["physical_argument"].strip():
        raise InputError("GW review evidence lacks its physical argument or has a different identity")
    update = {"review_evidence_sha256":sha256(path), "physical_argument":proof["physical_argument"]}
    supporting = {}
    for name, ref in proof.get("supporting_files", {}).items():
        supporting[name] = sha256(linked(path.parent, ref))
    if kind == "inapplicability_evidence":
        for corner, result in (response or {}).get("histories", {}).items():
            if result.get("status") == "CONDITIONAL":
                power = np.asarray(result.get("Omega_GW_today_per_logf", []), float)
                budget = result.get("bbn_budget", [])
                if (not len(power) or np.any(power != 0) or not budget
                        or any(epoch.get("rho_GW_over_rho_total") != 0 for epoch in budget)
                        or audit.get("histories", {}).get(corner, {}).get("numerical_status") != "RECONSTRUCTED"):
                    raise InputError("GW inapplicability contradicts or lacks verification of the computed response")
        outcome = "NOT_APPLICABLE_BY_PROOF"
        update.update(status="INAPPLICABILITY_FOR_REVIEW", scientific_acceptance="owner_review")
    else:
        required = {"source_calibration","source_uncertainty_propagation","PTA_HD","LVK"}
        if not required <= supporting.keys():
            raise InputError("incomplete external GW evidence")
        if not response or proof.get("response_sha256") != canonical_hash(response):
            raise InputError("GW review refers to a different P9 response")
        if not audit.get("detector_data_replayed") or not audit.get("histories") or not all(
                c.get("numerical_status") == "RECONSTRUCTED" for c in audit["histories"].values()):
            return {**update, "status":"OPEN_INPUT","missing":["complete independent P7/P9 detector and energy replay"]}
        hist = response["histories"]
        comparisons = {}
        for channel in ("PTA_HD", "LVK"):
            likelihood = read_json(linked(path.parent, proof["supporting_files"][channel]))
            if set(likelihood) != set(hist) or set(hist) != set(audit["histories"]):
                raise InputError("GW observational evidence omits a portal history")
            comparisons[channel] = {}
            for c, item in hist.items():
                r = likelihood[c]
                if r.get("response_sha256") != canonical_hash(item):
                    raise InputError("external GW likelihood belongs to another spectrum")
                comparisons[channel][c] = marginalize(r)
        for name in ("source_calibration","source_uncertainty_propagation"):
            upstream = read_json(linked(path.parent, proof["supporting_files"][name]))
            if (upstream.get("P7_file_sha256") != audit.get("source_P7_file_sha256")
                    or not upstream.get("source") or not upstream.get("method")
                    or upstream.get("source_hashes") != {c:r["source_sha256"] for c,r in hist.items()}):
                raise InputError("GW source calibration/uncertainty is not bound to the computed sources")
        update.update(status="FULL_RESPONSE_FOR_REVIEW", external_marginals=comparisons,
                      scientific_acceptance="owner_review")
        outcome = "FULL_RESPONSE"
    if "decision_id" in entry:
        if not supporting or row["role"] != "physical_candidate":
            raise InputError("ratified GW evidence requires a physical preparation and supporting files")
        if kind == "physical_evidence" and not {"P5","P7","P9"} <= {
                r["stage"] for r in row["stage_evidence"] if r["mode"] == "physical" and not r["lineage_reasons"]}:
            raise InputError("GW completion requires physical P5/P7/P9 evidence")
        update["decision"] = read_decision(entry["decision_id"], identity, sha256(path), outcome)
        update.update(status=outcome, scientific_acceptance="recorded_decision",missing=[],
                      full_physical_completion=(outcome == "FULL_RESPONSE"))
    return update


def submissions(inputs):
    if "gw_evidence" in inputs:
        if "inapplicability_evidence" in inputs:
            raise InputError("duplicate GW evidence routes")
        path = Path(inputs["gw_evidence"])
        return read_json(path), path.parent
    if "inapplicability_evidence" in inputs:
        path = Path(inputs["inapplicability_evidence"])
        return {read_json(path)["point_id"]:{"inapplicability_evidence":{"file":path.name,"sha256":sha256(path)}}},path.parent
    return {}, None
