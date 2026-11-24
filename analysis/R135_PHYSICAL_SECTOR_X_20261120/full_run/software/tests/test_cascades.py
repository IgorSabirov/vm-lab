"""Numerical contracts and an opt-in *actual donor* electromagnetic control.

Run real kernels with R135_ACROPOLIS_PATH set to the pinned fetched source.
Normal unit discovery performs no network access and substitutes no kernels.
"""
import copy
import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.special import zeta

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from r135 import cascades
from r135.common import HBARC_MEV_CM, InputError, OpenInput, canonical_hash


def em_fixture(*, amplitude=2e-24, samples=5, energy_points_per_decade=40):
    """A declared late radiation background, not a calibrated R135 model point."""
    t = np.linspace(1e6, 1.1e6, samples)
    a = np.sqrt(t/t[0])
    T = 1e-3/a
    nb = 6.1e-10 * 2*zeta(3)/np.pi**2 * T**3
    Y = np.array([0, 0, 1.9e-5, 1e-8, 8e-6, .06175, 1e-14, 2e-11, 4e-10])
    Y[1] = 1-cascades.MASS_NUMBER@Y
    rate = amplitude/a**3
    return {"schema": "r135.em_cascade.v1",
            "background": {"time_s": t.tolist(), "T_gamma_MeV": T.tolist(),
                "n_b_MeV3": nb.tolist(), "H_s": (.5/t).tolist(), "a": a.tolist(),
                "source": "explicit validation radiation solution a=(t/1e6 s)^0.5, eta=6.1e-10"},
            "initial_abundances": {"species": list(cascades.SPECIES), "Y": Y.tolist(),
                "epoch_time_s": float(t[0]), "source": "diagnostic late BBN composition, baryon-normalized",
                "covariance": np.diag([0, 0, 1e-14, 0, 0, 1e-10, 0, 0, 0]).tolist()},
            "injection": {"lines": [{"species": "photon", "energy_MeV": 5,
                "dN_dVdt_MeV3_s": rate.tolist()}], "power_MeV4_s": (5*rate).tolist(),
                "source": "diagnostic monoenergetic photon injection with prescribed comoving rate"},
            "applicability": {"fully_ionized": True, "thermal_nuclear_reactions_negligible": True,
                "source": "late T=1 keV post-BBN validation; perturbative radiation and target changes checked numerically"},
            "numerics": {"energy_points_per_decade": energy_points_per_decade}}


