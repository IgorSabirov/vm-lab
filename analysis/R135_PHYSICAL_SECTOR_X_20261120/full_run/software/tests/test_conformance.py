"""Regressions for PR160 dispositions, precision evidence, convergence and paired fits."""
import copy
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from r135 import audit, gw_review, history_observables, history_refinement, joint_grid, observations, weak_precision
from r135.common import canonical_hash, InputError, OpenInput, read_json, sha256, write_json
from r135.nuclear_covariance import covariance, validate_design
from test_observations import class_model, history, weak
from test_pr160_integration import KEY, p8_inputs


class PrecisionTests(unittest.TestCase):
    def test_free_flags_do_not_certify_nonthermal_histories(self):
        for flag in (None, True, False):
            with self.subTest(flag=flag), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                h = history()
                t = np.array([.01, .008, .006])
                a = t[0]/t
                rg = np.pi**2*t**4/15
                h.update(scale_factor=a.tolist(), T_gamma_MeV=t.tolist(), T_nu_MeV=(t*(4/11)**(1/3)).tolist(),
                         n_b_cm3=(1e20/a**3).tolist(), rho_gamma_MeV4=rg.tolist(),
                         rho_nu_MeV4=(3.044*(7/8)*(4/11)**(4/3)*rg).tolist(), rho_extra_MeV4=[0.]*3, p_extra_MeV4=[0.]*3)
                h["f_nu_e"] = h["f_antinu_e"] = {"energy_MeV": [.002,.01], "values": [[.5,.2]]*3}
                model = class_model()
                model["matching"] = dict(source="late diagnostic", transfer_finished=True, electron_annihilation_finished=True)
                files = p8_inputs(root, h)
                rates = weak()
                if flag is not None:
                    rates["production_precision_validated"] = flag
                rates["neutrino_spectra_sha256"] = observations.bridge_hash({k:h[k] for k in ("f_nu_e","f_antinu_e")})
                write_json(files["weak_rates"], {"histories":dict.fromkeys(observations.CORNERS,rates)})
                out = root/"P8"
                out.mkdir()
                observations.run({"_mode":"validation", "_key":KEY, "common_initial_abundances":[.2,.8,0,0,0,0,0,0],
                                  "class":model}, files, out)
                src = files["channel_history"]
                records = [{"name":"channel_history", "path":str(src), "sha256":sha256(src)}]
                result = audit.audit_p8({"root":out,"request":{"inputs":records}}, {sha256(src):src})
                self.assertEqual(result["status"], "PARTIAL")
                self.assertEqual(sum("WEAK" in reason for reason in result["unresolved"]), 5)

    def test_weak_error_budget_uses_both_helium_trajectories(self):
        rates = {"included_corrections":list(set(weak_precision.OMITTED_CORRECTIONS)-{"flavour_density_matrix_evolution"}),
                 "solver_sha256":"a"*64, "time_s":[0., 1.], "lambda_n_to_p_s_inv":[1.,.5], "lambda_p_to_n_s_inv":[.1,.05]}
        item = {"canonical":{"history":{"f_nu_e":{}}}, "weak_rates":rates}
        ref = {**rates, "solver_sha256":"b"*64, "input_sha256":canonical_hash(item), "source":"reference control",
               "unit":"s^-1", "Yp":.25, "Yp_abs_uncertainty":.001}
        policy = {"atol_s_inv":1e-6, "rtol":.01, "max_abs_delta_Yp":.003}
        check = weak_precision.compare(item,ref,policy)
        self.assertEqual(check["status"],"RATES_REPRODUCED")
        self.assertEqual(weak_precision.helium_check(check,{"linx":.25})["status"],"OPEN_INPUT")
        self.assertEqual(weak_precision.helium_check(check,{"linx":.25,"primat":.251})["status"],"PRECISION_VALIDATED")
        self.assertEqual(weak_precision.helium_check(check,{"linx":.25,"primat":.26})["status"],"FAIL_HELIUM_PRECISION")
        self.assertEqual(weak_precision.compare(item,{**ref,"lambda_n_to_p_s_inv":[3.,2.]},policy)["status"],"FAIL_RATE_PRECISION")
        with self.assertRaises(InputError):
            weak_precision.compare(item,{**ref,"input_sha256":"c"*64},policy)


