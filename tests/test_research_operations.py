import base64
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
from urllib.parse import urlsplit, parse_qs, unquote

spec = importlib.util.spec_from_file_location('operations', Path(__file__).resolve().parents[1] / 'tools/research_operations.py')
ops = importlib.util.module_from_spec(spec); spec.loader.exec_module(ops)


class Operations(unittest.TestCase):
    def setUp(self):
        self.config = {'repository': 'IgorSabirov/vm-lab', 'anchor_branch': 'anchor',
                       'control_path': 'CONTROL.json', 'ledger_path': 'LEDGER.json', 'pipeline_directory': 'pipeline'}
        self.control = {'active_branch': 'active', 'active_pr': 54, 'limits': {}, 'queue': {'status': 'PREPARATION_REQUIRED'},
                        'policy_version': 'no-daily-quota', 'controller_source_commit': 'c' * 40}
        self.files = {}
        self.put('CONTROL.json', self.control)
        self.put('LEDGER.json', {'policy_version': 'no-daily-quota', 'packages': [
            {'id': 'local', 'executor': 'local', 'status': 'FAILED'},
            {'id': 'vm', 'executor': 'vm', 'status': 'RESERVED'}]})
        self.put('SUMMARY.json', {'status': 'ENGINEERING_PASS', 'numerical_status': 'FAIL', 'scientific_acceptance': False})
        self.put('ARTIFACTS.json', {'files': {}})
        stage = {'id': 'S0', 'kind': 'import', 'status_field': 'numerical_status', 'expected_status': 'FAIL'}
        for key, path in [('summary', 'SUMMARY.json'), ('manifest', 'ARTIFACTS.json')]:
            stage[key] = {'path': path, 'sha256': hashlib.sha256(self.files[path]).hexdigest()}
        self.put('pipeline/PIPELINE.json', {'stages': [stage, {'id': 'S2', 'kind': 'theory', 'missing': ['physical law'], 'next': 'derive'}]})
        self.put('pipeline/RUN_REQUEST.json', {'execution_enabled': False})
        self.put('pipeline/CURRENT.json', {'request': 'completed'})
        self.requests = []
        self.gate = {'id': 3, 'name': 'merge-gate', 'status': 'completed', 'conclusion': 'success',
                     'app': {'id': 1, 'slug': 'github-actions'}}

    def put(self, path, value): self.files[path] = json.dumps(value).encode()

    def get(self, path):
        self.requests.append(path)
        u = urlsplit(path); q = parse_qs(u.query); p = unquote(u.path)
        if '/branches/' in p: return {'commit': {'sha': ('a' if p.endswith('/anchor') else 'b') * 40}}
        if '/contents/' in p:
            raw = self.files[p.split('/contents/')[1]]
            return {'encoding': 'base64', 'size': len(raw), 'content': base64.b64encode(raw).decode()}
        if '/actions/runs' in p:
            return {'workflow_runs': [{'id': 1, 'status': 'waiting', 'created_at': '2020-01-01'}] if q['status'] == ['waiting'] else []}
        if p.endswith('/pulls'):
            return [{'number': 54, 'head': {'sha': 'b' * 40, 'ref': 'active'}, 'base': {'ref': 'anchor'},
                     'title': 'Research pipeline: result', 'draft': True, 'html_url': 'https://example.test/54'}]
        if p.endswith('/check-runs'): return {'check_runs': [self.gate]}
        raise AssertionError(path)

    def test_readonly_view_keeps_failed_science_separate_and_queries_all_active_states(self):
        value = ops.collect(self.get, self.config)
        self.assertTrue(value['snapshot_consistent'])
        self.assertFalse(value['dispatch_authority'])
        self.assertEqual(value['evidence'][0]['science'], 'FAIL')
        self.assertFalse(value['evidence'][0]['scientific_acceptance'])
        self.assertFalse(value['evidence'][0]['raw_artifacts_reverified'])
        self.assertEqual([r['id'] for r in value['active_reservations']], ['vm'])
        self.assertEqual(value['active_actions'][0]['status'], 'waiting')
        self.assertEqual(len([p for p in self.requests if '/actions/runs?' in p]), len(ops.ACTIVE))
        self.assertTrue(all('?ref=' in p and len(p.rsplit('=', 1)[1]) == 40 for p in self.requests if '/contents/' in p))
        self.assertIn('FAIL', ops.render(value))

    def test_hash_mismatch_is_not_terminal_acceptance(self):
        self.files['SUMMARY.json'] += b' '
        value = ops.collect(self.get, self.config)
        self.assertFalse(value['snapshot_consistent'])
        self.assertIn('Receipt hash mismatch', value['blockers'][0])

    def test_branch_move_during_read_is_reported(self):
        counts = {}
        def moving(path):
            counts[path] = counts.get(path, 0) + 1
            if path.endswith('/branches/anchor') and counts[path] > 1:
                return {'commit': {'sha': 'd' * 40}}
            return self.get(path)
        self.assertFalse(ops.collect(moving, self.config)['snapshot_consistent'])

    def test_policy_divergence_is_visible(self):
        def different(path):
            if '/contents/CONTROL.json?ref=' + 'b' * 40 in path:
                raw = json.dumps({**self.control, 'policy_version': 'old'}).encode()
                return {'encoding': 'base64', 'content': base64.b64encode(raw).decode()}
            return self.get(path)
        self.assertIn('CONTROL mismatch: policy_version', ops.collect(different, self.config)['blockers'])

    def test_new_pending_check_supersedes_old_green(self):
        pending = {**self.gate, 'id': 4, 'status': 'queued', 'conclusion': None}
        self.assertEqual(ops.check_state([pending, self.gate]), 'RUNNING')
        self.assertEqual(ops.check_state([{**pending, 'status': 'completed', 'conclusion': 'failure'}, self.gate]), 'BLOCKED')
        self.assertEqual(ops.check_state([self.gate, {**self.gate, 'id': 5, 'name': 'optional', 'conclusion': 'skipped'}]), 'TECHNICAL_PASS')
        self.assertEqual(ops.check_state([{**self.gate, 'app': {'id': 9, 'slug': 'other'}}]), 'NOT_VERIFIED')

    def test_pagination_never_silently_drops_second_page(self):
        calls = []
        def paged(path):
            calls.append(path); return {'rows': list(range(100)) if len(calls) == 1 else [100]}
        self.assertEqual(len(list(ops.pages(paged, '/test?state=open', 'rows'))), 101)
        self.assertIn('&per_page=100&page=2', calls[-1])

    def test_incomplete_bytes_and_unsafe_paths_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            ops.blob(self.get, '', '../secret', 'a' * 40)
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            ops.blob(lambda _: {'encoding': 'base64', 'content': '', 'size': 1}, '', 'x', 'a' * 40)


if __name__ == '__main__': unittest.main()
