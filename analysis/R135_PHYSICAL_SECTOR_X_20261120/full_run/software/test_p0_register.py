import json
from pathlib import Path
import tempfile
import unittest

import p0_register as p0


class RegisterTests(unittest.TestCase):
    def setUp(self):
        self.area = tempfile.TemporaryDirectory()
        self.addCleanup(self.area.cleanup)
        self.root = Path(self.area.name)
        self.source = self.root / "inputs.json"
        self.records = p0.load(p0.HERE / "register_inputs.json")

    def build(self):
        self.source.write_text(json.dumps(self.records))
        return p0.build(self.source)

    def test_independent_repeat_and_tamper(self):
        data = self.build()
        dest = self.root / "frozen"
        first = p0.freeze(dest, data)
        self.assertEqual(first, p0.freeze(dest, self.build()))
        self.assertEqual(first, p0.verify(dest, self.build()))
        (dest / "model_register.json").write_text("{}")
        with self.assertRaises(ValueError):
            p0.freeze(dest, data)
        self.assertEqual((dest / "model_register.json").read_text(), "{}")

    def test_duplicate_point(self):
        self.records["points"].append(self.records["points"][0])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.build()

    def test_missing_model(self):
        self.records["points"][0]["model_id"] = "unknown"
        with self.assertRaisesRegex(ValueError, "Unknown point model"):
            self.build()

    def test_physical_point_uses_independent_inputs(self):
        point = dict(model_id="XA-graph", thermal_path="isolated_during_transition",
                     point_id="example-only", role="physical_candidate", origin="test")
        self.records["points"].append(point)
        with self.assertRaisesRegex(ValueError, "initial-history"):
            self.build()
        point.update(initial_history_id="test-history",
                     independent_parameters=[dict(name="scale",value=3,unit="MeV",source="test")])
        self.assertEqual(self.build()[p0.FILES[0]]["points"][-1],point)

    def test_locked_release_bytes(self):
        raw = b"test dataset"
        (self.root / "sample.bin").write_bytes(raw)
        release = self.records["data_releases"][-1]
        release.update(state="verified_files",files=[
            dict(path="sample.bin",bytes=len(raw),sha256=p0.sha(raw))])
        release.pop("missing")
        self.build()
        (self.root / "sample.bin").write_bytes(b"changed data")
        with self.assertRaisesRegex(ValueError,"SHA-256"):
            self.build()

    def test_refuses_nonfinite_measurement(self):
        self.records["data_releases"][0]["sigma"] = float("nan")
        with self.assertRaisesRegex(ValueError,"statistic"):
            self.build()

    def test_missing_observational_release(self):
        self.records["data_releases"].pop()
        with self.assertRaisesRegex(ValueError,"required observational dataset"):
            self.build()


if __name__ == "__main__":
    unittest.main()
