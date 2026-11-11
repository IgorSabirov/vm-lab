#!/usr/bin/env python3
"""Build/check the typed vm-lab registry graph; never infer scientific status.

Sources of truth: RESULTS_REGISTER.json, OPEN_QUESTIONS.json, PREMISES_CURRENT.md.
Generated views are navigation/provenance aids, not scientific evidence.
No network, external dependencies, science calculations or automatic commits.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path

MAIN = "analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.json"
MAIN_MD = MAIN.replace(".json", ".md")
QUESTIONS = "analysis/NOW_RESULTS_SYNTHESIS_20261106/OPEN_QUESTIONS.json"
QUESTIONS_MD = QUESTIONS.replace(".json", ".md")
PREMISES = "analysis/FOUNDATIONS_LITERATURE_20261103/PREMISES_CURRENT.md"
PREMISE_JSON = PREMISES.replace(".md", ".json")
OUT = "analysis/REGISTRY_LINKS"


def git_blob_sha(raw: bytes) -> str:
    """Git's content-addressed SHA for exact file bytes."""
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def unique(items, label):
    ids = [x["id"] for x in items]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate ID in {label}")
    return {x["id"]: x for x in items}


def ensure_main_anchors(text: str, ids: set[str]) -> str:
    lines = text.splitlines()
    present = {m.group(1).lower() for m in re.finditer(r'<a id="([RCL]\d+)"></a>', text, re.I)}
    out = []
    for line in lines:
        m = re.match(r"^(#{2,4})\s+(R\d{3}|C\d{3}|L\d{2})\b", line)
        if m and m.group(2) in ids and m.group(2).lower() not in present:
            out.append(f'<a id="{m.group(2).lower()}"></a>')
            present.add(m.group(2).lower())
        out.append(line)
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def ensure_question_anchors(text: str, ids: set[str]) -> str:
    lines = text.splitlines()
    present = {m.group(1).lower() for m in re.finditer(r'<a id="(U\d+)"></a>', text, re.I)}
    out = []
    for line in lines:
        m = re.match(r"^#{2,4}\s+(U\d{3})\b", line)
        if m and m.group(1) in ids and m.group(1).lower() not in present:
            out.append(f'<a id="{m.group(1).lower()}"></a>')
            present.add(m.group(1).lower())
        out.append(line)
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def ensure_premise_anchors(text: str) -> str:
    lines = []
    for line in text.splitlines():
        m = re.match(r"^\| ([A-G]\d{2}) \|", line)
        if m and f'<a id="premise-{m.group(1).lower()}"></a>' not in line:
            line = line.replace(f"| {m.group(1)} |", f'| <a id="premise-{m.group(1).lower()}"></a>{m.group(1)} |', 1)
        m = re.match(r"^- \*\*(N\d{2}) —", line)
        if m and f'<a id="obligation-{m.group(1).lower()}"></a>' not in line:
            line = line.replace(f"- **{m.group(1)} —", f'- <a id="obligation-{m.group(1).lower()}"></a> **{m.group(1)} —', 1)
        lines.append(line)
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def parse_premises(text: str):
    rows = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        m = re.match(
            r'^\| (?:<a id="premise-([A-G]\d{2})"></a>)?([A-G]\d{2}) \| (.*?) \| (.*?) \|\s*$',
            line,
        )
        if m:
            ident = m.group(2)
            rows.append({
                "id": ident,
                "current_statement": m.group(3),
                "sources_and_routes": m.group(4),
                "path": PREMISES,
                "fragment": "premise-" + ident.lower(),
                "line": line_number,
            })
    unique(rows, "premises")
    if len(rows) != 66:
        raise ValueError(f"Expected preserved 66 premise IDs, got {len(rows)}")
    return rows


def parse_obligations(text: str):
    marker = "## Новые явные долги, которые нельзя потерять между строками"
    if marker not in text:
        raise ValueError("Missing N-obligations section in PREMISES_CURRENT.md")
    block = text.split(marker, 1)[1].split("\n\nНет общего вывода", 1)[0]
    pattern = re.compile(
        r'(?ms)^- (?:<a id="obligation-(n\d{2})"></a> )?\*\*(N\d{2}) — (.*?)\.\*\*(.*?)(?=^- (?:<a id="obligation-n\d{2}"></a> )?\*\*N\d{2} — |\Z)'
    )
    rows = []
    base_line = text[: text.index(marker)].count("\n") + marker.count("\n") + 1
    for match in pattern.finditer(block):
        ident = match.group(2)
        rows.append({
            "id": ident,
            "title": match.group(3).strip(),
            "description": match.group(4).strip(),
            "path": PREMISES,
            "fragment": "obligation-" + ident.lower(),
            "line": base_line + block[: match.start()].count("\n") + 1,
            "status_is_not_inferred": True,
        })
    unique(rows, "obligations")
    expected = {f"N{i:02d}" for i in range(1, 10)}
    if {x["id"] for x in rows} != expected:
        raise ValueError(f"Expected N01-N09, got {[x['id'] for x in rows]}")
    return rows


