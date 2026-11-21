import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'infra'))
import copilot_thematic_corpus as corpus

MAIN = 'a' * 40
BRANCH = 'b' * 40
REPO = 'IgorSabirov/vm-lab'


class FakeGitHub:
    repository = REPO

    def __init__(self, snapshots):
        self.snapshots, self.values, self.calls, self._blobs = snapshots, {}, [], {}
        for files in snapshots.values():
            for text in files.values():
                self.values[corpus.git_blob_sha(text)] = text

    def tree(self, sha):
        return [{'path': path, 'type': 'blob', 'mode': '100644',
                 'sha': corpus.git_blob_sha(text), 'size': len(text.encode())}
                for path, text in sorted(self.snapshots[sha].items())]

    def blob(self, sha):
        self.calls.append(sha)
        return self.values[sha]


def snapshot(extra=None, declared=()):
    core = {
        'common_model': 'analysis/common/MODEL.md',
        'rho_genesis_specification': 'analysis/r128/SPECIFICATION.md',
        'contact_capacity_result': 'analysis/r129/REPORT.md',
    }
    files = {path: f'# Complete {ident}\nDefinitions without truncation.\n'
             for ident, path in core.items()}
    files[corpus.POLICY] = json.dumps({'rules': [{'documents': [
        {'id': ident, 'path': path} for ident, path in core.items()]}]})
    files[corpus.INDEX] = json.dumps({'sources': {p: 'digest' for p in declared},
        'managed_review_sources': {},
        'nodes': [{'key': 'result:R1', 'id': 'R1', 'path': p} for p in declared],
        'edges': [], 'counts': {'result': len(declared)}})
    files.update(extra or {})
    return files


def events(text='A partial scientific result.', extra=None, refs=None):
    value = {'schema': 'vm-lab-thematic-events-v1', 'repository': REPO,
        'source_sha': MAIN, 'package_id': 'c' * 64,
        'changes': [{'id': 'issue:174', 'kind': 'issue', 'text': text,
                     'revision': '2026-11-21T00:00:00Z', 'url': 'https://github.com/IgorSabirov/vm-lab/issues/174'}],
        'source_refs': refs or [{'sha': MAIN, 'label': 'main'}], 'coverage': {'complete_content': True}}
    value.update(extra or {})
    return value


