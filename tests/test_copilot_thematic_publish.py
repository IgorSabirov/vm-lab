import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'infra'))
import copilot_thematic_publish as p


class Memory:
    def __init__(self):
        self.files = {}
        self.commits = []

    def read(self, api, ref, path):
        return self.files.get(path)

    def state(self, api):
        return json.loads(self.files[p.STATE]) if p.STATE in self.files else {}

    def write(self, api, files, source, message):
        self.files.update(files)
        self.commits.append((copy.deepcopy(files), source, message))
        return 'c' * 40

    def archive(self, api, package):
        prefix = p.PREFIX + '/' + package + '/'
        return {name[len(prefix):]: value for name, value in self.files.items() if name.startswith(prefix)}


class Delivery(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        self.mem = Memory()
        self.package = 'a' * 64
        self.source = 'b' * 40
        self.events = {'package_id': self.package, 'source_sha': self.source,
                       'changes': [{'id': 'issue:174', 'text': 'Частичный результат'}],
                       'next_state': {'schema': 'vm-lab-thematic-monitor-v1',
                                      'source_versions': {'issue:174': 'x'}}}
        p.save(self.out / 'EVENTS.json', self.events)
        p.save(self.out / 'CONTEXT.json', {'package_id': self.package, 'source_sha': self.source})
        for name, function in [('file_at', self.mem.read), ('monitor', self.mem.state),
                               ('write_commit', self.mem.write), ('archived_files', self.mem.archive)]:
            started = patch.object(p, name, function)
            started.start()
            self.addCleanup(started.stop)

    def test_first_attempt_is_frozen_before_generation(self):
        result = p.reserve(None, self.out, '101', self.source)
        self.assertEqual(result['mode'], 'generate')
        prefix = p.PREFIX + '/' + self.package + '/'
        self.assertIn(prefix + 'CONTEXT.json', self.mem.files)
        attempt = json.loads(self.mem.files[prefix + 'ATTEMPT.json'])
        self.assertTrue(attempt['reserved_before_inference'])
        self.assertEqual(attempt['context_sha256'], p.digest((self.out / 'CONTEXT.json').read_bytes()))
        state = self.mem.state(None)
        self.assertEqual(state['attempts'][self.package]['status'], 'RESERVED')

    def test_repeated_unfinished_package_recovers_without_new_attempt(self):
        p.reserve(None, self.out, '101', self.source)
        writes = len(self.mem.commits)
        result = p.reserve(None, self.out, '102', self.source)
        self.assertEqual(result['mode'], 'recover')
        self.assertEqual(result['original_run_id'], '101')
        self.assertEqual(len(self.mem.commits), writes)

    def test_delivered_package_is_deduplicated(self):
        p.reserve(None, self.out, '101', self.source)
        state = self.mem.state(None)
        state['attempts'][self.package]['status'] = 'DELIVERED'
        self.mem.files[p.STATE] = p.encoded(state)
        self.assertEqual(p.reserve(None, self.out, '102', self.source)['mode'], 'skipped')

    def test_first_empty_scan_saves_baseline_without_inference(self):
        self.events['package_id'] = ''
        self.events['changes'] = []
        p.save(self.out / 'EVENTS.json', self.events)
        self.assertEqual(p.reserve(None, self.out, '101', self.source)['mode'], 'skipped')
        self.assertIn(p.STATE, self.mem.files)
        self.assertEqual(self.mem.state(None)['attempts'], {})

    def test_saved_context_cannot_be_replaced_before_publication(self):
        p.reserve(None, self.out, '101', self.source)
        (self.out / 'CONTEXT.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Frozen model input changed'):
            p.publish(None, self.out, 'IgorSabirov/vm-lab', '101')

    def test_raw_failure_is_published_and_never_claimed_complete(self):
        p.reserve(None, self.out, '101', self.source)
        raw = self.out / 'batches/0001/RAW_RESPONSE.txt'
        raw.parent.mkdir(parents=True)
        raw.write_text('Unparseable response with useful partial reasoning')
        with patch.object(p, 'ensure_pr', return_value={'number': 200, 'html_url': 'https://github.com/IgorSabirov/vm-lab/pull/200'}):
            result = p.publish(None, self.out, 'IgorSabirov/vm-lab', '101')
        self.assertFalse(result['complete'])
        prefix = p.PREFIX + '/' + self.package + '/'
        self.assertEqual(self.mem.files[prefix + 'batches/0001/RAW_RESPONSE.txt'], raw.read_text())
        self.assertEqual(self.mem.state(None)['attempts'][self.package]['status'], 'PUBLISHED_INCOMPLETE')
        self.assertIn('не завершена', self.mem.files[prefix + 'REPORT.md'])

    def test_expired_artifact_can_recover_raw_from_durable_branch(self):
        p.reserve(None, self.out, '101', self.source)
        prefix = p.PREFIX + '/' + self.package + '/'
        self.mem.files[prefix + 'batches/0001/RAW_RESPONSE.txt'] = 'Saved response'
        result = p.reserve(None, self.out, '102', self.source)
        self.assertEqual(result['mode'], 'recover')
        self.assertEqual((self.out / 'batches/0001/RAW_RESPONSE.txt').read_text(), 'Saved response')

    def test_collected_corpus_reserved_reviewed_published_and_deduplicated(self):
        import copilot_thematic_corpus as corpus
        import copilot_thematic_review as review
        from test_copilot_thematic_corpus import FakeGitHub, MAIN, snapshot, events
        from test_copilot_thematic_review import native, response
        event_package = events('Добавлен частичный научный результат.\n')
        event_package['next_state'] = {'schema': 'vm-lab-thematic-monitor-v1',
                                      'repository': 'IgorSabirov/vm-lab', 'source_versions': {}}
        context = corpus.prepare(FakeGitHub({MAIN: snapshot({
            'analysis/new/REGISTRY.json': '{"entries":[{"id":"new","status":"open"}]}',
        })}), event_package)
        p.save(self.out / 'EVENTS.json', event_package)
        p.save(self.out / 'CONTEXT.json', context)
        decision = p.reserve(None, self.out, '101', MAIN)
        self.assertEqual(decision['mode'], 'generate')
        def answer(prompt, timeout):
            payload = json.loads(prompt.split('EVIDENCE_JSON:\n', 1)[1])
            batch = next(b for b in context['batches'] if b['id'] == payload['batch_id'])
            return native(json.dumps(response(context, batch), ensure_ascii=False))
        with patch.object(review, 'invoke_native', side_effect=answer) as calls:
            self.assertTrue(review.generate(self.out)['complete'])
            with patch.object(p, 'ensure_pr', return_value={'number': 200, 'html_url': 'https://github.com/IgorSabirov/vm-lab/pull/200'}):
                delivery = p.publish(None, self.out, 'IgorSabirov/vm-lab', '101')
            self.assertTrue(delivery['complete'])
            self.assertEqual(calls.call_count, len(context['batches']))
            self.assertEqual(p.reserve(None, self.out, '102', MAIN)['mode'], 'skipped')
            self.assertEqual(calls.call_count, len(context['batches']))
        state = self.mem.state(None)
        self.assertEqual(state['attempts'][event_package['package_id']]['status'], 'DELIVERED')
        self.assertIn(p.PREFIX + '/' + event_package['package_id'] + '/DELIVERY.json', self.mem.files)

    def test_unknown_or_executable_model_files_are_not_publishable(self):
        (self.out / 'run.sh').write_text('touch /tmp/not-executed')
        files = p.collected_files(self.out)
        self.assertNotIn('run.sh', files)
        link = self.out / 'linked.json'
        link.symlink_to(self.out / 'CONTEXT.json')
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            p.collected_files(self.out)


class PublisherBoundary(unittest.TestCase):
    def test_invalid_paths_and_credentials_fail_before_network(self):
        for files in ({'analysis/RESULTS_REGISTER.json': '{}'},
                      {p.PREFIX + '/x/RAW_RESPONSE.txt': 'github_pat_' + 'abcdef'}):
            with self.assertRaises(ValueError):
                p.write_commit(None, files, 'a' * 40, 'invalid')


if __name__ == '__main__':
    unittest.main()
