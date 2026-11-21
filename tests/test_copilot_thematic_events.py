import copy
import base64
import importlib
import importlib.util
import io
import json
import sys
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch
import tempfile
import urllib.parse
import urllib.error
import urllib.request
import zipfile
from email.message import Message
from email.utils import format_datetime
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('thematic_events', ROOT / 'infra/copilot_thematic_events.py')
events = importlib.util.module_from_spec(spec)
spec.loader.exec_module(events)
MAIN, NEW, BLOB = '1' * 40, '2' * 40, '3' * 40
NOW = '2026-11-21T12:00:00Z'
LATER = '2026-11-21T12:05:00Z'


class FakeGitHub:
    repository = events.REPOSITORY

    def __init__(self):
        self.branches = [{'name': 'main', 'commit': {'sha': MAIN}}]
        self.pulls, self.closed_pulls, self.issues = [], [], []
        self.comments, self.reviews, self.commit_files = {}, {}, {}
        self.compares, self.blobs, self.gets, self.calls = {}, {}, {}, []
        self.trees = {}

    def pages(self, path, key=None):
        self.calls.append(('pages', path, key))
        if path == 'branches':
            return copy.deepcopy(self.branches)
        if path.startswith('pulls?state='):
            return copy.deepcopy(self.pulls + (self.closed_pulls if 'state=all' in path else []))
        if path.startswith('issues?'):
            return copy.deepcopy(self.issues)
        if path.startswith('issues/comments?') or path.startswith('pulls/comments?'):
            return copy.deepcopy(self.comments.get(path.split('?')[0], []))
        if path.startswith('commits/'):
            return copy.deepcopy(self.commit_files.get(path[8:], []))
        if path.startswith('commits?'):
            return [{'sha': NEW}]
        if path.startswith('compare/'):
            return [{'sha': sha} for sha in self.compares.get(path[8:], [NEW])]
        if path.endswith('/reviews'):
            return copy.deepcopy(self.reviews.get(path, []))
        if path.endswith('/comments'):
            return copy.deepcopy(self.comments.get(path, []))
        if path.endswith('/artifacts'):
            return [{'id': 5, 'name': events.SIGNAL_ARTIFACT, 'expired': False}]
        raise AssertionError('Unhandled fake endpoint: ' + path)

    def get(self, path):
        self.calls.append(('get', path))
        if path.startswith('compare/'):
            value = self.compares.get(path.split('?', 1)[0][8:], [NEW])
            if isinstance(value, dict):
                return copy.deepcopy(value)
            return {'status': 'ahead', 'total_commits': len(value), 'commits': [{'sha': sha} for sha in value]}
        return copy.deepcopy(self.gets[path])

    def tree(self, sha):
        return copy.deepcopy(self.trees[sha])

    def blob(self, sha):
        self.calls.append(('blob', sha))
        value = self.blobs[sha]
        if isinstance(value, Exception):
            raise value
        return value

    def request(self, method, path, data=None, raw=False):
        return self.archive


def issue(number=174, body='A partial observation; another calculation remains.', state='open'):
    return {'number': number, 'title': 'Open research question', 'body': body, 'state': state,
            'updated_at': NOW, 'html_url': f'https://github.com/{events.REPOSITORY}/issues/{number}'}


def comment(number=90, body='The measured sign changed.', **extra):
    return {'id': number, 'body': body, 'updated_at': NOW, 'user': {'login': 'IgorSabirov'},
            'html_url': f'https://github.com/{events.REPOSITORY}/issues/174#issuecomment-{number}', **extra}


def pull(number=185, branch='work/research', state='open'):
    return {'number': number, 'title': 'Research update', 'body': 'Partial control',
            'state': state, 'head': {'sha': NEW, 'ref': branch}, 'base': {'sha': MAIN},
            'html_url': f'https://github.com/{events.REPOSITORY}/pull/{number}', 'updated_at': NOW}


