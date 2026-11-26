from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify import verify

class SoundAudit(unittest.TestCase):
    def test_data_model_and_inference(self):
        self.assertTrue(verify()['all_assertions_passed'])
