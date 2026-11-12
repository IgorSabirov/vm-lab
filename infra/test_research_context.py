import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import copilot_review as review
import research_context as context


class ResearchContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = review.build_context(task='six-models-v2')

    def test_complete_definitions_and_typed_cards_replace_fragment(self):
        c = self.package
        for path in ('analysis/COMMON_MODEL_20261109/MODEL.md',
                     'analysis/R128_RHO_GENESIS_20261110/R128_1_SPECIFICATION_20261111.md',
                     'analysis/G3_CONTACT_CAPACITY_20261111/REPORT.md'):
            rows = [f for f in c['files'] if f['path'] == path]
            self.assertEqual(len(rows), 1)
            self.assertFalse(rows[0]['partial'])
            self.assertEqual(rows[0]['text'], (review.ROOT / path).read_text())
            self.assertTrue(rows[0]['required_by'])
        cards = c['context_contract']['cards']
        self.assertTrue({'result', 'construct', 'link', 'question', 'premise', 'obligation', 'decision'} <= {x['key'].split(':')[0] for x in cards})
        self.assertTrue(all(len(x['source_sha256']) == 64 and x['required_by'] for x in cards))
        self.assertIn('unknown', next(x['data'] for x in cards if x['key'] == 'question:U010'))
        self.assertLess(len(json.dumps(c, ensure_ascii=False, indent=2).encode()), 600000)
        self.assertTrue(c['context_contract']['frontier_not_expanded'])

    def test_missing_definition_or_stale_graph_stops_before_inference(self):
        original = context.read
        def missing(root, path):
            if path == 'analysis/COMMON_MODEL_20261109/MODEL.md':
                return original(root, path).replace(b'## 12.', b'## Missing.')
            return original(root, path)
        with patch.object(context, 'read', side_effect=missing), self.assertRaisesRegex(ValueError, 'definition'):
            context.resolve(review.ROOT, ['question:U010'])
        with patch.object(context.registry, 'run', return_value=(['INDEX.json'], {})), self.assertRaisesRegex(ValueError, 'Stale'):
            context.resolve(review.ROOT, ['question:U010'])

    def test_edge_identity_is_not_semantic_acceptance(self):
        graph = {'nodes': [{'key': 'result:R126'}, {'key': 'result:R127'}, {'key': 'result:R128'}],
                 'edges': [{'source': 'result:R126', 'target': 'result:R127', 'relation': 'parent'}]}
        proposals = [{'source': 'result:R126', 'target': 'result:R127', 'relation': 'parent'},
                     {'source': 'result:R126', 'target': 'result:R127', 'relation': 'candidate_interface'},
                     {'source': 'result:R126', 'target': 'result:R128', 'relation': 'candidate_interface'}]
        d = context.reconcile(proposals, graph)
        self.assertEqual(list(d['counts'].values()), [1, 1, 1])
        self.assertTrue(all(r['automatic_import'] is False and r['semantic_equivalence'] == 'NOT_EVALUATED' for r in d['rows']))
        self.assertFalse(d['rows'][1]['allowed_as_external_review_relation'])
        proposals[0]['target'] = 'result:R999'
        with self.assertRaisesRegex(ValueError, 'endpoint'): context.reconcile(proposals, graph)

    def test_context_is_data_and_paths_cannot_escape(self):
        for path in ('../private', '/etc/passwd'):
            with self.assertRaises(ValueError): context.read(review.ROOT, path)
        d = self.package
        keys = [x['key'] for x in d['context_contract']['cards']]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(d['context_contract']['scientific_acceptance'], 'NOT_GRANTED')

    def test_v2_generation_keeps_required_content_and_separate_statuses(self):
        c = {**self.package, 'executed_checks': []}
        path = c['files'][0]['path']
        d = {'summary': 'Conditional synthesis', 'models': [
            {'id': m['id'], 'contribution': 'Role', 'given': 'Inputs', 'obtained': 'Evidence',
             'gap': 'Missing law', 'evidence': [path]} for m in c['profile']['models']],
            'connections': [{'source': 'result:R126', 'target': 'result:R127',
                'relation': 'candidate_interface', 'claim': 'Proposed interface',
                'missing': 'Mapping', 'evidence': [path]}],
            'next_tests': [{'question': 'Effect?', 'observable': 'Action', 'control': 'Changed record',
                'discrimination': 'Different action', 'missing': 'Mapping', 'evidence': [path]}]}
        def fake(prompt, timeout):
            self.assertIn('## 12. Балансы', prompt)
            self.assertIn('rho_genesis_specification', prompt)
            self.assertGreater(len(prompt.encode()), 131072)
            return {'stdout': json.dumps(d), 'returncode': 0, 'timed_out': False, 'elapsed_seconds': 0}
        with tempfile.TemporaryDirectory() as tmp, patch.object(review, 'invoke_native', side_effect=fake):
            output = Path(tmp); review.dump(output / 'CONTEXT.json', c)
            review.generate(output)
            p = json.loads((output / 'native-proposal.json').read_text())
            self.assertEqual(p['receipt']['task_id'], 'six-models-v2')
            self.assertEqual(p['receipt']['review_stages']['scientific_acceptance'], 'NOT_GRANTED')
            self.assertEqual(p['receipt']['proposal_assessment']['counts']['EXISTING_ENDPOINT_PAIR_DIFFERENT_TYPE'], 1)


if __name__ == '__main__':
    unittest.main()
