"""Integration checks: real local Git and the inspected existing worker."""
import hashlib
import csv
import io
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import signal
import sys
import tempfile
import time
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('bridge', HERE / 'github_bridge.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
from github_result_reader import read_github_result, UnconfirmedResult


class LocalBridge(module.Bridge):
    # Local file transport is allowed in tests only; production permits SSH.
    def git(self, *args, **kwargs):
        return super().git('-c', 'protocol.file.allow=always', *args, **kwargs)


class Integration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.work = self.root / 'work'
        self.state = self.root / 'private'
        self.seed = self.root / 'seed'
        self.remote = self.root / 'remote.git'
        for name in ('code', 'jobs', 'results', 'data/vm_lab_queue', 'data/vm_lab_sources', 'data/vm_lab_status'):
            (self.work / name).mkdir(parents=True, exist_ok=True)
        self.state.mkdir()
        self.seed.mkdir()
        self.cmd('git', 'init', '--bare', '--initial-branch=main', str(self.remote))
        self.cmd('git', 'init', '--initial-branch=main', str(self.seed))
        self.git_seed('config', 'user.name', 'Integration test')
        self.git_seed('config', 'user.email', 'test@example.invalid')
        self.git_seed('remote', 'add', 'origin', str(self.remote))
        self.write_source()
        self.commit = self.commit_source('Initial input')
        self.config = {'state': str(self.state), 'work': str(self.work),
                       'repository': 'test/fixture', 'remote': str(self.remote), 'ssh_command': '/usr/bin/false'}
        self.bridge = LocalBridge(self.config)
        self.worker = subprocess.Popen([sys.executable, str(HERE / 'fixtures/worker_v4.py'), str(self.work)],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        self.until(lambda: (self.work / 'worker-health.json').exists())

    def tearDown(self):
        self.worker.terminate()
        self.worker.communicate(timeout=10)
        self.temp.cleanup()

    def cmd(self, *args, cwd=None):
        result = subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)
        return result.stdout.strip()

    def git_seed(self, *args):
        return self.cmd('git', *args, cwd=self.seed)

    def write_source(self, fail=False):
        (self.seed / 'config.json').write_text('{"value": 21}\n')
        (self.seed / 'run.py').write_text(
            'import json, os\nfrom pathlib import Path\n'
            'cfg=json.loads(Path(__file__).with_name("config.json").read_text())\n'
            'Path("report").mkdir()\n'
            'answer={"answer":cfg["value"]*2, "commit":os.environ["VM_SOURCE_COMMIT"]}\n'
            'Path("report/answer.json").write_text(json.dumps(answer))\n'
            'Path("report/metrics.json").write_text(json.dumps(answer))\n'
            'Path("report/README.md").write_text("Detailed test report\\n")\n'
            'Path("report/data_manifest.json").write_text("{\\"selection\\":\\"all test metrics\\"}\\n")\n'
            'print("VM test stdout")\n' + ('raise RuntimeError("expected test failure")\n' if fail else '')
        )

    def commit_source(self, message):
        self.git_seed('add', '.')
        self.git_seed('commit', '-m', message)
        self.git_seed('push', 'origin', 'main')
        return self.git_seed('rev-parse', 'HEAD')

    def until(self, predicate):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.1)
        self.fail('Timed out waiting for local fixture')

    def request(self, rid, commit=None):
        (self.work / 'data/vm_lab_queue' / (rid + '.json')).write_text(
            json.dumps({'run_id': rid, 'commit': commit or self.commit}))

    def record(self, rid):
        return json.loads((self.state / 'runs' / (rid + '.json')).read_text())

    def published(self, rid):
        self.bridge.tick()
        return self.record(rid)['stage'] == 'published'

    def remote_json(self, path):
        return json.loads(self.cmd('git', '--git-dir=' + str(self.remote), 'show', 'main:' + path))

    def accepted_result(self, rid, source_commit=None):
        result_commit = self.cmd('git', '--git-dir=' + str(self.remote), 'rev-parse', 'main')
        def fetch(repository, path, ref):
            self.assertEqual(repository, 'test/fixture')
            self.assertEqual(ref, result_commit)
            return subprocess.run(['git', '--git-dir=' + str(self.remote), 'show', ref + ':' + path],
                                  check=True, capture_output=True).stdout
        return read_github_result(fetch, repository='test/fixture', result_commit=result_commit,
                                  run_id=rid, source_commit=source_commit or self.commit)

    def test_success_duplicate_and_bridge_restart(self):
        rid = 'github_smoke_success'
        self.request(rid)
        self.until(lambda: self.published(rid))
        received = self.accepted_result(rid)
        report = received['report']
        answer = json.loads(received['artifacts']['files/answer.json'])
        self.assertEqual(report['job']['exit_code'], 0)
        self.assertEqual(answer, {'answer': 42, 'commit': self.commit})
        self.assertEqual(report['export_errors'], [])
        report_before = json.dumps(report, sort_keys=True)
        remote_before = self.cmd('git', '--git-dir=' + str(self.remote), 'rev-parse', 'main')
        self.bridge = LocalBridge(self.config)
        self.bridge.tick()
        self.assertEqual(report_before, json.dumps(self.accepted_result(rid)['report'], sort_keys=True))
        self.assertEqual(remote_before, self.cmd('git', '--git-dir=' + str(self.remote), 'rev-parse', 'main'))

    def test_failed_computation_still_publishes(self):
        self.write_source(fail=True)
        commit = self.commit_source('Fail deliberately')
        rid = 'github_expected_failure'
        self.request(rid, commit)
        self.until(lambda: self.published(rid))
        received = self.accepted_result(rid, commit)
        report = received['report']
        self.assertFalse(received['execution_succeeded'])
        self.assertEqual(report['job']['state'], 'failed')
        self.assertEqual(report['job']['exit_code'], 1)
        log = received['artifacts']['output.log'].decode()
        self.assertIn('expected test failure', log)

    def test_push_conflict_retries_export_without_rerunning(self):
        rid = 'github_export_retry'
        self.request(rid)
        original = self.bridge.git
        injected = []
        def inject(*args, **kwargs):
            if args[0] == 'push' and not injected:
                injected.append(True)
                (self.seed / 'parallel.txt').write_text('Concurrent edit must survive\n')
                self.commit_source('Concurrent edit')
            return original(*args, **kwargs)
        self.bridge.git = inject
        self.until(lambda: (self.bridge.tick() or self.record(rid)['stage'] == 'exporting'))
        failed = self.record(rid)
        self.assertIn('last_error', failed)
        with self.assertRaises(UnconfirmedResult):
            self.accepted_result(rid)
        exported = failed['export_sha256'].copy()
        failed['retry_after'] = 0
        module.atomic_private(self.state / 'runs' / (rid + '.json'), failed)
        self.bridge = LocalBridge(self.config)
        self.until(lambda: self.published(rid))
        accepted = self.accepted_result(rid)
        for name, data in accepted['artifacts'].items():
            self.assertEqual(hashlib.sha256(data).hexdigest(), exported[name])
        self.assertIn('Concurrent edit', self.cmd('git', '--git-dir=' + str(self.remote), 'show', 'main:parallel.txt'))

    def test_shared_symlinks_and_hardlinks_are_refused(self):
        outside = self.root / 'private-value'
        outside.write_text('not-for-export')
        (self.work / 'data/link').symlink_to(outside)
        os.link(outside, self.work / 'data/hardlink')
        for name in ('link', 'hardlink'):
            with self.assertRaises((OSError, ValueError)):
                self.bridge.work.read('data/' + name)
        (self.work / 'data/redirect').symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(OSError):
            self.bridge.work.write('data/redirect/escape', b'bad')
        self.assertFalse((self.root / 'escape').exists())

    def test_invalid_request_does_not_block_valid_request(self):
        (self.work / 'data/vm_lab_queue/bad_request_json.json').write_text('[]')
        self.request('github_after_invalid')
        self.until(lambda: self.published('github_after_invalid'))
        self.assertEqual(self.record('bad_request_json')['stage'], 'rejected')

    def test_pinned_source_survives_newer_main(self):
        (self.seed / 'config.json').write_text('{"value": 999}\n')
        newer = self.commit_source('Change main after freezing test input')
        self.assertNotEqual(self.commit, newer)
        rid = 'github_frozen_source'
        self.request(rid, self.commit)
        self.until(lambda: self.published(rid))
        answer = json.loads(self.accepted_result(rid)['artifacts']['files/answer.json'])
        self.assertEqual(answer, {'answer': 42, 'commit': self.commit})

    def test_queued_cancellation_is_reported_through_git(self):
        rid = 'github_cancel_queued'
        os.kill(self.worker.pid, signal.SIGSTOP)
        try:
            self.request(rid)
            self.bridge.tick()
            (self.work / 'jobs' / rid / 'cancel').touch()
        finally:
            os.kill(self.worker.pid, signal.SIGCONT)
        self.until(lambda: self.published(rid))
        accepted = self.accepted_result(rid)
        self.assertEqual(accepted['report']['job']['state'], 'cancelled')
        self.assertFalse(accepted['execution_succeeded'])

    def test_clone_from_another_repository_is_rejected(self):
        wrong = {**self.config, 'remote': str(self.root / 'different.git')}
        with self.assertRaisesRegex(ValueError, 'another repository'):
            LocalBridge(wrong)

    def test_existing_vm_content_is_preserved(self):
        old_source = self.work / 'code/existing_project.py'
        old_result = self.work / 'results/existing_result.txt'
        old_source.write_text('existing code must stay\n')
        old_result.write_text('existing result must stay\n')
        self.request('github_preserve_vm')
        self.until(lambda: self.published('github_preserve_vm'))
        self.assertTrue(self.accepted_result('github_preserve_vm')['execution_succeeded'])
        self.assertEqual(old_source.read_text(), 'existing code must stay\n')
        self.assertEqual(old_result.read_text(), 'existing result must stay\n')

    def test_large_full_data_stays_on_vm_and_is_listed_in_github_report(self):
        with (self.seed / 'run.py').open('a') as handle:
            handle.write('Path("full").mkdir()\nwith open("full/large.bin", "wb") as f:\n    f.truncate(9*1024*1024)\n')
        commit = self.commit_source('Keep a large raw file only on VM')
        rid = 'github_retained_data'
        self.request(rid, commit)
        self.until(lambda: self.published(rid))
        result = self.accepted_result(rid, commit)
        self.assertEqual(result['report']['full_data'], [{'path': 'results/' + rid + '/full/large.bin', 'bytes': 9*1024*1024, 'type': 'file'}])
        self.assertFalse(any('large.bin' in path for path in result['artifacts']))
        tree = self.cmd('git', '--git-dir=' + str(self.remote), 'ls-tree', '-r', '--name-only', 'main')
        self.assertNotIn('large.bin', tree)
        self.assertEqual((self.work / 'results' / rid / 'full/large.bin').stat().st_size, 9*1024*1024)

    def test_large_log_has_explicit_head_tail_metadata(self):
        with (self.seed / 'run.py').open('a') as handle:
            handle.write('print("A"*(9*1024*1024))\nprint("END-OF-LARGE-LOG")\n')
        commit = self.commit_source('Produce a bounded export of a large log')
        rid = 'github_large_log'
        self.request(rid, commit)
        self.until(lambda: self.published(rid))
        result = self.accepted_result(rid, commit)
        metadata = result['report']['log_export']
        self.assertEqual(metadata['method'], 'head_tail')
        self.assertGreater(metadata['omitted_bytes'], 0)
        self.assertLess(len(result['artifacts']['output.log']), module.MAX_FILE)
        self.assertIn(b'END-OF-LARGE-LOG', result['artifacts']['output.log'])

    def test_real_medium_report_is_complete_and_full_file_is_not_published(self):
        for name in ('run.py', 'reporting.py', 'config.json'):
            (self.seed / name).write_bytes((HERE / 'fixtures' / ('demo_' + name)).read_bytes())
        commit = self.commit_source('Test the actual medium-report implementation')
        rid = 'github_real_medium_report'
        self.request(rid, commit)
        self.until(lambda: self.published(rid))
        result = self.accepted_result(rid, commit)
        artifacts = result['artifacts']
        metrics = json.loads(artifacts['files/metrics.json'])
        manifest = json.loads(artifacts['files/data_manifest.json'])
        distribution = json.loads(artifacts['files/distribution.json'])
        rows = list(csv.DictReader(io.StringIO(artifacts['files/series.csv'].decode())))
        self.assertEqual(metrics['actual'], 10)
        self.assertTrue(metrics['ok'])
        self.assertEqual(sum(int(row['count']) for row in rows), metrics['sample_count'])
        self.assertEqual(sum(row['count'] for row in distribution), metrics['sample_count'])
        self.assertTrue(all(check['passed'] for check in json.loads(artifacts['files/checks.json'])))
        self.assertEqual(manifest['full_files'][0]['bytes'], result['report']['full_data'][0]['bytes'])
        self.assertFalse(any('values.bin' in name for name in artifacts))
        self.assertEqual(result['report']['full_data_inventory_errors'], [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
