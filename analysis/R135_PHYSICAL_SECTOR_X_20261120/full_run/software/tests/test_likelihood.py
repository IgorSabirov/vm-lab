import math
import os
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from r135.common import InputError, OpenInput
from r135.likelihood import (PlanckLikelihood, bbn_loglike, calibrated_decision,
                            joint_loglike, validate_spectra)


class LikelihoodTests(unittest.TestCase):
    def test_bbn_likelihood_at_frozen_mean(self):
        releases = [{"kind": "published_statistic", "observable": "log10_D_over_H", "value": -4.5974, "sigma": .0052},
                    {"kind": "published_statistic", "observable": "Y_p", "value": .2449, "sigma": .004}]
        result = bbn_loglike(10 ** -4.5974, .2449, releases, [[0., 0.], [0., 0.]])
        self.assertAlmostEqual(result["chi2_BBN"], 0.)
        changed = bbn_loglike(10 ** (-4.5974 + .0052), .2449 + .004, releases, [[0., 0.], [0., 0.]])
        self.assertAlmostEqual(changed["chi2_BBN"], 2.)
        with self.assertRaises(InputError):
            bbn_loglike(1e-5, .24, releases, [[1., 2.], [2., 1.]])

    def test_missing_planck_tail_and_wrong_units_rejected(self):
        spectra = {"ell": list(range(2, 2509)), "unit": "microK^2", "convention": "Cl",
                   "TT": [1.] * 2507, "EE": [.5] * 2507, "TE": [.1] * 2507}
        self.assertEqual(validate_spectra(spectra).shape, (6, 2509))
        spectra["unit"] = "dimensionless"
        with self.assertRaises(InputError):
            validate_spectra(spectra)
        spectra["unit"] = "microK^2"
        spectra["ell"] = list(range(2, 2501))
        with self.assertRaises(InputError):
            validate_spectra(spectra)

    def test_no_double_cmb_constraint_or_uncalibrated_exclusion(self):
        with self.assertRaises(InputError):
            joint_loglike({"logL_BBN": 1}, {"logL": 2, "log_prior": -1}, extra_cmb_gaussians={"Neff": [3., .1]})
        with self.assertRaises(OpenInput):
            calibrated_decision(5., {"threshold": 3.84})
        answer = calibrated_decision(5., {"threshold": 4.2, "source": "registered bootstrap", "sampling_distribution_sha256": "a" * 64})
        self.assertEqual(answer["outcome"], "EXCLUDED")


@unittest.skipUnless(os.environ.get("R135_PLANCK_ROOT"), "optional verified Planck archive and pinned clipy environment required")
class ActualPlanckTests(unittest.TestCase):
    def test_external_spectrum_read_and_nonzero_response(self):
        likelihood = PlanckLikelihood(os.environ["R135_PLANCK_ROOT"])
        theory = np.loadtxt(os.environ["R135_PLANCK_THEORY"])
        ell = theory[:, 0].astype(int)
        factor = 2 * np.pi / (ell * (ell + 1))
        spectra = {"ell": ell.tolist(), "unit": "microK^2", "convention": "Cl",
                   **{name: (theory[:, column] * factor).tolist() for name, column in (("TT", 1), ("TE", 2), ("EE", 3), ("BB", 4))}}
        baseline = likelihood.evaluate(spectra)
        self.assertAlmostEqual(baseline["logL"], -1382.11612551, delta=1e-5)
        spectra["TT"][198] *= 1.02
        changed = likelihood.evaluate(spectra)
        self.assertGreater(abs(changed["logL"] - baseline["logL"]), 1e-7)
        self.assertNotEqual(changed["spectra_sha256"], baseline["spectra_sha256"])
        self.assertEqual(likelihood.receipt()["actual_evaluations"], 2)


if __name__ == "__main__":
    unittest.main()