class Collection(unittest.TestCase):
    def test_initial_baseline_does_not_reanalyze_old_history(self):
        api = FakeGitHub()
        api.closed_pulls = [pull(state='closed')]
        api.reviews['pulls/185/reviews'] = [{'id': 7, 'body': 'Old review', 'state': 'COMMENTED',
                                          'submitted_at': '2026-11-01T00:00:00Z'}]
        first = events.collect(api, 'schedule', {}, MAIN, now=NOW)
        self.assertEqual(first['changes'], [])
        self.assertEqual(first['next_state']['started_at'], NOW)
        self.assertEqual(first['next_state']['branch_heads']['main'], MAIN)
        again = events.collect(api, 'schedule', {}, MAIN, state=first['next_state'], now=LATER)
        self.assertEqual(again['changes'], [])

    def test_partial_open_progress_and_close_are_both_evidence(self):
        api = FakeGitHub()
        first = events.collect(api, 'issues', {'action': 'edited', 'issue': issue()}, MAIN, now=NOW)
        self.assertEqual(len(first['changes']), 1)
        self.assertEqual(first['changes'][0]['state'], 'open')
        changed = events.collect(api, 'issues', {'action': 'edited', 'issue': issue(body='The first control now passes.')},
                                 MAIN, state=first['next_state'], now=LATER)
        self.assertEqual(len(changed['changes']), 1)
        closed = events.collect(api, 'issues', {'action': 'closed', 'issue': issue(state='closed')},
                                MAIN, state=changed['next_state'], now=LATER)
        self.assertEqual(closed['changes'][0]['state'], 'closed')

    def test_repeated_deliveries_and_stale_versions_do_not_reinvoke(self):
        api = FakeGitHub()
        old = {'action': 'edited', 'issue': issue(body='old')}
        newer = {'action': 'edited', 'issue': issue(body='new')}
        first = events.collect(api, 'issues', old, MAIN, now=NOW)
        second = events.collect(api, 'issues', newer, MAIN, state=first['next_state'], now=LATER)
        stale = events.collect(api, 'issues', old, MAIN, state=second['next_state'], now=LATER)
        self.assertEqual(stale['changes'], [])
        self.assertEqual(stale['next_state']['source_versions'], second['next_state']['source_versions'])
        self.assertEqual(stale['package_id'], '')

    def test_reopened_question_and_restored_text_are_new_versions(self):
        api = FakeGitHub()
        first_issue = issue(body='A')
        first = events.collect(api, 'issues', {'issue': first_issue}, MAIN, now=NOW)
        closed_issue = {**issue(body='B', state='closed'), 'updated_at': LATER}
        closed = events.collect(api, 'issues', {'issue': closed_issue}, MAIN, state=first['next_state'], now=LATER)
        third_time = '2026-11-21T12:10:00Z'
        reopened_issue = {**issue(body='A'), 'updated_at': third_time}
        reopened = events.collect(api, 'issues', {'issue': reopened_issue}, MAIN, state=closed['next_state'], now=third_time)
        self.assertEqual(len(reopened['changes']), 1)
        self.assertEqual(reopened['changes'][0]['state'], 'open')
        self.assertNotEqual(reopened['package_id'], first['package_id'])
        late = events.collect(api, 'issues', {'issue': first_issue}, MAIN, state=reopened['next_state'], now=third_time)
        self.assertEqual(late['changes'], [])

    def test_document_A_B_A_reversion_is_distinct_from_replayed_commit(self):
        api = FakeGitHub()
        commits = ['4' * 40, '5' * 40, '6' * 40]
        blob_b = '7' * 40
        api.blobs.update({BLOB: 'Assumption A', blob_b: 'Assumption B'})
        state, packages = None, []
        for sha, blob in zip(commits, [BLOB, blob_b, BLOB]):
            api.commit_files[sha] = [{'filename': 'analysis/assumption.md', 'status': 'modified', 'sha': blob}]
            found = events.collect(api, 'push', {'ref': 'refs/heads/work/research', 'after': sha}, MAIN, state=state, now=NOW)
            self.assertEqual(len(found['changes']), 1)
            packages.append(found['package_id'])
            state = found['next_state']
        self.assertEqual(len(set(packages)), 3)
        replay = events.collect(api, 'push', {'ref': 'refs/heads/work/research', 'after': commits[0]}, MAIN, state=state, now=LATER)
        self.assertEqual(replay['changes'], [])

    def test_force_push_behind_uses_final_trees_and_retains_deleted_text(self):
        api = FakeGitHub()
        api.branches[0]['commit']['sha'] = NEW
        first = events.collect(api, 'schedule', {}, MAIN, now=NOW)
        api.branches[0]['commit']['sha'] = MAIN
        api.compares[NEW + '...' + MAIN] = {'status': 'behind', 'total_commits': 0, 'commits': []}
        other_blob = '8' * 40
        api.trees[NEW] = [{'path': 'analysis/removed.md', 'type': 'blob', 'sha': BLOB},
                         {'path': 'analysis/changed.md', 'type': 'blob', 'sha': other_blob}]
        api.trees[MAIN] = [{'path': 'analysis/changed.md', 'type': 'blob', 'sha': BLOB}]
        api.blobs.update({BLOB: 'Old assumption', other_blob: 'New assumption'})
        event = {'ref': 'refs/heads/main', 'before': NEW, 'after': MAIN}
        found = events.collect(api, 'push', event, MAIN, state=first['next_state'], now=LATER)
        self.assertEqual(len(found['changes']), 2)
        deleted = next(x for x in found['changes'] if x['operation'] == 'removed')
        self.assertEqual(deleted['text'], 'Old assumption')
        self.assertIn(NEW, [ref['sha'] for ref in found['source_refs']])
        self.assertIn(MAIN, [ref['sha'] for ref in found['source_refs']])

    def test_push_and_reconciliation_deduplicate_identical_document(self):
        api = FakeGitHub()
        first = events.collect(api, 'schedule', {}, MAIN, now=NOW)
        api.branches[0]['commit']['sha'] = NEW
        api.blobs[BLOB] = '{"observation":"an unnamed partial control"}'
        api.commit_files[NEW] = [{'filename': 'research/schema.json', 'status': 'added', 'sha': BLOB}]
        event = {'ref': 'refs/heads/main', 'before': MAIN, 'after': NEW, 'commits': [{'id': NEW}]}
        changed = events.collect(api, 'push', event, MAIN, state=first['next_state'], now=LATER)
        self.assertEqual(len(changed['changes']), 1)
        self.assertEqual(changed['changes'][0]['text'], api.blobs[BLOB])
        api.commit_files[NEW][0]['status'] = 'modified'
        repeated = events.collect(api, 'push', event, MAIN, state=changed['next_state'], now=LATER)
        self.assertEqual(repeated['changes'], [])

    def test_github_token_comment_is_evidence_without_keyword_gate(self):
        api = FakeGitHub()
        first = events.collect(api, 'schedule', {}, MAIN, now=NOW)
        api.comments['issues/comments'] = [comment(body='2.291 versus 2.204', user={'login': 'github-actions[bot]'})]
        found = events.collect(api, 'schedule', {}, MAIN, state=first['next_state'], now=LATER)
        self.assertEqual([x['kind'] for x in found['changes']], ['issue_comment'])
        self.assertEqual(found['changes'][0]['text'], '2.291 versus 2.204')

    def test_review_edit_on_closed_pr_is_found_by_reconciliation(self):
        api = FakeGitHub()
        api.closed_pulls = [pull(state='closed')]
        api.reviews['pulls/185/reviews'] = [{'id': 7, 'body': 'Old review', 'state': 'COMMENTED',
                                          'submitted_at': '2026-11-01T00:00:00Z'}]
        first = events.collect(api, 'schedule', {}, MAIN, now=NOW)
        api.reviews['pulls/185/reviews'][0]['body'] = 'The published control has an error.'
        changed = events.collect(api, 'schedule', {}, MAIN, state=first['next_state'], now=LATER)
        self.assertEqual([x['id'] for x in changed['changes']], ['review:7'])

    def test_own_reports_ignored_but_binary_omissions_are_explicit(self):
        api = FakeGitHub()
        api.commit_files[NEW] = [
            {'filename': events.REPORT_PREFIX + 'REPORT.md', 'status': 'added', 'sha': BLOB},
            {'filename': 'results/array.npy', 'status': 'added', 'sha': BLOB},
        ]
        found = events.collect(api, 'push', {'ref': 'refs/heads/work/result', 'after': NEW}, MAIN, now=NOW)
        self.assertEqual(len(found['changes']), 1)
        self.assertFalse(found['coverage']['complete_content'])
        self.assertEqual(found['coverage']['omitted_contents'][0]['reason'], 'binary_or_raw_numeric_artifact')
        self.assertFalse(any(call[0] == 'blob' for call in api.calls))

    def test_deleted_assumption_retains_the_previous_text(self):
        api = FakeGitHub()
        api.blobs[BLOB] = 'The old calculation assumed an adiabatic history.'
        api.commit_files[NEW] = [{'filename': 'analysis/assumptions.md', 'status': 'removed', 'sha': BLOB}]
        found = events.collect(api, 'push', {'ref': 'refs/heads/work/research', 'after': NEW}, MAIN, now=NOW)
        self.assertEqual(found['changes'][0]['operation'], 'removed')
        self.assertEqual(found['changes'][0]['text'], api.blobs[BLOB])
        self.assertIn({'sha': NEW, 'label': 'work/research'}, found['source_refs'])

    def test_long_registry_document_is_not_omitted(self):
        api = FakeGitHub()
        api.blobs[BLOB] = 'A justified condition\n' * 60000
        api.commit_files[NEW] = [{'filename': 'analysis/RESULTS_REGISTER.md', 'status': 'modified', 'sha': BLOB}]
        found = events.collect(api, 'push', {'ref': 'refs/heads/main', 'after': NEW}, MAIN, now=NOW)
        self.assertTrue(found['coverage']['complete_content'])
        self.assertEqual(found['changes'][0]['text'], api.blobs[BLOB])

    def test_generated_comment_marker_requires_bot_author(self):
        self.assertTrue(events.own_comment(comment(body='<!-- vm-lab-thematic-report:x -->', user={'login': 'github-actions[bot]'})))
        self.assertFalse(events.own_comment(comment(body='<!-- vm-lab-thematic-report:x -->')))

    def test_pr_branch_code_is_never_executed(self):
        api = FakeGitHub()
        api.blobs[BLOB] = 'raise RuntimeError("Never execute this PR code")'
        api.commit_files[NEW] = [{'filename': 'infra/physical_solver.py', 'status': 'modified', 'sha': BLOB}]
        found = events.collect(api, 'pull_request', {'action': 'opened', 'pull_request': pull()}, MAIN, now=NOW)
        self.assertIn(api.blobs[BLOB], [x['text'] for x in found['changes']])

    def test_only_this_automation_implementation_is_excluded(self):
        api = FakeGitHub()
        api.blobs[BLOB] = 'Scientific solver change'
        api.commit_files[NEW] = [
            {'filename': 'infra/copilot_thematic_events.py', 'status': 'modified', 'sha': BLOB},
            {'filename': 'tests/test_copilot_thematic_events.py', 'status': 'modified', 'sha': BLOB},
            {'filename': 'infra/physical_solver.py', 'status': 'modified', 'sha': BLOB}]
        found = events.collect(api, 'push', {'ref': 'refs/heads/main', 'after': NEW}, MAIN, now=NOW)
        self.assertEqual([x['path'] for x in found['changes']], ['infra/physical_solver.py'])
        self.assertEqual(len([x for x in found['coverage']['ignored_generated_outputs']
                             if x['reason'] == 'thematic_automation_implementation']), 2)
        technical = events.collect(api, 'issues', {'issue': issue(number=186)}, MAIN, now=NOW)
        self.assertEqual(technical['changes'], [])
        self.assertTrue(events.own_branch('infra/copilot-thematic-storage-20261121'))
        self.assertFalse(events.own_branch('infra/physical-source-repair'))

    def test_api_error_retains_bounded_diagnostic_without_credentials(self):
        credential = 'github_pat_' + 'not_a_real_credential'
        error = events.APIError(422, '/git/blobs', 'Invalid request\n' + credential + ' Bearer example')
        self.assertEqual(error.status, 422)
        self.assertIn('Invalid request', str(error))
        self.assertNotIn(credential, str(error))
        self.assertNotIn('Bearer example', str(error))

    def test_signal_checks_origin_and_supports_pr_merge_sha(self):
        api = FakeGitHub()
        api.gets['actions/runs/17'] = {'repository': {'full_name': api.repository},
            'path': events.SIGNAL_PATH, 'event': 'pull_request', 'head_sha': NEW}
        event = {'repository': {'full_name': api.repository}, 'pull_request': pull(), 'action': 'edited'}
        metadata = {'repository': api.repository, 'run_id': '17', 'event_name': 'pull_request',
                    'source_sha': NEW, 'execution_sha': MAIN}
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as archive:
            archive.writestr('EVENT.json', json.dumps(event))
            archive.writestr('META.json', json.dumps(metadata))
        api.archive = output.getvalue()
        name, received = events.signal_event(api, 17)
        self.assertEqual(name, 'pull_request')
        self.assertEqual(received, event)
        api.gets['actions/runs/17']['path'] = '.github/workflows/other.yml'
        with self.assertRaisesRegex(ValueError, 'identity'):
            events.signal_event(api, 17)


