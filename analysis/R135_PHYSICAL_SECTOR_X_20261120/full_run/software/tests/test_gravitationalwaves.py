import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from r135.common import InputError, OpenInput, canonical_hash, read_json, write_json, sha256
from r135 import gravitationalwaves as gw


def source_definition():
    return dict(kind="comoving_frequency_power",source="assigned diagnostic spectral power",
                support_source="finite support chosen for a numerical control; zero outside",
                uncertainty_source="fixed diagnostic coefficients; no physical confidence interval",
                scale_factor_convention="a=1 on the initial P7 surface; q=a*f in Hz",
                q_frequency_edges_Hz=[2.,20.,2e4,2e11,2e14],time_s=[0.,.5,1.,1.5],
                power_MeV4_s_per_logq=[[0.,0.,0.,0.],[1e-5,5e-6,2e-6,1e-6],
                                     [1e-5,5e-6,2e-6,1e-6],[0.,0.,0.,0.]],
                zero_outside_time_support=True,omitted_frequency_energy_fraction_bound=0.,
                applicability=dict(source="diagnostic isotropic weak-field subhorizon radiation",
                    subhorizon_geometric_optics=True,free_propagation_after_source=True,
                    statistically_isotropic=True,maximum_rho_GW_over_total=.01))


def diagnostic_history(samples=601):
    source=gw.GWSource(source_definition(),offset=2)
    # A finite radiation reservoir, scale factor, and GW cell energies. The
    # Hubble rate is recomputed from the full density at every RHS evaluation.
    initial=np.zeros(source.size);initial[:2]=[1.,1.]
    source.initialize(initial)
    def evaluate(t,state):
        a,rho=state[:2];rgw,_=source.moments(state)
        H=np.sqrt((rho+rgw)/gw.critical_density(1.))
        derivative,q,record=source.rhs(t,state,a,H,"00")
        return np.r_[H*a,-4*H*rho-q,derivative],H,record
    knots=np.unique(np.r_[np.linspace(0,3,samples),source.time_knots_s])
    solution=solve_ivp(lambda t,y:evaluate(t,y)[0],(0,3),initial,t_eval=knots,
                       rtol=1e-10,atol=1e-14,max_step=.02,method="DOP853")
    if not solution.success:raise RuntimeError(solution.message)
    rows=[]
    for t,state in zip(solution.t,solution.y.T):
        source.validate_accepted(state)
        _,H,record=evaluate(t,state)
        rows.append(dict(time_s=float(t),scale_factor=float(state[0]),H_s_inv=float(H),
                         rho_X_MeV4=float(state[1]),rho_free_MeV4=record["rho_GW_MeV4"],gw=record))
    history={k:[r[k] for r in rows] for k in ("time_s","scale_factor","H_s_inv","rho_X_MeV4","rho_free_MeV4")}
    history["gw"]=gw.payload_from_records(rows)
    return history


def response_policy(history):
    a0,h0=history["scale_factor"][-1],history["H_s_inv"][-1]
    a=np.geomspace(a0,1e10,129)
    exponent=np.log(h0/2.2e-18)/np.log(a[-1]/a0)
    h=h0*(a/a0)**(-exponent)
    return dict(propagation_history=dict(source="diagnostic late power-law history; no physical R135 calibration",
               interpolation="piecewise_linear_H_of_a",free_propagation=True,
               scale_factor=a.tolist(),H_s_inv=h.tolist()),
               bbn_epochs=[dict(time_s=t,source="selected numerical control epoch") for t in (0.,.5,1.5,3.)],
               quadrature_rtol=1e-4)


KEY=dict(point_id="gw-coupled-control",model_id="XB-pureSU3",thermal_path="isolated_during_transition")


class GravitationalWaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h=diagnostic_history()
        cls.policy=response_policy(cls.h)

    def test_joint_friedmann_energy_exchange_and_free_redshift(self):
        h=self.h
        a=np.asarray(h["scale_factor"])
        total=np.asarray(h["rho_X_MeV4"])+np.asarray(h["rho_free_MeV4"])
        np.testing.assert_allclose(total*a**4,1.,rtol=2e-9,atol=0)
        np.testing.assert_allclose(total,gw.critical_density(h["H_s_inv"]),rtol=1e-13,atol=0)
        self.assertGreater(h["rho_free_MeV4"][-1],0)
        self.assertLess(h["rho_X_MeV4"][-1],a[-1]**-4)
        late=np.asarray(h["time_s"])>=1.5
        redshift=np.asarray(h["gw"]["rho_MeV4_per_logq"])[late]*a[late,None]**4
        np.testing.assert_allclose(redshift,np.broadcast_to(redshift[-1],redshift.shape),rtol=3e-8,atol=0)
        report=gw.audit_history(h,quadrature_rtol=1e-4)
        self.assertEqual(report["status"],"RECONSTRUCTED")

    def test_transfer_is_derived_from_actual_density_not_a_second_energy_source(self):
        result=gw.response_from_p7(self.h,KEY,self.policy)
        self.assertEqual(result["P7_history_sha256"],canonical_hash(self.h))
        self.assertEqual(result["bbn_budget"][0]["rho_GW_over_rho_total"],0.)
        self.assertGreater(result["bbn_budget"][1]["rho_GW_over_rho_total"],0.)
        self.assertTrue(all(x["density_already_in_P7_Friedmann"] for x in result["bbn_budget"]))
        self.assertGreater(result["integrated_Omega_GW_today"],0)
        self.assertEqual(result["physical_completion_status"],"OPEN_INPUT")
        self.assertEqual(result["detectors"]["status"],"OPEN_INPUT")
        report=gw.audit_response(self.h,result,KEY)
        self.assertEqual(report["status"],"PARTIAL")
        self.assertTrue(report["no_second_BBN_energy_addition"])

    def test_corrupt_spectral_history_and_response_are_detected(self):
        changed=copy.deepcopy(self.h)
        changed["gw"]["rho_MeV4_per_logq"][-1][0]*=2
        with self.assertRaisesRegex(InputError,"independent cell integral"):
            gw.audit_history(changed)
        changed=copy.deepcopy(self.h)
        changed["gw"]["power_MeV4_s_per_logq"][20][1]*=2
        with self.assertRaisesRegex(InputError,"declared source"):
            gw.audit_history(changed)
        result=gw.response_from_p7(self.h,KEY,self.policy)
        result["Omega_GW_today_per_logf"][0]*=2
        with self.assertRaisesRegex(InputError,"independent reconstruction"):
            gw.audit_response(self.h,result,KEY)
        result=gw.response_from_p7(self.h,KEY,self.policy)
        result["point_id"]="other"
        with self.assertRaisesRegex(InputError,"identity"):
            gw.audit_response(self.h,result,KEY)

    def test_missing_source_never_becomes_a_zero_prediction(self):
        blank=dict(self.h);blank.pop("gw")
        inputs={"histories":{c:blank for c in gw.CORNERS}}
        result=gw.responses_from_p7(inputs,KEY)
        self.assertEqual(set(result["histories"]),set(gw.CORNERS))
        self.assertTrue(all(x["status"]=="OPEN_INPUT" for x in result["histories"].values()))
        self.assertTrue(all("Omega_GW_today_per_logf" not in x for x in result["histories"].values()))

    def test_source_support_and_weak_field_domain_are_enforced(self):
        definition=source_definition();definition["power_MeV4_s_per_logq"][0][0]=1e-6
        with self.assertRaisesRegex(InputError,"zero endpoint"):
            gw.GWSource(definition,offset=0)
        definition=source_definition();definition.pop("support_source")
        with self.assertRaises(OpenInput):gw.GWSource(definition,offset=0)
        source=gw.GWSource(source_definition(),offset=0)
        state=np.full(source.size,.1)
        with self.assertRaisesRegex(OpenInput,"weak-field"):
            source.rhs(.5,state,1.,.1,"00")
        with self.assertRaisesRegex(OpenInput,"subhorizon"):
            source.rhs(.5,np.zeros(source.size),1.,100.,"00")

    def test_late_history_and_every_bbn_epoch_are_bound_to_p7(self):
        with self.assertRaisesRegex(OpenInput,"late H"):
            gw.response_from_p7(self.h,KEY,{})
        policy=copy.deepcopy(self.policy)
        policy["propagation_history"]["scale_factor"][0]*=1.01
        with self.assertRaisesRegex(InputError,"actual final P7"):
            gw.response_from_p7(self.h,KEY,policy)
        policy=copy.deepcopy(self.policy);policy["bbn_epochs"][1]["time_s"]+=.0001
        with self.assertRaisesRegex(InputError,"unique saved"):
            gw.response_from_p7(self.h,KEY,policy)
        short={k:(v[:100] if isinstance(v,list) else v) for k,v in self.h.items()}
        short["gw"]=copy.deepcopy(self.h["gw"])
        for name in ("rho_MeV4_per_logq","power_MeV4_s_per_logq","rho_GW_MeV4","Q_GW_MeV4_s","rho_GW_over_total"):
            short["gw"][name]=short["gw"][name][:100]
        with self.assertRaisesRegex(OpenInput,"has not ended"):
            gw.response_from_p7(short,KEY,self.policy)

    def test_horizon_between_late_nodes_is_checked(self):
        # aH may have a maximum BETWEEN both endpoint values under linear H(a).
        source=gw.GWSource(source_definition(),offset=0)
        hist={"scale_factor":[1.],"H_s_inv":[1.]}
        policy={"propagation_history":dict(source="deliberate diagnostic horizon crossing",
                  interpolation="piecewise_linear_H_of_a",free_propagation=True,
                  scale_factor=[1.,100.],H_s_inv=[1.,.001])}
        with self.assertRaisesRegex(OpenInput,"leaves the horizon"):
            gw._late_background(hist,policy,source,np.ones((1,source.size)))

    def test_late_expansion_cannot_hide_GW_domination(self):
        policy=copy.deepcopy(self.policy)
        policy["propagation_history"]["H_s_inv"][-1]*=1e-8
        with self.assertRaisesRegex(OpenInput,"weak-field domain during late"):
            gw.response_from_p7(self.h,KEY,policy)

    def test_all_frozen_P0_paths_remain_open_and_reject_wrong_corner(self):
        from r135 import audit
        p0=Path(__file__).resolve().parents[1]/"p0_snapshot/model_register.json"
        points=read_json(p0)["points"]
        report=audit._gw_coverage({"model_register":p0},[],[],{}, {})
        self.assertEqual(report["points"],len(points))
        self.assertEqual(len(points),52)
        self.assertTrue(all(row["status"]=="OPEN_INPUT" for row in report["rows"]))
        self.assertFalse(report["full_physical_completion"])
        wrong={"histories":{corner:copy.deepcopy(self.h) for corner in gw.CORNERS}}
        with self.assertRaisesRegex(InputError,"corner differs"):
            gw.responses_from_p7(wrong,KEY,self.policy)

    def test_P9_auditor_reconstructs_same_P7_as_BBN_and_rejects_freshly_hashed_corruption(self):
        from r135 import audit
        key=dict(claim_id="XB_SU3_cosmology",**KEY)
        channel={"histories":{corner:copy.deepcopy(self.h) for corner in gw.CORNERS}}
        for corner,h in channel["histories"].items():h["gw"]["corner"]=corner
        response=gw.responses_from_p7(channel,key,self.policy)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            p7=root/"p7.json";p8=root/"p8.json"
            write_json(p7,channel)
            response["source_P7_file_sha256"]=sha256(p7)
            write_json(p8,{"source_P7_file_sha256":sha256(p7)})
            write_json(root/"gw_response.json",response)
            bundle=dict(root=root,key=tuple(key[k] for k in audit.KEY_FIELDS),request={"inputs":[
                dict(name="channel_history",path=str(p7),sha256=sha256(p7)),
                dict(name="bbn_inputs",path=str(p8),sha256=sha256(p8))]})
            check=audit.audit_gw_p9(bundle,{})
            self.assertEqual(check["status"],"PARTIAL")
            self.assertTrue(all(r["numerical_status"]=="RECONSTRUCTED" for r in check["histories"].values()))
            response["histories"]["11full"]["Omega_GW_today_per_logf"][0]*=1.1
            write_json(root/"gw_response.json",response)
            with self.assertRaisesRegex(InputError,"independent reconstruction"):
                audit.audit_gw_p9(bundle,{})
            response["histories"]["11full"]["Omega_GW_today_per_logf"][0]/=1.1
            write_json(root/"gw_response.json",response)
            write_json(p8,{"source_P7_file_sha256":"0"*64})
            bundle["request"]["inputs"][1]["sha256"]=sha256(p8)
            with self.assertRaisesRegex(InputError,"same exact P7"):
                audit.audit_gw_p9(bundle,{})

    def test_marker_and_reduced_validation_do_not_require_unrelated_GW(self):
        from r135 import audit
        from test_audit import seal_fixture
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            for claim in ("graph_as_XB_marker","XB_SU3_cosmology"):
                p1=root/claim;p1.mkdir()
                key=dict(claim_id=claim,**KEY)
                for name in ("scale.json","eos_bundle.json","initial_history.json"):
                    write_json(p1/name,{"scope":"explicitly reduced audit fixture"})
                manifest=seal_fixture(p1,"P1",key=key)
                config=dict(_mode="validation",expected_keys=[key],required_stages={claim:["P1"]},
                            results=[dict(key=key,stage="P1",manifest_input="p1")])
                result=audit.run(config,{"p1":manifest},root/(claim+"-audit"))
                self.assertEqual(result["metrics"]["partial_rows"],0)
                matrix=read_json(root/(claim+"-audit")/"gw_channel_status.json")
                self.assertEqual(matrix["rows"][0]["status"],"OPEN_INPUT")

    def test_P7_auditor_combines_GW_with_resolved_free_particles(self):
        from r135 import audit,history
        from test_history import fixture
        args=list(copy.deepcopy(fixture()))
        config=args[0]
        config["gw_source"]=source_definition()
        config["kinetic_species"]=[dict(name="free-control",sector="free",source="diagnostic collisionless cells",
            statistics="fermion",degeneracy=1,q_edges_MeV=[0.,.1,1.],initial_occupation=[.1,.01],
            operator={"kind":"collisionless"})]
        config.update(dict(zip(("eos_bundle","nucleation_definition","wall_transport","collision_model","initial_history"),args[1:])))
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            self.assertEqual(history.run(config,{},root)["software_status"],"PASS")
            result=audit.audit_p7({"root":root},quadrature_rtol=.05)
            self.assertTrue(all(r["gw"]["status"]=="RECONSTRUCTED" for r in result["recomputed"].values()))

    def test_none_source_has_no_state_or_energy(self):
        source=gw.GWSource(None,offset=31)
        self.assertEqual(source.size,31)
        self.assertEqual(source.moments(np.zeros(31)),(0.,0.))
        self.assertIsNone(gw.payload_from_records([{"gw":None},{"gw":None}]))


if __name__ == "__main__":unittest.main()
