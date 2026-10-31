"""Synthetic end-to-end worker checks; no full-network stationary solve."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from e002e_exp.model import make_small
from e002e_exp.plan import workload
from e002e_exp.task import run
from e002e_exp.export import verify_report
from test_e002e import small_case


def config(work, stage):
    return dict(mode='production', stage=stage, source_commit='0'*40, expected_workload=workload(work),
                forecast=dict(expected_seconds=1., lower_seconds=.001, upper_seconds=30.),
                numerics=dict(solver=dict(method='lu', rtol=1e-12, atol=1e-14),
                              refinement_solver=dict(method='gmres_ilu', rtol=1e-12, atol=1e-14),
                              state_tolerance=1e-10, estimate_condition=True,
                              error_envelope=dict(absolute_floor=1e-10, difference_multiplier=10),
                              refinement_limits=dict(vector_inf=1e-9, observable_absolute=1e-9, observable_relative=1e-7),
                              qrt=dict(horizon=.1, dt_fine=.002, dt_coarse=.004, sample_interval=.02,
                                       checkpoint_stride_steps=20, absolute_tolerance=1e-8, relative_tolerance=1e-5)))


class WorkerIntegration(unittest.TestCase):
    def test_small_stage_exports_all_declared_cases(self):
        work = dict(small=[small_case(), small_case(8, 6, v=0.)], full=[], frequency=[], correlations=[])
        cfg = config(work, 'G')
        with tempfile.TemporaryDirectory() as temp, patch('e002e_exp.task.preflight', return_value=(work, {'comparable': True})):
            result = run(cfg, Path(temp))
            self.assertIsNone(result['failure'])
            self.assertEqual(result['actual_counts'], workload(work))
            self.assertEqual(result['runtime_gate']['status'], 'PASS')
            self.assertIn('VERIFIED', verify_report(Path(temp)/'report')['status'])
            rec = json.loads((Path(temp)/'report/small_000.json').read_text())
            self.assertIsNotNone(rec['conditional']['F_over_p_e']['uncertainty'])

    def test_synthetic_baseline_frequency_and_qrt(self):
        case = dict(id='full_synthetic', model='SYNTHETIC', phi_over_pi=.5, epsilon=.17,
                    node_noise=.05, m6_v_over_J=1., tasks=['NESS'])
        work = dict(small=[], full=[case], frequency=[dict(base_id=case['id'], omega_over_J=w) for w in (-.5, 0., .5)],
                    correlations=[dict(base_id=case['id'], input=n) for n in ('J_h', 'P_m6_N2', 'K')])
        model = make_small(small_case())
        model['observables'].update(P_m6_N2=model['observables']['p_e'], h6=model['observables']['J_h'])
        cfg = config(work, 'baseline')
        with tempfile.TemporaryDirectory() as temp, patch('e002e_exp.task.preflight', return_value=(work, {'comparable': True})), patch('e002e_exp.task.make_full', return_value=model):
            result = run(cfg, Path(temp))
            self.assertIsNone(result['failure']); self.assertEqual(result['actual_counts'], workload(work))
            self.assertTrue((Path(temp)/'report/full_synthetic_qrt.npz').exists())
            self.assertEqual(len(json.loads((Path(temp)/'report/responses.json').read_text())), 3)
            verify_report(Path(temp)/'report')


if __name__ == '__main__':
    unittest.main()