class WorkflowBoundary(unittest.TestCase):
    def test_trusted_jobs_and_automatic_event_coverage(self):
        import yaml
        workflow = yaml.safe_load((ROOT / '.github/workflows/copilot-thematic.yml').read_text())
        trigger = workflow.get('on', workflow.get(True))
        self.assertEqual(trigger['issue_comment']['types'], ['created', 'edited', 'deleted'])
        self.assertIn('edited', trigger['issues']['types'])
        self.assertIn('schedule', trigger)
        self.assertEqual(workflow['concurrency']['queue'], 'max')
        self.assertFalse(workflow['concurrency']['cancel-in-progress'])
        for job in workflow['jobs'].values():
            for step in job['steps']:
                if step.get('uses', '').startswith('actions/checkout@'):
                    self.assertEqual(step['with']['ref'], '${{ github.sha }}')
                    self.assertFalse(step['with']['persist-credentials'])
        tokens = [step for job in workflow['jobs'].values() for step in job['steps']
                  if 'COPILOT_GITHUB_TOKEN' in step.get('env', {})]
        self.assertEqual(len(tokens), 1)
        self.assertIn("== 'generate'", tokens[0]['if'])
        self.assertIn('always()', workflow['jobs']['publish']['if'])
        signal = yaml.safe_load((ROOT / '.github/workflows/thematic-events.yml').read_text())
        self.assertIn('pull_request_review_comment', signal.get('on', signal.get(True)))
        self.assertNotIn('checkout', json.dumps(signal))
        self.assertNotIn('secrets.', json.dumps(signal))


