"""Regressions for independently checked Copilot review findings."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from e002e_exp.plan import ROOT, inventory, validate_predictions, full_physical_key
from e002e_exp.analysis import f2_differences, evaluate_predictions
from e002e_exp.numerics import refinement_check
from e002e_exp.runtime import memory_preflight
from e002e_exp.export import write_full_manifest, write_manifest, verify_report
from e002e_exp.task import run
from test_e002e import small_case, full_case
from test_e002e_integration import config


def predictions():
    r = json.loads((ROOT/'experiments/e002e/f2_prereg_predictions.template.json').read_text())
    r.update(status='FROZEN', code_commit='a'*40, created_at_utc='2026-10-31T00:00:00Z', frozen_at_utc='2026-10-31T00:00:01Z',
             training_inputs=[dict(id='train', block='G', report_commit='b'*40, sha256='c'*64)])
    ids = r['heldout_case_ids']
    r['predictions'] = [dict(prediction_id='p1', model='QS/RR', physical_case_ids=ids,
                            observable_definition=dict(kind='linear_combination', observable='j6', linear_terms=[dict(case_id=i, coefficient=1./len(ids)) for i in ids]),
                            parameter_domain={'frozen': True}, prediction_type='value', expected_value_or_sign_or_interval=.3,
                            tolerance_and_error_rule=dict(absolute_tolerance=.01, error_rule='interval_with_numerical_uncertainty'),
                            training_input_ids=['train'], candidate_model_derivation='declared test candidate', denominator_validity_if_ratio='p>floor with propagated error',
                            outcome_on_failure='reject candidate', confirmatory_or_exploratory='confirmatory')]
    return r


class ReviewRegressions(unittest.TestCase):
    def test_finite_tolerance_and_external_cap(self):
        r = predictions(); validate_predictions(r, 'a'*40, {'p1': .02})
        for value in (float('inf'), float('nan'), 1e300, -.1, '0.01', True):
            bad = copy.deepcopy(r); bad['predictions'][0]['tolerance_and_error_rule']['absolute_tolerance'] = value
            with self.assertRaises(ValueError):
                validate_predictions(bad, 'a'*40, {'p1': .02})
        with self.assertRaises(ValueError):
            validate_predictions(r, 'a'*40)

    def test_bad_time_order_and_self_declared_training_rejected(self):
        r = predictions(); r['frozen_at_utc'] = '2026-10-30T00:00:00Z'
        with self.assertRaises(ValueError): validate_predictions(r, 'a'*40, {'p1': .02})
        r = predictions(); r['allowed_training_blocks'].append('SECRET_F2')
        r['training_inputs'][0]['block'] = 'SECRET_F2'
        with self.assertRaises(ValueError): validate_predictions(r, 'a'*40, {'p1': .02})

    def test_acceptable_residuals_do_not_override_refinement_disagreement(self):
        # Both states can lie in the kernel of a degenerate zero generator;
        # residual and trace alone cannot accept their distinct observable.
        x = np.array([.5, .5]); y = np.array([.6, .4])
        limits = dict(vector_inf=1e-6, observable_absolute=1e-6, observable_relative=1e-5)
        result = refinement_check(x, y, {'p': .5}, {'p': .6}, limits)
        self.assertFalse(result['pass_gate']); self.assertEqual(result['status'], 'NUMERICALLY_UNRESOLVED')

    def test_baseline_duplicates_overrides_and_error_propagation(self):
        b = dict(id='b', case=full_case(epsilon=0.), raw=dict(J_h=.2, h6=.1, P_m6_N2=.25),
                 conditional={'j6': {'value': .4, 'uncertainty': .002}},
                 primitive_uncertainty=dict(J_h=.001, h6=.001, P_m6_N2=.001))
        r = copy.deepcopy(b); r['id'] = 'r'; r['case']['m6_v_over_J'] = .5; r['raw']['J_h'] = .21
        b['physical_key'] = full_physical_key(b['case']); r['physical_key'] = full_physical_key(r['case'])
        baseline = dict(status='VERIFIED_GITHUB', records=[b])
        result = f2_differences([r], baseline)[0]
        self.assertAlmostEqual(result['changes']['J_h'], .01)
        self.assertAlmostEqual(result['changes']['J_h_uncertainty'], .002)
        bad = copy.deepcopy(baseline); bad['records'].append(b)
        with self.assertRaises(ValueError): f2_differences([r], bad)
        bad = copy.deepcopy(baseline); bad['records'][0]['case']['sink'] = 1.
        with self.assertRaises(ValueError): f2_differences([r], bad)

    def test_memory_budget_enforced(self):
        env = dict(memory_limit='1000', memory_current='100', memory_available='100 kB')
        budget = dict(peak_additional_bytes=500, reserve_bytes=100, measured_peak_rss_bytes=300, simultaneous_factor_storage_bytes=200)
        self.assertEqual(memory_preflight(budget, env)['status'], 'PASS')
        budget['peak_additional_bytes'] = 850
        with self.assertRaises(MemoryError): memory_preflight(budget, env)
        budget['measured_peak_rss_bytes'] = None
        with self.assertRaises(ValueError): memory_preflight(budget, env)

    def test_full_data_corruption_and_deletion_detected(self):
        for corrupt in (True, False):
            with tempfile.TemporaryDirectory() as temp:
                report = Path(temp)/'report'; full = Path(temp)/'full'; report.mkdir(); full.mkdir()
                p = full/'state.npz'; np.savez(p, x=np.array([1., 2.]))
                write_full_manifest(report, full); write_manifest(report)
                self.assertEqual(verify_report(report, full)['full_data'], 'VERIFIED')
                if corrupt: p.write_bytes(p.read_bytes()+b'bad')
                else: p.unlink()
                with self.assertRaises(ValueError): verify_report(report, full)

    def test_preflight_failure_is_persisted(self):
        work = dict(small=[small_case()], full=[], frequency=[], correlations=[])
        with tempfile.TemporaryDirectory() as temp, patch('e002e_exp.task.preflight', side_effect=ValueError('invalid provenance')):
            with self.assertRaises(ValueError): run(config(work, 'G'), Path(temp))
            status = json.loads((Path(temp)/'report/status.json').read_text())
            self.assertEqual(status['status'], 'FAILED')
            self.assertIn('invalid provenance', (Path(temp)/'report/terminal_failure.json').read_text())

    def test_final_export_failure_is_persisted_and_existing_run_untouched(self):
        work = dict(small=[small_case()], full=[], frequency=[], correlations=[])
        with tempfile.TemporaryDirectory() as temp, patch('e002e_exp.task.preflight', return_value=(work, {'comparable': True})), patch('e002e_exp.task.write_result', side_effect=ValueError('export failed')):
            with self.assertRaises(ValueError): run(config(work, 'G'), Path(temp))
            p = Path(temp)/'report/terminal_failure.json'; before = p.read_bytes()
            self.assertIn(b'export failed', before)
            with self.assertRaises(FileExistsError): run(config(work, 'G'), Path(temp))
            self.assertEqual(before, p.read_bytes())

    def test_f2_evaluation_failure_is_persisted(self):
        work = dict(small=[], full=[], frequency=[], correlations=[])
        with tempfile.TemporaryDirectory() as temp, patch('e002e_exp.task.preflight', return_value=(work, {'comparable': True})), patch('e002e_exp.task.pinned_file', return_value={}):
            cfg = config(work, 'F2'); cfg['baseline_report'] = {}; cfg['predictions'] = {}
            with self.assertRaises((ValueError, KeyError)): run(cfg, Path(temp))
            self.assertEqual(json.loads((Path(temp)/'report/status.json').read_text())['status'], 'FAILED')


if __name__ == '__main__': unittest.main()
