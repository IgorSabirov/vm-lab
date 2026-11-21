"""Independent controls of the public-input reconstruction, executable with unittest."""
import json
import unittest

import numpy as np
from scipy.integrate import simpson
from scipy.interpolate import PchipInterpolator

import replay_eos as eos


class StableEOS(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((eos.HERE/"donor_inputs.json").read_text())
        cls.result = json.loads((eos.HERE/"eos_pair_su3.json").read_text())

    def test_domain_and_shape(self):
        for phase, good, bad in (("hot", 1.08, 0.99931), ("cold", 0.9, 1.001)):
            self.assertIsInstance(eos.fits(self.data,phase,good)[0], float)
            result = eos.fits(self.data,phase,[[good],[good]])[0]
            self.assertEqual(result.shape, (2,1))
            for invalid in (bad, np.nan, np.inf):
                with self.assertRaises(ValueError):
                    eos.fits(self.data,phase,[good,invalid])

    def test_data_in_paper(self):
        for x, observation, error in [(0.8,0.030,0.009),(0.98,0.198,0.004),
                                      (1.08,3.301,0.031),(1.10,3.499,0.033)]:
            qs = eos.fits(self.data, "cold" if x < 1 else "hot", x)[0]
            self.assertLess(abs(qs-observation),error)
        boyd = self.result["cold_gas_control"]["Boyd"]
        self.assertAlmostEqual(boyd["0.8"]["s_T3"],0.026214,places=6)
        self.assertAlmostEqual(boyd["1.0"]["s_T3"],0.089508,places=6)

    def test_integrated_pressure_and_units(self):
        pc = self.result["anchor"]["p_Tc4"]
        for phase in eos.DOMAIN:
            rows = self.result["stable"][phase]
            at_tc = next(row for row in rows if row["x"]==1)
            self.assertEqual(at_tc["p_Tc4"], pc)
            for row in rows:
                x = row["x"]
                self.assertAlmostEqual(row["rho_Tc4"]+row["p_Tc4"],x*row["s_Tc3"])
                # Composite quadrature independent of QUADPACK. Split at hot fit join
                # and use x=1-u^3 below Tc to regularize the cold endpoint.
                if phase == "cold":
                    u = np.linspace(0., np.cbrt(1.-x), 513)
                    grid = np.maximum(0.8, 1.-u**3)
                    vals = -3*u**2*grid**3*eos.fits(self.data,phase,grid)[0]
                    area = simpson(vals,x=u)
                else:
                    edges = [1,1.1,x] if x>1.1 else [1,x]
                    area = 0.
                    for j,(lo,hi) in enumerate(zip(edges,edges[1:])):
                        grid = np.linspace(lo,hi,513)
                        coeff = self.data["entropy_fit"]["hot"][j]
                        area += simpson(grid**3*eos.rational(np.log(grid),coeff)[0],x=grid)
                self.assertAlmostEqual(pc+area,row["p_Tc4"],places=7)

    def test_literature_scenarios(self):
        checks = self.result["peer_review_controls"]
        self.assertLess(checks["max_absolute_pull_25_table_rows"],1.0)
        self.assertAlmostEqual(checks["common_anchor_using_cold_fit"],0.017769,places=6)
        self.assertAlmostEqual(checks["rankine_hugoniot_example"]["v_minus_wall_frame"],0.02946,places=5)
        self.assertAlmostEqual(checks["alpha_at_Tc_from_combined_L"],0.26626,places=5)
        self.assertGreater(1-checks["last_cold_fit_heat_capacity_zero_x"],1e-6)
        self.assertLess(1-checks["last_cold_fit_heat_capacity_zero_x"],2e-6)
        for scenario in checks["smooth_fit_scenarios"].values():
            self.assertTrue(np.all(np.linalg.eigvalsh(scenario["conditional_coefficient_covariance"])>0))
        seam = self.result["diagnostics"]["hot_join_left_right"]
        self.assertAlmostEqual(seam[1]["cs2_fit_diagnostic"]/seam[0]["cs2_fit_diagnostic"]-1,.0107,places=4)

    def test_common_anchor_and_sensitivity(self):
        for phase, x in (("cold", 0.95), ("hot", 1.05)):
            rows = eos.knots(self.data,phase)
            xx = np.array([r["T_over_Tc"] for r in rows])
            interp = PchipInterpolator(xx,xx**3*[r["value"] for r in rows])
            base,shifted = [eos.stable_row(self.data,phase,x,pc,interp) for pc in (.017,.019)]
            self.assertAlmostEqual(shifted["p_Tc4"]-base["p_Tc4"],.002)
            self.assertAlmostEqual(shifted["rho_Tc4"]-base["rho_Tc4"],-.002)
            self.assertEqual(shifted["w_Tc4"],base["w_Tc4"])
        cold = self.result["stable"]["cold"]
        self.assertIsNone(next(r for r in cold if r["x"]==1)["cs2_fit_diagnostic"])
        self.assertIsNone(self.result["delta_p_Tc4"]["off_coexistence"])
        self.assertFalse(self.result["handoff"]["hydro_ready"])


if __name__ == "__main__":
    unittest.main()
