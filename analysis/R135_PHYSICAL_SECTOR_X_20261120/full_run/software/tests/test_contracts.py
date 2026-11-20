import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from r135.common import InputError, OpenInput, canonical_hash, read_json, write_json, sha256
from r135.contracts import HERE, execute, seal, source_inventory, validate_request, verify_result


def request(stage="P0", config=None):
    config = {} if config is None else config
    return {"schema": "r135-stage-request-v1", "stage": stage,
        "execution_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=HERE, text=True).strip(),
        "source_sha256": source_inventory()["sha256"], "mode": "validation",
        "key": {"claim_id": "XA_carrier", "model_id": "XA-graph", "point_id": "software-validation",
                "thermal_path": "isolated_during_transition"},
        "applicability": {"description": "finite software controls, no physical production"},
        "config": config, "config_sha256": canonical_hash(config), "inputs": []}


class ContractTests(unittest.TestCase):
    def test_p0_atomic_repeat_and_manifest_tamper(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t)
            req = request()
            write_json(p/"request.json", req)
            first = execute("P0", p/"request.json", p/"result")
            self.assertEqual(first["result"]["software_status"], "PASS")
            self.assertEqual(first, execute("P0", p/"request.json", p/"result"))
            reg = read_json(p/"result/model_register.json")
            self.assertEqual(reg["point_counts"], {"diagnostic": 48, "literature_benchmark": 4, "physical_candidate": 0})
            (p/"result/model_register.json").write_text("{}")
            with self.assertRaisesRegex(InputError, "modified"):
                verify_result(p/"result")

    def test_source_config_and_stage_bindings(self):
        req = request()
        for changed in (dict(req, stage="P1"), dict(req, config={"changed": True}),
                        dict(req, source_sha256="0"*64), dict(req, execution_sha="0"*40)):
            with self.assertRaises(InputError):
                validate_request(changed, "P0", Path("."))

    def test_configuration_cannot_relabel_the_thermal_branch(self):
        req = request(config={"thermal_path": "exchange_during_transition"})
        with self.assertRaisesRegex(InputError, "thermal path"):
            validate_request(req, "P0", Path("."))

    def test_frozen_inputs_reject_tamper_and_duplicates(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            write_json(base/"source.json", {"x": 1})
            write_json(base/"config.json", {})
            template = request()
            template["inputs"] = [{"name": "source", "path": "source.json"}]
            write_json(base/"template.json", template)
            frozen = seal("P0", base/"config.json", base/"template.json", base/"frozen.json")
            duplicate = copy.deepcopy(frozen)
            duplicate["inputs"] *= 2
            with self.assertRaisesRegex(InputError, "duplicate"):
                validate_request(duplicate, "P0", base)
            write_json(base/"source.json", {"x": 2})
            with self.assertRaisesRegex(InputError, "checksum"):
                validate_request(frozen, "P0", base)

    def test_diagnostic_never_becomes_physical_candidate(self):
        req = request()
        req["mode"] = "physical"
        req["key"]["point_id"] = "XA-T0-0-0"
        reg = HERE/"p0_snapshot/model_register.json"
        from r135.common import sha256
        req["inputs"] = [{"name": "model_register", "path": str(reg), "sha256": sha256(reg)}]
        with patch("r135.contracts.source_matches_commit", return_value=True):
            with self.assertRaisesRegex(OpenInput, "physical_candidate"):
                validate_request(req, "P0", HERE)

    def test_no_extra_output_or_json_ambiguity(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            write_json(base/"request.json", request())
            execute("P0", base/"request.json", base/"result")
            (base/"result/unlisted.txt").write_text("extra")
            with self.assertRaisesRegex(InputError, "unlisted"):
                verify_result(base/"result")
            (base/"duplicate.json").write_text('{"x": 1, "x": 2}')
            with self.assertRaises(InputError):
                read_json(base/"duplicate.json")

    def test_semantic_tamper_rejected_even_with_refreshed_manifest(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            write_json(base/"request.json", request())
            execute("P0", base/"request.json", base/"result")
            receipt_path = base/"result/EXECUTION_RECEIPT.json"
            receipt = read_json(receipt_path)
            receipt["key"]["point_id"] = "different-point"
            write_json(receipt_path, receipt)
            manifest = read_json(base/"result/MANIFEST.json")
            rec = next(x for x in manifest["files"] if x["path"] == receipt_path.name)
            rec.update(bytes=receipt_path.stat().st_size, sha256=sha256(receipt_path))
            write_json(base/"result/MANIFEST.json", manifest)
            with self.assertRaisesRegex(InputError, "semantic binding"):
                verify_result(base/"result")

    def test_p0_claim_model_pairing_is_registered(self):
        req = request()
        req["mode"] = "conditional"
        reg = HERE/"p0_snapshot/model_register.json"
        point = next(p for p in read_json(reg)["points"] if p["role"] == "literature_benchmark")
        req["key"].update(model_id=point["model_id"], point_id=point["point_id"], thermal_path=point["thermal_path"])
        req["inputs"] = [{"name": "model_register", "path": str(reg), "sha256": sha256(reg)}]
        with patch("r135.contracts.source_matches_commit", return_value=True):
            with self.assertRaisesRegex(InputError, "claim/model"):
                validate_request(req, "P0", HERE)

    def test_changed_input_during_calculation_downgrades_pass(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            payload = base/"input.json"
            write_json(payload, {"v": 1})
            req = request()
            req["inputs"] = [{"name": "measured", "path": str(payload), "sha256": sha256(payload)}]
            write_json(base/"request.json", req)
            from r135.contracts import _p0
            def changed(config, inputs, out):
                result = _p0(config, inputs, out)
                write_json(payload, {"v": 2})
                return result
            with patch("r135.contracts._p0", side_effect=changed):
                receipt = execute("P0", base/"request.json", base/"result")
            self.assertEqual(receipt["result"]["software_status"], "FAIL")
            self.assertTrue(any("input changed" in msg for msg in receipt["result"]["limitations"]))


if __name__ == "__main__":
    unittest.main()
