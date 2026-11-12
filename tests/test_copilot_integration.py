"""No AI calls: verify real delegation, publication and provenance boundaries."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / (name + '.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


ctx = module('copilot_context')
compiler = module('compile_copilot_workflow')


class ContextTests(unittest.TestCase):
    def test_card_has_source_hash_and_pinned_locator(self):
        d = ctx.context('card', 'result:R122')
        self.assertEqual(d['data']['node']['id'], 'R122')
        self.assertIn(d['source_sha'], d['data']['locator'])
        self.assertEqual(len(d['index_sha256']), 64)

    def test_neighbors_are_bounded_and_declare_omissions(self):
        d = ctx.context('neighbors', 'result:R122', 1)['data']
        self.assertEqual(len(d['edges']), 1)
        self.assertGreater(d['total'], 1)
        self.assertTrue(d['truncated'])

    def test_unknown_or_path_like_keys_are_not_filesystem_queries(self):
        for key in ('../../etc/passwd', 'R99999', '/tmp/token'):
            with self.assertRaises(ValueError):
                ctx.context('card', key)
        for limit in (0, -1, 101, True):
            with self.assertRaises(ValueError):
                ctx.context('summary', limit=limit)

    def test_registry_context_preserves_status_and_source_contract(self):
        before = (ROOT / ctx.INDEX).read_bytes()
        d = ctx.context('sources', 'ISINGCAUSET')['data']['sources'][0]
        self.assertEqual(d['last_verified_sha'], None)
        self.assertEqual(len(d['source_sha']), 40)
        self.assertEqual((ROOT / ctx.INDEX).read_bytes(), before)


class DelegationTests(unittest.TestCase):
    def setUp(self):
        self.source = yaml.safe_load((ROOT / compiler.SOURCE).read_text().split('---', 2)[1])
        self.lock = yaml.safe_load((ROOT / compiler.LOCK).read_text())

    def test_source_and_generated_workflow_are_bound(self):
        compiler.check()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for p in (compiler.SOURCE, compiler.LOCK, compiler.MANIFEST):
                target = root / p
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / p).read_bytes())
            (root / compiler.SOURCE).write_text('changed question or permission')
            with self.assertRaisesRegex(ValueError, 'Regenerate'):
                compiler.check(root)

    def test_budget_and_no_blind_whole_session_retry(self):
        self.assertEqual(self.source['engine']['model'], 'gpt-5.6-luna-free-auto')
        self.assertEqual(self.source['safe-outputs']['threat-detection']['engine']['model'],
                         self.source['engine']['model'])
        self.assertEqual(self.source['engine']['harness']['max-retries'], 0)
        self.assertEqual(self.source['max-ai-credits'], 30)
        self.assertEqual(self.source['max-daily-ai-credits'], 60)
        self.assertEqual(self.source['safe-outputs']['threat-detection']['max-ai-credits'], 10)
        for j in self.lock['jobs'].values():
            self.assertTrue(1 <= j['timeout-minutes'] <= 10)
        for j in self.lock['jobs'].values():
            for s in j.get('steps', []):
                if s.get('uses', '').startswith('actions/upload-artifact@'):
                    self.assertEqual(s['with']['retention-days'], 7)

    def test_explicit_cli_version_has_authenticated_manifest_pin(self):
        # Regression: the first authenticated run failed before inference because
        # v1.0.105 was outside the pinned setup action's reviewed release table.
        engine = self.source['engine']
        checksum = engine['checksums-sha256']
        self.assertRegex(checksum, r'^[a-f0-9]{64}$')
        installs = [s['run'] for s in self.lock['jobs']['agent']['steps']
                    if s.get('name') == 'Install GitHub Copilot CLI']
        self.assertEqual(len(installs), 1)
        self.assertIn('" ' + engine['version'] + ' ', installs[0])
        self.assertIn('--checksums-sha256 ' + checksum, installs[0])

    def test_agent_cannot_publish_directly_or_merge(self):
        perms = self.lock['jobs']['agent']['permissions']
        self.assertTrue(all(v in ('read', 'none') for v in perms.values()))
        outputs = self.source['safe-outputs']
        self.assertNotIn('merge-pull-request', outputs)
        self.assertNotIn('dispatch-workflow', outputs)
        pr = outputs['create-pull-request']
        self.assertTrue(pr['draft'])
        self.assertEqual(pr['max'], 1)
        self.assertFalse(any(p.startswith(('.github/', 'tools/', 'experiments/')) for p in pr['allowed-files']))
        self.assertFalse(outputs['threat-detection']['continue-on-error'])

    def test_only_admin_requested_tasks_use_model(self):
        triggers = self.source.get('on', self.source.get(True))
        self.assertEqual(triggers['roles'], ['admin'])
        self.assertEqual(triggers['slash_command']['name'], 'vm-lab')
        self.assertNotIn('schedule', triggers)
        self.assertNotIn('pull_request_target', triggers)

    def test_generated_timeout_normalizer_is_idempotent(self):
        raw = 'jobs:\n  first:\n    steps: []\n  second:\n    timeout-minutes: 45\n    steps: []\n'
        bounded = compiler.bound_jobs(raw)
        self.assertEqual(compiler.bound_jobs(bounded), bounded)
        jobs = yaml.safe_load(bounded)['jobs']
        self.assertEqual(jobs['first']['timeout-minutes'], 5)
        self.assertEqual(jobs['second']['timeout-minutes'], 10)

    def test_proposal_validation_checks_exact_head_without_secrets(self):
        raw = (ROOT / '.github/workflows/copilot-pr-validation.yml').read_text()
        self.assertNotIn('secrets.', raw)
        d = yaml.safe_load(raw)
        check = d['jobs']['check']
        self.assertEqual(check['permissions'], {'contents': 'read'})
        checkout = check['steps'][0]['with']
        self.assertEqual(checkout['ref'], '${{ needs.locate.outputs.sha }}')
        self.assertFalse(checkout['persist-credentials'])
        self.assertIn('python tools/ci_suite.py integrity', raw)


if __name__ == '__main__':
    unittest.main()
