"""Export the published HTML atlas into native vm-lab records (requires lxml)."""
import argparse
import base64
import io
import zipfile
import hashlib
import itertools
import json
from pathlib import Path
import sys

from lxml import html

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import registry_links as registry

MODEL = HERE / "R141-R148.html"
ATLAS = HERE / "ATLAS.json"
MAIN = ROOT / registry.MAIN
IDS = [f"R{n}" for n in range(141, 149)]


def encode(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def plain(node):
    def words(el):
        if el.tag=="math":
            tex = el.find('.//annotation[@encoding="application/x-tex"]')
            if tex is not None:
                return "$" + tex.text_content() + "$"
        return (el.text or "") + "".join(words(child)+(child.tail or "") for child in el)
    return " ".join(words(node).split())


def table_md(rows):
    def row(cells):
        return "| " + " | ".join(x.replace("|", "\\|") for x in cells) + " |"
    return "\n".join([row(rows[0]), row(["---"]*len(rows[0])), *map(row, rows[1:])])


def review_text(section):
    lines = []
    for child in section:
        if child.tag == "h4":
            lines.append("**"+plain(child)+"**")
        elif child.tag == "div":
            lines.append(table_md([[plain(cell) for cell in row] for row in child.xpath(".//tr")]))
        elif child.tag == "p" and not child.xpath('./a[@href="#peer-audit"]'):
            lines.append(plain(child))
    return "\n\n".join(lines)


def extract():
    content = MODEL.read_bytes()
    doc = html.fromstring(content.decode("utf-8"))
    record = json.loads(doc.get_element_by_id("machine-record").findtext("pre"))
    ids = [r["id"] for r in record["nodes"]]
    if ids != IDS:
        raise ValueError("Unexpected set or ordering of HTML cards")
    # The visible table owns the descriptions. The embedded record supplies provenance.
    edge_rows = doc.xpath('//*[@id="edge-table"]//tr[@data-a]')
    original = {(x["a"], x["b"]):x for x in record["edges"]}
    expected = set(itertools.combinations(range(141,149),2))
    if set(original)!=expected or len(edge_rows)!=len(expected):
        raise ValueError("Incomplete or duplicated card comparisons")
    edges = []
    for row in edge_rows:
        a,b = int(row.get("data-a")), int(row.get("data-b"))
        kind, mapping, control = [plain(c) for c in row.xpath("./td")[1:]]
        edges.append(dict(original[a,b], type=kind, map=mapping, control=control, anchor=row.get("id")))
    if {(e["a"],e["b"]) for e in edges}!=expected:
        raise ValueError("Visible comparisons disagree with the card set")
    record["edges"] = edges
    visible_passports = doc.xpath('//details[contains(concat(" ",@class," ")," passport ")]')
    by_id = {n.get("id"):n for n in visible_passports}
    if len(by_id)!=len(visible_passports) or len(by_id)!=len(record["passports"]) or set(by_id)!={p["id"] for p in record["passports"]}:
        raise ValueError("Passport identifiers differ between the index and the cards")
    labels = {"Конструкция":"object","В корпусе":"result","Граница":"boundary",
              "Уточнение этой сборки":"integration_note"}
    for item in record["passports"]:
        node = by_id[item["id"]]
        item["name"] = plain(node.xpath('.//*[@class="passname"]')[0])
        item["addresses"] = plain(node.xpath('.//*[@class="passaddr"]')[0])
        item.pop("integration_note",None)
        for term in node.xpath("./div/dl/dt"):
            label, value = plain(term), term.getnext()
            if label in labels:
                item[labels[label]] = plain(value)
            elif label=="Источники":
                item["sources"] = value.xpath(".//a/@href")
    materials = []
    for li in doc.xpath('//*[@id="material-index"]//ul[contains(@class,"source-idx")]/li | //*[@class="source-idx"]//li'):
        link = li.find("a")
        anchor = link.get("href")[1:]
        doc.get_element_by_id(anchor)
        materials.append({"label":plain(link),"path":li.findtext("small"),"anchor":anchor})
    if len(materials)!=len({m["anchor"] for m in materials}) or not materials:
        raise ValueError("Invalid source catalog")
    record["materials"] = materials
    record["html_sha256"] = hashlib.sha256(content).hexdigest()
    record["html_path"] = MODEL.relative_to(ROOT).as_posix()
    for node in record["nodes"]:
        ident = node["id"]
        node["title"] = plain(doc.get_element_by_id("node"+ident[1:])).split(" · ",1)[1]
        heading = doc.get_element_by_id("node"+ident[1:])
        summary = []
        for child in heading.itersiblings():
            if child.get("id") in ("peer-"+ident, "body-"+ident[1:]):
                break
            if child.tag == "p":
                summary.append(plain(child))
            elif child.get("class") == "scrolltable":
                summary.append(table_md([[plain(c) for c in r] for r in child.xpath(".//tr")]))
        node["summary"] = "\n\n".join(summary)
        node["review"] = review_text(doc.get_element_by_id("peer-"+ident))
    record["task_boundaries"] = [
        [plain(c) for c in row.xpath("./td")]
        for row in doc.xpath('//*[@id="limits"]/following-sibling::div[1]//tr[td]')]
    attachment = doc.xpath('//a[@download="R148_temporal_and_controls.zip"]/@href')
    if len(attachment)!=1:
        raise ValueError("Expected one R148 reproduction archive")
    archive = base64.b64decode(attachment[0].split(",",1)[1], validate=True)
    members = ("code/temporal.py", "code/r130_reference.py", "code/audit_extensions.py",
               "results/temporal.json", "results/extensions.json")
    with zipfile.ZipFile(io.BytesIO(archive)) as package:
        if set(package.namelist())!=set(members) or len(package.infolist())!=len(members):
            raise ValueError("R148 archive members changed; review their destination paths")
        evidence = {HERE / name:package.read(name).decode("utf-8") for name in members}
    return record, evidence


def outputs():
    record, evidence = extract()
    register = json.loads(MAIN.read_text())
    rows = {r["id"]:r for r in register["results"]}
    files = {ATLAS:encode(record), **evidence}
    for node in record["nodes"]:
        ident = node["id"]
        row = rows[ident]
        row["model_review"] = ("#### "+node["title"]+" · общая модель\n\n"+
                               node["summary"]+"\n\n"+node["review"])
        card = MAIN.parent/ident
        files[card.with_suffix(".json")] = encode(row)
        files[card.with_suffix(".md")] = registry.render_card(row)
    files[MAIN] = encode(register)
    pairs = [["Карточки","Тип связи","Переход","Контроль"]]
    for edge in record["edges"]:
        a,b = edge["a"], edge["b"]
        link = lambda k: f"[R{k}](../{MAIN.parent.name}/R{k}.md)"
        pairs.append([link(a)+" ↔ "+link(b),edge["type"],edge["map"],edge["control"]])
    files[HERE/"PAIRS.md"] = "# Связи восьми карточек\n\n"+table_md(pairs)+"\n"
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write",action="store_true")
    args = parser.parse_args()
    changed = []
    for path, text in outputs().items():
        if not path.exists() or path.read_bytes()!=text.encode():
            changed.append(str(path.relative_to(ROOT)))
            if args.write:
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(text.encode())
    print("\n".join(changed) if changed else "HTML, atlas and eight registry cards agree")
    return bool(changed and not args.write)


if __name__ == "__main__":
    raise SystemExit(main())
