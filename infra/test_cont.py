"""CONT contracts with synthetic states; no real VM data or network access."""
import csv
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cont.model import sha, save_json
from cont.runner import input_state
from cont.report import export_series, write_report
import test_bridge as bridge_tests


def config():
    return json.loads((ROOT / 'config.json').read_text())


class ContIntegration(unittest.TestCase):
    # Reuse the real Git/worker transport fixture without inheriting its tests.
    for _name in ('setUp', 'tearDown', 'cmd', 'git_seed', 'write_source', 'commit_source',
                  'until', 'request', 'record', 'published', 'accepted_result'):
        locals()[_name] = getattr(bridge_tests.Integration, _name)

    def prepare(self, bad_hash=False):
        shutil.copy(ROOT / 'run.py', self.seed / 'run.py')
        shutil.copytree(ROOT / 'cont', self.seed / 'cont', ignore=shutil.ignore_patterns('__pycache__'))
        cfg = config()
        cfg['configs'] = {'QQ': cfg['configs']['QQ']}
        cfg['cases'] = cfg['cases'][:1]
        cfg['horizons'] = [101, 102]
        cfg['acceptance']['disk_floor_bytes'] = 0
        case = cfg['cases'][0]
        case['input_path'] = 'results/synthetic_fixture/state.npz'
        path = self.work / case['input_path']
        path.parent.mkdir()
        old = {'id': case['source_case_id'], 'phase_index': case['phase_index'],
               'mixed': False, 'phi': np.pi / 2}
        np.savez_compressed(path, rho=np.eye(216, dtype=complex) / 216,
                            time=100., case_json=json.dumps(old))
        case['input_sha256'] = '0' * 64 if bad_hash else sha(path)
        (self.seed / 'config.json').write_text(json.dumps(cfg))
        return self.commit_source('Synthetic CONT test input')

    def test_continuation_report_verified_from_remote_git(self):
        commit = self.prepare()
        rid = 'cont_synthetic_success'
        self.request(rid, commit)
        self.until(lambda: self.published(rid))
        received = self.accepted_result(rid, commit)
        self.assertTrue(received['execution_succeeded'], received['artifacts'].get('output.log'))
        metrics = json.loads(received['artifacts']['files/metrics.json'])
        self.assertEqual(metrics['source_commit'], commit)
        self.assertEqual(metrics['run_id'], rid)
        self.assertTrue(metrics['numerical_checks_passed'])
        case = metrics['cases']['QQ_phi1']
        self.assertEqual(case['summary']['final_time'], 102)
        self.assertEqual(len(case['summary']['endpoint_tests']), 2)
        self.assertFalse(case['summary']['stationarity']['passed'])
        self.assertEqual(case['coverage']['source_records'], 11)
        self.assertEqual(case['coverage']['published_series_records'], 3)
        self.assertEqual(case['coverage']['observable_count'], 164)
        manifest = json.loads(received['artifacts']['files/data_manifest.json'])
        self.assertEqual(sum(x['format'] == 'npz' for x in manifest['full_files']), 3)
        self.assertFalse(any(name.endswith('.npz') for name in received['artifacts']))
        self.assertTrue(all(len(x['sha256']) == 64 for x in manifest['full_files']))

    def test_checkpoint_mismatch_publishes_failure_not_success(self):
        commit = self.prepare(bad_hash=True)
        rid = 'cont_synthetic_bad_hash'
        self.request(rid, commit)
        self.until(lambda: self.published(rid))
        received = self.accepted_result(rid, commit)
        self.assertFalse(received['execution_succeeded'])
        self.assertEqual(received['report']['job']['exit_code'], 1)
        metrics = json.loads(received['artifacts']['files/metrics.json'])
        self.assertIn('checksum mismatch', metrics['failure']['message'])
        self.assertEqual(metrics['cases']['QQ_phi1']['status'], 'not_started')


class ReportContracts(unittest.TestCase):
    def test_subsample_spike_is_retained_in_extrema(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            full, report = root / 'full', root / 'report'
            (full / 'cases').mkdir(parents=True)
            report.mkdir()
            save_json(full / 'cases/test_schema.json', {'observable_names': ['signal']})
            records = [{'time': 100 + i * .2, 'values': [99 if i == 2 else 0]} for i in range(6)]
            (full / 'cases/test.jsonl').write_text(''.join(json.dumps(x) + '\n' for x in records))
            stats, coverage, _ = export_series(full, report, 'test', config()['report_policy'])
            with (report / 'series/test.csv').open() as handle:
                rows = list(csv.DictReader(handle))
            self.assertTrue(all(float(x['signal']) == 0 for x in rows))
            with (report / 'extrema/test.csv').open() as handle:
                peak = list(csv.DictReader(handle))[0]
            self.assertEqual(float(peak['max']), 99)
            self.assertAlmostEqual(float(peak['max_time']), 100.4)
            self.assertEqual(coverage['records_covered_by_extrema'], 6)
            self.assertEqual(stats['signal']['max'], 99)

    def test_checkpoint_path_cannot_escape_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            for path in ('../secret', '/etc/passwd', 'code/run.py'):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    input_state({'input_path': path}, Path(directory), None)

    def test_longest_four_case_report_fits_transport_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            full = root / 'full'
            (full / 'cases').mkdir(parents=True)
            cfg = config()
            rng = np.random.default_rng(414)
            times = 100 + np.arange(4501) * .2
            names = ['synthetic_observable_%03d' % i for i in range(164)]
            for case in cfg['cases']:
                cid = case['id']
                save_json(full / 'cases' / (cid + '_schema.json'), {'observable_names': names})
                with (full / 'cases' / (cid + '.jsonl')).open('w') as handle:
                    for t in times:
                        values = rng.normal(size=164) * 1e-8
                        handle.write(json.dumps({'time': float(t), 'values': values.tolist()}) + '\n')
            metadata = {'run_id': 'cont_export_budget_test', 'source_commit': '1' * 40,
                        'mode': 'continuation', 'task_exit_code': 1}
            # A synthetic interrupted series exercises the same report writer.
            size = write_report(root, cfg, metadata, failure={'type': 'Synthetic', 'message': 'Test only'})
            # Allow 2 MiB for real snapshot inventory and diagnostics not constructed here.
            self.assertLess(size['bytes'] + 2 * 1024**2, cfg['report_policy']['max_total_bytes'])
            self.assertLess(size['max_file_bytes'], cfg['report_policy']['max_file_bytes'])
            print('CONT maximum-duration synthetic report budget:', json.dumps(size), flush=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
