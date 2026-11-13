"""Prevent version drift and broken resource references without importing upstream."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import external_sources as ext
import registry_links as registry


class ExternalResources(unittest.TestCase):
    def setUp(self):
        self.source = next(r for r in ext.validate(ROOT) if r['id'] == 'PRIMAT')
        self.manifest = json.loads((ROOT / self.source['resource_manifest']).read_text())

    def resolve_changed(self, change):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = copy.deepcopy(self.manifest)
            change(manifest)
            path = root / self.source['resource_manifest']
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(manifest))
            for ref in manifest.get('project_references', []):
                p = root / ref
                p.parent.mkdir(parents=True, exist_ok=True)
                p.touch()
            return ext.resolve_resources(self.source, root)

    def test_links_use_source_pin_and_no_execution(self):
        result = ext.resolve_resources(self.source, ROOT)
        self.assertEqual(len(result['resources']), 20)
        for r in result['resources']:
            self.assertIn('/' + self.source['source_sha'] + '/', r['url'])
        self.assertFalse(result['execution_performed'])
        self.assertIsNone(self.source['last_verified_sha'])
        self.assertTrue(self.source['monitor_enabled'])

    def test_different_commit_tree_or_repository_rejected(self):
        for key, value in [('source_sha', 'a' * 40), ('source_tree_sha', 'b' * 40),
                           ('repository', 'different/project'), ('source_id', 'OTHER')]:
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'identity'):
                self.resolve_changed(lambda m: m.update({key: value}))

    def test_unsafe_duplicate_or_missing_resource_identity_rejected(self):
        for path in ['../rates.csv', '/rates.csv', 'a/../b', 'a//b',
                     'a?ref=main', 'a#L1', 'a\\b', 'a/%2e%2e/b', ' a', 'a\nb']:
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.resolve_changed(lambda m: m['resources'][0].update(path=path))
        for update in [{'git_sha': 'main'}, {'type': 'symlink'}, {'id': ''},
                       {'url': 'https://github.com/CyrilPitrou/primat/blob/master/LICENCE'},
                       {'data': 'not a reference'}]:
            with self.subTest(update=update), self.assertRaises(ValueError):
                self.resolve_changed(lambda m: m['resources'][0].update(update))
        with self.assertRaises(ValueError):
            self.resolve_changed(lambda m: m['resources'].append(copy.deepcopy(m['resources'][0])))

    def test_registration_and_metadata_are_visible_in_common_graph(self):
        _, graph = registry.run(ROOT)
        edges = graph['edges']
        expected = ['review:CCC_TL_20261112', 'link:L10',
                    'source:analysis/CCC_BBN_DRIFT_20261113/REPORT.md',
                    'source:infra/external/sources/PRIMAT.json']
        targets = {e['target'] for e in edges if e['source'] == 'external:PRIMAT'}
        self.assertTrue(set(expected).issubset(targets))
        evidence = next(e for e in edges if e['source'] == 'external:PRIMAT'
                        and e['target'] == 'source:infra/external/sources/PRIMAT.json')
        self.assertEqual(evidence['relation'], 'external_metadata_not_execution_evidence')


if __name__ == '__main__':
    unittest.main()
