"""Build and verify the standalone R141–R148 HTML from the repository."""
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

from lxml import etree, html

import model_blocks
import native_inputs as native
import render_html as render
import sync_html as sync

EDITION = sync.HERE / "edition.html"
KIT = sync.ROOT / "analysis/R141_R147_MODEL/evidence/R144_review_kit.zip"
KIT_JSON = {"R144_canonical.json":"R144_CANONICAL.json", "r144.schema.json":"r144.schema.json",
            "blind_cards.json":"blind_cards.json"}


def serialize(doc):
    return etree.tostring(doc, method="html", encoding="utf-8", doctype="<!doctype html>") + b"\n"


def editorial_source(data):
    """Keep offline editorial changes, without recursively embedding generated live copies."""
    doc = html.fromstring(data.decode())
    for item in doc.xpath('//*[@data-build="current"]'):
        item.getparent().remove(item)
    for box in doc.xpath('//*[@data-build="history"]'):
        for child in list(box)[1:]:
            box.addprevious(child)
        box.getparent().remove(box)
    return serialize(doc)


def download(doc, name):
    matches = doc.xpath('//a[@download=$name]', name=name)
    if len(matches) != 1:
        raise ValueError(f"Expected one download: {name}")
    return matches[0]


def pack(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, raw in files.items():
            entry = zipfile.ZipInfo(name, (1980,1,1,0,0,0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, raw)
    return buffer.getvalue()


def contents(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        if len(z.namelist()) != len(set(z.namelist())) or z.testzip() is not None:
            raise ValueError("Duplicate or corrupt ZIP member")
        return {name:z.read(name) for name in z.namelist()}


def set_download(link, raw, mime):
    link.set("href", f"data:application/{mime};base64," + base64.b64encode(raw).decode())


def archives(doc, updates, old, state):
    published = {}
    state["archives"] = {}
    for name, members in sync.ARCHIVES.items():
        link = download(doc, name)
        directory = sync.HERE / sync.STUDY_DIRS.get(name, "")
        files = {m:(directory/m).read_bytes() for m in members}
        if name in sync.STUDY_DIRS:
            path = sync.HERE / "ym_graph" / name
            previous = path.read_bytes()
        else:
            previous = base64.b64decode(link.get("href").split(",",1)[1], validate=True)
        if contents(previous) == files:
            raw = previous
        else:
            if name in sync.STUDY_DIRS and hashlib.sha256(previous).hexdigest() != old.get(name):
                raise ValueError(f"Edited ZIP disagrees with its native files: {name}")
            raw = pack(files)
        if name in sync.STUDY_DIRS:
            updates[path] = raw
            published[name] = raw
        state["archives"][name] = hashlib.sha256(raw).hexdigest()
        set_download(link, raw, "zip")
    raw = KIT.read_bytes()
    data = contents(raw)
    set_download(download(doc, KIT.name), raw, "zip")
    for name, member in KIT_JSON.items():
        json.loads(data[member])
        set_download(download(doc, name), data[member], "json")
    return published


def plan():
    atlas, rows, updates, state = native.read()
    doc = html.fromstring(EDITION.read_text())
    render.cards(doc, atlas, rows)
    render.pairs(doc, atlas["edges"])
    render.passports(doc, atlas["passports"])
    render.boundaries(doc, atlas["task_boundaries"])
    old = json.loads(native.STATE.read_text())
    published = archives(doc, updates, old.get("archives", {}), state)
    render.materials(doc, atlas, rows, updates, state)
    record = {k:v for k,v in atlas.items() if k not in ("html_sha256","html_path")}
    doc.get_element_by_id("machine-record").find("pre").text = sync.encode(record).rstrip("\n")
    content = serialize(doc)
    model_blocks.validate(content)
    extracted, evidence = sync.extract(content, published)
    for key, value in record.items():
        if extracted.get(key) != value:
            raise ValueError(f"HTML round-trip differs from ATLAS.json: {key}")
    for path, text in evidence.items():
        if text.encode() != path.read_bytes():
            raise ValueError(f"Embedded code or data differs: {path}")
    updates[sync.MODEL] = content
    updates[sync.ATLAS] = sync.encode(extracted).encode()
    updates[native.STATE] = sync.encode(state).encode()
    return updates


def guard_import():
    published = plan()[sync.MODEL]
    if hashlib.sha256(published).hexdigest() != json.loads(sync.ATLAS.read_text())["html_sha256"]:
        raise ValueError("Repository sources changed since publication. Build before applying offline edits.")
    def live_sections(data):
        doc = html.fromstring(data.decode())
        return [etree.tostring(el, with_tail=False) for el in doc.xpath('//*[@data-build="current"]')]
    if live_sections(published) != live_sections(sync.MODEL.read_bytes()):
        raise ValueError("A generated source view was edited. Apply that edit in its named repository file.")


def replays():
    runs = [
        ("code/audit_extensions.py", "results/extensions.json", []),
        ("code/temporal.py", "results/temporal.json", []),
        ("name_arithmetic/replay.py", "name_arithmetic/results.json", []),
        ("ym_graph/pilot/replay.py", "ym_graph/pilot/results.json", ["--reference","code/r130_reference.py"]),
        ("ym_graph/step5/check.py", "ym_graph/step5/results.json", []),
    ]
    for script, expected, args in runs:
        run = subprocess.run([sys.executable, script, *args], cwd=sync.HERE, check=True, stdout=subprocess.PIPE)
        if run.stdout != (sync.HERE/expected).read_bytes():
            raise ValueError(f"Replay differs from {expected}")
        print(f"PASS {script}", flush=True)


def atomic_write(path, raw):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        tmp = Path(f.name)
    try:
        tmp.write_bytes(raw)
        tmp.chmod(0o644)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def run(write, replay):
    updates = plan()
    changed = {p:v for p,v in updates.items() if not p.exists() or p.read_bytes() != v}
    if replay:
        replays()
    if changed and not write:
        for path in changed:
            print(f"Stale: {path.relative_to(sync.ROOT)}")
        return 1
    before = {}
    def replace(path, data):
        before[path] = path.read_bytes() if path.exists() else None
        atomic_write(path, data)
    try:
        for path, data in changed.items():
            replace(path, data)
        # The graph contains the byte hashes of this HTML and atlas. Regenerate only its
        # dependent outputs. An unrelated stale registry must not be silently rewritten.
        generated, _ = sync.registry.build(sync.ROOT)
        allowed = {sync.registry.MAIN_MD, sync.registry.OUT+"/INDEX.md", sync.registry.OUT+"/INDEX.json"}
        for name, text in generated.items():
            path = sync.ROOT/name
            if path.read_text() == text:
                continue
            if name not in allowed or not write:
                raise ValueError(f"Stale registry file: {name}")
            replace(path, text.encode())
    except BaseException:
        for path, raw in reversed(before.items()):
            if raw is None:
                path.unlink(missing_ok=True)
            else:
                atomic_write(path, raw)
        raise
    print(f"Verified 8 cards, 28 pairs, source catalog, anchors and ZIPs. Updated {len(before)} files.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--replay", action="store_true", help="Run all five native reference calculations")
    args = parser.parse_args()
    with model_blocks.lock_directory(sync.HERE):
        sys.exit(run(args.write, args.replay))
