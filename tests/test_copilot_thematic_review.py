import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'infra'))
import copilot_thematic_corpus as corpus
import copilot_thematic_review as review


SOURCE = 'a' * 40
PACKAGE = 'b' * 64
REPOSITORY = 'IgorSabirov/vm-lab'


def document(path, text):
    blob = corpus.git_blob_sha(text)
    return {'id': 'doc:' + blob, 'path': path, 'source_sha': SOURCE,
            'git_blob_sha': blob, 'text': text, 'sha256': corpus.sha256(text),
            'size_bytes': len(text.encode())}


def fixture(batch_count=1):
    shared = document('analysis/COMMON_MODEL.md', 'Общий контекст всех масштабов.\n')
    documents = [document(f'analysis/SCHEMA_{i}.md',
                         f'Схема {i}.\nНужен профиль напряжения и абсолютная энтальпия.\n')
                 for i in range(batch_count)]
    event = {'id': 'issue:174@abc', 'source_event_id': 'issue:174',
             'url': 'https://github.com/' + REPOSITORY + '/issues/174',
             'revision': '2026-11-21T12:00:00Z', 'kind': 'issue',
             'text': 'Получен контроль стенки. Физическое напряжение пока отсутствует.\n'}
    event.update(sha256=corpus.sha256(event['text']), size_bytes=len(event['text'].encode()))
    event_parts = corpus.segments(event, 10000, event=True)
    context = {'schema': corpus.SCHEMA, 'repository': REPOSITORY, 'source_sha': SOURCE,
               'package_id': PACKAGE, 'shared_documents': [shared],
               'documents': [{k: v for k, v in d.items() if k != 'text'} for d in [shared] + documents],
               'events': [{k: v for k, v in event.items() if k != 'text'}],
               'batches': [{'id': f'{i + 1:04d}', 'events': event_parts,
                            'documents': corpus.segments(d, 10000)} for i, d in enumerate(documents)],
               'coverage': {'planned_model_calls': batch_count, 'semantic_prefilter': False},
               'max_payload_bytes': 560000, 'existing_graph': {'nodes': [], 'edges': []}}
    corpus.validate_context(context)
    return context


def response(context, batch, findings=False):
    sources = review.sources_for(context, batch)
    result = {'schema': review.SCHEMA, 'package_id': context['package_id'], 'batch_id': batch['id'],
              'review_complete': True,
              'reviewed_event_ids': [s['id'] for s in sources.values() if s['source_kind'] == 'event'],
              'reviewed_document_ids': [s['id'] for s in sources.values() if s['source_kind'] == 'document'],
              'summary': 'Обновление даёт контроль, но не физический источник.',
              'findings': [], 'limitations': []}
    if findings:
        event, doc = batch['events'][0], batch['documents'][0]
        result['findings'] = [{
            'id': 'F1', 'kind': 'candidate_dependency', 'title': 'Вход в источник GW',
            'claim': 'Проверка стенки ещё не определяет напряжение.',
            'source': {'label': 'Стенка', 'scale': 'Микрофизика'},
            'target': {'label': 'Источник GW', 'scale': 'Космология'},
            'change_ids': [event['event_id']],
            'citations': [{'source_id': event['id'], 'start_line': 1, 'end_line': 1,
                           'quote': 'Физическое напряжение пока отсутствует.'},
                          {'source_id': doc['id'], 'start_line': 2, 'end_line': 2,
                           'quote': 'Нужен профиль напряжения и абсолютная энтальпия.'}],
            'consequence': 'Расчёт GW требует согласованного профиля.',
            'missing_input': 'Абсолютная энтальпия обеих фаз.',
            'question': 'Выполняется ли баланс энергии на одной подготовке?',
            'test': {'observable': 'Баланс энергии', 'control': 'Статический профиль',
                     'discriminator': 'Член излучения учитывается один раз.'},
            'statistics': None}]
    return result


def native(text):
    return {'stdout': text, 'stderr': '', 'returncode': 0, 'timed_out': False,
            'model_selector': 'native auto', 'tools': [], 'elapsed_seconds': 1.0,
            'repository_content_sent': False, 'max_ai_credits': 30}


