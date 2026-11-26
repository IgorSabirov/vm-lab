"""Verify the frozen catalog, matrix, directed graph, evidence addresses and arithmetic."""
from __future__ import annotations
import argparse
import csv
import json
import math
import re
import subprocess
from collections import Counter
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
NS = {"g": "http://graphml.graphdrawing.org/xmlns"}
def load(path):
    return json.loads(path.read_text())

def table(name):
    with (HERE / name).open() as stream:
        return list(csv.DictReader(stream, delimiter="\t"))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", action="store_true", help="Verify evidence lines against locally fetched frozen commits.")
    args = parser.parse_args()
    groups = load(HERE / "catalog.json")
    raw = load(HERE.parent / "R142_MAGIC_NUMBERS" / "CHECKS.json")["claims"]
    baseline = {r["id"]: (r["value"], r["units"], r["tier"], r["status"]) for r in raw}
    checked = [c for group in groups for c in group["claims"]]
    assert len(checked) == len(raw) == len(baseline)
    assert {c["id"]: (c["value"], c["units"], c["tier"], c["r142_status"]) for c in checked} == baseline
    ids = {g["id"] for g in groups}
    matrix = table("matrix.tsv")
    address_rows = table("addresses.tsv")
    addresses = {a["address"] for a in address_rows}
    assert {r["address"] for r in matrix} == addresses
    assert len(matrix) == len(address_rows) == len(addresses)
    assert set(matrix[0]) == ids | {"address"}
    assert "R142" not in addresses and "PR213" not in addresses
    records = load(HERE / "evidence.json")
    by_id = {r["id"]: r for r in records}
    assert len(records) == len(by_id)
    present = set()
    for row in matrix:
        for group in ids:
            cell = row[group]
            if cell in (".", "?"):
                continue
            for key in cell.split(","):
                record = by_id[key]
                assert group == record["group"] and row["address"] in record["addresses"]
                present.add((key, row["address"]))
    expected = {(r["id"], a) for r in records for a in r["addresses"]}
    assert present == expected
    snapshot = load(HERE / "snapshot.json")
    revisions = set(snapshot["branches"].values()) | set(load(HERE / "evidence_revisions.json").values())
    methods = set()
    for r in records:
        assert r["addresses"] and set(r["addresses"]) <= addresses
        assert all(r[k] for k in ("system", "role", "observation", "implementation", "data", "limit", "claim_scope"))
        assert r["status"] in {"P", "S", "D", "T", "A"} and r["evidence"]
        if "boundary_case" in r:
            boundary = by_id[r["boundary_case"]]
            assert boundary["status"] == "A" and boundary["group"] == r["group"]
        for method in r.get("methods", []):
            assert method["source"] in r["addresses"] and method["target"] in addresses
            methods.add((r["id"], method["source"], method["target"], method["evidence"]))
        for u in r["evidence"] + [m["evidence"] for m in r.get("methods", [])]:
            m = re.fullmatch(r"https://github.com/IgorSabirov/vm-lab/blob/([0-9a-f]{40})/(.+)#L([1-9][0-9]*)",u)
            assert m and m[1] in revisions, u
            if args.sources:
                s = subprocess.check_output(["git", "show", m[1]+":"+unquote(m[2])], cwd=ROOT)
                assert len(s.splitlines()) >= int(m[3]), u
    graph = ET.parse(HERE / "network.graphml")
    nodes = {n.attrib["id"]: n.find("g:data[@key='label']", NS).text for n in graph.findall(".//g:node", NS)}
    actual = []
    graph_methods = []
    for edge in graph.findall(".//g:edge", NS):
        key = edge.find("g:data[@key='case']", NS).text
        relation = edge.find("g:data[@key='relation']", NS).text
        if relation == "M":
            evidence = edge.find("g:data[@key='evidence']", NS).text
            graph_methods.append((key, nodes[edge.attrib["source"]], nodes[edge.attrib["target"]], evidence))
            continue
        assert relation == by_id[key]["status"]
        assert nodes[edge.attrib["source"]] == next(g["title"] for g in groups if g["id"] == by_id[key]["group"])
        actual.append((key, nodes[edge.attrib["target"]]))
    assert set(graph_methods) == methods and len(graph_methods) == len(methods)
    assert len(actual) == len(set(actual))
    assert set(actual) == {(k,a) for k,a in expected if by_id[k]["status"] != "A"}
    leads = {(row["address"], group) for row in matrix for group in ids if row[group] == "?"}
    screened = table("screening.tsv")
    assert {(row["address"], row["domain"]) for row in screened} == leads
    assert len(screened) == len(leads)
    trials = table("run_tasks.tsv")
    containers = {row["id"] for row in table("run_sources.tsv")}
    summary = load(HERE / "snapshot.json")["executed_task_records"]
    assert len(trials) == len({row["record_sha256"] for row in trials}) == summary["unique_full_record_sha256"]
    assert len({row["task_id"] for row in trials}) == summary["distinct_task_ids"]
    assert {row["source"] for row in trials} == containers
    v = load(HERE / "reuse_checks.json")
    calculated = v["mu"] / (v["inverse_alpha"] * v["alpha_G_p"])
    assert math.isclose(calculated, v["F_em_over_F_g_ep"], rel_tol=1e-14)
    c = v["c_m_s"]
    lam = 3 * v["Omega_Lambda"] * (v["H0_s_inv"] / c)**2
    lp2 = v["h_J_s"] * v["G_SI"] / (2*math.pi*c**3)
    assert math.isclose(lam, v["Lambda_m_inv2"], rel_tol=1e-14)
    assert math.isclose(lam*lp2, v["Lambda_lp2"], rel_tol=1e-14)
    assert math.isclose(lam*lp2/(8*math.pi), v["rhoLambda_over_rhoPlanck"], rel_tol=1e-14)
    print(f"{len(raw)} claims, {len(ids)} groups, {len(addresses)} addresses, {len(records)} cases, {len(actual)} domain edges, {len(methods)} method edges")
    print(dict(Counter(r["status"] for r in records)))
if __name__ == "__main__":
    main()
