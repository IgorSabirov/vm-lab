from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from r135.common import InputError, read_json, write_json
from r135.contracts import _commit, source_inventory
from r135.pipeline import ordered_nodes, run_pipeline


def node(name, stage="P0", inputs=None):
    return {"id": name, "stage": stage, "config": {}, "mode": "validation",
        "key": {"claim_id": "XA_carrier", "model_id": "XA-graph", "point_id": "control",
                "thermal_path": "isolated_during_transition"},
        "inputs": [] if inputs is None else inputs,
        "applicability": {"description": "isolated software control"}}


class PipelineTests(unittest.TestCase):
    def test_missing_law_blocks_only_its_consumers(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            nodes = [node("missing-law", "P2"), node("independent-register"),
                     node("dependent", "P4", [{"name": "graph_law", "from_node": "missing-law", "artifact": "graph_law.json"}])]
            plan = {"schema": "r135-pipeline-v1", "execution_sha": _commit(),
                    "source_sha256": source_inventory()["sha256"], "nodes": nodes}
            write_json(base/"plan.json", plan)
            report = run_pipeline(base/"plan.json", base/"run")
            self.assertEqual(report["nodes"]["missing-law"]["evidence_status"], "OPEN_INPUT")
            self.assertEqual(report["nodes"]["independent-register"]["software_status"], "PASS")
            self.assertEqual(report["nodes"]["dependent"]["software_status"], "NOT_EVALUATED")
            self.assertFalse(report["all_requested_software_completed"])
            before = read_json(base/"run/independent-register/EXECUTION_RECEIPT.json")
            run_pipeline(base/"plan.json", base/"run")
            self.assertEqual(before, read_json(base/"run/independent-register/EXECUTION_RECEIPT.json"))

    def test_cycle_and_unknown_parent_rejected(self):
        a = node("a", inputs=[{"from_node": "b"}])
        b = node("b", inputs=[{"from_node": "a"}])
        for nodes in ([a], [a, b], [node("a"), node("a")]):
            with self.assertRaises(InputError):
                ordered_nodes({"schema": "r135-pipeline-v1", "nodes": nodes})

    def test_audit_of_blocked_node_does_not_abort_independent_branch(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            bad = node("blocked", "P2", [{"name": "missing", "path": "absent.json", "sha256": "0"*64}])
            auditor = node("audit", "P10", [{"name": "blocked_manifest", "from_node": "blocked",
                                              "artifact": "MANIFEST.json", "for_audit": True}])
            plan = {"schema": "r135-pipeline-v1", "execution_sha": _commit(), "source_sha256": source_inventory()["sha256"],
                    "nodes": [bad, auditor, node("independent")]}
            write_json(base/"plan.json", plan)
            result = run_pipeline(base/"plan.json", base/"out")
            self.assertEqual(result["nodes"]["audit"]["software_status"], "NOT_EVALUATED")
            self.assertEqual(result["nodes"]["independent"]["software_status"], "PASS")


if __name__ == "__main__":
    unittest.main()