class APIBoundary(unittest.TestCase):
    def test_collector_restores_a_split_monitor_without_losing_deduplication_state(self):
        with patch.object(sys, 'path', [str(ROOT / 'infra')] + sys.path):
            publisher = importlib.import_module('copilot_thematic_publish')
            state = {'schema': 'vm-lab-thematic-monitor-v1', 'repository': events.REPOSITORY,
                     'source_versions': {'issue:155': ['previous-content-version']}}
            original = json.dumps(state, ensure_ascii=False) + '\n'
            with patch.object(publisher, 'STORAGE_PART_BYTES', 40):
                physical = publisher.storage_files({events.STATE_PATH: original})
                api = FakeGitHub()
                api.gets['contents/' + events.STATE_PATH + '?ref=' + events.encoded(events.REPORT_BRANCH)] = {
                    'encoding': 'base64', 'content': base64.b64encode(physical[events.STATE_PATH].encode()).decode()}
                api.blobs = {publisher.blob_sha(text): text for text in physical.values()}
                self.assertEqual(events.load_state(api), state)

    def test_pagination_is_complete_and_missing_fields_fail(self):
        api = events.GitHub(events.REPOSITORY, token='')
        def page(path):
            number = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(path).query))['page']
            return {'items': list(range(100)) if number == '1' else [100]}
        api.get = page
        self.assertEqual(api.pages('example?state=all', key='items'), list(range(101)))
        api.get = lambda path: {}
        with self.assertRaisesRegex(ValueError, 'Missing paginated'):
            api.pages('example', key='items')

    def test_artifact_redirect_does_not_forward_github_token(self):
        req = urllib.request.Request('https://api.github.com/repos/a/b/actions/artifacts/1/zip',
                                     headers={'Authorization': 'Bearer synthetic-test-value'})
        redirected = events._SafeRedirect().redirect_request(req, None, 302, '', {}, 'https://storage.example/signed')
        self.assertIsNone(redirected.get_header('Authorization'))
        api = events.GitHub(events.REPOSITORY, token='')
        with self.assertRaisesRegex(ValueError, 'Only GitHub API'):
            api.get('https://storage.example/untrusted')


