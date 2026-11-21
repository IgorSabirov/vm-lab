from copy import deepcopy
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from perturbations_reference.control import control_fixture
from r135.common import InputError, OpenInput
from r135.perturbations import (MPC_OVER_C_S, collision_drag, conformal_opacity_Mpc_inv,
                                ethos_opacity_Mpc_inv, match_ethos_history, validate_ethos_input)


class PerturbationTests(unittest.TestCase):
    def test_matching_derives_density_and_rates(self):
        h, cfg = control_fixture(.1)
        doc = match_ethos_history(h, cfg)
        self.assertAlmostEqual(doc["parameters"]["omega_idm"], .012)
        self.assertAlmostEqual(doc["parameters"]["N_idr"], .2)
        self.assertAlmostEqual(doc["parameters"]["N_ur"], 3.044)
        self.assertAlmostEqual(doc["parameters"]["a_idm_dr"], .1)
        self.assertLess(max(doc["matching"]["residuals"].values()), 2e-15)
        self.assertEqual(validate_ethos_input(doc), doc)

    def test_power_law_and_unit_conventions(self):
        self.assertEqual(conformal_opacity_Mpc_inv(1 / MPC_OVER_C_S, .2), .2)
        self.assertAlmostEqual(ethos_opacity_Mpc_inv(1e7 - 1, .12, .3, 4), .036)
        for n in (0, 2, 4):
            h, cfg = control_fixture(15., "free_streaming", n)
            self.assertAlmostEqual(match_ethos_history(h, cfg)["parameters"]["a_idm_dr"], 15.)

    def test_momentum_conservation_and_dissipation(self):
        for rm in (.001, 1., 1e6):
            for rr in (0., .25, 2e5):
                for tm, tr in ((1., -2.), (-2., 1.), (3., 3.)):
                    terms = collision_drag(tm, tr, rm, rr, .3)
                    weighted = rm * terms["idm"] + 4 * rr / 3 * terms["idr"]
                    self.assertAlmostEqual(weighted, 0., delta=1e-9 * max(rm, rr))
                    self.assertLessEqual((tm - tr) * (terms["idm"] - terms["idr"]), 0.)
        self.assertEqual(collision_drag(1., 2., 3., 4., 0.), {"idm": 0., "idr": 0.})

    def test_wrong_species_partition_or_pressure_rejected(self):
        for field in ("rho_extra_MeV4", "p_extra_MeV4", "p_idr_MeV4"):
            h, cfg = control_fixture()
            h[field][1] *= 1.1
            with self.assertRaises(OpenInput):
                match_ethos_history(h, cfg)
        h, cfg = control_fixture()
        h["p_idm_MeV4"] = (np.array(h["rho_idm_MeV4"]) * .01).tolist()
        with self.assertRaises(OpenInput):
            match_ethos_history(h, cfg)

    def test_wrong_rate_units_or_no_action_reaction_rejected(self):
        h, cfg = control_fixture()
        h["Gamma_idr_idm_s_inv"][1] *= MPC_OVER_C_S
        with self.assertRaises(OpenInput):
            match_ethos_history(h, cfg)
        h, cfg = control_fixture()
        h["Gamma_idr_idm_s_inv"][1] *= 1.1
        h["Gamma_idm_idr_s_inv"][1] *= 1.1
        with self.assertRaises(OpenInput):
            match_ethos_history(h, cfg)

    def test_free_streaming_with_finite_self_opacity(self):
        h, cfg = control_fixture(.1, "free_streaming", 2)
        # Gamma_self/Gamma_dr = b*omega_idr/(a*omega_idm).
        from r135.perturbations import photon_omega, ONE_NEUTRINO_FACTOR
        omega_idr = .2 * ONE_NEUTRINO_FACTOR * photon_omega(cfg["parameters"]["T_cmb"])
        h["Gamma_idr_self_s_inv"] = (np.array(h["Gamma_idr_idm_s_inv"]) * 5. * omega_idr / (.1 * .012)).tolist()
        self.assertAlmostEqual(match_ethos_history(h, cfg)["parameters"]["b_idr"], 5.)

    def test_source_or_inapplicable_domain_rejected(self):
        h, cfg = control_fixture()
        cfg["perturbation_model"]["no_late_particle_production_or_decay"] = False
        with self.assertRaises(OpenInput):
            match_ethos_history(h, cfg)
        h, cfg = control_fixture()
        cfg["perturbation_model"]["fluid_limit_source"] = ""
        with self.assertRaises(OpenInput):
            match_ethos_history(h, cfg)
        h, cfg = control_fixture()
        cfg["perturbation_model"]["microphysics"]["n_index_idm_dr"] = 3
        with self.assertRaises(OpenInput):
            match_ethos_history(h, cfg)

    def test_handoff_preserves_actual_p7_and_blocks_density_override(self):
        h, cfg = control_fixture()
        first = match_ethos_history(h, cfg)
        second = deepcopy(first)
        second["parameters"]["omega_idm"] *= 1.1
        with self.assertRaises(InputError):
            validate_ethos_input(second)
        second = deepcopy(first)
        second["ethos_matching_evidence"]["history"]["rho_idm_MeV4"][0] *= 1.1
        with self.assertRaises(OpenInput):
            validate_ethos_input(second)
        second = deepcopy(first)
        second["source_P7_history_sha256"] = "0" * 64
        with self.assertRaises(InputError):
            validate_ethos_input(second)
        second = deepcopy(first)
        second["parameters"].update(omega_b=.0225, YHe=.245)
        with self.assertRaises(InputError):
            validate_ethos_input(second)

    def test_real_p9_mass_handoff_is_accepted(self):
        from types import SimpleNamespace
        from r135.backends import matched_class_input
        h, cfg = control_fixture()
        doc = match_ethos_history(h, cfg)
        # Only exercises P9's mass/provenance transformation, not a BBN model.
        mass_cfg = SimpleNamespace(NuclExcessMass={name: 0. for name in ("p", "H2", "He3", "He4", "Li7")})
        abundance = {"final_Y": [0., .75, 0., 0., 0., .0625, 0., 0.]}
        result = matched_class_input(doc, abundance, mass_cfg)
        validate_ethos_input(result)
        result["matching"]["N_idr"] *= 2
        with self.assertRaises(InputError):
            validate_ethos_input(result)

    def test_late_matching_and_reheating_are_not_silently_discarded(self):
        h, cfg = control_fixture()
        h["H_s_inv"] = (np.array(h["H_s_inv"]) * .001).tolist()
        with self.assertRaises(OpenInput):
            match_ethos_history(h, cfg)
        h, cfg = control_fixture()
        h["T_gamma_MeV"][1] *= 1.1
        with self.assertRaises(OpenInput):
            match_ethos_history(h, cfg)

    def test_missing_calculated_rate_is_open_input(self):
        h, cfg = control_fixture()
        del h["Gamma_idm_idr_s_inv"]
        with self.assertRaises(OpenInput):
            match_ethos_history(h, cfg)

    def test_unmatched_clock_or_warm_idm_rejected(self):
        h, cfg = control_fixture()
        h["H_s_inv"] = (np.array(h["H_s_inv"]) * 2).tolist()
        with self.assertRaises(OpenInput):
            match_ethos_history(h, cfg)
        h, cfg = control_fixture()
        cfg["perturbation_model"]["microphysics"]["m_idm_eV"] = 1e6
        with self.assertRaises(OpenInput):
            match_ethos_history(h, cfg)

    def test_fluid_requires_actual_strong_self_scattering(self):
        h, cfg = control_fixture()
        h["Gamma_idr_self_s_inv"] = [0.] * 3
        with self.assertRaises(OpenInput):
            match_ethos_history(h, cfg)


if __name__ == "__main__":
    unittest.main()
