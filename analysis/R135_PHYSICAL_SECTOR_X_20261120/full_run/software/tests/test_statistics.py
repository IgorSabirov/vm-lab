"""Manufactured streams for estimator correctness; no science acceptance."""
import copy
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from r135 import statistics as stat


def stream(chain, seed, role, n=96):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        field = np.exp(2j * np.pi * rng.integers(3, size=(4, 4, 4)) / 3 + 0.05j * rng.normal(size=(4, 4, 4)))
        rows.append(dict(chain_id=chain, seed=seed, config_id=f'{chain}:{i}',
                         grid_id='2x4x4x4', geometry=[2, 4, 4, 4], beta=5.7,
                         start='cold' if seed % 2 else 'hot', role=role, sweep=1000 + i * 8,
                         burn_sweeps=1000, plaquette=float(rng.normal(0.5, 0.02)),
                         polyakov_abs=float(abs(field.mean())),
                         link_verification='UNVERIFIED_LINKS',
                         counts_by_cut=[stat.count_windows(field, 1, c) for c in (0., np.pi / 30)]))
    return rows


class StatisticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cal = stream('c1', 21, 'calibration') + stream('c2', 22, 'calibration')
        cls.lock = stat.freeze_calibration(cls.cal)
        cls.held = stream('h1', 23, 'heldout') + stream('h2', 24, 'heldout')

    def test_vectorized_cumulant_matches_existing_independent_estimator(self):
        rng = np.random.default_rng(532)
        rows = rng.integers(0, 100, (21, 81))
        actual = stat.connected_many(rows)
        expected = [stat.estimate(row)['connected_even'] for row in rows]
        np.testing.assert_allclose(actual, expected, atol=2e-16)
        uniform = np.ones((1, 81), dtype=np.int64)
        self.assertAlmostEqual(float(stat.connected_many(uniform)[0]), 0, places=14)

    def test_known_ar1_autocorrelation(self):
        rng = np.random.default_rng(1451)
        x = np.zeros(40000)
        for i in range(1, len(x)):
            x[i] = 0.8 * x[i - 1] + rng.normal()
        answer = stat.autocorrelation(x[1000:])
        self.assertAlmostEqual(answer['tau_int'], (1 + 0.8) / (2 * (1 - 0.8)), delta=0.8)
        self.assertTrue(answer['stable'])
        self.assertIsNone(stat.autocorrelation(np.ones(100))['tau_int'])

    def test_freeze_uses_equal_chain_counts_and_no_heldout(self):
        unequal = self.cal + stream('c3', 25, 'calibration', n=16)
        lock = stat.freeze_calibration(unequal)
        self.assertEqual(lock['n_per_chain'], 16)
        values = [row['plaquette'] for chain in ('c1', 'c2', 'c3')
                  for row in [r for r in unequal if r['chain_id'] == chain][:16]]
        self.assertEqual(lock['lower_cut'], np.quantile(values, .25))
        with self.assertRaisesRegex(ValueError, 'Heldout'):
            stat.freeze_calibration(self.held)

    def test_tampering_or_identity_leak_is_rejected(self):
        bad = copy.deepcopy(self.lock)
        bad['upper_cut'] += 0.1
        with self.assertRaisesRegex(ValueError, 'altered'):
            stat.verify_calibration(bad)
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            stat.validate_rows(self.held + [self.held[0]])
        badrows = copy.deepcopy(self.held)
        badrows[0]['role'] = 'calibration'
        with self.assertRaises(ValueError):
            stat.analyze_chains(badrows, self.lock, draws=20)
        seed_leak = copy.deepcopy(self.held)
        for row in seed_leak:
            if row['chain_id'] == 'h1':
                row['seed'] = 21
        with self.assertRaisesRegex(ValueError, 'seeds overlap'):
            stat.analyze_chains(seed_leak, self.lock, draws=20)

    def test_block_bootstrap_recomputes_pooled_window_cumulant(self):
        result = stat.block_bootstrap(self.held, self.lock, 0, 6, draws=100, seed=91)
        lo = sum((stat.pooled_counts(r) for r in self.held if r['plaquette'] <= self.lock['lower_cut']),
                 np.zeros(81, dtype=np.int64))
        hi = sum((stat.pooled_counts(r) for r in self.held if r['plaquette'] >= self.lock['upper_cut']),
                 np.zeros(81, dtype=np.int64))
        expected = stat.estimate(hi)['connected_even'] - stat.estimate(lo)['connected_even']
        self.assertAlmostEqual(result['D4'], expected, places=15)
        np.testing.assert_array_equal(result['pooled_counts'], [lo, hi])
        repeated = stat.block_bootstrap(self.held, self.lock, 0, 6, draws=100, seed=91)
        self.assertEqual(result['bootstrap_values'], repeated['bootstrap_values'])
        self.assertEqual(set(result['blocks']), {'h1', 'h2'})
        self.assertEqual(len(result['marginal_differences']), 14)

    def test_unverified_or_underpowered_input_cannot_pass_science(self):
        result = stat.analyze_chains(self.held, self.lock, draws=20)
        self.assertEqual(result['scientific_status'], 'INCONCLUSIVE')
        for row in result['estimates']:
            self.assertEqual(row['classification'], 'INCONCLUSIVE')
            self.assertIn('UNVERIFIED_LINKS', row['reasons'])
            self.assertIn('NO_INDEPENDENT_PLAQUETTE_COMPARATOR', row['reasons'])
            self.assertIn('FEWER_THAN_4000_PREREGISTERED_BOOTSTRAPS', row['reasons'])
            self.assertEqual(set(row['leave_one_chain_out']), {'h1', 'h2'})

    def test_chronology_and_coverage_are_validated(self):
        altered = copy.deepcopy(self.held)
        altered[1]['sweep'] = altered[0]['sweep']
        with self.assertRaisesRegex(ValueError, 'chronological'):
            stat.validate_rows(altered)
        altered = copy.deepcopy(self.held)
        altered[0]['counts_by_cut'][0]['axes']['x']['counts'][0] += 1
        with self.assertRaisesRegex(ValueError, 'coverage'):
            stat.validate_rows(altered)


if __name__ == '__main__':
    unittest.main()