class CascadeContractTests(unittest.TestCase):
    def test_p7_handoff_preserves_baryon_density_and_rejects_wrong_source(self):
        cfg = em_fixture()
        bg = cfg["background"]
        history = {"time_s": bg["time_s"], "T_gamma_MeV": bg["T_gamma_MeV"],
                   "n_b_cm3": (np.array(bg["n_b_MeV3"])/HBARC_MEV_CM**3).tolist(),
                   "H_s_inv": bg["H_s"], "scale_factor": bg["a"],
                   "Q_MeV4_s": {"gamma": cfg["injection"]["power_MeV4_s"]}}
        initial = copy.deepcopy(cfg["initial_abundances"])
        initial["epoch_time_s"] = bg["time_s"][1]
        injection = {**cfg["injection"], "time_s": bg["time_s"], "p7_power_binding": "positive_Q_gamma"}
        bound = cascades.config_from_p7(history, injection, initial, start_index=1,
                                         applicability=cfg["applicability"])
        np.testing.assert_allclose(bound["background"]["n_b_MeV3"], bg["n_b_MeV3"][1:], rtol=2e-16)
        self.assertEqual(bound["injection"]["power_MeV4_s"], cfg["injection"]["power_MeV4_s"][1:])
        self.assertEqual(bound["p7_handoff"]["history_sha256"], canonical_hash(history))
        injection["source_history_sha256"] = "0"*64
        with self.assertRaisesRegex(InputError, "different P7 history"):
            cascades.config_from_p7(history, injection, initial, start_index=1,
                                     applicability=cfg["applicability"])

    def test_input_preserves_actual_background_and_energy(self):
        cfg = em_fixture()
        before = canonical_hash(cfg)
        data = cascades.validate_config(cfg)
        self.assertEqual(canonical_hash(cfg), before)
        np.testing.assert_array_equal(data["nb"], cfg["background"]["n_b_MeV3"])
        self.assertGreater(data["injected_radiation_fraction"], 0)
        self.assertLess(data["injected_radiation_fraction"], .01)

    def test_missing_six_lithium_and_epoch_mismatch_rejected(self):
        cfg = em_fixture()
        cfg["initial_abundances"]["species"].remove("Li6")
        with self.assertRaisesRegex(OpenInput, "Li6"):
            cascades.validate_config(cfg)
        cfg = em_fixture()
        cfg["initial_abundances"]["epoch_time_s"] = 0
        with self.assertRaisesRegex(InputError, "first supplied physical time"):
            cascades.validate_config(cfg)

    def test_power_and_baryon_mismatches_rejected(self):
        cfg = em_fixture()
        cfg["injection"]["power_MeV4_s"][2] *= 2
        with self.assertRaisesRegex(InputError, "declared EM power"):
            cascades.validate_config(cfg)
        cfg = em_fixture()
        cfg["background"]["n_b_MeV3"][2] *= 2
        with self.assertRaisesRegex(InputError, "n_b\\*a\\^3"):
            cascades.validate_config(cfg)

    def test_charge_and_early_bbn_domains_are_not_silently_thermalized(self):
        cfg = em_fixture()
        cfg["injection"]["lines"][0]["species"] = "electron"
        with self.assertRaisesRegex(OpenInput, "electric charge"):
            cascades.validate_config(cfg)
        cfg = em_fixture()
        cfg["background"]["T_gamma_MeV"][0] = .01
        with self.assertRaisesRegex(OpenInput, "post-BBN"):
            cascades.validate_config(cfg)
        cfg = em_fixture()
        cfg["injection"]["energy_MeV"] = [.1, .6, 2.]
        for particle in ("electron", "positron"):
            cfg["injection"][particle+"_dN_dVdt_dE_MeV2_s"] = [[0, 1e-25, 1e-25]]*5
        with self.assertRaisesRegex(InputError, "extend below m_e"):
            cascades.validate_config(cfg)

    def test_piecewise_linear_spectrum_energy_is_integrated_exactly(self):
        E = np.array([1., 2., 7.])
        source = E * 3
        self.assertAlmostEqual(cascades.linear_spectrum_moment(E, source), 7**3-1)
        self.assertAlmostEqual(cascades.linear_spectrum_moment(E, source, energy_weighted=False), 1.5*(7**2-1))

    def test_zero_source_gives_only_same_epoch_radioactive_decays(self):
        Y = np.array([.1, .5, 0, .02, 0, .085, 0, 0, 0])
        # Sum of baryon numbers is exactly one.
        t = np.linspace(100, 1100, 7)
        result = cascades.evolve_abundances(t, np.zeros((7, 17)), Y, rtol=1e-10)
        self.assertAlmostEqual(result["final_Y"][0], Y[0]*np.exp(-1000/879.4), delta=2e-9)
        self.assertAlmostEqual(result["final_Y"][3], Y[3]*np.exp(-1000/5.605e8), delta=2e-12)
        self.assertLess(result["baryon_residual"], 1e-12)

    def test_actual_noncommuting_network_uses_physical_time_order(self):
        # First t->d+n then d->n+p; reversing that order changes final d.
        Y = np.zeros(9)
        Y[3] = 1/3
        t = np.array([0., 1., 1.01, 2.01])
        rates = np.zeros((4, 17))
        rates[:2, 1] = 1
        rates[2:, 0] = 1
        forward = cascades.evolve_abundances(t, rates, Y)["final_Y"]
        reverse = cascades.evolve_abundances(t, rates[::-1], Y)["final_Y"]
        self.assertGreater(reverse[2]-forward[2], .1)

    def test_inclusive_lithium_loss_is_explicit_unresolved_baryons(self):
        Y = np.zeros(9)
        Y[6] = 1/6
        rates = np.zeros((2, 17))
        rates[:, 10] = .1
        result = cascades.evolve_abundances([0., 10.], rates, Y, rtol=1e-10)
        self.assertAlmostEqual(result["final_Y"][6], np.exp(-1)/6, delta=2e-9)
        self.assertAlmostEqual(result["unresolved_Li6_history"][-1], (1-np.exp(-1))/6, delta=2e-9)
        self.assertLess(result["baryon_residual"], 1e-12)
        self.assertEqual(result["final_Y"][1], 0)

    def test_exclusive_hadronic_table_convolution_checks_baryon_yields(self):
        K = [10., 20., 30.]
        xi = np.zeros((2, 3, 9))
        xi[0, :, 1], xi[1, :, 0] = 1, 1
        response = {"source": "diagnostic identity-thermalization response, no hadronic physics implied",
                    "projectiles": ["p", "n"], "species": list(cascades.SPECIES),
                    "energy_MeV": K, "net_yield": xi.tolist(), "net_baryons_per_projectile": [1, 1]}
        result = cascades.hadronic_source_from_response(K, np.ones((2, 3))*1e-20, response, 1e-18)
        np.testing.assert_allclose(result["production_over_nb_s_inv"][:2], [.2, .2])
        self.assertIsNone(result["dY_dt_s_inv"])
        background = np.zeros(9)
        background[1] = 1
        normalized = cascades.hadronic_source_from_response(K, np.ones((2, 3))*1e-20, response, 1e-18,
                                                              background_Y=background)
        self.assertAlmostEqual(cascades.MASS_NUMBER @ normalized["dY_dt_s_inv"], 0)
        response["net_yield"][0][0][1] = 2
        with self.assertRaisesRegex(InputError, "baryon ledger"):
            cascades.hadronic_source_from_response(K, np.ones((2, 3)), response, 1)


