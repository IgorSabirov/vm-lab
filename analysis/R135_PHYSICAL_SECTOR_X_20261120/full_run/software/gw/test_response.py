import copy
import json
import math
import hashlib
from pathlib import Path
import unittest
import tempfile

import numpy as np
from response import spectrum, transfer
from status import coverage


class WaveTransfer(unittest.TestCase):
    def setUp(self):
        self.h = json.loads(
            (Path(__file__).parent / "validation_input.json").read_text()
        )

    def test_constant_spectrum_and_horizon(self):
        self.h["source"].update(f_star_Hz=[1.0, 10.0], omega_star=[0.001, 0.001])
        # Epoch inside our simple mock history, with an independently specified horizon.
        self.h["bbn_epochs"].append(dict(a_over_a0=2e-10, H_s_inv=2 * math.pi))
        f, o, b = transfer(self.h)
        np.testing.assert_allclose(f, [1e-10, 1e-9], rtol=1e-13, atol=0)
        self.assertEqual(b[0]["rho_GW_over_rho_total"], 0)
        self.assertAlmostEqual(b[1]["rho_GW_over_rho_total"], 0.001 * math.log(10))
        self.assertAlmostEqual(
            b[2]["rho_GW_over_rho_total"],
            0.001 * math.log(5) / (16 * (2 * math.pi) ** 2),
        )
        self.h["source"]["omega_star"] = [0.0, 0.0]
        self.assertEqual(max(transfer(self.h)[1]), 0.0)

    def test_acoustic_energy_fraction_and_duration(self):
        self.h["source"] = dict(
            kind="sound",
            R_star_light_seconds=0.01,
            sound_speed_c=0.57,
            bulk_kinetic_over_total_density=0.08,
            k_peak_R=10.0,
            duration_seconds=0.03,
            tilde_Omega=0.012,
            frequency_support_Hz=[1, 1e4],
        )
        f, o = spectrum(self.h)
        other = copy.deepcopy(self.h)
        other["source"]["bulk_kinetic_over_total_density"] *= 2
        other["source"]["duration_seconds"] /= 2
        np.testing.assert_allclose(spectrum(other)[1], 2 * o)
        self.assertLess(abs(f[np.argmax(o)] / (10 / (0.02 * math.pi)) - 1), 0.005)
        other["source"]["frequency_support_Hz"] = [0.01, 10.0]
        with self.assertRaises(ValueError):
            spectrum(other)

    def test_missing_physical_source(self):
        point = dict(
            point_id="XB",
            thermal_path="isolated",
            model_id="SU3",
            role="literature_benchmark",
        )
        self.assertEqual(coverage([point], {}, Path("."))[0]["status"], "OPEN_INPUT")
        with self.assertRaises(ValueError):
            coverage([point], {"not-X": {}}, Path("."))
        with self.assertRaisesRegex(ValueError,"Duplicate"):
            coverage([point,point], {}, Path("."))

    def test_new_checksums_do_not_validate_wrong_transfer(self):
        self.h.update(model_id="diagnostic-SU3",thermal_path="isolated_during_transition")
        point={k:self.h[k] for k in ("point_id","model_id","thermal_path")}
        point["role"]="diagnostic"
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            def save(name,value):
                path=root/name
                path.write_text(json.dumps(value))
                return dict(file=name,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            history=save("history.json",self.h)
            f,omega,budget=transfer(self.h)
            response=dict(history_id=self.h["history_id"],point_id=point["point_id"],
                          input_sha256=history["sha256"],f_today_Hz=f.tolist(),
                          Omega_GW_today=omega.tolist(),bbn_budget=budget,
                          detectors={"scope":"diagnostic artifact; no likelihood claim"})
            submissions={point["point_id"]:dict(history=history,response=save("response.json",response))}
            self.assertEqual(coverage([point],submissions,root)[0]["status"],"CONDITIONAL")
            response["Omega_GW_today"][0]*=2
            submissions[point["point_id"]]["response"]=save("response.json",response)
            with self.assertRaisesRegex(ValueError,"independent reconstruction"):
                coverage([point],submissions,root)
