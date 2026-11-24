import json
from pathlib import Path
import sys
import unittest

PAIRED = Path(__file__).resolve().parents[1] / "paired"
sys.path.insert(0, str(PAIRED))
from repeat_boxes import audit


class RepeatBoxes(unittest.TestCase):
    def test_frozen_comparison(self):
        result = audit()
        self.assertEqual(result, json.loads((PAIRED / "repeat_boxes.json").read_text()))
        self.assertEqual(result["counts_all_conditions"]["known_same_length"], 1)
        self.assertEqual(result["counts_with_D2"]["missing_one_or_both_lengths"], 15)
        for grid in result["paired_frequency_grid_candidates"].values():
            self.assertLess(grid["42.5"]["relative_difference_ppm"], 3)
        self.assertIsNone(result["observed_width_ratio"])
