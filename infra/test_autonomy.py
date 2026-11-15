"""Technical routing/accounting fixtures: no scientific process or remote writes."""
import copy
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from autonomy import admit, finish
from autonomy.execution_policy import validate
import research_pipeline

LIMITS = {'new_packages_per_rolling_24h': 2, 'memory_bytes': 4 * 1024**3, 'output_bytes': 2 * 1024**3}


def example(seconds=(3600,), kind='independent_realizations'):
    evidence = {'path': 'fixture.json', 'sha256': 'f' * 64}
    sections = [{'id': f's{i}', 'task_ids': [f't{i}'], 'setup_seconds': 30,
                 'compute_seconds': t, 'verification_seconds': 10, 'publication_seconds': 20,
                 'wall_seconds': t + 60, 'memory_bytes': 1024**3} for i, t in enumerate(seconds)]
    total = sum(s['wall_seconds'] for s in sections)
    route = 'local' if total <= 600 else 'github_actions' if max(seconds) + 60 <= 21600 else 'vm'
    return {'schema': 'vm-lab-execution-plan-v1', 'package_id': 'fixture_package_001',
            'source_commit': 'a' * 40, 'publication_branch': 'science/autonomous-fixture',
            'workload_kind': kind, 'executor': route,
            'input_manifest': copy.deepcopy(evidence), 'acceptance': copy.deepcopy(evidence),
            'calibration': {**evidence, 'measured_seconds': 2, 'executor': route,
                            'environment_reference': 'fixture-only/not-a-real-calibration'},
            'tasks': [{'id': f't{i}', 'forecast_seconds': t * .8, 'process_seconds': t,
                       'seed': i} for i, t in enumerate(seconds)],
            'sections': sections, 'parallel_sections': 1,
            'budget': {'package_seconds': total, 'section_seconds': max(seconds) + 60,
                       'process_seconds': max(seconds), 'memory_bytes': 4 * 1024**3,
                       'output_bytes': 1024**3, 'vm_seconds': total if route == 'vm' else None},
            'checkpoint_policy': 'not_required', 'scientific_acceptance': False, 'automatic_retry': False,
            'verified_vm_limits': {'executor_id': 'fixture-worker', 'wall_seconds': total,
                                   'memory_bytes': 4 * 1024**3, 'output_bytes': 1024**3,
                                   'evidence': copy.deepcopy(evidence)}}


class Routing(unittest.TestCase):
    def test_local_boundary_applies_to_entire_package(self):
        self.assertEqual(validate(example((540,)), LIMITS)['executor'], 'local')
        self.assertEqual(validate(example((541,)), LIMITS)['executor'], 'github_actions')
        self.assertEqual(validate(example((300, 300)), LIMITS)['executor'], 'github_actions')

    def test_twelve_hour_package_uses_three_whole_sections(self):
        p = example((14400, 14400, 14400))
        r = validate(p, LIMITS)
        self.assertEqual(r['executor'], 'github_actions')
        self.assertGreater(r['budget']['package_seconds'], 21600)
        self.assertEqual([s['timeout_minutes'] for s in r['sections']], [241, 241, 241])

    def test_continuous_with_overhead_boundary_and_vm(self):
        self.assertEqual(validate(example((21540,), 'continuous'), LIMITS)['executor'], 'github_actions')
        self.assertEqual(validate(example((21541,), 'continuous'), LIMITS)['executor'], 'vm')
        self.assertEqual(validate(example((30000,), 'continuous'), LIMITS)['executor'], 'vm')

    def test_continuous_cannot_be_disguised_as_sections(self):
        with self.assertRaisesRegex(ValueError, 'cannot be split'):
            validate(example((10000, 10000), 'continuous'), LIMITS)

    def test_vm_cannot_be_used_to_avoid_batching_independent_tasks(self):
        p = example((14000, 14000))
        p['sections'] = [{**p['sections'][0], 'task_ids': ['t0', 't1'],
                          'compute_seconds': 28000, 'wall_seconds': 28060}]
        p['budget']['section_seconds'] = 28060
        with self.assertRaisesRegex(ValueError, 'Repartition'):
            validate(p, LIMITS)

    def test_vm_requires_verified_capacity_and_own_finite_budget(self):
        for mutation in (lambda p: p['budget'].update(vm_seconds=None),
                         lambda p: p['verified_vm_limits'].update(wall_seconds=21600),
                         lambda p: p['verified_vm_limits'].update(memory_bytes=1)):
            p = example((30000,), 'continuous'); mutation(p)
            with self.assertRaises(ValueError): validate(p, LIMITS)

    def test_tasks_must_be_covered_once(self):
        for ids in ([], ['t0', 't0'], ['unknown']):
            p = example(); p['sections'][0]['task_ids'] = ids
            with self.assertRaises(ValueError): validate(p, LIMITS)

    def test_same_ab_seed_is_allowed_but_duplicate_task_id_is_not(self):
        p = example((1000, 1000)); p['tasks'][1]['seed'] = 0
        validate(p, LIMITS)
        p['tasks'][1]['id'] = 't0'
        with self.assertRaisesRegex(ValueError, 'Duplicate'): validate(p, LIMITS)

    def test_budget_and_parallel_memory_are_enforced(self):
        changes = [lambda p: p['budget'].update(package_seconds=1),
                   lambda p: p['sections'][0].update(wall_seconds=3600),
                   lambda p: p['sections'][0].update(compute_seconds=3000),
                   lambda p: p['budget'].update(process_seconds=1),
                   lambda p: p['budget'].update(section_seconds=1),
                   lambda p: p['budget'].update(output_bytes=3 * 1024**3),
                   lambda p: p['tasks'][0].update(forecast_seconds=float('nan'))]
        for change in changes:
            with self.subTest(change=change):
                p = example(); change(p)
                with self.assertRaises(ValueError): validate(p, LIMITS)
        p = example((1000,) * 5); p['parallel_sections'] = 5
        with self.assertRaisesRegex(ValueError, 'aggregate memory'): validate(p, LIMITS)
        p['parallel_sections'] = 4; validate(p, LIMITS)

    def test_evidence_bytes_and_checkpoint_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); f = root / 'fixture.json'; f.write_text('{}')
            p = example()
            for key in ('input_manifest', 'acceptance', 'calibration'):
                p[key]['sha256'] = hashlib.sha256(f.read_bytes()).hexdigest()
            validate(p, LIMITS, root=root)
            f.write_text('{"changed":true}')
            with self.assertRaisesRegex(ValueError, 'Changed evidence'): validate(p, LIMITS, root=root)
        p = example(); p['checkpoint_policy'] = 'method_defined'
        with self.assertRaises(KeyError): validate(p, LIMITS)

    def test_wrong_calibration_and_automatic_acceptance_rejected(self):
        for change in (lambda p: p['calibration'].update(executor='vm'),
                       lambda p: p.update(scientific_acceptance=True),
                       lambda p: p.update(automatic_retry=True)):
            p = example(); change(p)
            with self.assertRaises(ValueError): validate(p, LIMITS)