@unittest.skipUnless(os.environ.get("R135_ACROPOLIS_PATH"), "actual pinned donor path not set; no implicit CI download")
class ActualAcropolisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = em_fixture()
        cls.result = cascades.run_electromagnetic_cascade(cls.config, fetch=False)

    def test_nonzero_actual_cascade_destroys_deuterium_and_preserves_baryons(self):
        r = self.result
        self.assertEqual(r["donor"]["commit"], cascades.ACROPOLIS_SHA)
        self.assertGreater(np.max(r["photodisintegration_rates_s_inv"][:, 0]), 0)
        self.assertLess(r["final_Y"][2], self.config["initial_abundances"]["Y"][2])
        self.assertTrue(any(x["components"] for x in r["spectra"]))
        self.assertLess(r["baryon_residual"], 1e-10)
        self.assertIsNone(r["energy_ledger"]["thermal_deposition_power_MeV4_s"])

    def test_zero_actual_injection_and_linear_rate_scaling(self):
        zero = cascades.run_electromagnetic_cascade(em_fixture(amplitude=0), fetch=False)
        expected = cascades.evolve_abundances(self.config["background"]["time_s"], np.zeros((5, 17)),
                                              self.config["initial_abundances"]["Y"])
        np.testing.assert_allclose(zero["final_Y"], expected["final_Y"], atol=1e-15, rtol=1e-12)
        half = cascades.run_electromagnetic_cascade(em_fixture(amplitude=1e-24), fetch=False)
        np.testing.assert_allclose(half["photodisintegration_rates_s_inv"],
                                   .5*self.result["photodisintegration_rates_s_inv"], rtol=2e-10, atol=1e-190)
        self.assertLess(self.result["D_over_H"], half["D_over_H"])
        self.assertLess(half["D_over_H"], zero["D_over_H"])

    def test_actual_cascade_energy_grid_refinement_and_input_covariance(self):
        fine = cascades.run_electromagnetic_cascade(em_fixture(energy_points_per_decade=80), fetch=False)
        # This is a 5MeV/1keV development check, not a universal precision claim.
        effect = self.config["initial_abundances"]["Y"][2]-fine["final_Y"][2]
        self.assertLess(abs(fine["final_Y"][2]-self.result["final_Y"][2])/effect, .03)
        cov = self.result["final_covariance"]
        np.testing.assert_allclose(cov, cov.T, atol=1e-25)
        self.assertGreaterEqual(np.min(np.linalg.eigvalsh(cov)), -1e-25)

    def test_modified_donor_is_rejected_before_import(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root/"LICENSE").write_text("corrupted")
            with self.assertRaisesRegex(InputError, "hash mismatch"):
                cascades.fetch_acropolis(root, fetch=False)

    def test_actual_p7_solver_hands_its_own_history_to_nonzero_cascade(self):
        from tests.test_history import fixture as p7_fixture
        from r135.history import CoupledModel, _payload
        args = list(p7_fixture())
        args[0].update(samples=65, rtol=1e-7, max_step_H0=.1)
        args[1]["phases"]["hot"]["T_range_MeV"] = [1e-8, 2]
        args[1]["phases"]["hot"]["coefficients"][0] = -1e-12
        args[1]["phases"]["cold"]["T_range_MeV"] = [1e-8, 2]
        args[1]["transitions"][0].update(T_c_MeV=.001, latent_heat_MeV4=4e-12)
        args[4] = {"source": "diagnostic zero direct transfer", "thermal_channels": []}
        args[5].update(T_X_MeV=.001, T_gamma_MeV=.001, T_nu_MeV=.000714,
                       T_free_MeV=.0001, phase_fraction=1, surface="postconfinement", time_s=1e6)
        records, _ = CoupledModel(*args).solve("00")
        history = _payload(records)
        rate = 1e-26/np.array(history["scale_factor"])**3
        injection = {"source": "separately prescribed weak photon injection on actual P7 diagnostic history",
                     "time_s": history["time_s"], "power_MeV4_s": (5*rate).tolist(),
                     "lines": [{"species": "photon", "energy_MeV": 5, "dN_dVdt_MeV3_s": rate.tolist()}]}
        config = cascades.config_from_p7(history, injection, self.config["initial_abundances"],
                      start_index=0, applicability=self.config["applicability"], numerics=self.config["numerics"])
        result = cascades.run_electromagnetic_cascade(config, fetch=False)
        self.assertEqual(result["p7_handoff"]["history_sha256"], canonical_hash(history))
        self.assertLess(result["final_Y"][2], config["initial_abundances"]["Y"][2])
        self.assertEqual(result["p7_handoff"]["thermal_feedback"], "NOT_COMPUTED_POSTPROCESSING_ONLY")


if __name__ == "__main__":
    unittest.main()