class CorpusTests(unittest.TestCase):
    def test_discovery_includes_unlinked_registries_and_arbitrary_diagram_paths(self):
        extra = {
            'new/unrelated/cards.json': '{"type":"object","properties":{"card":{"type":"string"}}}',
            'another/new.md': '# Unnamed document\n```mermaid\ngraph TD\n A-->B\n```\n',
            'another/table.md': '# New cards\n| ID | Definition |\n| --- | --- |\n| X1 | A new relation |\n',
            'another/arbitrary.json': '{"entries":[{"key":"X1","definition":"new relation"}]}',
            'elsewhere/new.schema.yaml': 'type: object\nproperties:\n  x: string\n',
            'evidence/curated.py': 'raise RuntimeError("never execute this")\n',
            'results/raw.json': '[0.1,0.2,0.3]',
            'analysis/prose.md': '# Earlier prose\nAn unrelated historical paragraph.\n',
        }
        context = corpus.prepare(FakeGitHub({MAIN: snapshot(extra, ['evidence/curated.py'])}), events())
        paths = {d['path'] for d in context['documents']}
        self.assertTrue(set(extra) - {'results/raw.json', 'analysis/prose.md'} <= paths)
        self.assertNotIn('results/raw.json', paths)
        self.assertNotIn('analysis/prose.md', paths)
        audited = {x['path']: x for x in context['coverage']['inventory']}
        self.assertEqual(audited['results/raw.json']['disposition'],
                         'pointer_scanned_non_registry_document_or_raw_data')
        self.assertTrue(audited['analysis/prose.md']['content_read'])
        self.assertFalse(context['coverage']['semantic_prefilter'])

    def test_source_variants_are_deduplicated_by_blob_and_remain_pinned(self):
        main = snapshot({'new/REGISTRY.json': '{"items":["old"]}'})
        branch = {**main, 'new/REGISTRY.json': '{"items":["new"]}',
                  'branch/schema.json': '{"type":"object","properties":{"u":{}}}'}
        api = FakeGitHub({MAIN: main, BRANCH: branch})
        context = corpus.prepare(api, events(refs=[{'sha': BRANCH, 'label': 'pr:160'}]))
        registry_docs = [d for d in context['documents'] if d['path'] == 'new/REGISTRY.json']
        self.assertEqual({d['source_sha'] for d in registry_docs}, {MAIN, BRANCH})
        one_core = context['shared_documents'][0]
        self.assertEqual(one_core['source_sha'], MAIN)
        original = next(d for d in context['documents'] if d['id'] == one_core['id'])
        self.assertEqual({x['source_sha'] for x in original['origins']}, {MAIN, BRANCH})
        self.assertEqual(len(api.calls), len(set(api.calls)))

    def test_all_versions_and_all_unicode_bytes_cross_every_corpus_segment(self):
        text = ('Строка λ с физическим смыслом\n' * 170) + ('🙂' * 1400)
        api = FakeGitHub({MAIN: snapshot({'new/REGISTER.md': '# Реестр\n' + text})})
        source = events(text)
        source['changes'].append({**source['changes'][0], 'text': text + '\nUpdated value.'})
        context = corpus.prepare(api, source, max_payload_bytes=14_000)
        self.assertGreater(len(context['batches']), 1)
        self.assertEqual(len(context['events']), 2)
        self.assertEqual(len({e['id'] for e in context['events']}), 2)
        self.assertTrue(all(e['source_event_id'] == 'issue:174' for e in context['events']))
        result = corpus.validate_context(context)
        self.assertTrue(result['complete'])
        self.assertEqual(result['pairs'], context['coverage']['cartesian_pair_count'])
        for batch in context['batches']:
            self.assertLessEqual(len(corpus.compact(corpus.payload(context, batch)).encode()), 14_000)

    def test_validation_rejects_missing_cartesian_pair_even_with_all_bytes_elsewhere(self):
        context = corpus.prepare(FakeGitHub({MAIN: snapshot({'new/registry.txt': 'C' * 20_000})}),
                                 events('E' * 20_000), max_payload_bytes=12_000)
        self.assertGreater(len(context['batches']), 4)
        changed = copy.deepcopy(context)
        changed['batches'].pop(0)
        with self.assertRaisesRegex(ValueError, 'every update segment'):
            corpus.validate_context(changed)

    def test_corrupt_or_missing_bytes_are_not_called_complete(self):
        context = corpus.prepare(FakeGitHub({MAIN: snapshot()}), events())
        changed = copy.deepcopy(context)
        changed['batches'][0]['documents'][0]['text'] += 'x'
        with self.assertRaisesRegex(ValueError, 'Corrupt source segment'):
            corpus.validate_context(changed)
        changed = copy.deepcopy(context)
        changed['batches'][0]['documents'].pop(0)
        with self.assertRaisesRegex(ValueError, 'never supplied'):
            corpus.validate_context(changed)

    def test_missing_declared_file_or_core_definition_stops_preparation(self):
        with self.assertRaisesRegex(ValueError, 'absent files'):
            corpus.prepare(FakeGitHub({MAIN: snapshot(declared=['missing/contract.json'])}), events())
        files = snapshot()
        del files['analysis/r128/SPECIFICATION.md']
        with self.assertRaisesRegex(ValueError, 'mandatory definition'):
            corpus.prepare(FakeGitHub({MAIN: files}), events())

    def test_tampered_blob_cannot_become_model_input(self):
        api = FakeGitHub({MAIN: snapshot()})
        original = api.blob
        api.blob = lambda sha: original(sha) + 'tampered'
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            corpus.prepare(api, events())

    def test_blob_verified_local_files_prevent_redundant_api_reads(self):
        files = snapshot()
        api = FakeGitHub({MAIN: files})
        with tempfile.TemporaryDirectory() as name:
            for path, text in files.items():
                target = Path(name) / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(text.encode())
            context = corpus.prepare(api, events(), local_root=Path(name))
            self.assertEqual(api.calls, [])
            self.assertTrue(corpus.validate_context(context)['complete'])
            # A local worktree edit cannot substitute for the pinned source.
            (Path(name) / corpus.INDEX).write_text('{}')
            api2 = FakeGitHub({MAIN: files})
            corpus.prepare(api2, events(), local_root=Path(name))
            self.assertEqual(api2.calls, [corpus.git_blob_sha(files[corpus.INDEX])])

    def test_report_loop_exclusion_and_no_events_do_not_start_analysis(self):
        extra = {corpus.REPORT_PREFIX + 'old/REGISTRY.json': '{"schema":"loop"}'}
        context = corpus.prepare(FakeGitHub({MAIN: snapshot(extra)}), events(extra={'changes': []}))
        self.assertEqual(context['batches'], [])
        self.assertEqual(context['coverage']['planned_model_calls'], 0)
        self.assertNotIn(next(iter(extra)), {d['path'] for d in context['documents']})

    def test_full_shared_context_budget_failure_does_not_truncate(self):
        files = snapshot()
        files['analysis/common/MODEL.md'] = 'mandatory definition ' * 2000
        with self.assertRaisesRegex(ValueError, 'mandatory shared definitions'):
            corpus.prepare(FakeGitHub({MAIN: files}), events(), max_payload_bytes=12_000)

    def test_archives_and_numeric_outputs_are_pointers_but_declared_sources_and_updates_survive(self):
        archive = 'results/VM_WORKSPACE_SNAPSHOTS/old/files/REGISTRY.json'
        declared_archive = 'results/VM_WORKSPACE_SNAPSHOTS/old/files/evidence.md'
        raw = 'results/EXPERIMENT_RAW/main_output/rows/42.json'
        named_schema = 'results/EXPERIMENT_RAW/main_output/rows/new.schema.json'
        receipt = 'analysis/new/run.json'
        extra = {
            archive: '{"results":[{"id":"R9","title":"Old backup"}]}',
            declared_archive: 'An explicitly registered historical witness.\n',
            raw: '{"nodes":[1,2],"edges":[[1,2]],"schema":"graph-sample-v1"}',
            named_schema: '{"type":"object","properties":{"weight":{"type":"number"}}}',
            receipt: '{"schema":"receipt-v1","results":[1,2,3],"success":true}',
        }
        api = FakeGitHub({MAIN: snapshot(extra, [declared_archive])})
        source = events(extra[archive])
        source['changes'][0].update(id='file:' + archive, path=archive, kind='document')
        context = corpus.prepare(api, source)
        paths = {d['path'] for d in context['documents']}
        self.assertTrue({declared_archive, named_schema} <= paths)
        self.assertFalse({archive, raw, receipt} & paths)
        self.assertNotIn(corpus.git_blob_sha(extra[archive]), api.calls)
        self.assertNotIn(corpus.git_blob_sha(extra[raw]), api.calls)
        self.assertEqual(''.join(p['text'] for p in context['batches'][0]['events']), extra[archive])
        audited = {x['path']: x for x in context['coverage']['inventory']}
        self.assertEqual(audited[archive]['disposition'], 'pointer_archival_workspace_backup')
        self.assertEqual(audited[raw]['disposition'], 'pointer_raw_numerical_output')

    def test_serialization_tags_and_numeric_results_do_not_define_registries(self):
        for text in ['{"schema":"receipt-v1","results":[1,2]}',
                     '{"$schema":"instance-format","samples":[1,2]}',
                     '{"results":[{"time":1,"value":2}]}',
                     'schema: receipt-v1\nresults:\n  - 1\n  - 2\n']:
            path = 'opaque.yaml' if text.startswith('schema:') else 'opaque.json'
            self.assertFalse(corpus.structural_document(path, text))
        self.assertTrue(corpus.structural_document('opaque.json', '{"$defs":{}}'))
        self.assertTrue(corpus.structural_document('opaque.json',
            '{"results":[{"id":"R1","title":"A scientific card"}]}'))

    def test_many_refs_share_compact_inventory_and_graph_identity(self):
        files = snapshot({'new/REGISTRY.json': '{"cards":[{"id":"X1","title":"A"}]}'})
        shas = [MAIN] + [f'{i:040x}' for i in range(1, 33)]
        api = FakeGitHub({sha: files for sha in shas})
        context = corpus.prepare(api, events(refs=[{'sha': sha, 'label': 'pr:' + str(i)}
                                                   for i, sha in enumerate(shas)]))
        coverage = context['coverage']
        self.assertLess(len(coverage['inventory']), 2 * len(files))
        self.assertTrue(all(count == len(files) for count in coverage['inventory_entries_by_ref'].values()))
        self.assertEqual(len(context['graph_variants']), 1)
        self.assertEqual(len(context['graph_variants'][0]['source_refs']), len(shas))
        self.assertTrue(all('source_sha' not in row and 'labels' not in row
                            for row in coverage['inventory']))
        self.assertTrue(corpus.validate_context(context)['complete'])


if __name__ == '__main__':
    unittest.main()