def render_card(r):
    obligations = ", ".join(r.get("obligation_ids", [])) or "—"
    return (
        f'<a id="{r["id"].lower()}"></a>\n\n### {r["id"]}. {r["title"]}\n\n'
        f'**Статус:** {r["status"]}\n\n**Результат.** {r["result"]}\n\n'
        f'**Условия.** {r["inputs"]}\n\n**Граница.** {r["limit"]}\n\n'
        f'**Место в рамке.** {r["framework_role"]}\n\n'
        f'**Родители:** {", ".join(r.get("parent_result_ids", []))}. '
        f'**Конструкции:** {", ".join(r.get("construct_ids", []))}. '
        f'**Вопросы:** {", ".join(r.get("open_question_ids", []))}. '
        f'**N-долги:** {obligations}.\n\n'
        "**Источники:** " + "; ".join(f"[{Path(p).name}](../../{p})" for p in r["sources"]) + ".\n\n"
        "**Предпосылки:** " + ", ".join(r.get("premise_ids", [])) +
        "; [реестр 66 условий и N-долгов](../FOUNDATIONS_LITERATURE_20261103/PREMISES_CURRENT.md).\n"
    )


def replace_block(text, key, body):
    begin, end = f"<!-- generated:{key} -->", f"<!-- /generated:{key} -->"
    pattern = re.escape(begin) + r".*?" + re.escape(end)
    replacement = begin + "\n" + body.rstrip() + "\n" + end
    matches = re.findall(pattern, text, re.S)
    if len(matches) > 1:
        raise ValueError(f"Duplicate generated block {key}")
    return re.sub(pattern, lambda _: replacement, text, flags=re.S) if matches else text.rstrip() + "\n\n" + replacement + "\n"


