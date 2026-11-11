import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("registry_links", ROOT / "tools/registry_links.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class RegistryIntegrity(unittest.TestCase):
    def fixture(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        dst = Path(tmp.name)
        for path in (mod.MAIN, mod.MAIN_MD, mod.QUESTIONS, mod.QUESTIONS_MD, mod.PREMISES):
            target = dst / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text((ROOT / path).read_text(encoding="utf-8"), encoding="utf-8")

        main = json.loads((dst / mod.MAIN).read_text(encoding="utf-8"))
        for record in main["results"]:
            for source in record.get("managed_sources", []):
                target = dst / source
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("fixture source: " + source, encoding="utf-8")

        mod.refresh_source_pins(dst)
        mod.run(dst, True)
        return dst

    def change_main(self, root, fn):
        path = root / mod.MAIN
        data = json.loads(path.read_text(encoding="utf-8"))
        fn(data)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_current_snapshot(self):
        stale, graph, provenance = mod.run(ROOT)
        self.assertEqual(stale, [])
        self.assertEqual(graph["counts"]["premise"], 66)
        self.assertEqual(graph["counts"]["obligation"], 9)
        self.assertEqual(len(provenance["entries"]), 4)

    def test_typed_obligations_and_context_not_closure(self):
        _, graph, _ = mod.run(ROOT)
        nodes = {node["key"]: node for node in graph["nodes"]}
        self.assertEqual(nodes["obligation:N03"]["status"], "CONDITIONALLY_RESOLVED")
        self.assertEqual(nodes["obligation:N02"]["status"], "OPEN")
        self.assertIn("obligation-n02", nodes["obligation:N02"]["target"])
        refs = [edge for edge in graph["edges"]
                if edge["target"] == "obligation:N02"]
        self.assertTrue(refs)
        self.assertTrue(all(edge["relation"] == "contextual_reference_not_closure" for edge in refs))

    def test_deep_links_resolve_to_stable_anchors(self):
        _, graph, _ = mod.run(ROOT)
        nodes = {node["key"]: node for node in graph["nodes"]}
        self.assertIn("#result-r129", nodes["result:R129"]["target"])
        self.assertIn("#question-u010", nodes["question:U010"]["target"])
        self.assertIn("#premise-b03", nodes["premise:B03"]["target"])
        self.assertIn("#obligation-n02", nodes["obligation:N02"]["target"])

    def test_duplicate_id_rejected(self):
        root = self.fixture()
        self.change_main(root, lambda data: data["results"].append(copy.deepcopy(data["results"][0])))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            mod.build(root)

    def test_unknown_parent_rejected(self):
        root = self.fixture()
        self.change_main(root, lambda data: data["results"][-1]["parent_result_ids"].append("R999"))
        with self.assertRaisesRegex(ValueError, "Dangling"):
            mod.build(root)

    def test_missing_premise_rejected(self):
        root = self.fixture()
        path = root / mod.PREMISES
        path.write_text(
            "\n".join(line for line in path.read_text(encoding="utf-8").splitlines()
                       if not line.startswith("| ") or "premise-a01" not in line),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "66 premise"):
            mod.build(root)

    def test_missing_pinned_source_rejected(self):
        root = self.fixture()
        main = json.loads((root / mod.MAIN).read_text(encoding="utf-8"))
        source = main["results"][-1]["managed_sources"][0]
        (root / source).unlink()
        with self.assertRaisesRegex(ValueError, "Missing pinned managed source"):
            mod.build(root)

    def test_source_drift_rejected_until_explicit_refresh(self):
        root = self.fixture()
        main = json.loads((root / mod.MAIN).read_text(encoding="utf-8"))
        source = main["results"][-1]["managed_sources"][0]
        target = root / source
        target.write_text(target.read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Source pin mismatch"):
            mod.build(root)
        mod.refresh_source_pins(root)
        _, _, provenance = mod.run(root, True)
        self.assertTrue(all(item["integrity"] == "PASS" for item in provenance["entries"]))

    def test_stale_index_detected(self):
        root = self.fixture()
        (root / mod.OUT / "INDEX.json").write_text("{}", encoding="utf-8")
        stale, _, _ = mod.run(root)
        self.assertIn(mod.OUT + "/INDEX.json", stale)

    def test_scientific_status_not_inferred(self):
        root = self.fixture()
        self.change_main(root, lambda data: data["results"][-1].update(status="REVIEW_REQUIRED_BY_HUMAN"))
        mod.run(root, True)
        data = json.loads((root / mod.MAIN).read_text(encoding="utf-8"))
        self.assertEqual(data["results"][-1]["status"], "REVIEW_REQUIRED_BY_HUMAN")
        self.assertIn("REVIEW_REQUIRED_BY_HUMAN", (root / mod.MAIN_MD).read_text(encoding="utf-8"))

    def test_r122_boundary_drift_detected(self):
        root = self.fixture()
        path = root / mod.MAIN_MD
        text = path.read_text(encoding="utf-8")
        old = "следующий интервал восстановления не считался"
        if old not in text:
            self.skipTest("Pinned R122 boundary wording is absent in this source revision")
        path.write_text(text.replace(old, "восстановление невозможно"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "R122"):
            mod.build(root)


if __name__ == "__main__":
    unittest.main()