class ThematicReview(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        env = patch.dict(review.os.environ, {'GITHUB_RUN_ID': '101'})
        env.start()
        self.addCleanup(env.stop)

    def prepare(self, count=1):
        self.context = fixture(count)
        review.save(self.out / 'CONTEXT.json', self.context)
        review.save(self.out / 'EVENTS.json', {'package_id': PACKAGE, 'source_sha': SOURCE})
        review.save(self.out / 'ATTEMPT.json', {
            'schema': 'vm-lab-thematic-attempt-v1', 'package_id': PACKAGE, 'source_sha': SOURCE,
            'run_id': '101', 'reserved_before_inference': True,
            'context_sha256': review.digest((self.out / 'CONTEXT.json').read_bytes()),
            'events_sha256': review.digest((self.out / 'EVENTS.json').read_bytes())})

    def good_native(self, prompt, timeout):
        payload = json.loads(prompt.split('EVIDENCE_JSON:\n', 1)[1])
        batch = next(b for b in self.context['batches'] if b['id'] == payload['batch_id'])
        folder = self.out / 'batches' / batch['id']
        self.assertEqual(json.loads((folder / 'RECEIPT.json').read_text())['status'], 'ATTEMPTING')
        self.assertEqual(payload['events'], batch['events'])
        self.assertEqual(payload['documents'], batch['documents'])
        self.assertEqual(payload['shared_documents'], self.context['shared_documents'])
        return native(json.dumps(response(self.context, batch), ensure_ascii=False))

    def test_all_batches_and_zero_findings_are_complete_without_duplicate_calls(self):
        self.prepare(2)
        with patch.object(review, 'invoke_native', side_effect=self.good_native) as call:
            result = review.generate(self.out)
            self.assertTrue(result['complete'])
            self.assertEqual(result['findings'], 0)
            self.assertEqual(call.call_count, 2)
            self.assertEqual(result['actual_native_calls'], 2)
            self.assertEqual(result['native_elapsed_seconds'], 2.0)
            self.assertEqual(result['actual_charge'], 'NOT_REPORTED')
            saved = json.loads((self.out / 'batches/0001/RECEIPT.json').read_text())
            self.assertTrue(saved['native']['repository_content_sent'])
            self.assertEqual(saved['native']['input_package_id'], PACKAGE)
            self.assertEqual(saved['native']['input_source_sha'], SOURCE)
            self.assertEqual(saved['native']['supplied_prompt_bytes'],
                             len((self.out / 'batches/0001/PROMPT.txt').read_bytes()))
            self.assertTrue(review.generate(self.out)['complete'])
            self.assertTrue(review.recover(self.out)['complete'])
            review.validate_saved(self.out)
            self.assertEqual(call.call_count, 2)

    def test_raw_malformed_reply_survives_and_is_never_inferred_again(self):
        self.prepare()
        bad = 'Это не JSON. Полный ответ должен сохраниться.\nХвост ответа.'
        with patch.object(review, 'invoke_native', return_value=native(bad)) as call:
            self.assertFalse(review.generate(self.out)['complete'])
            self.assertEqual((self.out / 'batches/0001/RAW_RESPONSE.txt').read_text(), bad)
            self.assertFalse(review.generate(self.out)['complete'])
            self.assertFalse(review.recover(self.out)['complete'])
            self.assertEqual(call.call_count, 1)
        with self.assertRaisesRegex(ValueError, 'every expected batch'):
            review.validate_saved(self.out)

    def test_invalid_returned_answer_does_not_skip_remaining_corpus(self):
        self.prepare(2)
        def replies(prompt, timeout):
            supplied = json.loads(prompt.split('EVIDENCE_JSON:\n', 1)[1])
            if supplied['batch_id'] == '0001':
                return native('Malformed but durably saved first answer')
            return self.good_native(prompt, timeout)
        with patch.object(review, 'invoke_native', side_effect=replies) as call:
            result = review.generate(self.out)
            self.assertFalse(result['complete'])
            self.assertEqual(call.call_count, 2)
            self.assertEqual(result['batches'][1]['status'], 'VALIDATED')
            self.assertFalse(review.recover(self.out)['complete'])
            self.assertEqual(call.call_count, 2)

    def test_model_declared_partial_review_does_not_skip_later_batches(self):
        self.prepare(2)
        def replies(prompt, timeout):
            supplied = json.loads(prompt.split('EVIDENCE_JSON:\n', 1)[1])
            batch = next(b for b in self.context['batches'] if b['id'] == supplied['batch_id'])
            result = response(self.context, batch)
            if batch['id'] == '0001':
                result.update(review_complete=False, limitations=['Первую схему не удалось разобрать.'])
            return native(json.dumps(result))
        with patch.object(review, 'invoke_native', side_effect=replies) as call:
            result = review.generate(self.out)
            self.assertFalse(result['complete'])
            self.assertEqual(call.call_count, 2)
            self.assertEqual(result['batches'][0]['status'], 'REVIEW_INCOMPLETE')
            self.assertEqual(result['batches'][1]['status'], 'VALIDATED')

    def test_validation_bug_can_be_recovered_from_original_raw_without_inference(self):
        self.prepare()
        raw = json.dumps(response(self.context, self.context['batches'][0]), ensure_ascii=False)
        with patch.object(review, 'invoke_native', return_value=native(raw)) as call:
            with patch.object(review, 'validate_response', side_effect=ValueError('validator defect')):
                self.assertFalse(review.generate(self.out)['complete'])
            self.assertTrue(review.recover(self.out)['complete'])
            self.assertEqual(call.call_count, 1)
        self.assertEqual((self.out / 'batches/0001/RAW_RESPONSE.txt').read_text(), raw)
        saved = json.loads((self.out / 'batches/0001/RECEIPT.json').read_text())
        self.assertEqual(saved['initial_validation_error'], 'validator defect')
        review.validate_saved(self.out)

    def test_finding_requires_exact_text_at_declared_lines_and_both_sides(self):
        self.prepare()
        batch = self.context['batches'][0]
        good = response(self.context, batch, findings=True)
        review.validate_response(good, self.context, batch)
        bad = copy.deepcopy(good)
        bad['findings'][0]['citations'][1]['quote'] = 'Энтальпия уже получена.'
        with self.assertRaisesRegex(ValueError, 'not exact'):
            review.validate_response(bad, self.context, batch)
        bad = copy.deepcopy(good)
        bad['findings'][0]['citations'][1]['start_line'] = 1
        bad['findings'][0]['citations'][1]['end_line'] = 1
        with self.assertRaisesRegex(ValueError, 'not exact'):
            review.validate_response(bad, self.context, batch)
        bad = copy.deepcopy(good)
        bad['findings'][0]['citations'].pop()
        with self.assertRaisesRegex(ValueError, 'update and a corpus document'):
            review.validate_response(bad, self.context, batch)
        bad = copy.deepcopy(good)
        bad['findings'][0]['change_ids'] = ['issue:999@made-up']
        with self.assertRaisesRegex(ValueError, 'change_ids'):
            review.validate_response(bad, self.context, batch)

    def test_statistics_are_not_inferred_from_text_similarity(self):
        self.prepare()
        batch = self.context['batches'][0]
        result = response(self.context, batch, findings=True)
        stats = {'measure': 'Pearson r', 'value': '0.99', 'sample': 'Десять экспериментов',
                 'method': 'Парная корреляция', 'uncertainty': 'Не сообщена', 'citation_indices': [1]}
        result['findings'][0]['statistics'] = stats
        with self.assertRaisesRegex(ValueError, 'Textual connections'):
            review.validate_response(result, self.context, batch)
        result['findings'][0]['kind'] = 'reported_statistical_correlation'
        with self.assertRaisesRegex(ValueError, 'literally'):
            review.validate_response(result, self.context, batch)

    def test_omitted_acknowledgement_cannot_claim_full_pass(self):
        self.prepare()
        batch = self.context['batches'][0]
        result = response(self.context, batch)
        result['reviewed_document_ids'].pop()
        with self.assertRaisesRegex(ValueError, 'acknowledgement'):
            review.validate_response(result, self.context, batch)
        result['review_complete'] = False
        result['limitations'] = ['Не удалось разобрать вторую схему.']
        with patch.object(review, 'invoke_native', return_value=native(json.dumps(result))):
            self.assertFalse(review.generate(self.out)['complete'])

    def test_interrupted_attempt_does_not_repeat_unknown_paid_call(self):
        self.prepare()
        batch = self.context['batches'][0]
        prompt = review.prompt_for(self.context, batch)
        attempt = json.loads((self.out / 'ATTEMPT.json').read_text())
        folder = self.out / 'batches/0001'
        review.write(folder / 'PROMPT.txt', prompt)
        review.save(folder / 'RECEIPT.json', {
            **review.batch_identity(self.context, batch, attempt, prompt),
            'status': 'ATTEMPTING', 'complete': False, 'invocation_attempted': True})
        with patch.object(review, 'invoke_native') as call:
            result = review.generate(self.out)
            self.assertFalse(result['complete'])
            self.assertEqual(result['actual_native_calls'], 0)
            self.assertEqual(result['unknown_native_call_outcomes'], 1)
            self.assertFalse(review.recover(self.out)['complete'])
            call.assert_not_called()

    def test_no_new_run_may_reinvoke_an_old_reservation(self):
        self.prepare()
        with patch.dict(review.os.environ, {'GITHUB_RUN_ID': '102'}), \
                patch.object(review, 'invoke_native') as call:
            with self.assertRaisesRegex(ValueError, 'New run must recover'):
                review.generate(self.out)
            self.assertFalse(review.recover(self.out)['complete'])
            call.assert_not_called()

    def test_prompt_budget_fails_before_any_model_call(self):
        self.prepare(2)
        with patch.object(review, 'MAX_PROMPT_BYTES', 10), patch.object(review, 'invoke_native') as call:
            with self.assertRaisesRegex(ValueError, 'no truncation'):
                review.generate(self.out)
            call.assert_not_called()

    def test_publisher_rejects_raw_prompt_or_report_tampering(self):
        self.prepare()
        with patch.object(review, 'invoke_native', side_effect=self.good_native):
            review.generate(self.out)
        review.validate_saved(self.out)
        report = self.out / 'REPORT.md'
        original = report.read_text()
        report.write_text(original + '\nПринято научно.\n')
        with self.assertRaisesRegex(ValueError, 'receipt|deterministic'):
            review.validate_saved(self.out)
        report.write_text(original)
        raw = self.out / 'batches/0001/RAW_RESPONSE.txt'
        raw.write_text(raw.read_text() + ' ')
        with self.assertRaisesRegex(ValueError, 'every expected batch'):
            review.validate_saved(self.out)
        with patch.object(review, 'invoke_native') as call:
            self.assertFalse(review.recover(self.out)['complete'])
            call.assert_not_called()

    def test_changed_frozen_context_blocks_inference(self):
        self.prepare()
        changed = copy.deepcopy(self.context)
        changed['coverage']['new_claim'] = True
        review.save(self.out / 'CONTEXT.json', changed)
        with patch.object(review, 'invoke_native') as call:
            with self.assertRaisesRegex(ValueError, 'reservation identity'):
                review.generate(self.out)
            call.assert_not_called()

    def test_nonzero_native_exit_keeps_raw_but_cannot_be_accepted(self):
        self.prepare(2)
        raw = json.dumps(response(self.context, self.context['batches'][0]))
        failed = {**native(raw), 'returncode': 1}
        with patch.object(review, 'invoke_native', return_value=failed) as call:
            self.assertFalse(review.generate(self.out)['complete'])
            self.assertFalse(review.recover(self.out)['complete'])
            self.assertEqual(call.call_count, 1)
        self.assertEqual((self.out / 'batches/0001/RAW_RESPONSE.txt').read_text(), raw)
        self.assertFalse((self.out / 'batches/0002').exists())

    def test_grounded_finding_renders_only_generated_source_links(self):
        self.prepare()
        result = response(self.context, self.context['batches'][0], findings=True)
        result['findings'][0]['claim'] += ' [Внешняя команда](https://malicious.invalid) <img src=x>'
        with patch.object(review, 'invoke_native', return_value=native(json.dumps(result))):
            self.assertTrue(review.generate(self.out)['complete'])
        report = (self.out / 'REPORT.md').read_text()
        self.assertIn('/blob/' + SOURCE + '/analysis/SCHEMA_0.md#L2-L2', report)
        self.assertNotIn('<img', report)
        self.assertNotIn('[Внешняя команда]', report)
        review.validate_saved(self.out)

    def test_duplicate_json_keys_and_nonfinite_numbers_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON key'):
            review.parsed('{"review_complete":false,"review_complete":true}')
        with self.assertRaisesRegex(ValueError, 'Non-finite'):
            review.parsed('{"value":NaN}')


if __name__ == '__main__':
    unittest.main()
