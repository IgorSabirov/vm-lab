"""Project native data into the offline edition while retaining its historical sources and MathML."""
from collections import defaultdict
from pathlib import Path
import re
from urllib.parse import urlsplit

from lxml import etree

import native_inputs as native
import sync_html as sync


def el(parent, tag, text=None, **attrs):
    node = etree.SubElement(parent, tag, attrs)
    node.text = text
    return node


def empty(node):
    for child in list(node):
        node.remove(child)
    node.text = None


def put(node, value):
    if sync.plain(node) != value:
        empty(node)
        node.text = value


def prose(parent, text, review=False):
    for part in text.split("\n\n"):
        lines = part.splitlines()
        if part.startswith("| ") and len(lines) >= 2:
            table = el(el(parent, "div", **{"class": "scrolltable"}), "table")
            for i, line in enumerate(lines):
                if i == 1:
                    continue
                tr = el(table, "tr")
                for cell in native.cells(line):
                    el(tr, "th" if i == 0 else "td", cell)
        elif review and part.startswith("**") and part.endswith("**"):
            el(parent, "h4", part[2:-2])
        else:
            el(parent, "p", part)


def cards(doc, atlas, rows):
    for node in atlas["nodes"]:
        ident = node["id"]
        heading = doc.get_element_by_id("node" + ident[1:])
        put(heading, ident + " · " + node["title"])
        peer = doc.get_element_by_id("peer-" + ident)
        summary = []
        for item in heading.itersiblings():
            if item == peer:
                break
            if item.tag == "p" or item.get("class") == "scrolltable":
                summary.append(item)
        def summary_part(item):
            if item.tag == "p":
                return sync.plain(item)
            return sync.table_md([[sync.plain(c) for c in r] for r in item.xpath(".//tr")])
        if "\n\n".join(map(summary_part, summary)) != node["summary"]:
            for item in summary:
                item.getparent().remove(item)
            fragment = etree.Element("div")
            prose(fragment, node["summary"])
            for item in list(fragment):
                peer.addprevious(item)
        if sync.review_text(peer) != node["review"]:
            empty(peer)
            prose(peer, node["review"], review=True)
        # The native record contains scientific fields absent from the editorial summary.
        row = rows[ident]
        current = etree.Element("details", {"class": "native-record", "data-build": "current"})
        peer.addnext(current)
        el(current, "summary", "Карточка реестра · " + row["title"])
        dl = el(current, "dl")
        for key, label in (("status","Статус"), ("result","Результат"), ("inputs","Условия"),
                           ("limit","Граница"), ("framework_role","Место в общей модели")):
            el(dl, "dt", label)
            el(dl, "dd", row[key])
        machine = el(current, "details")
        el(machine, "summary", "Полная запись реестра · JSON")
        el(machine, "pre", sync.encode(row), **{"class":"raw-content"})


def pairs(doc, edges):
    table = doc.get_element_by_id("edge-table")
    tbody = table.find("tbody")
    empty(tbody)
    relations = {}
    for n in range(141,149):
        box = doc.get_element_by_id(f"relations-{n}")
        for child in box.xpath('./div[@class="relation-line"]'):
            box.remove(child)
        relations[n] = box
    for i, edge in enumerate(edges):
        a, b = edge["a"], edge["b"]
        row = el(tbody, "tr", id=edge["anchor"], **{"data-a":str(a), "data-b":str(b),
                                                     "class": "odd" if i % 2 == 0 else "even"})
        cell = el(row, "td", **{"data-label":"Карточки"})
        el(cell, "a", f"R{a}", href=f"#node{a}").tail = " ↔ "
        el(cell, "a", f"R{b}", href=f"#node{b}")
        for field, label in zip(native.FIELDS, ("Тип связи","Переход","Контроль")):
            el(row, "td", edge[field], **{"data-label": label})
        for start, end in ((a,b),(b,a)):
            line = el(relations[start], "div", **{"class":"relation-line"})
            el(line, "a", f"R{end}", href=f"#node{end}")
            el(line, "strong", edge["type"])
            el(line, "p", edge["map"])
            el(line, "p", edge["control"], **{"class":"condition"})
            el(line, "a", "Строка общей таблицы", href="#" + edge["anchor"])


def passports(doc, items):
    groups = doc.xpath('//div[@class="passport-group"]')
    parent, position = groups[0].getparent(), groups[0].getparent().index(groups[0])
    source_labels = {a.get("href"):a.text_content() for g in groups for a in g.xpath(".//dd/a")}
    for group in groups:
        parent.remove(group)
    by_group = defaultdict(list)
    seen = set()
    for p in items:
        if p["id"] in seen or not all(p.get(k) for k in ("id","group","name","object","result","boundary","sources")):
            raise ValueError(f"Incomplete or duplicate passport {p.get('id')}")
        seen.add(p["id"])
        by_group[p["group"]].append(p)
    if not items:
        raise ValueError("Empty passport catalog")
    names = {p["id"]:p["name"] for p in items}
    for a in parent.xpath('./div[@class="quick"]/a'):
        key = a.get("href","")[1:]
        if key in names:
            a.text = names[key]
        else:
            a.getparent().remove(a)
    intro = parent.find("p")
    if intro is not None and intro.text:
        intro.text = re.sub(r"^\d+(?= индивидуальных паспортов)", str(len(items)), intro.text)
    doc.get_element_by_id("machine-record").find("summary").text = (
        f"Единая машинная карточка · 8 блоков · 28 пар · паспорта ({len(items)})")
    for i, (title, people) in enumerate(by_group.items(),1):
        group = etree.Element("div", {"class":"passport-group", "id":f"group-{i}"})
        parent.insert(position+i-1, group)
        el(el(group, "h3", title + " "), "span", f"· {len(people)}", **{"class":"small"})
        for p in people:
            card = el(group, "details", id=p["id"], **{"class":"passport"})
            head = el(card, "summary")
            for field, cls in (("name","passname"),("addresses","passaddr"),("id","passid")):
                el(head, "span", p[field], **{"class":cls})
            dl = el(el(card, "div", **{"class":"passbody"}), "dl")
            for field, label in (("object","Конструкция"),("result","В корпусе"),("boundary","Граница"),
                                  ("sources","Источники"),("integration_note","Уточнение этой сборки")):
                if field not in p:
                    continue
                el(dl, "dt", label)
                dd = el(dl, "dd")
                if field == "sources":
                    for href in p[field]:
                        if not href.startswith("#") and urlsplit(href).scheme not in {"http","https"}:
                            raise ValueError(f"Invalid passport source {href}")
                        el(dd, "a", source_labels.get(href, href), href=href).tail = " "
                else:
                    dd.text = p[field]
            card.set("data-search", " ".join(card.itertext()).lower())