class Accounting(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 15, 14, 9, 29, tzinfo=timezone.utc)
        self.ledger = {'packages': [
            {'id': 'eta', 'executor': 'github_actions', 'workflow_run_id': 1,
             'started_utc': '2026-11-14T14:09:28Z', 'result_sha': 'a' * 40},
            {'id': 'local', 'executor': 'local', 'started_utc': '2026-11-14T14:32:49.197918Z'}]}
        self.runs = [{'id': 1, 'head_branch': 'science/autonomous-eta', 'status': 'completed',
                      'created_at': '2026-11-14T14:09:28Z'}]
        self.new = {'id': 'new', 'started_utc': self.now.isoformat(), 'executor': 'vm', 'status': 'RESERVED'}

    def decide(self, candidate=None, now=None):
        return admit.decision(self.ledger, self.runs, candidate or self.new, now or self.now, LIMITS)

    def test_mixed_executors_rolling_boundary(self):
        self.assertFalse(self.decide(now=self.now - timedelta(seconds=2))['admitted'])
        self.assertTrue(self.decide()['admitted'])
        self.ledger['packages'].append({**self.new, 'status': 'COMPLETED'})
        second = {'id': 'second'}
        blocked = self.decide(second)
        self.assertEqual(blocked['reason'], 'BUDGET_WAIT')
        self.assertEqual(blocked['not_before_utc'], '2026-11-15T14:32:49.197918+00:00')
        self.assertTrue(self.decide(second, datetime(2026, 11, 15, 14, 32, 50, tzinfo=timezone.utc))['admitted'])

    def test_expired_package_never_retried(self):
        self.assertEqual(self.decide({'id': 'eta'})['reason'], 'ALREADY_REGISTERED_NO_RETRY')

    def test_active_vm_excludes_new_actions_even_after_24h(self):
        self.ledger['packages'][0]['status'] = 'RUNNING'
        self.assertEqual(self.decide()['reason'], 'ACTIVE_PACKAGE')

    def test_multiple_workflow_sections_are_one_package(self):
        self.ledger['packages'][1].update(workflow_run_ids=[2, 3])
        self.runs += [dict(self.runs[0], id=i, created_at='2026-11-15T12:00:00Z') for i in (2, 3)]
        self.assertEqual(self.decide()['packages_last_24h'], ['local'])

    def test_unknown_actions_are_conservatively_counted(self):
        self.runs.append(dict(self.runs[0], id=99, created_at='2026-11-15T12:00:00Z'))
        self.assertFalse(self.decide()['admitted'])

    def test_current_run_is_reserved_once(self):
        self.runs.append(dict(self.runs[0], id=99, created_at='2026-11-15T12:00:00Z', status='in_progress'))
        self.assertTrue(admit.decision(self.ledger, self.runs, self.new, self.now, LIMITS, 99)['admitted'])

    def test_cas_conflict_rechecks_and_prevents_second_admission(self):
        attempts = []
        def read(): return copy.deepcopy(self.ledger), str(len(self.ledger['packages']))
        def write(value, expected):
            attempts.append(expected)
            self.ledger['packages'].append({**self.new, 'id': 'competitor'})
            return False
        result = admit.reserve(read, write, self.runs, self.new, self.now, LIMITS)
        self.assertEqual(result['reason'], 'ACTIVE_PACKAGE')
        self.assertEqual(len(attempts), 1)

    def test_uncertain_write_is_not_retried(self):
        calls = []
        def write(*args): calls.append(1); raise TimeoutError('uncertain delivery')
        with self.assertRaises(TimeoutError):
            admit.reserve(lambda: (self.ledger, 'blob'), write, self.runs, self.new, self.now, LIMITS)
        self.assertEqual(len(calls), 1)

    def test_terminal_receipt_does_not_accept_science_or_rewrite_fail(self):
        reservation = {**self.new, 'workflow_run_id': 7, 'source_sha': 'a' * 40, 'execution_plan_sha256': 'b' * 64}
        self.ledger['packages'].append(reservation)
        terminal = finish.close(self.ledger, reservation, 'failure', 'c' * 40)
        self.assertEqual(terminal['packages'][-1]['status'], 'FAILED')
        self.assertFalse(terminal['packages'][-1]['scientific_acceptance'])
        with self.assertRaisesRegex(ValueError, 'already terminal'):
            finish.close(terminal, reservation, 'success', 'd' * 40)

    def test_disabled_request_never_reserves_or_queries_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {'GITHUB_REPOSITORY': admit.REPOSITORY, 'GITHUB_RUN_ATTEMPT': '1',
                                        'GITHUB_REF_NAME': 'science/autonomous-fixture', 'RUNNER_TEMP': tmp}), \
                    patch.object(admit, 'api', side_effect=AssertionError('network forbidden')):
                admit.main()
            self.assertFalse(json.loads((Path(tmp) / 'autonomy-budget.json').read_text())['execute'])


