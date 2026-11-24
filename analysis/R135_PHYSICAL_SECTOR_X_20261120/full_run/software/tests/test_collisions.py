from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from r135.collisions import (Distribution, PolynomialAmplitude, ThermalTransfer,
    collision_2to2, decay_table, two_body_width, cannibal_rate)
from r135.common import InputError


def amplitude():
    return {"source": "constant scalar diagnostic matrix element", "normalization": "one distinct scalar per leg",
            "coefficient_units": "dimensionless", "sqrt_s_max_MeV": 100.,
            "terms": [{"real": 1., "s_power": 0, "t_power": 0, "portal": 1}]}


def distribution(stat="MB", t=1.):
    return {"kind": "thermal", "statistics": stat, "mass_MeV": 0., "T_MeV": t}


class CollisionTests(unittest.TestCase):
    def test_quantum_detailed_balance_and_energy_conservation(self):
        for stat in ("MB", "BE", "FD"):
            r = collision_2to2([distribution(stat) for _ in range(4)], amplitude(),
                               p_max_MeV=[5, 5], order=3)
            self.assertLess(r["relative_equilibrium_residual"], 1e-12)
        r = collision_2to2([distribution(t=2), distribution(t=2), distribution(t=.5), distribution(t=.5)], amplitude(), p_max_MeV=[8, 8], order=3)
        self.assertLess(abs(sum(r["energy_MeV5"])), 1e-12*max(abs(x) for x in r["energy_MeV5"]))
        self.assertGreater(sum(r["energy_MeV5"][2:]), 0)

    def test_invariant_measure_against_massless_analytic_rate(self):
        empty = {"kind": "tabulated", "statistics": "MB", "mass_MeV": 0.,
                 "p_MeV": [0, 1, 100], "occupation": [0, 0, 0], "tail": "zero"}
        r = collision_2to2([distribution(), distribution(), empty, empty], amplitude(),
                           p_max_MeV=[14, 14], order=9)
        expected = 1/(128*np.pi**5)
        self.assertAlmostEqual(r["forward_MeV4"]/expected, 1, delta=6e-5)
        self.assertAlmostEqual(sum(r["energy_MeV5"][2:])/expected, 4, delta=1e-3)

    def test_interference_is_added_before_squaring(self):
        a = amplitude()
        a["terms"].append({"real": -1., "s_power": 0, "t_power": 0, "portal": 2})
        m = PolynomialAmplitude(a)
        self.assertEqual(m.squared(1., -.1, "11full"), 0.)
        self.assertEqual(m.squared(1., -.1, "11add"), 2.)

    def test_dimensions_and_phase_bounds_cannot_be_ignored(self):
        a = amplitude()
        a["terms"][0]["s_power"] = 1
        with self.assertRaisesRegex(InputError, "unit"):
            PolynomialAmplitude(a)
        with self.assertRaises(InputError):
            cannibal_rate(1., 1., 1., 1., degeneracy=-1.)
        model = ThermalTransfer({"source": "empty isolated diagnostic", "thermal_channels": []})
        with self.assertRaisesRegex(InputError, "phase fraction"):
            model.at({"T_X_MeV": 1, "T_gamma_MeV": 1, "T_nu_MeV": 1, "T_free_MeV": 1, "phase_fraction": 1.1})

    def test_computed_moment_table_and_equilibrium_validation(self):
        axes = np.array([.5, 1., 2.])
        q = axes[:, None]-axes[None, :]
        channel = {"id": "moment", "source": "independently computed diagnostic grid", "recipient": "nu",
                   "kind": "tabulated_moment", "unit": "MeV^4/s", "T_X_MeV": axes.tolist(),
                   "T_recipient_MeV": axes.tolist(), "Q_MeV4_s": {c: (k*q).tolist() for c, k in [("00", 0), ("10", 1), ("01", 4), ("11full", 9)]}}
        model = ThermalTransfer({"source": "diagnostic", "thermal_channels": [channel]})
        state = {"T_X_MeV": 1.3, "T_gamma_MeV": 1., "T_nu_MeV": .7, "T_free_MeV": 0., "phase_fraction": .2}
        self.assertAlmostEqual(model.at(state)["nu"], 9*.6)
        state["T_nu_MeV"] = state["T_X_MeV"]
        self.assertAlmostEqual(model.at(state)["nu"], 0.)
        channel["Q_MeV4_s"]["10"][1][1] = .1
        with self.assertRaisesRegex(InputError, "detailed balance"):
            ThermalTransfer({"source": "diagnostic", "thermal_channels": [channel]})

    def test_decay_threshold_branching_and_stable_relic(self):
        self.assertEqual(two_body_width(2, [1, 1], 1), 0.)
        self.assertAlmostEqual(two_body_width(10, [0, 0], 4), 4/(160*np.pi))
        species = {"id": "test", "source": "diagnostic", "mass_MeV": 2., "channels": [
            {"id": "a", "source": "diagnostic", "kind": "supplied_width", "recipient": "gamma", "width_MeV": 1., "daughter_masses_MeV": [0, 0]},
            {"id": "b", "source": "diagnostic", "kind": "supplied_width", "recipient": "nu", "width_MeV": 3., "daughter_masses_MeV": [0, 0]}]}
        rows = decay_table([species])
        self.assertEqual(sum(x["branching_fraction"] for x in rows), 1.)
        species["channels"] = []
        self.assertTrue(decay_table([species])[0]["stable"])

    def test_thermal_mixed_moment_uses_identical_state(self):
        model = ThermalTransfer({"source": "diagnostic matched rate", "thermal_channels": [{
            "id": "two_portals", "recipient": "gamma", "kind": "matched_power_law", "power": 4,
            "coefficient_unit": "MeV^0/s", "amplitudes": [0, 1, 2],
            "T_range_MeV": [.01, 10], "source": "diagnostic",
            "phase_weights": {"hot": 1, "cold": 3}}]})
        state = {"T_X_MeV": 2., "T_gamma_MeV": 1., "T_nu_MeV": 1., "T_free_MeV": 1., "phase_fraction": .5}
        full, additive = model.at(state, "11full"), model.at(state, "11add")
        self.assertEqual(full["gamma"]-additive["gamma"], 4*2*(16-1))
        self.assertEqual(sum(full.values()), 0.)
        state["T_gamma_MeV"] = state["T_X_MeV"]
        self.assertEqual(model.at(state)["gamma"], 0.)


if __name__ == "__main__":
    unittest.main()
