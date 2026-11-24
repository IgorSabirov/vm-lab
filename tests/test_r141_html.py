"""Exercise both input formats and protect the last published file on a bad input."""
import base64
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from lxml import html

MODEL = Path(__file__).resolve().parents[1] / "analysis/R141_R148_MODEL"
sys.path.insert(0, str(MODEL))
import build_html as build
import native_inputs as native
import sync_html as sync


class BuildTests(unittest.TestCase):
    def overlay(self, changes):
        original_bytes, original_text = Path.read_bytes, Path.read_text
        bytes_patch = patch.object(Path, "read_bytes", lambda p: changes[p] if p in changes else original_bytes(p))
        text_patch = patch.object(Path, "read_text", lambda p,*a,**k: changes[p].decode() if p in changes else original_text(p,*a,**k))
        bytes_patch.start()
        self.addCleanup(bytes_patch.stop)
        text_patch.start()
        self.addCleanup(text_patch.stop)

    def test_forward_sources_are_visible_and_recoverable(self):
        atlas = json.loads(sync.ATLAS.read_text())
        passport = atlas["passports"][0]
        passport["result"] += " Passport test."
        native_card = sync.MAIN.parent / "R141.md"
        result = json.loads(native_card.with_suffix(".json").read_text())["result"]
        pair = atlas["edges"][0]
        pairs = native.PAIRS.read_text().replace(pair["control"], pair["control"]+" Pair test.", 1)
        script = MODEL / "ym_graph/step5/check.py"
        code = script.read_bytes()+b"\n# ZIP propagation test\n"
        self.overlay({sync.ATLAS:sync.encode(atlas).encode(), native.PAIRS:pairs.encode(),
                      native_card:native_card.read_text().replace(result, result+" Card test.",1).encode(),
                      script:code})
        updates = build.plan()
        doc = html.fromstring(updates[sync.MODEL].decode())
        self.assertIn("Card test.",doc.xpath('//*[@id="peer-R141"]/following-sibling::details[1]')[0].text_content())
        self.assertIn("Card test.",json.loads(updates[native_card.with_suffix(".json")])["result"])
        self.assertIn("Pair test.",doc.get_element_by_id(pair["anchor"]).text_content())
        for n in (141,142):
            self.assertIn("Pair test.",doc.get_element_by_id(f"relations-{n}").text_content())
        self.assertIn("Passport test.",doc.get_element_by_id(passport["id"]).text_content())
        z = "R130_step5_13_14.zip"
        embedded = base64.b64decode(build.download(doc,z).get("href").split(",",1)[1])
        self.assertEqual(embedded,updates[MODEL/"ym_graph"/z])
        with ZipFile(io.BytesIO(embedded)) as archive:
            self.assertEqual(archive.read("check.py"),code)
        source = next(m for m in atlas["materials"] if m["path"].endswith("/R141.md") and "NOW_RESULTS" in m["path"])
        self.assertIn("Card test.",doc.get_element_by_id(source["anchor"]).text_content())

    def test_invalid_anchor_preserves_published_bytes(self):
        before = sync.MODEL.read_bytes()
        atlas = json.loads(sync.ATLAS.read_text())
        atlas["passports"][0]["sources"] = ["#absent-test-anchor"]
        self.overlay({sync.ATLAS:sync.encode(atlas).encode()})
        with self.assertRaisesRegex(ValueError,"absent-test-anchor"):
            build.run(True, False)
        self.assertEqual(sync.MODEL.read_bytes(),before)

    def test_conflicting_register_and_card_are_rejected(self):
        path = sync.MAIN.parent/"R141.json"
        row = json.loads(path.read_text())
        register = json.loads(sync.MAIN.read_text())
        next(r for r in register["results"] if r["id"]=="R141")["result"] += " Register edit."
        row["result"] += " Different card edit."
        self.overlay({path:sync.encode(row).encode(),sync.MAIN:sync.encode(register).encode()})
        with self.assertRaisesRegex(ValueError,"Conflicting native edits: R141.result"):
            native.read()

    def test_output_is_not_a_build_input(self):
        self.overlay({sync.MODEL:b"output removed"})
        updates = build.plan()
        self.assertEqual(json.loads(sync.ATLAS.read_text())["html_sha256"],
                         build.hashlib.sha256(updates[sync.MODEL]).hexdigest())
