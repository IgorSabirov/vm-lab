from copy import deepcopy
import os
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from r135.backends import (HistoryInterpolator, NativePair, convergence_gate, prepare_native_rates,
    run_class, thermal_weak_rates, import_computed_spectra, class_refinement_gate, validate_class_refinement,
    validate_thermal_weak_domain)
from r135.common import InputError, OpenInput, canonical_hash, sha256, write_json
from r135.observations import adapt_history
from test_observations import history, item, weak, class_model


class BackendControlTests(unittest.TestCase):
    def test_thermal_weak_domain_requires_numeric_bounds_and_rejects_hot_X(self):
        policy = {"source": "software fixture", "fermi_dirac_electron_neutrinos": True,
                  "native_thermal_corrections_applicable": True}
        with self.assertRaises(OpenInput):
            thermal_weak_rates(history(), policy)
        policy["applicability"] = {"source": "test fixture only", "T_gamma_range_MeV": [.0052, 8.6],
                                   "T_nu_range_MeV": [.0037, 8.6], "xi_nu_range": [0., 0.]}
        self.assertEqual(validate_thermal_weak_domain(history(), policy), 0.)
        for field in ("T_gamma_MeV", "T_nu_MeV"):
            for outside in (404., .001):
                h = history()
                h[field][0] = outside
                with self.assertRaises(OpenInput):
                    thermal_weak_rates(h, policy)
        policy["xi_nu"] = .1
        with self.assertRaises(OpenInput):
            validate_thermal_weak_domain(history(), policy)

    def test_weak_history_not_sorted_by_temperature(self):
        interp = HistoryInterpolator(item(), 8.617333262e-11)
        left, right = interp.value(0.), interp.value(2.)
        self.assertEqual(left[0], right[0])
        self.assertNotEqual(left[2], right[2])
        with self.assertRaises(InputError):
            interp.value(2.1)

    def test_all_rate_support_crossings_found(self):
        h = history()
        h["T_gamma_MeV"] = [.8, 1., .8]
        interp = HistoryInterpolator(item(h), 8.617333262e-11)
        segments = interp.segments(item(h)["canonical"]["rates"])
        self.assertEqual(len(segments), 3)
        self.assertLess(segments[0][1], 1.)
        self.assertGreater(segments[1][1], 1.)

    def test_unstable_corner_cannot_hide_behind_stable_residual(self):
        values = np.ones((3, 5))
        values[0, 1] += 1e-4
        self.assertEqual(convergence_gate(values)["status"], "FAIL_CONVERGENCE")
        values = np.ones((3, 5))
        self.assertEqual(convergence_gate(values)["status"], "BELOW_NUMERICAL_FLOOR")
        values[:, 3] += 3e-6
        self.assertEqual(convergence_gate(values)["status"], "RESOLVED")

    def test_mixed_residual_itself_must_converge(self):
        values = np.ones((3, 5))
        values[0, 3] += 9e-8
        values[0, 4] -= 9e-8
        self.assertEqual(convergence_gate(values)["status"], "FAIL_CONVERGENCE")
        self.assertEqual(convergence_gate(np.zeros((3, 5)))["status"], "FAIL_CONVERGENCE")

    def test_external_computed_spectrum_requires_same_history_and_receipt(self):
        h = item()
        abundance = {"D_H": 2e-5, "Yp": .24}
        producer = {"repository": "diagnostic-solver", "commit": "a" * 40, "equations_source": "manufactured test"}
        class_input = {"external_solver": producer, "source_P7_history_sha256": h["source_history_sha256"],
                       "perturbation_model": {"kind": "external_computed_perturbations"}}
        spectra = {"ell": list(range(2, 2509)), "TT": [1.] * 2507, "EE": [.5] * 2507,
                   "TE": [.1] * 2507, "unit": "microK^2", "convention": "Cl"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_json(root / "spectrum.json", spectra)
            receipt = {"producer": producer, "state": "COMPLETED", "exit_code": 0,
                       "inputs": {"P7_history_sha256": h["source_history_sha256"], "BBN_observables_sha256": canonical_hash(abundance)},
                       "outputs": {"spectra_sha256": sha256(root / "spectrum.json")}}
            write_json(root / "execution.json", receipt)
            entry = {"producer": producer, **receipt["inputs"], "spectra_sha256": sha256(root / "spectrum.json"),
                     "execution_receipt_sha256": sha256(root / "execution.json"), "spectra_input": "spectrum",
                     "execution_receipt_input": "external_execution"}
            inputs = {"spectrum": root / "spectrum.json", "external_execution": root / "execution.json"}
            result, consumed = import_computed_spectra(entry, class_input, h, abundance, inputs, root / "output")
            self.assertEqual(result, spectra)
            self.assertEqual(consumed["actual_model"], "VERIFIED_EXTERNAL_COMPUTATION")
            entry["P7_history_sha256"] = "b" * 64
            with self.assertRaises(InputError):
                import_computed_spectra(entry, class_input, h, abundance, inputs, root / "bad")

    def test_class_precision_refinement_and_likelihood_gate(self):
        levels = [{"tol_perturbations_integration": 1e-5, "l_linstep": 40},
                  {"tol_perturbations_integration": 1e-6, "l_linstep": 20}]
        self.assertEqual(validate_class_refinement(levels), levels)
        with self.assertRaises(InputError):
            validate_class_refinement(levels[::-1])
        with self.assertRaises(InputError):
            validate_class_refinement([levels[0], levels[0]])
        # These two synthetic backend outputs exercise gate arithmetic; they
        # are deliberately NOT represented as two CLASS accuracy levels.
        values = [-1394.8165519854451, -1394.828163808989]
        self.assertEqual(class_refinement_gate(values, .001)["status"], "FAIL_CMB_CONVERGENCE")
        self.assertEqual(class_refinement_gate(values, .1)["status"], "PASS")


@unittest.skipUnless(os.environ.get("R135_NATIVE_TESTS") == "1", "optional pinned native source checkouts required")
class NativeConsumptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pair = NativePair()
        rates, reverse = prepare_native_rates()
        for reaction in rates["reactions"]:
            reaction["values"] = [0.] * len(reaction["values"])
        h = history()
        h["time_s"] = [0., .5, 1., 1.5, 2.]
        h["scale_factor"] = [1.] * 5
        h["H_s_inv"] = [1e-30] * 5
        h["T_gamma_MeV"] = [.1] * 5
        h["T_nu_MeV"] = [.08] * 5
        h["n_b_cm3"] = [1e20] * 5
        w = {"time_s": h["time_s"], "lambda_n_to_p_s_inv": [.2, .3, .4, .5, .6],
             "lambda_p_to_n_s_inv": [0.] * 5, "unit": "s^-1", "source": "manufactured pure n->p decay fixture"}
        cls.input = adapt_history(h, rates, w, producer="software test", created_utc="2026-11-20T00:00:00Z",
                                  initial_abundances=[.2, .8, 0., 0., 0., 0., 0., 0.])
        cls.input["reverse_alpha_beta_gamma"] = reverse

    def test_both_native_kernels_read_weak_rates_and_reproduce_decay(self):
        policy = {"rtol": 1e-10, "atol": 1e-13}
        expected = .2 * np.exp(-.8)
        with tempfile.TemporaryDirectory() as directory:
            for engine in ("linx", "primat"):
                answer, receipt = self.pair.solve(self.input, engine, policy, Path(directory) / engine)
                self.assertAlmostEqual(answer["final_Y"][0], expected, delta=3e-9)
                self.assertGreater(receipt["history_reads"], 0)
                self.assertEqual(receipt["first_rhs_input"]["lambda_n_to_p_s_inv"], .2)
                self.assertLess(answer["max_baryon_error"], 1e-10)
                _, replay = self.pair.solve(self.input, engine, policy, Path(directory) / engine)
                self.assertTrue(replay["cache_reused"])
                changed = deepcopy(self.input)
                changed["weak_rates"]["lambda_n_to_p_s_inv"][2] *= 2
                with self.assertRaises(InputError):
                    self.pair.solve(changed, engine, policy, Path(directory) / engine)

    def test_controlled_rate_change_changes_both_native_answers(self):
        modified = deepcopy(self.input)
        modified["weak_rates"]["lambda_n_to_p_s_inv"] = [2 * x for x in modified["weak_rates"]["lambda_n_to_p_s_inv"]]
        with tempfile.TemporaryDirectory() as directory:
            for engine in ("linx", "primat"):
                answer, _ = self.pair.solve(modified, engine, {"rtol": 1e-10, "atol": 1e-13}, Path(directory) / engine)
                self.assertAlmostEqual(answer["final_Y"][0], .2 * np.exp(-1.6), delta=3e-9)

    def test_nuclear_table_is_actually_consumed(self):
        changed = deepcopy(self.input)
        reaction = next(r for r in changed["canonical"]["rates"]["reactions"] if r["id"] == "npdg")
        reaction["values"] = [1e6] * len(reaction["values"])
        from r135.observations import bridge_hash
        changed["canonical"]["provenance"]["rates_sha256"] = bridge_hash(changed["canonical"]["rates"])
        with tempfile.TemporaryDirectory() as directory:
            answers = []
            for engine in ("linx", "primat"):
                answer, receipt = self.pair.solve(changed, engine, {"rtol": 1e-10, "atol": 1e-13}, Path(directory) / engine)
                answers.append(answer)
                self.assertGreater(answer["D_H"], 0.)
                self.assertEqual(receipt["nuclear_rates_sha256"], changed["canonical"]["provenance"]["rates_sha256"])
            self.assertAlmostEqual(answers[0]["D_H"] / answers[1]["D_H"], 1., delta=1e-7)

    def test_thermal_weak_integral_keeps_two_times_at_same_temperature(self):
        result = thermal_weak_rates(history(), {"source": "software-only thermal input test",
                    "fermi_dirac_electron_neutrinos": True, "native_thermal_corrections_applicable": True,
                    "applicability": {"source": "manufactured domain for software validation only",
                                      "T_gamma_range_MeV": [.0052, 8.6], "T_nu_range_MeV": [.0037, 8.6],
                                      "xi_nu_range": [0., 0.]}})
        self.assertGreater(abs(result["lambda_n_to_p_s_inv"][0] - result["lambda_n_to_p_s_inv"][-1]), 1e-10)


@unittest.skipUnless(os.environ.get("R135_CLASS_ROOT"), "optional pinned built CLASS source checkout required")
class ClassConsumptionTests(unittest.TestCase):
    def test_real_class_lensed_spectra_and_parameter_response(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = class_model()
            first, receipt = run_class(cfg, os.environ["R135_CLASS_ROOT"], Path(directory) / "first", YHe=.245)
            cfg["parameters"]["N_ur"] += .1
            second, other = run_class(cfg, os.environ["R135_CLASS_ROOT"], Path(directory) / "second", YHe=.245)
            self.assertEqual(first["ell"][-1], 2508)
            self.assertEqual(first["convention"], "Cl")
            self.assertGreater(first["TT"][198], .1)
            self.assertGreater(abs(first["TT"][198] - second["TT"][198]), 1e-5)
            self.assertNotEqual(receipt["parameters_sha256"], other["parameters_sha256"])


if __name__ == "__main__":
    unittest.main()
