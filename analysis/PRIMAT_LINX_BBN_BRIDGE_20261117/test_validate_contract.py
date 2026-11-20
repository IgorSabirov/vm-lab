import copy
import unittest

from validate_contract import ContractError, canonical_sha256, validate_input


def fixture():
    history = {
        "time_s": [0.0, 1.0, 2.0],
        "scale_factor": [1.0, 1.1, 1.2],
        "H_s_inv": [1.0, 0.9, 0.8],
        "T_gamma_MeV": [1.0, 0.8, 0.6],
        "n_b_cm3": [10.0, 9.0, 8.0],
    }
    rates = {
        "network_id": "minimal-control",
        "species": ["n", "p", "d"],
        "reactions": [{
            "id": "npdg",
            "reactants": {"n": 1, "p": 1},
            "products": {"d": 1},
            "T9": [0.1, 1.0, 10.0],
            "values": [1.0, 2.0, 3.0],
        }],
        "temperature_unit": "T9",
        "rate_units": "declared-test-units",
        "interpolation": "linear",
        "extrapolation": "reject",
        "detailed_balance_policy": "declared",
    }
    return {
        "schema_version": "vm-lab-canonical-bbn-input-v1",
        "history": history,
        "rates": rates,
        "provenance": {
            "history_sha256": canonical_sha256(history),
            "rates_sha256": canonical_sha256(rates),
            "producer": "unit-test",
            "created_utc": "2026-11-17T00:00:00Z",
        },
    }


class BridgeContractTests(unittest.TestCase):
    def test_valid_minimal_payload(self):
        result = validate_input(fixture())
        self.assertTrue(result["valid"])
        self.assertEqual(result["history_points"], 3)
        self.assertEqual(result["species"], 3)
        self.assertEqual(result["reactions"], 1)

    def test_rejects_nonmonotonic_time(self):
        payload = fixture()
        payload["history"]["time_s"] = [0.0, 2.0, 1.0]
        payload["provenance"]["history_sha256"] = canonical_sha256(payload["history"])
        with self.assertRaisesRegex(ContractError, "strictly increasing"):
            validate_input(payload)

    def test_rejects_misaligned_history(self):
        payload = fixture()
        payload["history"]["H_s_inv"].pop()
        payload["provenance"]["history_sha256"] = canonical_sha256(payload["history"])
        with self.assertRaisesRegex(ContractError, "length"):
            validate_input(payload)

    def test_rejects_unknown_species(self):
        payload = fixture()
        payload["rates"]["reactions"][0]["products"] = {"He4": 1}
        payload["provenance"]["rates_sha256"] = canonical_sha256(payload["rates"])
        with self.assertRaisesRegex(ContractError, "unknown species"):
            validate_input(payload)

    def test_rejects_stale_hash(self):
        payload = fixture()
        payload["history"]["T_gamma_MeV"][0] = 1.01
        with self.assertRaisesRegex(ContractError, "SHA-256 mismatch"):
            validate_input(payload)

    def test_rejects_nonfinite_values(self):
        payload = fixture()
        payload["history"]["H_s_inv"][1] = float("nan")
        with self.assertRaisesRegex(ContractError, r"history\.H_s_inv\[1\]: value must be finite"):
            validate_input(payload)


if __name__ == "__main__":
    unittest.main()
