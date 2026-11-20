import json
import math
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from fetch import HERE, acquire
from extract import baseline_observations
from kinetic_control import hubble, moments
from scipy.integrate import quad

COOKE = r"\begin{abstract}deduce that the primordial deuterium abundance is $\log_{10}\,({\rm D/H})_{\rm P} = -4.5974\pm0.0052$\end{abstract}"
AVER = (
    "\n"
    + r"\abstract{"
    + "\n"
    + r"From a regression to zero metallicity, we determine Y$_{p}$ $=$ 0.2449 $\pm$ 0.0040"
    + "\n}\n"
    + r"\keywords{}"
)


class PhysicalInputs(unittest.TestCase):
    def test_bbn_malformed_abstract(self):
        for bad in [
            COOKE.replace("deduce", "omit"),
            COOKE + COOKE,
            COOKE.replace("-4.5974", "-0.20"),
            COOKE.replace(r"\begin{abstract}", ""),
        ]:
            with (
                self.subTest(bad=bad),
                patch("extract.article", side_effect=[bad, AVER]),
                self.assertRaises(ValueError),
            ):
                baseline_observations(dict(cooke=None, aver=None))
        with patch("extract.article", side_effect=[COOKE + " -3.0", AVER]):
            self.assertEqual(
                baseline_observations(dict(cooke=None, aver=None))["Aver-Yp"]["value"],
                0.2449,
            )

    def test_friedmann_and_relativistic_gas(self):
        for rho in (1e-9, 12.0):
            self.assertAlmostEqual(
                hubble(rho) / math.sqrt(8 * math.pi * 6.70883e-39 * rho / 3),
                1.0,
                delta=0.0002,
            )
        for x in (5.0, 8.28, 22.3):

            def weight(p):
                return p**2 * math.exp(-math.hypot(p, x))

            n = quad(weight, 0, math.inf, epsabs=1e-15)[0]
            energy = (
                quad(lambda p: math.hypot(p, x) * weight(p), 0, math.inf, epsabs=1e-15)[
                    0
                ]
                / n
            )
            logn, e, cv = moments(x, 1.0)
            self.assertAlmostEqual(
                math.exp(logn) * 2 * math.pi**2 * x**3 / n, 1.0, places=7
            )
            self.assertAlmostEqual(e, energy, places=7)
            self.assertGreater(cv, 0.0)

    @unittest.skipUnless(
        os.getenv("R135_DONOR_CACHE"), "requires the immutable donor cache"
    )
    def test_real_release_replay(self):
        from audit import run

        cache = Path(os.environ["R135_DONOR_CACHE"])
        data = run(
            acquire(
                cache,
                {
                    "physics",
                    "observations",
                    "bbn_baseline",
                    "interface",
                    "portal",
                    "lattice_controls",
                },
                True,
            )
        )
        ref = json.loads((HERE / "validation.json").read_text())

        def same(a, b):
            if isinstance(b, dict):
                self.assertEqual(a.keys(), b.keys())
                for k in b:
                    same(a[k], b[k])
            elif isinstance(b, list):
                self.assertEqual(len(a), len(b))
                for x, y in zip(a, b):
                    same(x, y)
            elif isinstance(b, float):
                self.assertTrue(math.isclose(a, b, rel_tol=1e-6, abs_tol=5e-11), (a, b))
            else:
                self.assertEqual(a, b)

        same(data, ref)
        self.assertEqual(len(data["source_physics"]["states"]), 12)
        self.assertEqual(len(data["source_physics"]["continuum_s_over_T3"]), 25)
        self.assertEqual(
            [r["point_id"] for r in data["rows"]],
            [
                "XB-FMS-top-left",
                "XB-FMS-top-right",
                "XB-FMS-bottom-left",
                "XB-FMS-bottom-right",
            ],
        )
        self.assertEqual(
            data["matched_interface"]["sigma_over_Tc3"],
            {"value": 0.0125, "sigma": 0.0017},
        )
        self.assertAlmostEqual(
            data["dim8_portal"]["K_gg"],
            8 * 0.25 * (2.3 / (120 * math.pi)) ** 2 / (4 * math.pi),
        )
