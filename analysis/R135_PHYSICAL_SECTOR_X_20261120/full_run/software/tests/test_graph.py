from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from r135.common import InputError, read_json
from r135.graph import Hamiltonian, canonical_ensemble, orbit, run, su3_map


def identity_map(labels=range(4)):
    return {"source": "diagnostic representation, not a proposed physical map", "representation": "SU3-fundamental",
            "operators": {str(s): {"real": np.eye(3).tolist(), "imag": np.zeros((3, 3)).tolist()} for s in labels}}


def law():
    return {"version": "diagnostic-1", "source": "R130 occupation conservation control", "eps": [1],
        "hamiltonian": {"source": "unit occupation-energy test", "unit": "MeV", "onsite": {"0": 0, "1": 1, "2": 1, "3": 2}},
        "calibration_ids": ["training"], "balance": {"kind": "isolated"}}


class GraphTests(unittest.TestCase):
    def test_named_variable_length_orbit_preserves_declared_energy(self):
        h = Hamiltonian(law()["hamiltonian"])
        trace = orbit([1, 2, 0, 2, 1, 0], 8)
        self.assertTrue(len({row["length"] for row in trace}) > 1)
        self.assertEqual({h(row["word"]) for row in trace}, {4})
        self.assertIn(3, {s for row in trace for s in row["word"]})

    def test_missing_three_is_reported_not_relabelled(self):
        config = {"law": law(), "state_map": identity_map(range(3)), "steps": 8,
            "preparations": [{"id": "new", "word": [1, 2, 0, 2, 1, 0], "role": "heldout", "source": "independent diagnostic state"}]}
        with tempfile.TemporaryDirectory() as t:
            result = run(config, {}, Path(t))
            self.assertEqual(result["evidence_status"], "OPEN_INPUT")
            self.assertIn(3, read_json(Path(t)/"state_map.json")["missing_labels"])

    def test_reject_leaked_preparation_and_nonunitary_map(self):
        config = {"law": law(), "state_map": identity_map(),
                  "preparations": [{"id": "training", "word": [1, 2], "role": "heldout", "source": "test"}]}
        with tempfile.TemporaryDirectory() as t, self.assertRaisesRegex(InputError, "overlap"):
            run(config, {}, Path(t))
        bad = identity_map()
        bad["operators"]["0"]["real"][0][0] = 2
        with self.assertRaises(InputError):
            su3_map(bad)

    def test_finite_partition_exact_two_state_control(self):
        h = Hamiltonian(law()["hamiltonian"])
        r = canonical_ensemble([[0], [1]], h, 1.)
        p = 1/(1+np.e)
        self.assertAlmostEqual(r["mean_energy_MeV"], p)
        self.assertAlmostEqual(r["heat_capacity"], p*(1-p))


if __name__ == "__main__":
    unittest.main()
