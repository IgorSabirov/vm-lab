#!/usr/bin/env python3
"""Typed registry compiler: navigation and provenance, never scientific inference."""
from __future__ import annotations
import argparse, hashlib, json, posixpath, re
from pathlib import Path

MAIN = "analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.json"
MAIN_MD = MAIN.replace(".json", ".md")
QUESTIONS = "analysis/NOW_RESULTS_SYNTHESIS_20261106/OPEN_QUESTIONS.json"
QUESTIONS_MD = QUESTIONS.replace(".json", ".md")
PREMISES = "analysis/FOUNDATIONS_LITERATURE_20261103/PREMISES_CURRENT.md"
OUT = "analysis/REGISTRY_LINKS"
SOURCE_PINS = OUT + "/SOURCE_PINS.json"


def unique(items, label):
    ids = [x["id"] for x in items]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate ID in {label}")
    return {x["id"]: x for x in items}


def blob_sha(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def parse_premises(text):
    pat = re.compile(r'^\| (?:<a id="premise-([A-G]\d{2})"></a>)?([A-G]\d{2}) \| (.*?) \| (.*?) \|\s*$')
    rows = []
    for line in text.splitlines():
        m = pat.match(line)
        if m:
            anchor, ident, statement, sources = m.groups()
            if anchor and anchor != ident:
                raise ValueError(f"Premise anchor mismatch: {anchor} != {ident}")
            rows.append({"id": ident, "current_statement": statement,
                         "sources_and_routes": sources, "anchor": "premise-" + ident.lower()})
    unique(rows, "premises")
    if len(rows) != 66:
        raise ValueError(f"Expected 66 premise IDs, got {len(rows)}")
    return rows


def ensure_premise_anchors(text):
    out = []
    pat = re.compile(r"^(\| )([A-G]\d{2})( \|.*)$")
    for line in text.splitlines():
        m = pat.match(line)
        if m:
            ident = m.group(2)
            line = f'| <a id="premise-{ident.lower()}"></a>{ident} | ' + m.group(3)[3:]
        out.append(line)
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def parse_obligations(text):
    lines = text.splitlines()
    start = next((i for i, x in enumerate(lines)
                  if x.strip() == "## Новые явные долги, которые нельзя потерять между строками"), None)
    if start is None:
        raise ValueError("Missing N-debts section")
    header = re.compile(r'^- (?:<a id="obligation-(N\d{2})"></a> )?\*\*(N\d{2}) — (.*?)\.\*\*\s*(.*)$')
    rows, current, body = [], None, []

    def flush():
        nonlocal current, body
        if current is None:
            return
        source_text = "\n".join(body).strip()
        combined = current["title"] + "\n" + source_text
        refs = re.findall(r"\[(R\d{3})\]\(([^)]+)\)", combined)
        rows.append({
            "id": current["id"], "title": current["title"],
            "status": "CONDITIONALLY_RESOLVED" if re.search("условно решено", combined, re.I) else "OPEN",
            "source_text": source_text, "source_path": PREMISES,
            "source_anchor": "obligation-" + current["id"].lower(),
            "linked_result_ids": sorted({x[0] for x in refs}),
            "closure_condition": None,
            "closure_condition_status": "NOT_EXPLICITLY_DEFINED_IN_SOURCE",
            "evidence_links": [{"label": x[0], "target": x[1]} for x in refs],
            "interpretation_rule": "Contextual reference does not establish closure."
        })
        current, body = None, []

    for line in lines[start + 1:]:
        if line.startswith("## ") or line.startswith("Нет общего вывода"):
            break
        m = header.match(line)
        if m:
            flush()
            current = {"id": m.group(1), "title": m.group(2)}
            body = [m.group(3)] if m.group(3) else []
        elif current is not None:
            body.append(line)
    flush()
    unique(rows, "obligations")
    expected = [f"N{i:02d}" for i in range(1, 10)]
    if [x["id"] for x in rows] != expected:
        raise ValueError(f"Expected N01-N09, got {[x['id'] for x in rows]}")
    return rows


def ensure_obligation_anchors(text):
    out = []
    pat = re.compile(r"^- \*\*(N\d{2}) — ")
    for line in text.splitlines():
        m = pat.match(line)
        if m:
            anchor = f'<a id="obligation-{m.group(1).lower()}"></a>'
            if anchor not in line:
                line = "- " + anchor + " " + line[2:]
        out.append(line)
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")
def ensure_heading_anchors(markdown, groups):
    lines, out, found = markdown.splitlines(), [], set()
    pat = re.compile(r"^#{2,4}\s+(R\d{3}|C\d{3}|L\d{2})(?:\s|[.:—-]|$)")
    lookup = {
        "result": {x["id"] for x in groups.get("result", [])},
        "construct": {x["id"] for x in groups.get("construct", [])},
        "link": {x["id"] for x in groups.get("link", [])},
    }
    for line in lines:
        m = pat.match(line)
        if m:
            ident = m.group(1)
            kind = "result" if ident.startswith("R") else "construct" if ident.startswith("C") else "link"
            if ident in lookup[kind]:
                anchor = f'<a id="{kind}-{ident.lower()}"></a>'
                if not out or out[-1].strip() != anchor:
                    out.append(anchor)
                found.add((kind, ident))
        out.append(line)
    missing = [x["id"] for kind in ("result", "construct")
               for x in groups.get(kind, []) if (kind, x["id"]) not in found]
    if missing:
        raise ValueError(f"Missing Markdown headings for records: {missing[:12]}")
    return "\n".join(out) + ("\n" if markdown.endswith("\n") else ""), found


def ensure_question_anchors(markdown, questions):
    lines, out, found = markdown.splitlines(), [], set()
    wanted = {x["id"] for x in questions}
    pat = re.compile(r"^#{2,4}\s+(U\d{3})(?:\s|$)")
    for line in lines:
        m = pat.match(line)
        if m and m.group(1) in wanted:
            ident = m.group(1)
            anchor = f'<a id="question-{ident.lower()}"></a>'
            if not out or out[-1].strip() != anchor:
                out.append(anchor)
            found.add(ident)
        out.append(line)
    if found != wanted:
        raise ValueError(f"Missing U headings: {sorted(wanted-found)}")
    return "\n".join(out) + ("\n" if markdown.endswith("\n") else "")


def managed_sources(main):
    refs = {}
    for record in main["results"]:
        for path in record.get("managed_sources", []):
            refs.setdefault(path, []).append(record["id"])
    return {path: sorted(set(ids)) for path, ids in refs.items()}


def make_pins(root, main, previous=None):
    previous = previous or {}
    old = {x["path"]: x for x in previous.get("sources", [])}
    items = []
    for path, refs in sorted(managed_sources(main).items()):
        f = root / path
        if not f.is_file():
            raise ValueError(f"Missing managed source: {path}")
        data = f.read_bytes()
        prior = old.get(path, {})
        items.append({
            "path": path, "git_blob_sha": blob_sha(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "role": prior.get("role", "managed_evidence_source"),
            "fragment": prior.get("fragment"), "referenced_by": refs
        })
    return {
        "schema": "vm-lab-source-pins-v1",
        "snapshot_commit": previous.get("snapshot_commit"),
        "note": "Human-reviewed pins. Source changes require explicit refresh and diff review. Hashes establish identity, not semantic truth.",
        "sources": items
    }


def verify_pins(root, main, doc):
    expected = managed_sources(main)
    pins = unique(doc.get("sources", []), "source pins")
    if set(pins) != set(expected):
        raise ValueError(f"Source pin coverage mismatch; missing={sorted(set(expected)-set(pins))}, extra={sorted(set(pins)-set(expected))}")
    out = []
    for path, refs in sorted(expected.items()):
        pin, f = pins[path], root / path
        if not f.is_file():
            raise ValueError(f"Missing pinned managed source: {path}")
        data = f.read_bytes()
        actual_blob, actual_sha = blob_sha(data), hashlib.sha256(data).hexdigest()
        if pin.get("git_blob_sha") != actual_blob or pin.get("sha256") != actual_sha:
            raise ValueError(f"Source pin mismatch: {path}. Review source diff, then run --refresh-source-pins --write.")
        if sorted(pin.get("referenced_by", [])) != refs:
            raise ValueError(f"Stale source reference list for {path}")
        out.append({
            "path": path, "git_blob_sha": actual_blob, "sha256": actual_sha,
            "role": pin.get("role"), "fragment": pin.get("fragment"),
            "referenced_by": refs, "integrity": "PASS"
        })
    return out


def render_card(r):
    return (
        f'<a id="{r["id"].lower()}"></a><a id="result-{r["id"].lower()}"></a>\n\n'
        f'### {r["id"]}. {r["title"]}\n\n'
        f'**Статус:** {r["status"]}\n\n**Результат.** {r["result"]}\n\n'
        f'**Условия.** {r["inputs"]}\n\n**Граница.** {r["limit"]}\n\n'
        f'**Место в рамке.** {r["framework_role"]}\n\n'
        f'**Родители:** {", ".join(r.get("parent_result_ids", []))}. '
        f'**Конструкции:** {", ".join(r.get("construct_ids", []))}. '
        f'**Вопросы:** {", ".join(r.get("open_question_ids", []))}.\n\n'
        "**Источники:** " + "; ".join(f"[{Path(p).name}](../../{p})" for p in r["sources"]) + ".\n\n"
        "**Предпосылки:** " + ", ".join(r.get("premise_ids", [])) +
        "; [реестр 66 условий](../FOUNDATIONS_LITERATURE_20261103/PREMISES_CURRENT.md).\n"
    )


def replace_block(text, key, body):
    begin, end = f"<!-- generated:{key} -->", f"<!-- /generated:{key} -->"
    pattern = re.escape(begin) + r".*?" + re.escape(end)
    replacement = begin + "\n" + body.rstrip() + "\n" + end
    matches = re.findall(pattern, text, re.S)
    if len(matches) > 1:
        raise ValueError(f"Duplicate generated block {key}")
    return re.sub(pattern, lambda _: replacement, text, flags=re.S) if matches else text.rstrip() + "\n\n" + replacement + "\n"


def rel_target(path, anchor):
    relative = posixpath.relpath(path, OUT)
    return f"{relative}#{anchor}" if anchor else relative


def build(root):
    paths = (MAIN, MAIN_MD, QUESTIONS, QUESTIONS_MD, PREMISES, SOURCE_PINS)
    raw = {p: (root / p).read_bytes() for p in paths}
    content = {p: raw[p].decode("utf-8") for p in paths}
    main, questions = json.loads(content[MAIN]), json.loads(content[QUESTIONS])
    pins = json.loads(content[SOURCE_PINS])

    groups0 = {"result": main["results"], "construct": main["constructs"], "link": main["open_links"]}
    main_md, main_anchors = ensure_heading_anchors(content[MAIN_MD], groups0)
    questions_md = ensure_question_anchors(content[QUESTIONS_MD], questions["questions"])
    premises_md = ensure_premise_anchors(content[PREMISES])
    premise_rows = unique(parse_premises(premises_md), PREMISES)
    obligations_md = ensure_obligation_anchors(premises_md)
    obligations = parse_obligations(obligations_md)

    groups = {
        "result": unique(main["results"], MAIN),
        "construct": unique(main["constructs"], MAIN),
        "link": unique(main["open_links"], MAIN),
        "question": unique(questions["questions"], QUESTIONS),
        "premise": premise_rows,
        "obligation": unique(obligations, PREMISES + "#N01-N09")
    }

    nodes = []
    for kind, collection in groups.items():
        for ident, item in collection.items():
            if kind == "premise":
                path, anchor = PREMISES, item["anchor"]
            elif kind == "obligation":
                path, anchor = PREMISES, item["source_anchor"]
            elif kind == "question":
                path, anchor = QUESTIONS_MD, "question-" + ident.lower()
            elif kind == "link":
                path = MAIN_MD
                anchor = "link-" + ident.lower() if ("link", ident) in main_anchors else None
            else:
                path, anchor = MAIN_MD, kind + "-" + ident.lower()
            nodes.append({
                "key": kind + ":" + ident, "id": ident, "kind": kind,
                "title": item.get("title", item.get("current_statement", "")),
                "status": item.get("status"), "path": path, "anchor": anchor,
                "target": rel_target(path, anchor)
            })

    edges = set()

    def add(ka, a, kb, b, relation):
        if a not in groups[ka] or b not in groups[kb]:
            raise ValueError(f"Dangling typed reference: {ka}:{a} -> {kb}:{b}")
        edges.add((ka + ":" + a, kb + ":" + b, relation))

    for ident, record in groups["result"].items():
        for parent in record.get("parent_result_ids", []):
            add("result", parent, "result", ident, "parent")
        for construct in record.get("construct_ids", []):
            add("result", ident, "construct", construct, "addresses")
        for premise in record.get("premise_ids", []):
            add("result", ident, "premise", premise, "direct_conditional_evidence")
        for link in record.get("open_link_ids", []):
            add("result", ident, "link", link, "boundary_open")
        for question in record.get("open_question_ids", []):
            add("result", ident, "question", question, "informs_not_closes")
    for result, constructs in main.get("result_to_constructs", {}).items():
        for construct in constructs:
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
    for obligation, item in groups["obligation"].items():
        for result in item.get("linked_result_ids", []):
            add("result", result, "obligation", obligation, "contextual_reference_not_closure")

    legacy = [x for x in main.get("legacy_crosswalk", []) if x.get("source") == PREMISES]
    if {x["id"] for x in legacy} != set(groups["premise"]):
        raise ValueError("Legacy crosswalk must cover exactly all 66 premise IDs")
    for item in legacy:
        for construct in item.get("constructs", []):
            add("premise", item["id"], "construct", construct, "historical_navigation_not_proof")

    source_entries = verify_pins(root, main, pins)
    provenance = {
        "schema": "vm-lab-source-provenance-v1",
        "source_pins": SOURCE_PINS,
        "note": "File hashes verify identity, not whether every proposition in a file supports a linked claim.",
        "entries": source_entries
    }
    graph = {
        "schema": "vm-lab-registry-links-v2",
        "sources": {p: hashlib.sha256(data).hexdigest() for p, data in raw.items()},
        "counts": {k: len(v) for k, v in groups.items()},
        "semantics": "Typed navigation. Links do not prove claims or close questions. N-obligation references are contextual, not closure. Literature Lxx and project link Lxx namespaces are distinct.",
        "nodes": sorted(nodes, key=lambda x: x["key"]),
        "edges": [{"source": a, "target": b, "relation": rel} for a, b, rel in sorted(edges)]
    }

    bykey = {x["key"]: x for x in nodes}
    def mdlink(key):
        return f'[{bykey[key]["id"]}]({bykey[key]["target"]})'

    lines = [
        "# Связи реестров", "",
        "Сгенерировано через registry_links.py --write. Научные статусы берутся из исходных карточек; связи их не повышают.", "",
        "[Результаты](../NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.md) · "
        "[66 предпосылок](../FOUNDATIONS_LITERATURE_20261103/PREMISES_CURRENT.md) · "
        "[N-долги](../FOUNDATIONS_LITERATURE_20261103/N_DEBTS.json) · "
        "[Вопросы](../NOW_RESULTS_SYNTHESIS_20261106/OPEN_QUESTIONS.md)", "",
        "Число записей: " + ", ".join(f"{k}={v}" for k, v in graph["counts"].items()) + ".", "",
        "## Предпосылка → результаты", "",
        "| ID | Прямое адресное свидетельство | Историческая навигация через конструкции |",
        "|---|---|---|"
    ]
    for premise in premise_rows.values():
        pk = "premise:" + premise["id"]
        direct = sorted(a for a, b, rel in edges if b == pk and rel == "direct_conditional_evidence")
        constructs = sorted(b for a, b, rel in edges if a == pk and rel == "historical_navigation_not_proof")
        navigation = sorted({a for a, b, rel in edges if b in constructs and rel == "addresses"})
        premise["direct_result_ids"] = [bykey[k]["id"] for k in direct]
        premise["navigation_construct_ids"] = [bykey[k]["id"] for k in constructs]
        premise["navigation_result_ids"] = [bykey[k]["id"] for k in navigation]
        lines.append(
            f'| {mdlink(pk)} | {", ".join(mdlink(k) for k in direct) or "Нет новой прямой аттестации"} '
            f'| {", ".join(mdlink(k) for k in constructs)}; {", ".join(mdlink(k) for k in navigation)} |'
        )

    lines += ["", "## N-долг → контекстные результаты", "",
              "| Долг | Статус в источнике | Контекстные ссылки (не закрытие) | Условие закрытия |",
              "|---|---|---|---|"]
    for ident, item in groups["obligation"].items():
        linked = sorted(a for a, b, rel in edges
                        if b == "obligation:" + ident and rel == "contextual_reference_not_closure")
        closure = "Не формализовано в исходной записи" if item["closure_condition"] is None else item["closure_condition"]
        lines.append(
            f'| {mdlink("obligation:" + ident)} | {item["status"]} | '
            f'{", ".join(mdlink(k) for k in linked) or "Нет явной ссылки"} | {closure} |'
        )

    lines += ["", "## Результат → предпосылки", "", "| Результат | Прямые условные связи |", "|---|---|"]
    for result in groups["result"]:
        premises = sorted(b for a, b, rel in edges
                          if a == "result:" + result and rel == "direct_conditional_evidence")
        if premises:
            lines.append(f'| {mdlink("result:" + result)} | {", ".join(mdlink(k) for k in premises)} |')
    lines += ["", "Полный граф: [INDEX.json](INDEX.json). Хеши управляемых источников: [SOURCE_PROVENANCE.json](SOURCE_PROVENANCE.json).", "",
              "premise:C01 не равно construct:C001; N-долг не равен предпосылке; литературные L01–L71 не являются открытыми связями проекта."]

    premises_json = {
        "schema": "premises-current-mirror-v2", "source": PREMISES, "main_registry": MAIN,
        "note": "Generated mirror of the 66 source rows. Navigation is not proof.",
        "entries": list(premise_rows.values())
    }
    obligations_json = {
        "schema": "vm-lab-obligations-v1", "source": PREMISES, "count": len(obligations),
        "note": "Parsed from the existing N01-N09 section. No closure conditions or status changes are inferred.",
        "entries": obligations
    }

    for record in groups["result"].values():
        if record.get("managed_card"):
            main_md = replace_block(main_md, record["id"], render_card(record))
    main_md, _ = ensure_heading_anchors(main_md, groups)

    outputs = {
        OUT + "/INDEX.json": json.dumps(graph, ensure_ascii=False, indent=2) + "\n",
        OUT + "/INDEX.md": "\n".join(lines) + "\n",
        OUT + "/SOURCE_PROVENANCE.json": json.dumps(provenance, ensure_ascii=False, indent=2) + "\n",
        PREMISES.replace(".md", ".json"): json.dumps(premises_json, ensure_ascii=False, indent=2) + "\n",
        "analysis/FOUNDATIONS_LITERATURE_20261103/N_DEBTS.json": json.dumps(obligations_json, ensure_ascii=False, indent=2) + "\n",
        MAIN_MD: main_md, QUESTIONS_MD: questions_md, PREMISES: obligations_md
    }
    return outputs, graph, provenance


def refresh_source_pins(root):
    main = json.loads((root / MAIN).read_text(encoding="utf-8"))
    path = root / SOURCE_PINS
    previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    doc = make_pins(root, main, previous)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return doc


def run(root, write=False):
    outputs, graph, provenance = build(root)
    stale = []
    for path, data in outputs.items():
        target = root / path
        if not target.exists() or target.read_text(encoding="utf-8") != data:
            stale.append(path)
            if write:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(data, encoding="utf-8")
    return stale, graph, provenance


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--refresh-source-pins", action="store_true",
                        help="Explicitly re-pin managed evidence files; inspect the source diff.")
    args = parser.parse_args()
    if args.refresh_source_pins and not args.write:
        parser.error("--refresh-source-pins requires --write")
    if args.refresh_source_pins:
        refresh_source_pins(args.root)

    stale, graph, provenance = run(args.root, args.write)
    status = "UPDATED" if args.write and stale else "FAIL" if stale else "PASS"
    summary = {
        "status": status, "counts": graph["counts"], "edges": len(graph["edges"]),
        "pinned_sources": len(provenance["entries"]), "stale": stale
    }
    rendered = json.dumps(summary, ensure_ascii=False)
    print(rendered)
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as stream:
            stream.write("Registry consistency summary (JSON):\n" + rendered + "\n")
    if stale and not args.write:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
