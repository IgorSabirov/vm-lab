from copy import deepcopy
import sys
from pathlib import Path
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from r135.common import InputError, OpenInput
from r135.observations import adapt_history, bridge_hash, validate_history, validate_class_model, match_class_history, SPECIES
from r135.common import HBARC_MEV_CM


def history():
    t = np.array([0., 1., 2.])
    a = np.exp(.1 * t)
    return {"time_s": t.tolist(), "scale_factor": a.tolist(), "H_s_inv": [.1] * 3,
            "T_gamma_MeV": [.1, .08, .1], "T_nu_MeV": [.1, .07, .06],
            "n_b_cm3": (1e20 / a ** 3).tolist()}


def weak():
    return {"time_s": [0., 1., 2.], "lambda_n_to_p_s_inv": [1., 2., 3.],
            "lambda_p_to_n_s_inv": [0., .1, .2], "unit": "s^-1", "source": "analytic software fixture"}


def rates():
    return {"network_id": "fixture", "species": list(SPECIES), "reactions": [
        {"id": "npdg", "reactants": {"n": 1, "p": 1}, "products": {"d": 1}, "T9": [.1, 10.], "values": [1., 2.]}],
        "temperature_unit": "T9", "rate_units": "cm3 mol-1 s-1", "interpolation": "linear",
        "extrapolation": "upstream-zero-linear", "detailed_balance_policy": "diagnostic fixture"}


def item(h=None, w=None):
    return adapt_history(h or history(), rates(), w or weak(), producer="test", created_utc="2026-11-20T00:00:00Z",
                         initial_abundances=[.2, .8, 0., 0., 0., 0., 0., 0.])


def class_model():
    return {"perturbation_model": {"kind": "standard_free_streaming_after_matching", "source": "diagnostic model",
            "domain_proof_source": "test fixture only", "all_transfer_finished_before_relevant_modes_enter": True,
            "adiabatic_initial_perturbations": True, "massless_collisionless_extra_radiation": True,
            "no_surviving_interacting_relic": True},
            "parameters": {"H0": 67.4, "omega_b": .02242, "omega_cdm": .12, "T_cmb": 2.7255,
                           "tau_reio": .054, "n_s": .965, "A_s": 2.1e-9, "N_ur": 3.044}}


class ObservationTests(unittest.TestCase):
    def test_reheating_and_distinct_weak_rates_survive(self):
        adapted = item()
        self.assertEqual(adapted["canonical"]["history"]["T_gamma_MeV"], [.1, .08, .1])
        self.assertEqual(adapted["weak_rates"]["lambda_n_to_p_s_inv"], [1., 2., 3.])

    def test_hash_binds_actual_history(self):
        first = item()
        altered = history()
        altered["T_nu_MeV"][1] *= 1.01
        second = item(altered)
        self.assertNotEqual(first["source_history_sha256"], second["source_history_sha256"])

    def test_time_order_and_baryon_injection_rejected(self):
        bad = history()
        bad["time_s"] = [0., 2., 1.]
        with self.assertRaises(InputError):
            validate_history(bad)
        bad = history()
        bad["n_b_cm3"][1] *= 1.1
        with self.assertRaises(OpenInput):
            validate_history(bad)

    def test_nonthermal_weak_rates_must_bind_spectra(self):
        h = history()
        spectral = {"energy_MeV": [.01, .1], "values": [[.5, .2]] * 3}
        h.update(f_nu_e=deepcopy(spectral), f_antinu_e=deepcopy(spectral))
        with self.assertRaises(OpenInput):
            item(h)
        w = weak()
        w["neutrino_spectra_sha256"] = bridge_hash({k: h[k] for k in ("f_nu_e", "f_antinu_e")})
        self.assertEqual(item(h, w)["weak_rates"]["neutrino_spectra_sha256"], w["neutrino_spectra_sha256"])
        h["f_nu_e"]["values"][0][0] = .4
        with self.assertRaises(OpenInput):
            item(h, w)

    def test_missing_or_wrong_unit_weak_rates_not_thermalized_silently(self):
        with self.assertRaises(OpenInput):
            adapt_history(history(), rates(), None, producer="test", created_utc="2026-11-20T00:00:00Z")
        w = weak()
        w["unit"] = "MeV"
        with self.assertRaises(InputError):
            item(w=w)

    def test_class_requires_perturbation_applicability(self):
        good = class_model()
        good["precision"] = {"tol_perturbations_integration": 1e-6, "accurate_lensing": 1}
        self.assertEqual(validate_class_model(good)["l_max_scalars"], 2508)
        self.assertEqual(validate_class_model(good)["precision"], good["precision"])
        good["perturbation_model"]["no_surviving_interacting_relic"] = False
        with self.assertRaises(OpenInput):
            validate_class_model(good)
        with self.assertRaises(OpenInput):
            validate_class_model({"background": history()})

    def test_late_class_matching_uses_actual_energy_and_baryon_history(self):
        h = history()
        tg = np.asarray([.01, .008, .006])
        a = tg[0] / tg
        rg = np.pi ** 2 * tg ** 4 / 15
        h.update(T_gamma_MeV=tg.tolist(), scale_factor=a.tolist(),
                 n_b_cm3=(6e-10 * 2 * 1.2020569031595942 / np.pi ** 2 * (tg / HBARC_MEV_CM) ** 3).tolist(),
                 rho_gamma_MeV4=rg.tolist(),
                 rho_nu_MeV4=(3.044 * (7 / 8) * (4 / 11) ** (4 / 3) * rg).tolist(),
                 rho_extra_MeV4=[0.] * 3, p_extra_MeV4=[0.] * 3)
        cfg = class_model()
        cfg["matching"] = {"source": "analytic post-annihilation fixture", "transfer_finished": True,
                           "electron_annihilation_finished": True}
        result = match_class_history(h, cfg)
        self.assertAlmostEqual(result["matching"]["eta"], 6e-10, delta=1e-20)
        self.assertAlmostEqual(result["parameters"]["N_ur"], 3.044)
        h["rho_extra_MeV4"] = (rg * .1).tolist()
        with self.assertRaises(OpenInput):
            match_class_history(h, cfg)


if __name__ == "__main__":
    unittest.main()
