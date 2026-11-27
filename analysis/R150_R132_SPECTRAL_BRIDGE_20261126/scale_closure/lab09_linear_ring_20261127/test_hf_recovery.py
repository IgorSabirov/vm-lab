"""Regressions on archived failure modes and on calibrated interval coverage."""
import unittest
from copy import deepcopy
from statistics import NormalDist

import numpy as np

import hf_port
import hf_recovery as hf
import lab09


class RecoveryTests(unittest.TestCase):
    def test_unperturbed_fixture_does_not_cross(self):
        ring, _ = hf_port.ring_matrix()
        target = lab09.LINES_MHZ[1]
        edges = [np.linalg.eigvalsh(lab09.hamiltonian(ring, target + shift, 1.))
                 for shift in (-.4, .4)]
        slots = [np.argmin(abs(e - target)) for e in edges]
        self.assertEqual(slots[0], slots[1])
        self.assertLess(abs(edges[0][slots[0]] - edges[1][slots[1]]), 1e-8)
        self.assertTrue(hf_port.assert_spectral())

    def test_invalid_sweep_fails_through_normal_entry(self):
        baseline = lab09.synthetic_kit("hf_both_detuned")
        for case, expected in [
                ("denominator", "UNRESOLVED_CALIBRATION"), ("covariance", "SAMPLE_COVARIANCE"),
                ("center", "SWEEP_CENTER"), ("open", "CLOSED_HERMITIAN"),
                ("labels", "BRANCH_TRACKING"), ("missing_half_step", "STENCIL_DESIGN")]:
            with self.subTest(case=case):
                kit = deepcopy(baseline)
                s = kit["port_on"]["spectral_sweep"]
                if case == "denominator":
                    for row in s["samples_mhz"]:
                        row[-1] = 6600.
                elif case == "covariance":
                    s["sample_covariance_mhz2"][0][0] = -1e-12
                elif case == "center":
                    s["samples_mhz"][s["offsets"].index(0.)][0] += .1
                elif case == "open":
                    s["closed_hermitian"] = False
                elif case == "labels":
                    s["branch_ids"].reverse()
                else:
                    s["steps"] = [.013]
                self.assertEqual(lab09.evaluate_kit(kit)["limit"], expected)

    def test_trace_null_and_order(self):
        kit = lab09.synthetic_kit("hf_trace_detuned")
        on = kit["port_on"]
        sweep = on["spectral_sweep"]
        order = [4, 6, 2, 1, 0, 5, 3]
        for key in ("frequencies_mhz", "sigma_freq_mhz", "branch_ids"):
            on[key] = [on[key][i] for i in order]
        sweep["branch_ids"] = on["branch_ids"]
        samples = np.asarray(sweep["samples_mhz"])
        perm = (7 * np.arange(len(samples))[:, None] + np.array(order)).ravel()
        sweep["samples_mhz"] = samples[:, order]
        sweep["sample_covariance_mhz2"] = np.asarray(sweep["sample_covariance_mhz2"])[np.ix_(perm, perm)]
        result = lab09.evaluate_kit(kit)
        self.assertEqual(result["linear_decision"], "METHOD_PASS_SYNTHETIC")
        diag = result["diagnostics"]["spectral_recovery"]
        self.assertEqual(diag["branch_ids"], list(range(7)))
        np.testing.assert_allclose(np.array(diag["covariance"]).sum(axis=0), 0., atol=1e-22)
        self.assertNotIn("PORT_WEIGHT_SUM", result["comparison"]["passed_method_checks"])

    def test_analytic_nonlinear_tuning_and_interval(self):
        # Independent polynomial lines, negative local tuning and correlated sample noise.
        # All fifth derivatives vanish. A deterministic design fixes h before any draw.
        x = np.array([-.4, -.2, -.1, .1, .2, .4])
        w = np.array([.10, .20, .30, .05, .15, .12, .08])
        port = -2 * x + 3 * x**3
        samples = np.column_stack((port[:, None] * w, port))
        cov = np.kron(np.eye(len(x)), .0001 * (np.eye(8) + .7 * np.ones((8, 8))))
        sweep = dict(normalization="calibrated", steps=[.2, .4], offsets=x, samples_mhz=samples,
                     sample_covariance_mhz2=cov, fifth_derivative_bounds=np.zeros(8))
        est = hf.recover(sweep)
        self.assertEqual(est["step"], .4)
        np.testing.assert_allclose(est["weights"], w, atol=1e-14)
        den = np.eye(8)[-1]
        z = NormalDist().inv_cdf(.975)
        _, _, stencil, slope_cov, _ = hf.design(x, [.2, .4], 8, cov, np.zeros(8), den, z)
        rng = np.random.default_rng(20261127)
        raw = samples.ravel() + rng.standard_normal((4096, samples.size)) @ np.linalg.cholesky(cov).T
        draws = np.einsum("t,btj->bj", stencil, raw.reshape(-1, len(x), 8))
        hits = 0
        for slopes in draws:
            lo, hi = hf.ratio(slopes, slope_cov, np.zeros(8), den, z)["intervals"][2]
            hits += lo <= w[2] <= hi
        self.assertGreater(hits / len(draws), .935)
        self.assertLess(hits / len(draws), .965)


if __name__ == "__main__":
    unittest.main()
