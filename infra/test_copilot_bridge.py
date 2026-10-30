"""Offline regression tests: no credentials, network calls or AI quota needed."""

import json
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import copilot_bridge as bridge


class BridgeTests(unittest.TestCase):
    @patch.object(bridge, "cli_path", return_value="/cli")
    @patch.object(bridge, "request", return_value={"status": "OK"})
    def test_default_waits_without_deadline_and_explicit_deadline_is_opt_in(self, request, _cli):
        with patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(bridge.main(["ping"]), 0)
            self.assertIsNone(request.call_args.args[2])
            self.assertEqual(bridge.main(["--timeout", "30", "ping"]), 0)
            self.assertEqual(request.call_args.args[2], 30)

    def test_custom_config_directory_is_hardened(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"COPILOT_HOME": tmp}):
            self.assertEqual(bridge.config_dir(), Path(tmp))
            bridge.harden_config()
            self.assertEqual(Path(tmp).stat().st_mode & 0o777, 0o700)

    def test_new_requests_inherit_current_proxy_and_ignore_unrelated_tokens(self):
        with patch.dict(os.environ, {"HTTPS_PROXY": "http://localhost:1111", "GH_TOKEN": "unrelated"}):
            first = bridge.child_env()
        with patch.dict(os.environ, {"HTTPS_PROXY": "http://localhost:2222", "GH_TOKEN": "unrelated"}):
            second = bridge.child_env()
        self.assertEqual(first["HTTPS_PROXY"], "http://localhost:1111")
        self.assertEqual(second["HTTPS_PROXY"], "http://localhost:2222")
        self.assertNotIn("GH_TOKEN", second)

    def test_prompt_is_one_argument_not_shell_code(self):
        prompt = "literal $(touch /tmp/should-not-exist) `command`\nкириллица"
        argv = bridge.prompt_command("/cli", "/empty", prompt)
        self.assertEqual(argv[-2:], ["-p", prompt])
        self.assertNotIn("--allow-all", argv)
        self.assertIn("--disable-builtin-mcps", argv)
        self.assertIn("--no-custom-instructions", argv)
        self.assertIn("--disallow-temp-dir", argv)

    def test_captured_execution_does_not_use_a_shell(self):
        result = bridge.captured([os.sys.executable, "-c", "import sys; print(sys.argv[1])",
                                  "$(this_is_not_a_command)"], 5)
        self.assertEqual(result["returncode"], 0)
        self.assertEqual(result["stdout"].strip(), "$(this_is_not_a_command)")

    def test_timeout_stops_process(self):
        result = bridge.captured([os.sys.executable, "-c", "import time; time.sleep(10)"], 0.1)
        self.assertTrue(result["timed_out"])
        self.assertNotEqual(result["returncode"], 0)
        self.assertEqual(bridge.failure_status(result), "TIMEOUT")

    def test_policy_failure_is_not_reported_as_bad_login(self):
        result = {"stderr": 'Network access to "https://github.com:443" was blocked by policy.'}
        self.assertEqual(bridge.failure_status(result), "POLICY_BLOCKED")
        self.assertEqual(bridge.failure_status({"stderr": "401 Unauthorized"}), "AUTH_REQUIRED")
        self.assertEqual(bridge.failure_status({"stderr": "429 rate limit"}), "LIMIT_REACHED")
        self.assertEqual(bridge.failure_status({"stderr": "unknown failure"}), "REQUEST_FAILED")

    def test_tokens_and_proxy_credentials_redacted(self):
        for value in ("gho_private123", "github_pat_private123", "ghp_private123"):
            self.assertNotIn(value, bridge.redact(value))
        self.assertNotIn("password", bridge.redact("http://user:password@example.com:8080"))

    @patch.object(bridge, "checked_version", return_value=bridge.CLI_VERSION)
    def test_success_requires_exact_fresh_answer_and_real_exit_success(self, _version):
        base = {"returncode": 0, "timed_out": False, "elapsed_seconds": 0.1, "stderr": ""}
        observed_directories = []

        def fake_capture(argv, timeout):
            directory = Path(argv[argv.index("-C") + 1])
            self.assertTrue(directory.is_dir())
            self.assertEqual(list(directory.iterdir()), [])
            observed_directories.append(directory)
            return dict(base, stdout="FRESH\n")

        with patch.object(bridge, "captured", side_effect=fake_capture):
            result = bridge.request("/cli", "test", 5, expected="FRESH")
        self.assertEqual(result["status"], "OK")
        self.assertFalse(observed_directories[0].exists())
        with patch.object(bridge, "captured", return_value=dict(base, stdout="OLD")):
            self.assertEqual(bridge.request("/cli", "test", 5, "FRESH")["status"], "UNEXPECTED_RESPONSE")
        with patch.object(bridge, "captured", return_value=dict(base, stdout="")):
            self.assertEqual(bridge.request("/cli", "test", 5)["status"], "EMPTY_RESPONSE")
        with patch.object(bridge, "captured", return_value=dict(base, returncode=1, stdout="FRESH", stderr="failed")):
            self.assertEqual(bridge.request("/cli", "test", 5, "FRESH")["status"], "REQUEST_FAILED")

    @patch.object(bridge, "captured")
    def test_reject_credentials_and_oversized_prompt_before_transmission(self, capture):
        with self.assertRaisesRegex(ValueError, "POSSIBLE_CREDENTIAL"):
            bridge.request("/cli", "token=github_pat_private123", 5)
        with self.assertRaisesRegex(ValueError, "PROMPT_TOO_LARGE"):
            bridge.request("/cli", "x" * (bridge.MAX_PROMPT_BYTES + 1), 5)
        capture.assert_not_called()

    def test_harden_config_does_not_copy_credentials(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(Path, "home", return_value=Path(tmp)):
            config = Path(tmp) / ".copilot" / "config.json"
            bridge.harden_config()
            config.write_text('{"token":"private"}')
            config.chmod(0o644)
            bridge.harden_config()
            self.assertEqual(config.stat().st_mode & 0o777, 0o600)
            self.assertEqual(config.parent.stat().st_mode & 0o777, 0o700)
            self.assertEqual(json.loads(config.read_text()), {"token": "private"})

    def test_symlinked_credential_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(Path, "home", return_value=Path(tmp)):
            directory = Path(tmp) / ".copilot"
            directory.mkdir()
            target = Path(tmp) / "elsewhere"
            target.write_text("untouched")
            (directory / "config.json").symlink_to(target)
            with self.assertRaisesRegex(RuntimeError, "SYMLINKED"):
                bridge.harden_config()
            self.assertEqual(target.read_text(), "untouched")


if __name__ == "__main__":
    unittest.main()
