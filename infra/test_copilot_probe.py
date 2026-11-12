"""Exercise the control with a fake CLI; never invoke inference in CI."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PROBE = Path(__file__).with_name('copilot_probe.py')


class NativeControlTests(unittest.TestCase):
    def run_fake(self, body):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cli = root / 'copilot'
            cli.write_text('#!' + sys.executable + '\n' + body)
            cli.chmod(0o755)
            env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ['PATH'],
                       COPILOT_GITHUB_TOKEN='github_pat_FAKESECRET',
                       GH_TOKEN='unrelated', GITHUB_TOKEN='unrelated',
                       COPILOT_PROVIDER_BASE_URL='https://invalid.example',
                       GH_AW_MODEL_ROUTING='1')
            result = subprocess.run([sys.executable, str(PROBE)], cwd=root, env=env,
                                    capture_output=True, text=True, timeout=10)
            return result, json.loads((root / 'copilot-probe.json').read_text())

    def test_native_control_has_no_project_or_tools_or_overrides(self):
        r, d = self.run_fake('''import os,sys
from pathlib import Path
assert not list(Path.cwd().iterdir())
assert os.environ['COPILOT_GITHUB_TOKEN'] == 'github_pat_FAKESECRET'
assert not any(k in os.environ for k in ['GH_TOKEN','GITHUB_TOKEN','COPILOT_PROVIDER_BASE_URL','GH_AW_MODEL_ROUTING'])
assert sys.argv[sys.argv.index('--model')+1] == 'auto'
assert sys.argv[sys.argv.index('--max-ai-credits')+1] == '30'
assert sys.argv[sys.argv.index('--available-tools')+1] == '--deny-tool'
assert '--no-custom-instructions' in sys.argv
print('VM_LAB_COPILOT_OK')
''')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(d['status'], 'NATIVE_INFERENCE_PASS')
        self.assertEqual(d['tools'], [])

    def test_failed_output_does_not_publish_token_or_claim_success(self):
        r, d = self.run_fake("import os,sys\nprint(os.environ['COPILOT_GITHUB_TOKEN'],file=sys.stderr)\nsys.exit(1)\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(d['status'], 'NATIVE_INFERENCE_FAILED')
        self.assertNotIn('FAKESECRET', json.dumps(d) + r.stdout + r.stderr)
        self.assertIn('[REDACTED]', d['stderr'])


if __name__ == '__main__':
    unittest.main()
