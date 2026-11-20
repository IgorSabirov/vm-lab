"""Small manufactured link arrays; these are not physical SU(3) ensembles."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from r135 import lattice


class WilsonTests(unittest.TestCase):
    def test_cold_and_fixed_holonomy(self):
        chain = lattice.WilsonChain((3, 4, 4, 4), 5.7, 135)
        self.assertAlmostEqual(lattice.plaquette(chain.links), 1)
        np.testing.assert_allclose(lattice.polyakov(chain.links), 1)
        phases = np.array([0.3, -0.1, -0.2])
        chain.links[..., 0, :, :] = np.diag(np.exp(1j * phases / 3))
        np.testing.assert_allclose(lattice.polyakov(chain.links), np.exp(1j * phases).mean(), atol=1e-14)
        self.assertAlmostEqual(lattice.plaquette(chain.links), 1)

    def test_staple_matches_full_action_for_all_directions(self):
        chain = lattice.WilsonChain((2, 3, 2, 2), 5.75, 511, start="hot")
        self.assertAlmostEqual(lattice.plaquette(chain.links), lattice.plaquette_reference(chain.links), places=14)
        rng = np.random.default_rng(271)
        for mu in range(4):
            for pair in lattice.PAIRS:
                site = (1, 2, 0, 1)
                previous = chain.links[site + (mu,)].copy()
                next_value = lattice.su2_proposal(rng, 0.8, pair) @ previous
                local_delta = -chain.beta / 3 * np.trace((next_value - previous) @ lattice.staple(chain.links, site, mu)).real
                original_action = lattice.wilson_action(chain.links, chain.beta)
                chain.links[site + (mu,)] = next_value
                actual_delta = lattice.wilson_action(chain.links, chain.beta) - original_action
                self.assertAlmostEqual(float(local_delta), actual_delta, places=10)
                chain.links[site + (mu,)] = previous

    def test_local_gauge_center_conjugation(self):
        rng = np.random.default_rng(819)
        u = lattice.initial_links((2, 4, 4, 4), "hot", rng)
        gauge = lattice.haar_su3(rng, u.shape[:4])
        v = lattice.gauge_transform(u, gauge)
        np.testing.assert_allclose(lattice.polyakov(v), lattice.polyakov(u), atol=2e-15)
        self.assertAlmostEqual(lattice.plaquette(v), lattice.plaquette(u), places=14)
        z = np.exp(2j * np.pi / 3)
        centered = lattice.center_transform(u)
        np.testing.assert_allclose(lattice.polyakov(centered), z * lattice.polyakov(u), atol=2e-15)
        self.assertAlmostEqual(lattice.plaquette(centered), lattice.plaquette(u), places=14)
        np.testing.assert_allclose(lattice.polyakov(np.conjugate(u)), np.conjugate(lattice.polyakov(u)))
        field = lattice.polyakov(u)
        from r135.statistics import count_windows, estimate
        def cumulant(f):
            entry = count_windows(f, 1)
            return estimate(sum(np.array(entry['axes'][axis]['counts']) for axis in 'xyz'))
        self.assertAlmostEqual(cumulant(field)['connected_even'], cumulant(z * field)['connected_even'], places=14)
        self.assertAlmostEqual(cumulant(field)['raw_odd'], -cumulant(np.conjugate(field))['raw_odd'], places=14)

    def test_checkpoint_continuation_is_exact(self):
        chain = lattice.WilsonChain((2, 2, 2, 2), 5.7, 109, start="hot")
        chain.sweep(2)
        with tempfile.TemporaryDirectory() as directory:
            metadata = chain.checkpoint(directory)
            restored = lattice.WilsonChain.resume(metadata)
            chain.sweep(2)
            restored.sweep(2)
            np.testing.assert_array_equal(chain.links, restored.links)
            self.assertEqual(chain.rng.bit_generator.state, restored.rng.bit_generator.state)
            self.assertEqual(chain.accepted, restored.accepted)
            with self.assertRaisesRegex(ValueError, 'immutable'):
                restored.checkpoint(directory)
            data = json.loads(metadata.read_text())
            data['beta'] = 6
            metadata.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'altered'):
                lattice.WilsonChain.resume(metadata)

    def test_beta_zero_acceptance_and_group_preservation(self):
        chain = lattice.WilsonChain((2, 2, 2, 2), 0, 112, start="hot")
        chain.sweep(3)
        self.assertEqual(chain.attempted, chain.accepted)
        lattice.validate_links(chain.links)

    def test_invalid_group_is_not_silently_projected(self):
        u = lattice.initial_links((2, 2, 2, 2), "cold", np.random.default_rng(0))
        u[0, 0, 0, 0, 0, 0, 0] = 1.01
        with self.assertRaisesRegex(ValueError, 'outside SU'):
            lattice.validate_links(u)
        with self.assertRaises(ValueError):
            lattice.WilsonChain((1, 2, 2, 2), 5.7, 1)

    def test_measure_source_checks_and_periodic_counts(self):
        chain = lattice.WilsonChain((2, 4, 4, 4), 5.7, 121, start="hot")
        row = lattice.measure(chain.links, chain_id='test', config_id='test:0', sweep=0,
                              role='calibration', beta=5.7, seed=121, start='hot')
        self.assertEqual(row['link_verification'], 'VERIFIED_LINKS')
        self.assertLess(row['link_checks']['gauge_polyakov_max_abs'], 1e-10)
        for item in row['counts_by_cut']:
            for axis in 'xyz':
                self.assertEqual(item['axes'][axis]['total'], 64)
                self.assertEqual(sum(item['axes'][axis]['counts']), item['axes'][axis]['accepted'])


if __name__ == '__main__':
    unittest.main()
