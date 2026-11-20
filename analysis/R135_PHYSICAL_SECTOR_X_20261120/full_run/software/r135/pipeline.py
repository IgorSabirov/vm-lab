"""Run an explicit local DAG of stage requests and retain independent branches.

This is a numerical dependency runner, not a job-platform integration. Every
edge names one content-addressed artifact; no stage discovers mutable 'latest'
results. A missing physical input propagates only to its declared consumers.
"""
from __future__ import annotations

import os
from pathlib import Path
import re

from .common import InputError, OpenInput, canonical_hash, read_json, sha256, write_json
from .contracts import _commit, execute, source_inventory, verify_result


def ordered_nodes(plan):
    if plan.get("schema") != "r135-pipeline-v1":
        raise InputError("unknown pipeline schema")
    nodes = plan.get("nodes", [])
    names = [n.get("id") for n in nodes]
    if not names or any(not isinstance(n, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", n) for n in names) or len(names) != len(set(names)):
        raise InputError("pipeline nodes must have unique safe ids")
    lookup = dict(zip(names, nodes))
    dependencies = {}
    for n in nodes:
        if not re.fullmatch(r"P(?:[0-9]|10)", n.get("stage", "")):
            raise InputError("invalid node stage")
        if n["stage"] != "P10" and any(x.get("for_audit", False) for x in n.get("inputs", [])):
            raise InputError("for_audit status bypass is restricted to P10")
        deps = {a["from_node"] for a in n.get("inputs", []) if "from_node" in a}
        if not deps <= set(names) or n["id"] in deps:
            raise InputError("unknown or self-referential dependency")
        dependencies[n["id"]] = deps
    order, done = [], set()
    while len(order) != len(nodes):
        ready = [n for n in names if n not in done and dependencies[n] <= done]
        if not ready:
            raise InputError("stage dependency cycle")
        for n in ready:
            order.append(lookup[n])
            done.add(n)
    return order


def run_pipeline(plan_path, output):
    path, output = Path(plan_path).resolve(), Path(output).resolve()
    plan = read_json(path)
    nodes = ordered_nodes(plan)
    inventory = source_inventory()
    if plan.get("source_sha256") != inventory["sha256"] or plan.get("execution_sha") != _commit():
        raise InputError("pipeline must be frozen against the current source and commit")
    digest = canonical_hash(plan)
    output.mkdir(parents=True, exist_ok=True)
    frozen = output / "PIPELINE.json"
    if frozen.exists() and canonical_hash(read_json(frozen)) != digest:
        raise InputError("output belongs to another pipeline")
    write_json(frozen, plan)
    records = {}
    for node in nodes:
        input_records = []
        blocked = []
        damaged = False
        for artifact in node.get("inputs", []):
            if "from_node" in artifact:
                parent = records[artifact["from_node"]]
                if parent.get("software_status") != "PASS" and not artifact.get("for_audit", False):
                    blocked.append(f"{artifact['from_node']}: {parent.get('software_status')}")
                    continue
                allowed = artifact.get("allow_evidence_status", ["CONDITIONAL", "SUPPORTED", "DESIGN_RECORDS", "DIAGNOSTIC"])
                if parent.get("evidence_status") not in allowed and not artifact.get("for_audit", False):
                    blocked.append(f"{artifact['from_node']}: {parent.get('evidence_status')}")
                    continue
                folder = output / artifact["from_node"]
                if not (folder / "MANIFEST.json").is_file():
                    blocked.append(f"{artifact['from_node']}: no completed parent bundle")
                    continue
                try:
                    verify_result(folder)
                except (InputError, OSError) as exc:
                    blocked.append(f"{artifact['from_node']}: invalid parent bundle: {exc}")
                    damaged = True
                    continue
                relative = Path(artifact["artifact"])
                if relative.is_absolute() or ".." in relative.parts:
                    raise InputError("unsafe pipeline artifact")
                source = folder / relative
            else:
                source = Path(artifact["path"])
                if not source.is_absolute():
                    source = path.parent / source
                if not source.is_file():
                    blocked.append(f"external input {artifact['name']}: missing")
                    continue
                if sha256(source) != artifact.get("sha256"):
                    blocked.append(f"external input {artifact['name']}: changed checksum")
                    damaged = True
                    continue
            if not source.is_file():
                blocked.append(f"missing artifact {source.name}")
                continue
            input_records.append({"name": artifact["name"], "path": str(source), "sha256": sha256(source)})
        if blocked:
            records[node["id"]] = {"stage": node["stage"], "key": node["key"],
                "software_status": "FAIL" if damaged else "NOT_EVALUATED",
                "evidence_status": "TECHNICAL_FAILURE" if damaged else "OPEN_INPUT", "reasons": blocked}
        else:
            config = node["config"]
            request = {"schema": "r135-stage-request-v1", "stage": node["stage"],
                "execution_sha": plan["execution_sha"], "source_sha256": inventory["sha256"],
                "mode": node["mode"], "key": node["key"], "config": config,
                "config_sha256": canonical_hash(config), "inputs": input_records,
                "applicability": node["applicability"]}
            request_path = output / "requests" / f"{node['id']}.json"
            write_json(request_path, request)
            try:
                receipt = execute(node["stage"], request_path, output / node["id"])
                records[node["id"]] = {"stage": node["stage"], "key": node["key"],
                    "request_sha256": receipt["request_sha256"],
                    "software_status": receipt["result"]["software_status"],
                    "evidence_status": receipt["result"]["evidence_status"],
                    "reasons": receipt["result"].get("limitations", [])}
            except (OpenInput, InputError) as exc:
                records[node["id"]] = {"stage": node["stage"], "key": node["key"],
                    "software_status": "NOT_EVALUATED" if isinstance(exc, OpenInput) else "FAIL",
                    "evidence_status": "OPEN_INPUT" if isinstance(exc, OpenInput) else "TECHNICAL_FAILURE",
                    "reasons": [str(exc)]}
        report = {"schema": "r135-pipeline-receipt-v1", "plan_sha256": digest,
            "source_sha256": inventory["sha256"], "nodes": records,
            "all_requested_software_completed": len(records) == len(nodes) and all(
                x["software_status"] == "PASS" for x in records.values()),
            "declared_stages": sorted({n["stage"] for n in nodes}, key=lambda s: int(s[1:])),
            "covers_all_stages": {n["stage"] for n in nodes} == {f"P{i}" for i in range(11)},
            "scientific_acceptance": "owner_review", "physical_completion": "REQUIRES_P10_COVERAGE_AUDIT"}
        temporary = output / ".PIPELINE_RECEIPT.tmp"
        write_json(temporary, report)
        os.replace(temporary, output / "PIPELINE_RECEIPT.json")
    return report
