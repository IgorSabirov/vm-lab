"""Run the offline publisher recovery tests; never contact GitHub."""
from pathlib import Path
import subprocess
import unittest


class PublicationTests(unittest.TestCase):
    def test_safe_recovery(self):
        subprocess.run(['node', '--test', str(Path(__file__).with_name('copilot_publish.test.cjs'))],
                       check=True, capture_output=True, text=True, timeout=15)
