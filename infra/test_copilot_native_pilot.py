import unittest
from copilot_native_pilot import validate_report


class NativeReportTests(unittest.TestCase):
    def test_missing_evidence_and_secret_output_rejected(self):
        with self.assertRaises(ValueError):
            validate_report('unrelated text ' * 100)
        with self.assertRaises(ValueError):
            validate_report('R127 F02 N02 IsingCauset github_pat_NOTREAL ' * 30)

    def test_markdown_is_data_not_code_to_execute(self):
        text = 'R127 F02 N02 IsingCauset: candidate, not verified.\n' * 20
        self.assertEqual(validate_report(text), text)


if __name__ == '__main__':
    unittest.main()
