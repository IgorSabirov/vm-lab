from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from r135.common import InputError, OpenInput
from r135.kinetics import (MomentumGrid, EmissionAbsorption, ConservativeScattering,
    detailed_balance_transition, kinetic_rhs, integrate_kinetic_bath)
from r135.neutrino_rates import nucleon_rates


class KineticTests(unittest.TestCase):
    def test_massless_free_streaming_redshifts_exactly(self):
        grid = MomentumGrid([0., .2, .7, 2., 5.], degeneracy=1.)
        occupation = [.7, .4, .1, .02]
        first, last = grid.moments(occupation, 1.), grid.moments(occupation, 3.)
        self.assertAlmostEqual(last["number_MeV3"]*27/first["number_MeV3"], 1., places=14)
        self.assertAlmostEqual(last["rho_MeV4"]*81/first["rho_MeV4"], 1., places=14)
        self.assertAlmostEqual(last["pressure_MeV4"]/last["rho_MeV4"], 1/3, places=14)
        result = integrate_kinetic_bath(grid, occupation, [], np.linspace(0, 2, 8),
            bath_coefficient=2., bath_T_MeV=1., H_s_inv=.2)
        np.testing.assert_array_equal(result["occupation"], np.tile(occupation, (8, 1)))
        self.assertLess(max(abs(np.asarray(result["relative_energy_balance"]))), 2e-8)

    def test_massive_moments_satisfy_liouville_energy_equation(self):
        grid = MomentumGrid([0., .3, 1., 2., 4.], mass_MeV=2.)
        f = [.5, .3, .1, .01]
        a, step = 1.7, 1e-5
        centre = grid.moments(f, a)
        derivative = (grid.moments(f, a*np.exp(step))["rho_MeV4"]
                      - grid.moments(f, a*np.exp(-step))["rho_MeV4"])/(2*step)
        expected = -3*(centre["rho_MeV4"]+centre["pressure_MeV4"])
        self.assertAlmostEqual(derivative/expected, 1., delta=1e-8)

    def test_emission_absorption_analytic_solution_and_pauli_bounds(self):
        grid = MomentumGrid([0., 1., 2., 3.])
        j, kappa = np.array([.3, .8, 1.]), np.array([1., .2, .1])
        f0 = np.array([0., 1., .2])
        operator = EmissionAbsorption(grid, j, kappa, source="diagnostic known linear relaxation")
        time = np.linspace(0., 1.5, 12)
        result = integrate_kinetic_bath(grid, f0, [operator], time,
            bath_coefficient=100., bath_T_MeV=2., rtol=1e-10, atol=1e-12)
        equilibrium = j/(j+kappa)
        expected = equilibrium[None, :]+(f0-equilibrium)[None, :]*np.exp(-time[:, None]*(j+kappa)[None, :])
        np.testing.assert_allclose(result["occupation"], expected, rtol=2e-9, atol=2e-11)
        self.assertEqual(result["max_occupation_bound_violation"], 0.)
        self.assertLess(max(abs(np.asarray(result["relative_energy_balance"]))), 2e-12)

    def test_scattering_number_conservation_and_detailed_balance(self):
        for statistics in ("fermion", "boson", "classical"):
            grid = MomentumGrid([0., .4, 1., 2., 4.], statistics=statistics)
            conductance = np.full((4, 4), .01)
            matrix = detailed_balance_transition(grid, 1., .7, conductance)
            operator = ConservativeScattering(grid, matrix, source="diagnostic reversible transition matrix")
            equilibrium = grid.equilibrium(1., .7, -.2)
            derivative, source = kinetic_rhs(grid, [operator], 0., equilibrium, 1., .7)
            self.assertLess(np.max(abs(derivative)), 1e-14)
            disturbed = np.array([.8, .3, .1, .04])
            derivative, source = kinetic_rhs(grid, [operator], 0., disturbed, 1., .7)
            self.assertAlmostEqual(source["number_MeV3_s"], 0., delta=1e-16)
            self.assertGreater(abs(source["energy_MeV4_s"]), 1e-4)

    def test_boson_and_classical_stimulation_are_not_fermi_capped(self):
        for statistics, expected in (("boson", 2.), ("classical", 4.)):
            grid = MomentumGrid([0., 1.], mass_MeV=2., statistics=statistics)
            grid.occupation([2.])
            # At f=2, C=4*(1+f)-5*f=2 for BE, C=4-0*f=4 for MB.
            op = EmissionAbsorption(grid, [4.], [5. if statistics == "boson" else 0.],
                                    source="diagnostic stimulation coefficients")
            self.assertAlmostEqual(op.rhs(0., [2.], 1., 1.)[0], expected)
            equilibrium = grid.equilibrium(1., .7, .2)
            j = equilibrium/(1+grid.statistical_sign*equilibrium)
            reversible = EmissionAbsorption(grid, j, [1.], source="diagnostic reversible emissivity")
            self.assertLess(abs(reversible.rhs(0., equilibrium, 1., .7)[0]), 1e-14)
        with self.assertRaises(InputError):
            MomentumGrid([0., 1.], statistics="boson").equilibrium(1., 1., .1)

    def test_finite_bath_temperature_feeds_back_and_energy_balances(self):
        grid = MomentumGrid(np.linspace(0., 5., 13))
        # This is an explicit test kernel, not a derived SM interaction rate.
        def emission(t, a, temperature):
            return 4*temperature**2*grid.fermi_dirac(a, temperature)
        def absorption(t, a, temperature):
            return 4*temperature**2*(1-grid.fermi_dirac(a, temperature))
        operator = EmissionAbsorption(grid, emission, absorption,
                                      source="diagnostic thermal reservoir with declared relaxation rate")
        time = np.linspace(0., 2., 21)
        finite = integrate_kinetic_bath(grid, np.zeros(grid.size), [operator], time,
            bath_coefficient=.5, bath_T_MeV=1., rtol=1e-9, atol=1e-12)
        pinned = EmissionAbsorption(grid, emission(0, 1, 1), absorption(0, 1, 1),
                                     source="diagnostic fixed-temperature counterfactual")
        fixed = integrate_kinetic_bath(grid, np.zeros(grid.size), [pinned], time,
            bath_coefficient=100., bath_T_MeV=1., rtol=1e-9, atol=1e-12)
        self.assertLess(finite["bath_T_MeV"][-1], .95)
        self.assertGreater(np.max(np.abs(np.array(finite["occupation"][-1])-fixed["occupation"][-1])), .01)
        self.assertLess(max(abs(np.asarray(finite["relative_energy_balance"]))), 1e-10)

    def test_kinetic_cells_feed_actual_weak_rates(self):
        grid = MomentumGrid([0., .5, 1., 2., 5.])
        f = np.array([.4, .3, .1, .01])
        first = nucleon_rates(.5, grid.massless_spectrum(f, 1.), grid.massless_spectrum(f, 1.))
        later = nucleon_rates(.5, grid.massless_spectrum(f, 2.), grid.massless_spectrum(f, 2.))
        self.assertGreater(first["lambda_n_to_p_s_inv"], later["lambda_n_to_p_s_inv"])
        self.assertGreater(first["lambda_p_to_n_s_inv"], later["lambda_p_to_n_s_inv"])

    def test_unphysical_or_unattributed_inputs_are_rejected(self):
        grid = MomentumGrid([0., 1.])
        with self.assertRaises(InputError):
            grid.occupation([1.2])
        with self.assertRaises(OpenInput):
            EmissionAbsorption(grid, [1.], [1.], source="")
        op = EmissionAbsorption(grid, [-1.], [1.], source="invalid diagnostic")
        with self.assertRaises(InputError):
            op.rhs(0., [.3], 1., 1.)


if __name__ == "__main__":
    unittest.main()