class RateRuntime:
    def __init__(self):
        self.epoch = 1_800_000_000.0
        self.elapsed = 0.0
        self.sleeps = []
        self.progress = []

    def clock(self):
        return self.epoch + self.elapsed

    def monotonic(self):
        return self.elapsed

    def sleep(self, seconds):
        if not 0 < seconds <= 60:
            raise AssertionError('Sleep must be a positive chunk of at most 60 seconds')
        self.sleeps.append(seconds)
        self.elapsed += seconds


def rate_error(status=403, message='API rate limit exceeded for installation', headers=None):
    response_headers = Message()
    for name, value in (headers or {}).items():
        response_headers[name] = str(value)
    return urllib.error.HTTPError('https://api.github.com/repos/example/repo/test', status, 'failure',
        response_headers, io.BytesIO(json.dumps({'message': message}).encode()))


class RateBackoff(unittest.TestCase):
    def client(self, outcomes, runtime=None):
        runtime = runtime or RateRuntime()
        api = events.GitHub(events.REPOSITORY, token='synthetic-rate-token',
            clock=runtime.clock, monotonic=runtime.monotonic, sleep=runtime.sleep,
            progress=runtime.progress.append)
        class Opener:
            def __init__(self):
                self.outcomes = list(outcomes)
                self.calls = []
            def open(self, request, timeout):
                self.calls.append({'method': request.get_method(), 'time': runtime.elapsed, 'data': request.data})
                if not self.outcomes:
                    raise AssertionError('Unexpected extra request')
                value = self.outcomes.pop(0)
                if isinstance(value, BaseException):
                    raise value
                return io.BytesIO(json.dumps(value).encode())
        api.opener = Opener()
        return api, runtime

    def test_primary_limit_waits_for_reset_in_short_chunks_without_secrets(self):
        runtime = RateRuntime()
        api, runtime = self.client([rate_error(headers={
            'X-RateLimit-Remaining': 0, 'X-RateLimit-Reset': runtime.epoch + 125,
            'private-header': 'synthetic-rate-token'}), {'ok': True}], runtime)
        self.assertEqual(api.get('contents/state?ref=branch&unused=synthetic-rate-token'), {'ok': True})
        self.assertEqual(runtime.sleeps, [60, 60, 6])
        self.assertEqual([call['time'] for call in api.opener.calls], [0, 126])
        log = json.dumps(runtime.progress)
        self.assertNotIn('synthetic-rate-token', log)
        self.assertNotIn('private-header', log)
        self.assertNotIn('?ref=', log)
        self.assertTrue(all(row['retry'] == 1 and row['max_retries'] == 2 for row in runtime.progress))

    def test_explicit_secondary_rejection_retries_same_mutation_after_retry_after(self):
        runtime = RateRuntime()
        api, runtime = self.client([rate_error(message='You have exceeded a secondary rate limit.',
            headers={'Retry-After': 125, 'X-RateLimit-Remaining': 900, 'X-RateLimit-Reset': runtime.epoch + 3600}),
            {'sha': MAIN}], runtime)
        result = api.request('POST', 'git/trees', {'tree': [], 'context': 'private-input'})
        self.assertEqual(result['sha'], MAIN)
        self.assertEqual(runtime.sleeps, [60, 60, 5])
        self.assertEqual(api.opener.calls[0]['data'], api.opener.calls[1]['data'])
        self.assertEqual(api.opener.calls[1]['time'], 125)
        self.assertNotIn('private-input', json.dumps(runtime.progress))

    def test_combined_server_deadlines_are_never_shortened(self):
        runtime = RateRuntime()
        api, runtime = self.client([rate_error(headers={'Retry-After': 30,
            'X-RateLimit-Remaining': 0, 'X-RateLimit-Reset': runtime.epoch + 120}), {}], runtime)
        api.get('contents/state')
        self.assertEqual(api.opener.calls[1]['time'], 121)

    def test_429_without_deadline_uses_finite_exponential_waits(self):
        api, runtime = self.client([rate_error(429, 'Too many requests'),
                                   rate_error(429, 'Too many requests'), {'ok': True}])
        self.assertEqual(api.get('contents/state'), {'ok': True})
        self.assertEqual(runtime.sleeps, [60, 60, 60])
        self.assertEqual([call['time'] for call in api.opener.calls], [0, 60, 180])

    def test_retry_exhaustion_keeps_original_diagnostic(self):
        api, runtime = self.client([rate_error() for _ in range(3)])
        with self.assertRaises(events.APIError) as failure:
            api.get('contents/state')
        self.assertEqual(len(api.opener.calls), 3)
        self.assertEqual(runtime.elapsed, 180)
        self.assertIn('API rate limit exceeded for installation', str(failure.exception))
        self.assertIn('retry budget exhausted after 2 waits', str(failure.exception))

    def test_permission_auth_validation_and_unknown_write_failures_do_not_retry(self):
        failures = [rate_error(403, 'Resource not accessible by integration',
                              {'X-RateLimit-Remaining': 0, 'X-RateLimit-Reset': 1_800_000_100, 'Retry-After': 60}),
                    rate_error(403, 'Forbidden'), rate_error(401, 'Bad credentials'),
                    rate_error(422, 'Validation failed'), rate_error(503, 'Unavailable'),
                    urllib.error.URLError('Connection ended before a response')]
        for failure in failures:
            with self.subTest(error=str(failure)):
                api, runtime = self.client([failure])
                with self.assertRaises((events.APIError, urllib.error.URLError)):
                    api.request('POST', 'git/refs', {'ref': 'refs/heads/example', 'sha': MAIN})
                self.assertEqual(len(api.opener.calls), 1)
                self.assertEqual(runtime.sleeps, [])
                self.assertEqual(runtime.progress, [])

    def test_over_budget_server_wait_fails_visibly_instead_of_shortening(self):
        api, runtime = self.client([rate_error(headers={'Retry-After': events.MAX_RATE_WAIT_SECONDS + 1})])
        with self.assertRaisesRegex(events.APIError, 'exceeds remaining retry wait budget'):
            api.get('contents/state')
        self.assertEqual(len(api.opener.calls), 1)
        self.assertEqual(runtime.sleeps, [])
        with patch.object(events, 'MAX_RATE_WAIT_SECONDS', 180):
            api, runtime = self.client([rate_error(headers={'Retry-After': 100}),
                                       rate_error(headers={'Retry-After': 100})])
            with self.assertRaisesRegex(events.APIError, 'exceeds remaining retry wait budget'):
                api.get('contents/state')
            self.assertEqual(runtime.elapsed, 100)
            self.assertEqual(len(api.opener.calls), 2)

    def test_http_date_retry_after_is_honored(self):
        runtime = RateRuntime()
        date = format_datetime(datetime.fromtimestamp(runtime.epoch + 90, timezone.utc), usegmt=True)
        api, runtime = self.client([rate_error(429, 'Too many requests', {'Retry-After': date}), {}], runtime)
        api.get('contents/state')
        self.assertEqual(runtime.elapsed, 90)

    def test_mutations_are_spaced_by_at_least_one_second(self):
        api, runtime = self.client([{}, {}, {}, {}, {}])
        for method in ['POST', 'GET', 'PATCH', 'PUT', 'DELETE']:
            api.request(method, 'git/refs', {} if method != 'GET' else None)
        self.assertEqual([call['time'] for call in api.opener.calls], [0, 0, 1, 2, 3])
        self.assertEqual(runtime.sleeps, [1, 1, 1])

    def test_default_progress_flushes_output(self):
        runtime = RateRuntime()
        api = events.GitHub(events.REPOSITORY, token='', clock=runtime.clock,
                            monotonic=runtime.monotonic, sleep=runtime.sleep)
        with patch('builtins.print') as output:
            api._wait_for_rate(runtime.epoch + 1, 'GET', '/repos/example/repo/state', 403, 0)
        self.assertTrue(output.call_args.kwargs['flush'])


