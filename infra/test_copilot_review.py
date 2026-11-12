import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import copilot_review as review


class SixModelReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = review.build_context()

    def valid(self):
        evidence = [self.context['files'][0]['path']]
        return {'summary': 'Proposed comparison, not accepted physics.',
                'models': [dict(id=r['id'], contribution='Conditional contribution',
                    given='Declared foundation', obtained='Scoped result', gap='Missing joint law',
                    evidence=evidence) for r in self.context['profile']['models']],
                'connections': [dict(source='result:R126', target='result:R127',
                    relation='candidate_interface', claim='A proposed mapping',
                    missing='Source-specific correspondence', evidence=evidence)],
                'next_tests': [dict(question='What changes under the control?', observable='Continuation',
                    control='Declared alternative', discrimination='Preserved versus lost capability',
                    missing='Joint transition law', evidence=evidence)]}

    def test_pinned_evidence_and_all_six_roles_fit_bounded_prompt(self):
        self.assertEqual(len(self.context['profile']['models']), 6)
        self.assertLess(len(json.dumps(self.context, ensure_ascii=False, separators=(',', ':')).encode()), 110000)
        self.assertTrue(any(f['partial'] for f in self.context['files']))
        self.assertTrue(all(len(f['sha256']) == 64 for f in self.context['files']))
        self.assertEqual({s['id'] for s in self.context['sources']}, set(self.context['profile']['source_ids']))

    def test_all_models_and_known_graph_endpoints_required(self):
        valid = self.valid()
        self.assertEqual(review.validate_analysis(valid, self.context), valid)
        for mutation in ('omit_model', 'unknown_node', 'unknown_evidence', 'invent_status', 'unknown_relation'):
            d = copy.deepcopy(valid)
            if mutation == 'omit_model': d['models'].pop()
            if mutation == 'unknown_node': d['connections'][0]['target'] = 'result:R999'
            if mutation == 'unknown_evidence': d['models'][0]['evidence'] = ['/etc/passwd']
            if mutation == 'invent_status': d['models'][0]['status'] = 'PHYSICAL_PASS'
            if mutation == 'unknown_relation': d['connections'][0]['relation'] = 'proved'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                review.validate_analysis(d, self.context)

    def test_render_does_not_execute_or_accept_proposals(self):
        d = self.valid(); d['summary'] = '$(touch should-not-exist) is untrusted prose'
        c = {**self.context, 'executed_checks': [{'id': 'ccc_algebra', 'status': 'FAIL'}]}
        with patch('subprocess.run', side_effect=AssertionError('No execution in rendering')):
            output = review.markdown(d, c)
        self.assertIn('PROPOSED_FOR_REVIEW', output)
        self.assertIn('ccc_algebra: FAIL', output)
        self.assertIn(self.context['source_sha'], output)

    def test_paths_cannot_escape_repository(self):
        for path in ('../private', '/etc/passwd'):
            with self.assertRaises(ValueError): review.read(path)

    def test_metadata_pointer_is_not_claimed_as_supplied_content(self):
        d = self.valid()
        pointer = self.context['result_cards'][-1]['sources'][0]
        self.assertEqual(review.evidence_ledger(self.context)[pointer], 'REGISTRY_POINTER_ONLY')
        d['models'][0]['evidence'] = [pointer]
        review.validate_analysis(d, self.context)
        self.assertIn('текст модели не передавался', review.markdown(d, {**self.context, 'executed_checks': []}))
        d['models'][0]['evidence'] = ['analysis/UNSEEN_FILE.md']
        with self.assertRaises(ValueError): review.validate_analysis(d, self.context)

    def test_recovery_preserves_response_and_rejects_tampering_without_inference(self):
        c = {**self.context, 'executed_checks': []}
        d = self.valid()
        f = {'run_id': '123', 'source_sha': c['source_sha'], 'returncode': 0,
             'timed_out': False, 'elapsed_seconds': 1, 'error': 'old citation check',
             'stdout': json.dumps(d)}
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            review.dump(output / 'CONTEXT.json', c); review.dump(output / 'FAILURE.json', f)
            m = {'run_id': 123, 'source_sha': c['source_sha'],
                 'context_sha256': review.sha((output / 'CONTEXT.json').read_bytes()),
                 'failure_sha256': review.sha((output / 'FAILURE.json').read_bytes())}
            with patch.object(review, 'read', return_value=json.dumps(m).encode()), patch.object(
                    review, 'invoke_native', side_effect=AssertionError('No repeated inference')):
                review.recover(output)
                proposal = json.loads((output / 'native-proposal.json').read_text())
                self.assertEqual(proposal['analysis'], d)
                self.assertEqual(proposal['receipt']['recovery']['new_model_invocations'], 0)
                (output / 'FAILURE.json').write_text('{}')
                with self.assertRaisesRegex(ValueError, 'digest mismatch'): review.recover(output)

    def test_v2_declared_check_paths_are_uninspected_pointers(self):
        c = review.build_context(task='six-models-v2')
        paths = ['analysis/CCC_TL_REVIEW_20261112/ALGEBRA_CHECK.json',
                 'analysis/ANTHROPIC_BH_20261112/CHECKS.json']
        ledger = review.evidence_ledger(c)
        d = self.valid()
        for i, path in enumerate(paths):
            self.assertEqual(ledger[path], 'REGISTRY_POINTER_ONLY')
            d['models'][i]['evidence'] = [path]
        self.assertEqual(review.validate_analysis(d, c), d)
        rendered = review.markdown(d, {**c, 'executed_checks': []})
        self.assertEqual(rendered.count('текст модели не передавался'), 2)
        # Neither arbitrary prose nor unsafe typed values broaden the ledger.
        c['context_contract']['cards'].append({'source': review.RESULTS, 'data': {
            'description': 'analysis/NOT_SUPPLIED.json',
            'managed_sources': ['/etc/passwd', '../secret', {'path': 'analysis/FAKE.json'}]}})
        ledger = review.evidence_ledger(c)
        for path in ('analysis/NOT_SUPPLIED.json', '/etc/passwd', '../secret', 'analysis/FAKE.json'):
            self.assertNotIn(path, ledger)
        c['files'].append({'path': paths[0], 'partial': False})
        self.assertEqual(review.evidence_ledger(c)[paths[0]], 'SUPPLIED_CONTENT')

    def test_invalid_response_is_preserved_in_full_and_recovery_keeps_original_failure(self):
        response = 'invalid JSON ' + ('я' * 40000)
        receipt = {'returncode': 0, 'timed_out': False, 'elapsed_seconds': 1}
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            with self.assertRaises(SystemExit):
                review.finish(output, b'{}', self.context, receipt.copy(), response)
            original = (output / 'FAILURE.json').read_bytes()
            failure = json.loads(original)
            self.assertEqual(failure['stdout'], response)
            self.assertEqual(failure['response_bytes'], len(response.encode()))
            self.assertEqual(failure['response_sha256'], review.sha(response.encode()))
            self.assertEqual((output / 'RAW_RESPONSE.txt').read_text(), response)
            with self.assertRaises(SystemExit):
                review.finish(output, b'{}', self.context, {**receipt, 'recovery': {}}, response)
            self.assertEqual((output / 'FAILURE.json').read_bytes(), original)
            self.assertTrue((output / 'RECOVERY_FAILURE.json').exists())

    def test_v2_recovery_selects_manifest_and_checks_task_identity(self):
        c = {**review.build_context(task='six-models-v2'), 'executed_checks': []}
        d = self.valid()
        d['models'][0]['evidence'] = ['analysis/CCC_TL_REVIEW_20261112/ALGEBRA_CHECK.json']
        f = {'run_id': '456', 'source_sha': c['source_sha'], 'returncode': 0,
             'timed_out': False, 'elapsed_seconds': 1, 'error': 'old citation check',
             'stdout': json.dumps(d)}
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            review.dump(output / 'CONTEXT.json', c); review.dump(output / 'FAILURE.json', f)
            m = {'run_id': 456, 'source_sha': c['source_sha'],
                 'context_sha256': review.sha((output / 'CONTEXT.json').read_bytes()),
                 'failure_sha256': review.sha((output / 'FAILURE.json').read_bytes())}
            with patch.object(review, 'read', return_value=json.dumps(m).encode()) as read, patch.object(
                    review, 'invoke_native', side_effect=AssertionError('No repeated inference')):
                review.recover(output, 'six-models-v2')
                read.assert_called_once_with('infra/copilot/tasks/six-models-v2-recovery.json')
                proposal = json.loads((output / 'native-proposal.json').read_text())
                self.assertEqual(proposal['analysis'], d)
                self.assertEqual(proposal['receipt']['recovery']['new_model_invocations'], 0)
                with self.assertRaisesRegex(ValueError, 'identity'):
                    review.recover(output, 'six-models-v1')


if __name__ == '__main__':
    unittest.main()