def build(root: Path):
    raw = {
        MAIN: (root / MAIN).read_text(encoding="utf-8"),
        MAIN_MD: (root / MAIN_MD).read_text(encoding="utf-8"),
        QUESTIONS: (root / QUESTIONS).read_text(encoding="utf-8"),
        QUESTIONS_MD: (root / QUESTIONS_MD).read_text(encoding="utf-8"),
        PREMISES: (root / PREMISES).read_text(encoding="utf-8"),
    }
    main, questions = json.loads(raw[MAIN]), json.loads(raw[QUESTIONS])
    results = unique(main["results"], MAIN)
    constructs = unique(main["constructs"], MAIN)
    links = unique(main["open_links"], MAIN)
    question_group = unique(questions["questions"], QUESTIONS)
    all_main_ids = set(results) | set(constructs) | set(links)
    main_md = ensure_main_anchors(raw[MAIN_MD], all_main_ids)
    questions_md = ensure_question_anchors(raw[QUESTIONS_MD], set(question_group))
    premises_md = ensure_premise_anchors(raw[PREMISES])
    raw[MAIN_MD], raw[QUESTIONS_MD], raw[PREMISES] = main_md, questions_md, premises_md

    premise_rows = parse_premises(premises_md)
    obligation_rows = parse_obligations(premises_md)
    premises = unique(premise_rows, PREMISES)
    obligations = unique(obligation_rows, "N obligations")

    source_rows = {}
    for result in results.values():
        for source in result.get("managed_sources", []):
            source_path = root / source
            if not source_path.is_file():
                raise ValueError(f"Missing managed source {source}")
            content = source_path.read_bytes()
            source_rows[source] = {
                "id": source,
                "title": source,
                "path": source,
                "snapshot_status": "PRESENT_AND_HASHED",
                "git_blob_sha": git_blob_sha(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
            }
    sources = unique(list(source_rows.values()), "managed sources")

    groups = {
        "result": results,
        "construct": constructs,
        "link": links,
        "question": question_group,
        "premise": premises,
        "obligation": obligations,
        "source": sources,
    }
    nodes = []
    for kind, group in groups.items():
        for ident, item in group.items():
            if kind in ("result", "construct", "link"):
                path, fragment = MAIN_MD, ident.lower()
            elif kind == "question":
                path, fragment = QUESTIONS_MD, ident.lower()
            elif kind in ("premise", "obligation"):
                path, fragment = PREMISES, item["fragment"]
            else:
                path, fragment = item["path"], None
            node = {
                "key": f"{kind}:{ident}",
                "id": ident,
                "kind": kind,
                "title": item.get("title", item.get("current_statement", item.get("path", ""))),
                "status": item.get("status"),
                "path": path,
                "fragment": fragment,
            }
            if kind == "source":
                node.update({
                    "snapshot_status": item["snapshot_status"],
                    "git_blob_sha": item["git_blob_sha"],
                    "sha256": item["sha256"],
                    "size_bytes": item["size_bytes"],
                })
            nodes.append(node)

    edges = set()

    def add(kind_a, a, kind_b, b, relation):
        if a not in groups[kind_a] or b not in groups[kind_b]:
            raise ValueError(f"Dangling typed reference: {kind_a}:{a} -> {kind_b}:{b}")
        edges.add((f"{kind_a}:{a}", f"{kind_b}:{b}", relation))

    for ident, result in groups["result"].items():
        for parent in result.get("parent_result_ids", []):
            add("result", parent, "result", ident, "parent")
        for construct in result.get("construct_ids", []):
            add("result", ident, "construct", construct, "addresses")
        for premise in result.get("premise_ids", []):
            add("result", ident, "premise", premise, "direct_conditional_evidence")
        for link in result.get("open_link_ids", []):
            add("result", ident, "link", link, "boundary_open")
        for question in result.get("open_question_ids", []):
            add("result", ident, "question", question, "informs_not_closes")
        for obligation in result.get("obligation_ids", []):
            add("result", ident, "obligation", obligation, "updates_not_closes")
        for source in result.get("managed_sources", []):
            add("result", ident, "source", source, "managed_evidence_source")

    for result, construct_ids in main.get("result_to_constructs", {}).items():
        for construct in construct_ids:
            add("result", result, "construct", construct, "addresses")
    for construct, item in groups["construct"].items():
        for result in item.get("results", []):
            add("result", result, "construct", construct, "addresses")
    for edge in main.get("lineage_edges", []):
        add("result", edge["parent"], "result", edge["child"], "parent")
    for question, item in groups["question"].items():
        for result in item.get("records", []):
            add("result", result, "question", question, "informs_not_closes")
        for link in item.get("open_links", []):
            add("question", question, "link", link, "related_open_link")

    legacy = [x for x in main.get("legacy_crosswalk", []) if x.get("source") == PREMISES]
    if {x["id"] for x in legacy} != set(groups["premise"]):
        raise ValueError("Legacy crosswalk must cover exactly all 66 premise IDs")
    for item in legacy:
        for construct in item.get("constructs", []):
            add("premise", item["id"], "construct", construct, "historical_navigation_not_proof")

    graph = {
        "schema": "vm-lab-registry-links-v2",
        "sources": {path: git_blob_sha(content.encode("utf-8")) for path, content in raw.items()},
        "source_hash_algorithm": "git-blob-sha1",
        "counts": {kind: len(group) for kind, group in groups.items()},
        "semantics": (
            "Typed navigation and content-addressed snapshots of explicitly managed evidence sources. "
            "Links do not prove claims or close questions. N obligations are distinct from premises. "
            "Historical literature Lxx and research link Lxxx namespaces are not inferred from prose. "
            "Hashes identify file revisions; they do not attest semantic validity."
        ),
        "nodes": sorted(nodes, key=lambda item: item["key"]),
        "edges": [{"source": a, "target": b, "relation": relation} for a, b, relation in sorted(edges)],
    }
    bykey = {item["key"]: item for item in nodes}

    def mdlink(key):
        node = bykey[key]
        fragment = f'#{node["fragment"]}' if node.get("fragment") else ""
        return f'[{node["id"]}](../../{node["path"]}{fragment})'

    lines = [
        "# Связи реестров",
        "",
        "Сгенерировано tools/registry_links.py --write. Научные статусы берутся из исходных карточек; связи их не повышают.",
        "",
        "[Результаты](../NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.md) · "
        "[66 предпосылок и девять N-долгов](../FOUNDATIONS_LITERATURE_20261103/PREMISES_CURRENT.md) · "
        "[Вопросы](../NOW_RESULTS_SYNTHESIS_20261106/OPEN_QUESTIONS.md)",
        "",
        "Число записей: " + ", ".join(f"{kind}={count}" for kind, count in graph["counts"].items()) + ".",
        "",
        "## Предпосылка → результаты",
        "",
        "| ID | Прямое адресное свидетельство | Историческая навигация через конструкции |",
        "|---|---|---|",
    ]
    for premise in premise_rows:
        key = "premise:" + premise["id"]
        direct = sorted(a for a, b, rel in edges if b == key and rel == "direct_conditional_evidence")
        constructs_for_premise = sorted(b for a, b, rel in edges if a == key and rel == "historical_navigation_not_proof")
        navigation = sorted({a for a, b, rel in edges if b in constructs_for_premise and rel == "addresses"})
        lines.append(
            f'| {mdlink(key)} | {", ".join(mdlink(x) for x in direct) or "Нет новой прямой аттестации"} | '
            f'{", ".join(mdlink(x) for x in constructs_for_premise)}; {", ".join(mdlink(x) for x in navigation)} |'
        )

    lines += [
        "",
        "## N-долг → результаты",
        "",
        "| Долг | Прямо связанные результаты |",
        "|---|---|",
    ]
    for obligation in obligation_rows:
        key = "obligation:" + obligation["id"]
        direct = sorted(a for a, b, rel in edges if b == key and rel == "updates_not_closes")
        lines.append(f'| {mdlink(key)} | {", ".join(mdlink(x) for x in direct) or "Нет прямой аттестации"} |')

    lines += [
        "",
        "## Результат → свидетельства",
        "",
        "| Результат | Управляемые источники и снимки |",
        "|---|---|",
    ]
    for result_id in groups["result"]:
        sources_for_result = sorted(
            b for a, b, rel in edges if a == "result:" + result_id and rel == "managed_evidence_source"
        )
        if sources_for_result:
            lines.append(f'| {mdlink("result:" + result_id)} | {", ".join(mdlink(x) for x in sources_for_result)} |')

    lines += [
        "",
        "## Результат → предпосылки",
        "",
        "| Результат | Прямые связи |",
        "|---|---|",
    ]
    for result_id in groups["result"]:
        direct = sorted(
            b for a, b, rel in edges if a == "result:" + result_id and rel == "direct_conditional_evidence"
        )
        if direct:
            lines.append(f'| {mdlink("result:" + result_id)} | {", ".join(mdlink(x) for x in direct)} |')
    lines += [
        "",
        "Полный типизированный граф: [INDEX.json](INDEX.json).",
        "",
        "Историческая навигация не является прямым свидетельством. Хеш источника фиксирует версию файла, не истинность его содержания.",
    ]

    premise_json = {
        "schema": "premises-current-mirror-v2",
        "source": PREMISES,
        "main_registry": MAIN,
        "note": (
            "Generated mirror. Preserves all 66 historical premise IDs and all nine N-obligations. "
            "N-obligations are a separate type, not additional premises. Navigation is not proof."
        ),
        "entries": premise_rows,
        "obligations": obligation_rows,
    }
    outputs = {
        OUT + "/INDEX.json": json.dumps(graph, ensure_ascii=False, indent=2) + "\n",
        OUT + "/INDEX.md": "\n".join(lines) + "\n",
        PREMISE_JSON: json.dumps(premise_json, ensure_ascii=False, indent=2) + "\n",
        MAIN_MD: main_md,
        QUESTIONS_MD: questions_md,
        PREMISES: premises_md,
    }
    for result in groups["result"].values():
        if result.get("managed_card"):
            main_md = replace_block(main_md, result["id"], render_card(result))
    outputs[MAIN_MD] = main_md

    for kind in ("result", "construct"):
        for ident in groups[kind]:
            if not re.search(r"^#{2,4}\s+" + re.escape(ident) + r"(?:[. —:]|$)", main_md, re.M):
                raise ValueError(f"Missing Markdown entry {ident}")
            if f'<a id="{ident.lower()}"></a>' not in main_md:
                raise ValueError(f"Missing deep-link anchor for {ident}")
    for ident in groups["question"]:
        if f'<a id="{ident.lower()}"></a>' not in questions_md:
            raise ValueError(f"Missing deep-link anchor for {ident}")
    for ident in groups["premise"]:
        if f'<a id="premise-{ident.lower()}"></a>' not in premises_md:
            raise ValueError(f"Missing deep-link anchor for premise {ident}")
    for ident in groups["obligation"]:
        if f'<a id="obligation-{ident.lower()}"></a>' not in premises_md:
            raise ValueError(f"Missing deep-link anchor for obligation {ident}")

    r122 = groups["result"]["R122"]
    if r122.get("managed_boundary") and r122["limit"] not in main_md:
        raise ValueError("R122 Markdown boundary diverges from JSON")
    return outputs, graph


def run(root: Path, write=False):
    outputs, graph = build(root)
    stale = []
    for path, content in outputs.items():
        target = root / path
        if not target.exists() or target.read_text(encoding="utf-8") != content:
            stale.append(path)
            if write:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
    return stale, graph


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()
    stale, graph = run(args.root, args.write)
    summary = json.dumps({
        "status": "UPDATED" if args.write and stale else "FAIL" if stale else "PASS",
        "counts": graph["counts"],
        "edges": len(graph["edges"]),
        "stale": stale,
    }, ensure_ascii=False)
    print(summary)
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as f:
            f.write("### Registry consistency\n\n" + summary + "\n")
    if stale and not args.write:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
