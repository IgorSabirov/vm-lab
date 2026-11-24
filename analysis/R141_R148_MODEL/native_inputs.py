"""Reconcile the editable repository records against their last published agreement."""
import copy
import hashlib
import json
import re

import sync_html as sync

STATE = sync.HERE / "build_state.json"
PAIRS = sync.HERE / "PAIRS.md"
SCALARS = {
    "title": r"^### R\d+\. (.*?)$",
    "status": r"^\*\*Статус:\*\* (.*?)$",
    "result": r"^\*\*Результат\.\*\* (.*?)(?=\n\n\*\*Условия)",
    "inputs": r"^\*\*Условия\.\*\* (.*?)(?=\n\n\*\*Граница)",
    "limit": r"^\*\*Граница\.\*\* (.*?)(?=\n\n\*\*Место)",
    "framework_role": r"^\*\*Место в рамке\.\*\* (.*?)(?=\n\n\*\*Родители)",
}
FIELDS = ("type", "map", "control")


def digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()


def agree(old_hash, variants, label):
    distinct = {digest(value): value for value in variants}
    if len(distinct) == 1:
        return next(iter(distinct.values()))
    distinct.pop(old_hash, None)
    if len(distinct) != 1:
        raise ValueError(f"Conflicting native edits: {label}")
    return next(iter(distinct.values()))


def review(node):
    return f"#### {node['title']} · общая модель\n\n{node['summary']}\n\n{node['review']}"


def set_review(node, text):
    head, sep, body = text.partition("\n\n")
    title = re.fullmatch(r"#### (.+) · общая модель", head)
    if not sep or not title:
        raise ValueError(f"Invalid model_review header in {node['id']}")
    # Preserve the original split if only one half changed.
    start = node["summary"] + "\n\n"
    end = "\n\n" + node["review"]
    if body.startswith(start):
        summary, notes = node["summary"], body[len(start):]
    elif body.endswith(end):
        summary, notes = body[:-len(end)], node["review"]
    else:
        summary, marker, notes = body.partition("\n\n**")
        if not marker:
            raise ValueError(f"Missing review heading in {node['id']}")
        notes = "**" + notes
    node.update(title=title[1], summary=summary, review=notes)


def markdown_changes(md, base):
    """Only accept a parse that round-trips. Never discard unrecognised text."""
    row = copy.deepcopy(base)
    for field, pattern in SCALARS.items():
        match = re.search(pattern, md, re.M | re.S if field not in ("title", "status") else re.M)
        if match:
            row[field] = match[1]
    marker = "\n#### "
    if marker in md:
        row["model_review"] = "#### " + md.split(marker, 1)[1].removesuffix("\n")
    if sync.registry.render_card(row) != md:
        raise ValueError(f"{row['id']}.md: edit structured lists/links in the card JSON, or reconcile the Markdown layout")
    return row


def cells(line):
    return [c.strip().replace(r"\|", "|") for c in re.split(r"(?<!\\)\|", line.strip()[1:-1])]


def pair_rows(text):
    rows = {}
    for line in text.splitlines():
        if not line.startswith("| ["):
            continue
        label, *values = cells(line)
        ids = re.findall(r"\[R(\d+)\]\(", label)
        key = "-".join(ids)
        if len(ids) != 2 or len(values) != 3 or key in rows or not all(values):
            raise ValueError("Invalid or duplicate row in PAIRS.md")
        rows[key] = values
    return rows


def pairs_md(edges):
    rows = [["Карточки", "Тип связи", "Переход", "Контроль"]]
    for edge in edges:
        links = [f"[R{i}](../{sync.MAIN.parent.name}/R{i}.md)" for i in (edge["a"], edge["b"])]
        rows.append([" ↔ ".join(links), *(edge[key] for key in FIELDS)])
    return "# Связи восьми карточек\n\n" + sync.table_md(rows) + "\n"


def read():
    old = json.loads(STATE.read_text())
    atlas = json.loads(sync.ATLAS.read_text())
    register = json.loads(sync.MAIN.read_text())
    rows = {r["id"]: r for r in register["results"]}
    if [n["id"] for n in atlas["nodes"]] != sync.IDS:
        raise ValueError("Expected exactly R141–R148")
    updates = {}
    state = {"cards": {}, "pairs": {}, "live_materials": dict(old["live_materials"])}
    if "r144_full_replay_sha256" in old:
        state["r144_full_replay_sha256"] = old["r144_full_replay_sha256"]
    for node in atlas["nodes"]:
        ident = node["id"]
        reg = rows[ident]
        card = sync.MAIN.parent / (ident + ".json")
        native = json.loads(card.read_text())
        if native.get("id") != ident:
            raise ValueError(f"Wrong identity in {card.name}")
        md = card.with_suffix(".md")
        text = md.read_text()
        baseline = old["cards"][ident]
        variants = [reg, native]
        if digest(text) != baseline["md"] and text not in [sync.registry.render_card(r) for r in variants]:
            variants.append(markdown_changes(text, native))
        keys = set().union(*variants, baseline["fields"])
        # Missing and null are distinct; preserve insertion order of the repository record.
        row = {}
        for key in dict.fromkeys([*reg, *native, *sorted(keys)]):
            values = [[key in v, v.get(key)] for v in variants]
            present, value = agree(baseline["fields"].get(key, digest([False, None])), values, ident + "." + key)
            if present:
                row[key] = value
        combined = agree(baseline["review"], [review(node), row["model_review"]], ident + ".model_review")
        if combined != review(node):
            set_review(node, combined)
        row["model_review"] = combined
        reg.clear()
        reg.update(row)
        text = sync.registry.render_card(row)
        updates[card] = sync.encode(row).encode()
        updates[md] = text.encode()
        state["cards"][ident] = {"fields": {k:digest([True, v]) for k,v in row.items()},
                                 "md": digest(text), "review": digest(combined)}
    pairs = pair_rows(PAIRS.read_text())
    expected = {f"{a}-{b}" for a in range(141,149) for b in range(a+1,149)}
    if set(pairs) != expected or len(atlas["edges"]) != 28:
        raise ValueError("Expected 28 distinct pairs")
    for edge in atlas["edges"]:
        key = f"{edge['a']}-{edge['b']}"
        values = agree(old["pairs"][key], [[edge[k] for k in FIELDS], pairs.pop(key)], "pair " + key)
        edge.update(zip(FIELDS, values))
        state["pairs"][key] = digest(values)
    updates[sync.MAIN] = sync.encode(register).encode()
    updates[PAIRS] = pairs_md(atlas["edges"]).encode()
    return atlas, rows, updates, state
