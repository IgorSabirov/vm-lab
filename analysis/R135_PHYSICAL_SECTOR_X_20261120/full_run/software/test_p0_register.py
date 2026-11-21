import json
from pathlib import Path
import shutil
import tempfile
import unittest

import p0_register as p0


class RegisterTests(unittest.TestCase):
    def setUp(self):
        self.area = tempfile.TemporaryDirectory()
        self.addCleanup(self.area.cleanup)
        self.root = Path(self.area.name)
        self.source = self.root / "inputs.json"
        for directory in ("xb_reference", "planck_pr3"):
            shutil.copytree(p0.HERE / directory, self.root / directory)
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

    def test_dominance_control_is_separate_from_grid_and_fms(self):
        case = next(p for p in self.records["points"] if p["point_id"] == "XB-SU3-X1-DOMINANCE")
        model_register = self.build()["model_register.json"]
        self.assertIn(case, model_register["points"])
        self.assertEqual(model_register["point_counts"],
                         {"diagnostic": 49, "literature_benchmark": 4, "physical_candidate": 0})
        for change in (dict(X=False), dict(X=0.1), dict(xi_event=1), dict(R_post=0.001),
                       dict(role="physical_candidate"), dict(physical_launch_authorized=True)):
            with self.subTest(change=change):
                original = case.copy()
                case.update(change)
                with self.assertRaisesRegex(ValueError, "Dominance case"):
                    self.build()
                case.clear()
                case.update(original)

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
        with self.assertRaisesRegex(ValueError, "Missing physical point evidence"):
            self.build()
        for key, record in [
                ("history_file", dict(history_id="test-history", model_id="XA-graph",
                                      thermal_path=point["thermal_path"], epoch="unit test",
                                      initial_conditions={"temperature_MeV": 12})),
                ("calibration_file", dict(model_id="XA-graph", kind="independent_measurement",
                         independent_of_R135_BBN_CMB=True, source_locator="test only",
                         uncertainty_budget={"sigma_MeV": 0.1}, scale_MeV=3,
                         parameters=point["independent_parameters"]))]:
            path = self.root / (key + ".json")
            raw = p0.encoded(record)
            path.write_bytes(raw)
            point[key] = dict(path=path.name, bytes=len(raw), sha256=p0.sha(raw))
        self.assertEqual(self.build()[p0.FILES[0]]["point_counts"]["physical_candidate"], 1)
        point["initial_history_id"] = "wrong"
        with self.assertRaisesRegex(ValueError, "preparation mismatch"):
            self.build()

    def test_benchmark_cannot_be_promoted_or_reassigned(self):
        point = self.records["points"][-1]
        point["role"] = "physical_candidate"
        with self.assertRaisesRegex(ValueError, "benchmark coverage"):
            self.build()
        point["role"] = "literature_benchmark"
        point["R_post"] *= 2
        with self.assertRaisesRegex(ValueError, "Published preparation"):
            self.build()

    def test_planck_manifest_tamper(self):
        (self.root / "planck_pr3/nuisance.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            self.build()


    def test_locked_release_bytes(self):
        raw = b"test dataset"
        (self.root / "sample.bin").write_bytes(raw)
        release = self.records["data_releases"][-1]
        release.update(state="verified_files",files=[
            dict(path="sample.bin",bytes=len(raw),sha256=p0.sha(raw))])
        release.pop("missing", None)
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
