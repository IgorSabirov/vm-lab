"""Technical failure-path tests. No CA, systemd or production VM calls."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('reconnect_vm', Path(__file__).with_name('reconnect_vm.py'))
vm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vm)


class ReconnectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cfg = {'public_ip': '158.160.130.220', 'token': 'test-only-token',
                    'bind': '0.0.0.0', 'port': 443,
                    'tls_cert': str(self.root / 'fullchain.pem'),
                    'tls_key': str(self.root / 'privkey.pem'),
                    'resources': {'threads': 7}, 'work': '/retained/work',
                    'unknown_future_option': {'preserve': True}}
        self.config = self.root / 'server.json'
        self.config.write_text(json.dumps(self.cfg))
        self.config.chmod(0o640)
        for name in ('certbot', 'deploy_cert.py'):
            (self.root / name).touch()
        for attr, value in {'ROOT': self.root, 'CONFIG': self.config,
                            'CERTBOT': self.root / 'certbot',
                            'HOOK': self.root / 'deploy_cert.py'}.items():
            p = patch.object(vm, attr, value)
            p.start()
            self.addCleanup(p.stop)
        self.calls = []

    def runner(self, failure=None, timer_active=True, renew_state='inactive'):
        def fake(*args, **kwargs):
            self.calls.append((args, kwargs))
            if args[:2] == ('systemctl', 'is-active'):
                return subprocess.CompletedProcess(args, 0 if timer_active else 3)
            if args[:2] == ('systemctl', 'show'):
                return subprocess.CompletedProcess(args, 0, renew_state + '\n')
            if args[0] == str(vm.CERTBOT) and failure:
                raise failure
            return subprocess.CompletedProcess(args, 0)
        return fake

    def test_success_preserves_token_options_permissions_and_active_worker(self):
        before = self.config.stat()
        with patch.object(vm, 'public_ip', return_value='158.160.159.114'), \
             patch.object(vm, 'run', side_effect=self.runner()), \
             patch.object(vm, 'verify') as check, patch('builtins.print'):
            vm.reconnect('158.160.159.114')
        expected = dict(self.cfg, public_ip='158.160.159.114')
        self.assertEqual(json.loads(self.config.read_text()), expected)
        after = self.config.stat()
        self.assertEqual((before.st_mode, before.st_uid, before.st_gid),
                         (after.st_mode, after.st_uid, after.st_gid))
        check.assert_called_once_with('vm-158-160-159-114.sslip.io', 'test-only-token')
        commands = [a for a, _ in self.calls]
        self.assertIn(('systemctl', 'start', vm.WORKER), commands)
        self.assertFalse(any(vm.WORKER in a and ('restart' in a or 'stop' in a) for a in commands))
        issue = [(a, k) for a, k in self.calls if a[0] == str(vm.CERTBOT)]
        self.assertEqual(len(issue), 1)
        self.assertIn('--force-renewal', issue[0][0])
        self.assertEqual(issue[0][1]['timeout'], 240)
        self.assertEqual(commands[-1], ('systemctl', 'start', vm.TIMER))

    def test_ca_failure_or_timeout_preserves_config_and_timer_state(self):
        for error in (subprocess.CalledProcessError(1, ['certbot']),
                      subprocess.TimeoutExpired(['certbot'], 240)):
            for was_active in (True, False):
                with self.subTest(error=type(error).__name__, was_active=was_active):
                    self.calls.clear()
                    before = self.config.read_bytes()
                    with patch.object(vm, 'public_ip', return_value='158.160.159.114'), \
                         patch.object(vm, 'run', side_effect=self.runner(error, was_active)), \
                         patch('builtins.print'), self.assertRaises(type(error)):
                        vm.reconnect('158.160.159.114')
                    self.assertEqual(self.config.read_bytes(), before)
                    commands = [a for a, _ in self.calls]
                    self.assertEqual(commands.count(('systemctl', 'start', vm.TIMER)), int(was_active))
                    self.assertFalse(any(vm.WORKER in a or vm.API in a for a in commands))
                    self.assertEqual(sum(a[0] == str(vm.CERTBOT) for a in commands), 1)

    def test_wrong_ip_fails_before_any_command(self):
        with patch.object(vm, 'public_ip', return_value='158.160.159.114'), \
             patch.object(vm, 'run') as run, self.assertRaises(RuntimeError):
            vm.reconnect('158.160.130.220')
        run.assert_not_called()

    def test_existing_renewal_is_not_interrupted(self):
        with patch.object(vm, 'public_ip', return_value='158.160.159.114'), \
             patch.object(vm, 'run', side_effect=self.runner(renew_state='activating')), \
             self.assertRaises(RuntimeError):
            vm.reconnect('158.160.159.114')
        commands = [a for a, _ in self.calls]
        self.assertFalse(any(a[0] == str(vm.CERTBOT) for a in commands))
        self.assertEqual(commands[-1], ('systemctl', 'start', vm.TIMER))

    def test_same_ip_does_not_force_another_certificate(self):
        with patch.object(vm, 'public_ip', return_value='158.160.130.220'), \
             patch.object(vm, 'run', side_effect=self.runner()), \
             patch.object(vm, 'verify'), patch('builtins.print'):
            vm.reconnect('158.160.130.220')
        command = next(a for a, _ in self.calls if a[0] == str(vm.CERTBOT))
        self.assertIn('--keep-until-expiring', command)
        self.assertNotIn('--force-renewal', command)

    def test_failed_worker_check_never_prints_ready_and_restores_timer(self):
        with patch.object(vm, 'public_ip', return_value='158.160.159.114'), \
             patch.object(vm, 'run', side_effect=self.runner()), \
             patch.object(vm, 'verify', side_effect=RuntimeError('worker')), \
             patch('builtins.print') as output, self.assertRaises(RuntimeError):
            vm.reconnect('158.160.159.114')
        self.assertFalse(any('ГОТОВО' in str(c) for c in output.call_args_list))
        self.assertEqual(self.calls[-1][0], ('systemctl', 'start', vm.TIMER))


if __name__ == '__main__':
    unittest.main()
