import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("address_status", ROOT / "infra/copilot_address_status.py")
status = importlib.util.module_from_spec(spec)
spec.loader.exec_module(status)


class AddressStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registered, cls.issues = status.load_registry()

    def test_registered_registry_address_is_scientific(self):
        self.assertEqual(status.classify({"path": "analysis/NOW_PROJECT_INTEGRATION_20261119/REPORT.md"},
                                         self.registered, self.issues), "scientific")

    def test_registered_external_contract_is_scientific(self):
        self.assertEqual(status.classify({"path": "infra/external/contracts/PRIMAT.json"},
                                         self.registered, self.issues), "scientific")

    def test_unregistered_analysis_document_is_candidate(self):
        self.assertEqual(status.classify({"path": "analysis/NEW_REVIEW/REPORT.md"},
                                         self.registered, self.issues), "candidate")

    def test_r135_issue_is_scientific(self):
        self.assertEqual(status.classify({"kind": "issue", "number": 174},
                                         self.registered, self.issues), "scientific")

    def test_r135_tracker_is_scientific(self):
        self.assertEqual(status.classify({"kind": "issue", "number": 155},
                                         self.registered, self.issues), "scientific")

    def test_comment_in_scientific_issue_is_scientific(self):
        self.assertEqual(status.classify({"kind": "issue_comment", "number": 174},
                                         self.registered, self.issues), "scientific")

    def test_technical_workflow_is_excluded(self):
        self.assertEqual(status.classify({"path": ".github/workflows/copilot-thematic.yml"},
                                         self.registered, self.issues), "technical")

    def test_technical_test_is_excluded(self):
        self.assertEqual(status.classify({"path": "tests/test_copilot_thematic_events.py"},
                                         self.registered, self.issues), "technical")

    def test_unknown_root_is_excluded(self):
        self.assertEqual(status.classify({"path": "website/README.md"},
                                         self.registered, self.issues), "technical")

    def test_both_scientific_and_candidate_are_routed(self):
        events = {"changes": [
            {"id": "s", "path": "analysis/NOW_PROJECT_INTEGRATION_20261119/REPORT.md"},
            {"id": "c", "path": "analysis/NEW_REVIEW/REPORT.md"},
            {"id": "t", "path": ".github/workflows/copilot-thematic.yml"},
        ]}
        result = status.route_changes(events)
        self.assertEqual([x["id"] for x in result["changes"]], ["s", "c"])
        self.assertEqual([x["address_status"] for x in result["changes"]], ["scientific", "candidate"])
        self.assertEqual(result["address_routing"]["technical_skipped"], 1)


if __name__ == "__main__":
    unittest.main()