def repo_path(path):
    result = (sync.ROOT / path).resolve()
    if not result.is_relative_to(sync.ROOT) or Path(path).is_absolute():
        raise ValueError(f"Source outside repository: {path}")
    return result


def materials(doc, atlas, rows, updates, state):
    slots = {e.get("id"):e for e in doc.xpath('//details[@class="source-doc"]')}
    lists = doc.xpath('//ul[@class="source-idx"]')
    for ul in lists:
        empty(ul)
    lookup = {}
    for item in atlas["materials"]:
        anchor, path, label = item["anchor"], item["path"], item["label"]
        if anchor in lookup.values() or path in lookup:
            raise ValueError(f"Duplicate material: {path}")
        lookup[path] = anchor
        box = slots.get(anchor)
        src = state["live_materials"].get(anchor)
        # A renamed catalog entry must resolve the new source. Frozen entries keep the edition.
        if src is None or (box is not None and box.get("data-path") != path):
            src = next((p for p in [repo_path(path), repo_path(sync.HERE.relative_to(sync.ROOT)/path)]
                        if p.is_file()), None)
        else:
            src = repo_path(src)
        if box is None:
            owner = re.match(r"R(14[1-8])\b", label)
            if not owner or src is None:
                raise ValueError(f"A new material needs a repository source and R141–R148 label: {path}")
            box = el(doc.get_element_by_id("files-"+owner[1]), "details", id=anchor,
                     **{"class":"source-doc","data-node":owner[1]})
            el(box, "summary", label)
        if src is None and box.get("data-path") != path:
            raise ValueError(f"Unresolved source {path}")
        box.set("data-path", path)
        box.set("data-title", label.split(" · ",1)[-1])
        ul = lists[0]
        li = el(ul, "li", **{"data-needle":(label + " " + path).lower()})
        el(li, "a", label, href="#"+anchor)
        el(li, "small", path)
        if src is not None:
            rel = src.relative_to(sync.ROOT).as_posix()
            state["live_materials"][anchor] = rel
            lookup[rel] = anchor
            raw = updates[src] if src in updates else src.read_bytes()
            current = etree.Element("div", {"data-build":"current"})
            box.insert(1, current)
            el(current, "small", rel + " · текущая версия в репозитории")
            el(current, "pre", raw.decode(), **{"class":"raw-content"})
            archive = etree.Element("details", {"data-build":"history"})
            el(archive, "summary", "Материал исходной редакции")
            for child in list(box)[2:]:
                archive.append(child)
            if len(archive)>1:
                box.append(archive)
        elif not list(box)[1:]:
            raise ValueError(f"Missing historical content: {path}")
    for anchor in set(slots) - {m["anchor"] for m in atlas["materials"]}:
        box = slots[anchor]
        box.getparent().remove(box)
        state["live_materials"].pop(anchor, None)
    # Additional sources referenced by the working cards are available offline as well.
    lookup.update({sync.MODEL.relative_to(sync.ROOT).as_posix():"node141",
                   sync.ATLAS.relative_to(sync.ROOT).as_posix():"machine-record",
                   native.PAIRS.relative_to(sync.ROOT).as_posix():"edge-table",
                   "analysis/R141_R147_MODEL/evidence/R144_review_kit.zip":"r144full-tests"})
    for ident in sync.IDS:
        panel = doc.xpath('//*[@id=$peer]/following-sibling::details[@class="native-record"][1]',
                          peer="peer-"+ident)[0]
        ul = el(panel, "ul")
        for path in dict.fromkeys(rows[ident]["sources"] + rows[ident].get("managed_sources", [])):
            li = el(ul, "li")
            if path not in lookup:
                src = repo_path(path)
                raw = updates[src] if src in updates else src.read_bytes()
                anchor = "native-" + native.digest(path)[:16]
                lookup[path] = anchor
                details = el(li, "details", id=anchor)
                el(details, "summary", path)
                if path.endswith(".zip"):
                    import base64
                    el(details, "a", "Скачать ZIP", download=src.name,
                       href="data:application/zip;base64,"+base64.b64encode(raw).decode())
                else:
                    el(details, "pre", raw.decode(), **{"class":"raw-content"})
            else:
                el(li, "a", path, href="#"+lookup[path])


def boundaries(doc, rows):
    body = doc.get_element_by_id("limits").getnext().find(".//tbody")
    empty(body)
    for values in rows:
        if len(values) != 2 or not all(values):
            raise ValueError("Invalid task boundary")
        row = el(body,"tr")
        for value in values:
            el(row,"td",value)
