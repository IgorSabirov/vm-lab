from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from r135.common import InputError, OpenInput
from r135.neutrino_rates import (BinnedSpectrum, ThermalSpectrum, TabulatedSpectrum,
    NEUTRON_PROTON_GAP_MEV, ELECTRON_MASS_MEV, nucleon_rates, weak_rates_from_history)
from r135.observations import validate_weak_rates


class NeutrinoRateTests(unittest.TestCase):
    def test_vacuum_normalization_and_inverse_rates(self):
        empty = BinnedSpectrum([0., 10.], [0.])
        result = nucleon_rates(0., empty, empty, neutron_lifetime_s=880.)
        self.assertAlmostEqual(result["lambda_n_to_p_s_inv"], 1/880., delta=2e-13)
        self.assertEqual(result["lambda_p_to_n_s_inv"], 0.)
        self.assertEqual(result["channels_s_inv"]["n_nu_to_p_e"], 0.)
        self.assertFalse(result["production_precision_validated"])

    def test_all_inverse_pairs_obey_chemical_detailed_balance(self):
        pairs = (("n_nu_to_p_e", "p_e_to_n_nu"),
                 ("n_positron_to_p_antinu", "p_antinu_to_n_positron"),
                 ("neutron_decay", "inverse_neutron_decay"))
        for temperature, mu_e, mu_nu in ((.3, 0., 0.), (1., .12, -.09), (3., -.2, .3)):
            result = nucleon_rates(temperature, ThermalSpectrum(temperature, mu_nu),
                                    ThermalSpectrum(temperature, -mu_nu), mu_e_MeV=mu_e)
            expected = np.exp(-(NEUTRON_PROTON_GAP_MEV-mu_e+mu_nu)/temperature)
            for forward, backward in pairs:
                actual = result["channels_s_inv"][backward]/result["channels_s_inv"][forward]
                self.assertAlmostEqual(actual/expected, 1., delta=1e-8)
            self.assertAlmostEqual(result["lambda_p_to_n_s_inv"]/result["lambda_n_to_p_s_inv"]/expected,
                                   1., delta=1e-8)

    def test_pauli_blocking_and_antineutrino_threshold(self):
        empty = BinnedSpectrum([0., 10.], [0.])
        threshold = NEUTRON_PROTON_GAP_MEV+ELECTRON_MASS_MEV
        low_filled = BinnedSpectrum([0., threshold-1e-5, 10.], [1., 0.])
        result = nucleon_rates(.2, empty, low_filled)
        self.assertEqual(result["channels_s_inv"]["p_antinu_to_n_positron"], 0.)
        self.assertEqual(result["channels_s_inv"]["neutron_decay"], 0.)
        self.assertGreater(result["channels_s_inv"]["inverse_neutron_decay"], 0.)
        above = BinnedSpectrum([0., threshold+1., 10.], [1., 0.])
        self.assertGreater(nucleon_rates(.2, empty, above)["channels_s_inv"]["p_antinu_to_n_positron"], 0.)

    def test_same_energy_spectra_are_not_interchangeable(self):
        edges = np.array([0., .5, 1., 2., 4., 8.])
        original = np.array([.4, .3, .15, .05, .005])
        altered = original.copy()
        energy_weights = np.diff(edges**4)
        altered[2] += .3
        altered[3] -= .3*energy_weights[2]/energy_weights[3]
        self.assertAlmostEqual(float(energy_weights @ original), float(energy_weights @ altered), places=13)
        anti = ThermalSpectrum(.7)
        first = nucleon_rates(.7, BinnedSpectrum(edges, original), anti)
        second = nucleon_rates(.7, BinnedSpectrum(edges, altered), anti)
        relative = abs(first["lambda_n_to_p_s_inv"]/second["lambda_n_to_p_s_inv"]-1)
        self.assertGreater(relative, 1e-3)

    def test_tabulated_spectrum_refinement_converges_to_exact_thermal(self):
        target = nucleon_rates(.7, ThermalSpectrum(.9), ThermalSpectrum(.6))
        errors = []
        for count in (48, 96, 192):
            energy = np.linspace(0., 36., count)
            nu = ThermalSpectrum(.9)(energy)
            anti = ThermalSpectrum(.6)(energy)
            nu[-1] = anti[-1] = 0.
            result = nucleon_rates(.7, TabulatedSpectrum(energy, nu, tail="zero"),
                                    TabulatedSpectrum(energy, anti, tail="zero"))
            errors.append(abs(result["lambda_n_to_p_s_inv"]/target["lambda_n_to_p_s_inv"]-1))
        self.assertLess(errors[1], errors[0]/3)
        self.assertLess(errors[2], errors[1]/3)
        self.assertLess(errors[-1], .01)

    def test_unknown_support_and_invalid_occupancy_are_rejected(self):
        with self.assertRaises(OpenInput):
            TabulatedSpectrum([.1, 1.], [.5, 0.], tail="zero")
        with self.assertRaises(OpenInput):
            TabulatedSpectrum([0., 1.], [.5, .1], tail="zero")
        with self.assertRaises(InputError):
            BinnedSpectrum([0., 1.], [1.1])
        band = TabulatedSpectrum([1., 2., 3.], [.2, .1, 0.], low_energy="zero", tail="zero")
        self.assertEqual(band(.5), 0.)
        self.assertEqual(band(4.), 0.)

    def test_vacuum_quadrature_against_closed_phase_space_formula(self):
        empty = BinnedSpectrum([0., 10.], [0.])
        delta, me = NEUTRON_PROTON_GAP_MEV, ELECTRON_MASS_MEV
        gap = delta/me
        analytic = me**5*(np.sqrt(gap*gap-1)*(-8-9*gap**2+2*gap**4)/60+gap*np.arccosh(gap)/4)
        computed = nucleon_rates(0., empty, empty)["vacuum_phase_space_MeV5"]
        self.assertAlmostEqual(computed/analytic, 1., delta=1e-13)

    def test_time_indexed_rates_preserve_reheating_and_bind_actual_spectra(self):
        h = {"time_s": [0., 1., 2.], "T_gamma_MeV": [.4, .8, .4],
             "f_nu_e": {"energy_edges_MeV": [[0., 1., 4.], [0., .8, 3.2], [0., .6, 2.4]],
                        "values": [[.3, .05], [.4, .1], [.2, .02]]},
             "f_antinu_e": {"energy_edges_MeV": [0., 1., 4.],
                            "values": [[.2, .05], [.3, .1], [.1, .02]]}}
        weak = weak_rates_from_history(h)
        self.assertEqual(weak["time_s"], h["time_s"])
        self.assertNotEqual(weak["lambda_n_to_p_s_inv"][0], weak["lambda_n_to_p_s_inv"][2])
        validate_weak_rates(weak, h)
        h["f_nu_e"]["values"][0][0] += .01
        with self.assertRaises(OpenInput):
            validate_weak_rates(weak, h)


if __name__ == "__main__":
    unittest.main()