class SourceEventPreservation(unittest.TestCase):
    def test_original_event_is_saved_before_load_state_can_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original = root / 'original-event.json'
            raw = ('{\r\n  "issue": {"number":174,"body":"Новый частичный результат"}\r\n}\r\n').encode('utf-8')
            original.write_bytes(raw)
            output = root / 'output'
            def fail_state(api):
                self.assertEqual((output / 'SOURCE_EVENT.json').read_bytes(), raw)
                raise events.APIError(403, '/contents/state', 'API rate limit exceeded for installation')
            environment = {'GITHUB_EVENT_PATH': str(original), 'GITHUB_EVENT_NAME': 'issues',
                           'GITHUB_REPOSITORY': events.REPOSITORY, 'GITHUB_SHA': MAIN}
            with patch.dict(events.os.environ, environment, clear=True), patch.object(sys, 'argv',
                    ['copilot_thematic_events.py', 'collect', '--output', str(output)]), \
                    patch.object(events, 'GitHub', return_value=object()), patch.object(events, 'load_state', side_effect=fail_state):
                with self.assertRaises(events.APIError):
                    events.main()
            self.assertEqual((output / 'SOURCE_EVENT.json').read_bytes(), raw)
            failure = json.loads((output / 'COLLECTION_FAILURE.json').read_text())
            self.assertEqual(failure['source_event'], 'SOURCE_EVENT.json')
            self.assertEqual(failure['event_name'], 'issues')
            self.assertIn('API rate limit exceeded for installation', failure['error'])


class RecoveryArtifact(unittest.TestCase):
    def test_missing_or_partial_artifact_uses_archived_data(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            saved, target = root / 'saved', root / 'target'
            target.mkdir()
            for setup in (lambda: None, lambda: saved.mkdir(), lambda: (saved / 'EVENTS.json').write_text('{}')):
                setup()
                result = events.restore_recovery_batches(saved, target)
                self.assertEqual(result['status'], 'ARTIFACT_UNAVAILABLE_USING_ARCHIVED_DATA')

    def test_complete_wrong_artifact_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            saved, target = root / 'saved', root / 'target'
            saved.mkdir(); target.mkdir()
            (saved / 'EVENTS.json').write_text('{}')
            (saved / 'CONTEXT.json').write_text('{"changed":true}')
            expected = hashlib.sha256(b'{}').hexdigest()
            (target / 'ATTEMPT.json').write_text(json.dumps({'events_sha256': expected, 'context_sha256': expected}))
            with self.assertRaisesRegex(ValueError, 'identity mismatch'):
                events.restore_recovery_batches(saved, target)


if __name__ == '__main__':
    unittest.main()