class CoverageTests(unittest.TestCase):
    def test_gw_ordinary_matrix_reads_scoped_argument(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            register = Path(__file__).resolve().parents[1]/"p0_snapshot/model_register.json"
            p = next(p for p in read_json(register)["points"] if p["point_id"]=="XB-FMS-bottom-left")
            ident = {k:p[k] for k in gw_review.IDENTITY}
            proof = root/"proof.json"
            write_json(proof,{**ident,"physical_argument":"synthetic routing test"})
            key = ("XB_SU3_cosmology",p["model_id"],p["point_id"],p["thermal_path"])
            result = audit._gw_coverage({"model_register":register,"inapplicability_evidence":proof},[key],[],{}, {})
            row = next(r for r in result["rows"] if r["point_id"]==p["point_id"])
            self.assertEqual(row["status"],"INAPPLICABILITY_FOR_REVIEW")
            self.assertFalse(row["full_physical_completion"])
            with self.assertRaises(InputError):
                gw_review.review(row,{"inapplicability_evidence":{"file":proof.name,"sha256":sha256(proof)}},
                                 root,{"histories":{"00":{"status":"CONDITIONAL"}}},{})

    def test_gw_marginal_likelihood_and_raw_readback(self):
        record = dict.fromkeys(("release","foreground_model","systematics","prior","solver_version","overlap_policy"), "control")
        record.update(weights=[.25,.75],logL_signal=[1,3], logL_null=[2,4],delta_logL=-1.)
        out = gw_review.marginalize(record)
        self.assertAlmostEqual(out["logL_signal"], math.log(.25*math.exp(1)+.75*math.exp(3)))
        with self.assertRaises(InputError):
            gw_review.marginalize({**record,"delta_logL":0.})

    def test_weighted_nuclear_population(self):
        np.testing.assert_allclose(covariance([[0,1],[2,5]],[.25,.75]), [[.75,1.5],[1.5,3.]])
        with self.assertRaises(InputError):
            validate_design({"source":"test","reaction_order":["r"],"nodes":[{"q":[0],"weight":.5}]*2},
                            {"reactions":[{"id":"r"}]})

    def test_kinetic_entropy_and_equality(self):
        s = history_observables.kinetic_entropy({"occupation":[.5],"statistics":"fermion","degeneracy":2,"q_edges_MeV":[0,1]})
        self.assertAlmostEqual(s, math.log(2)/(3*math.pi**2))
        crossing = history_observables.domination([0,1],[1,2],[1,.5],[[0,2,0,0,1],[1,1,0,0,1]])
        self.assertAlmostEqual(crossing["a"],1.5)
        self.assertAlmostEqual(crossing["T_gamma_MeV"],.75)

    def test_mixed_convergence_checks_factorial_response(self):
        level = {"time_s":[0.,1.], "f":[0.,.4], "T_X_over_T0":[1.,.5], "H_over_H0":[1.,.2],
                 "delivered_energy":[[0.,0.],[1.,-1.]]}
        cases = {c:{"levels":[copy.deepcopy(level) for i in range(3)]} for c in observations.CORNERS}
        cases["10"]["levels"][2]["f"][-1]+=.1
        result = history_refinement.mixed_check(cases,.001)
        self.assertEqual(result["residuals"]["full_minus_additive"]["status"],"PASS")
        self.assertEqual(result["residuals"]["factorial_interaction"]["status"],"FAIL_CONVERGENCE")

    def test_unfinished_grid_never_reports_an_optimum(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ref = {"file":"plan.json","P9":"p9","sha256":"1"*64}
            coordinates = {"eta_b_gamma":6e-10}
            spec = {"schema":"r135-joint-grid-v1","axes":{"eta_b_gamma":[6e-10]}, "corner":"11full",
                    "cells":[{"coordinates":coordinates,"pipelines":{"baseline":ref,"X":{**ref,"sha256":"2"*64}}}]}
            write_json(root/"spec.json",spec)
            with patch.object(joint_grid,"evaluate_cell",side_effect=OpenInput("missing physical history")):
                result = joint_grid.run(root/"spec.json",root/"out")
            self.assertEqual(result["status"],"OPEN_INPUT")
            self.assertFalse(result["profiles"])
            with self.assertRaises(InputError):
                joint_grid.cells_for({**spec,"cells":[]})

    def test_complete_gw_grid_still_needs_point_decision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            identity = dict(zip(gw_review.IDENTITY, ("theory","test-point","exchange_during_transition")))
            row = {**identity, "role":"physical_candidate", "stage_evidence":[
                {"stage":s,"mode":"physical","lineage_reasons":[]} for s in ("P5","P7","P9")]}
            def save(name, data):
                path = root/(name+".json")
                write_json(path,data)
                return {"file":path.name,"sha256":sha256(path)}
            histories = {c:{"source_sha256":canonical_hash(c),"status":"CONDITIONAL"} for c in observations.CORNERS}
            response = {"histories":histories}
            checked = {"detector_data_replayed":True,"source_P7_file_sha256":"1"*64,"histories":{
                c:{"numerical_status":"RECONSTRUCTED"} for c in histories}}
            source = {"source":"synthetic positive-path arithmetic test","method":"prescribed test distribution",
                      "P7_file_sha256":"1"*64,"source_hashes":{c:r["source_sha256"] for c,r in histories.items()}}
            likelihood = {}
            for c,r in histories.items():
                rec=dict.fromkeys(("release","foreground_model","systematics","prior","solver_version","overlap_policy"), "test")
                likelihood[c]={**rec,"response_sha256":canonical_hash(r),"weights":[1.],"logL_signal":[.2],"logL_null":[.1],"delta_logL":.1}
            supporting={k:save(k,source) for k in ("source_calibration","source_uncertainty_propagation")}
            supporting.update({k:save(k,likelihood) for k in ("PTA_HD","LVK")})
            proof = save("proof",{**identity,"physical_argument":"test only","supporting_files":supporting,
                                   "response_sha256":canonical_hash(response)})
            entry={"physical_evidence":proof}
            self.assertEqual(gw_review.review(row,entry,root,response,checked)["status"],"FULL_RESPONSE_FOR_REVIEW")
            with self.assertRaises(InputError):
                gw_review.review(row,{**entry,"decision_id":"invalid"},root,response,checked)

    def test_pion_projection_keeps_channels_distinct_and_checks_history(self):
        from r135.meson_conversion import project
        from r135.common import HBARC_MEV_CM
        species = {"mass_MeV":139.57039,"statistics":"boson","degeneracy":1,"q_edges_MeV":[0.,1.],"occupation":[.25]}
        h = {"time_s":[0.,1.],"scale_factor":[1.,2.],"kinetic_species":[
                [{**species,"name":n} for n in ("minus","plus")] for _ in range(2)]}
        channels = {k:{"species":n,"mass_MeV":139.57039,"q_edges_MeV":[0.,1.],"sigma_v":[[x],[x]]}
                    for k,n,x in (("pi_minus_p_to_n","minus",2e-17),("pi_plus_n_to_p","plus",1e-17))}
        record = {"history_sha256":"test","source":"test kernel","unit":"cm^3/s","time_s":h["time_s"],"channels":channels}
        result = project(h,record,"test")
        self.assertAlmostEqual(result["p_to_n_s_inv"][0]*6*math.pi**2*HBARC_MEV_CM**3/.25/2e-17,1.)
        self.assertAlmostEqual(result["p_to_n_s_inv"][0]/result["n_to_p_s_inv"][1],16.)
        with self.assertRaises(InputError):
            project(h,record,"other")

    def test_grid_covers_every_independent_X_preparation(self):
        coordinates = {"eta_b_gamma":6e-10}
        spec = {"axes":{"eta_b_gamma":[6e-10]}, "X_points":["a","b"],
                "cells":[{"coordinates":coordinates, "X_point_id":p, "pipelines":{"baseline":{},"X":{}}}
                         for p in ("a","b")]}
        self.assertEqual(len(joint_grid.cells_for(spec)),2)
        with self.assertRaises(InputError):
            joint_grid.cells_for({**spec,"cells":spec["cells"][:1]})