class Controller(unittest.TestCase):
    def test_package_import_used_by_bh0_workflow(self):
        subprocess.run([sys.executable, '-c', 'from infra.research_pipeline import evaluate'],
                       cwd=research_pipeline.REPO, check=True, timeout=5)

    def test_existing_flat_s3_manifest_is_verified_without_rewriting_evidence(self):
        plan = research_pipeline.read(research_pipeline.PKG / 'PIPELINE.json')
        stage = next(s for s in plan['stages'] if s['id'] == 'S3_INPUT_AUDIT')
        result = research_pipeline.verify_import(stage)
        self.assertTrue(research_pipeline.contract_complete(result, stage))
        self.assertEqual(result['scientific_status'], 'INPUT_DIAGNOSTIC_ONLY')
        self.assertFalse(result['scientific_acceptance'])
        bad = copy.deepcopy(stage); bad['manifest']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'Pinned manifest'):
            research_pipeline.verify_import(bad)

    def test_process_exit_and_hard_deadline(self):
        self.assertEqual(research_pipeline.bounded_process([sys.executable, '-c', 'pass'], 5), 0)
        with self.assertRaisesRegex(ValueError, 'budget exhausted'):
            research_pipeline.bounded_process([sys.executable, '-c', 'import time; time.sleep(5)'], .03)

    def test_admission_binds_exact_plan_and_workflow(self):
        p = example()
        r = validate(p, LIMITS)
        receipt = {**r, 'execute': True, 'reservation': {'id': p['package_id'], 'workflow_run_id': 17}}
        request = {'id': p['package_id'], 'execution_plan': 'fixture-plan.json'}
        def read(path):
            name = Path(path).name
            return {'autonomy-budget.json': receipt, 'fixture-plan.json': p,
                    'CONTROL.json': {'limits': LIMITS}}[name]
        with patch.dict(os.environ, {'RUNNER_TEMP': '/tmp/fixture', 'GITHUB_RUN_ID': '17'}), \
                patch.object(research_pipeline, 'read', side_effect=read), \
                patch.object(research_pipeline, 'validate_execution', return_value=r):
            self.assertEqual(research_pipeline.execution_admission(request), p)
            receipt['reservation']['workflow_run_id'] = 18
            with self.assertRaisesRegex(ValueError, 'admission'):
                research_pipeline.execution_admission(request)

    def test_source_changes_after_freeze_are_rejected(self):
        p = example(); request = {'id': p['package_id']}
        with patch.dict(os.environ, {'GITHUB_REF_NAME': p['publication_branch']}), \
                patch.object(admit.subprocess, 'run'), \
                patch.object(admit.subprocess, 'check_output', return_value='infra/research_pipeline.py\n'):
            with self.assertRaisesRegex(ValueError, 'Source changed'):
                admit.source_check(p, 'fixture-plan.json', request)


if __name__ == '__main__':
    unittest.main()
