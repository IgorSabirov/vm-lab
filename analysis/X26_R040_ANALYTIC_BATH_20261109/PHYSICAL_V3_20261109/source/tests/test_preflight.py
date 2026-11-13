import json
import unittest
from pathlib import Path
from x26r040.provenance import preflight


ROOT=Path(__file__).resolve().parents[1]


def accepted_test_manifest():
    d=json.loads((ROOT/"configs/R040_SPECTRAL_INPUT.template.json").read_text())
    d["model_assumptions_accepted"]=True
    d["freeze_state"]="FROZEN"
    d["freeze_record_ref"]="test:synthetic-freeze-only"
    d["freeze_record_sha256"]="a"*64
    d["energy_unit"]="arb_energy_test_only"
    d["time_unit"]="hbar/energy"
    d["model"].update({"E_V":0.8,"E_1":0.2,"E_2":0.1,"t_1":0.15,
                       "t_2":0.3,"gamma_d":0.2,"kappa":1.0,"g":0.22})
    for key in d["provenance"]:
        d["provenance"][key]={"source":"MODEL_ASSUMPTION",
                              "evidence_ref":None,
                              "assumption":"Synthetic preflight fixture only; not physical input."}
    d["pole_search"]["seeds"]=[[0.33,-0.02]]
    d["runtime_gate"]={"status":"CALIBRATED","calibration_ref":"test:synthetic-only",
                        "calibration_sha256":"b"*64,"forecast_sha256":"c"*64,
                        "environment_fingerprint":"d"*64,
                        "forecast_ref":"test:synthetic-only","forecast_seconds":10.0,
                        "lower_seconds":5.0,"upper_seconds":15.0,"hard_wall_seconds":20.0,
                        "memory_limit_mib":1024,"disk_limit_mib":256}
    return d


class TestPreflight(unittest.TestCase):
    def test_template_blocks_main_and_vm_submit(self):
        d=json.loads((ROOT/"configs/R040_SPECTRAL_INPUT.template.json").read_text())
        result=preflight(d)
        self.assertFalse(result["submit_allowed"])
        self.assertGreater(result["blocker_count"],0)
        self.assertEqual(result["scientific_status"],"CONDITIONAL_MODEL_ONLY; NOT_ADD_DERIVED")

    def test_explicitly_accepted_model_assumptions_pass_formal_gate(self):
        result=preflight(accepted_test_manifest())
        self.assertTrue(result["submit_allowed"])
        self.assertEqual(result["blocker_count"],0)

    def test_fabricated_provenance_status_is_rejected(self):
        d=accepted_test_manifest()
        d["provenance"]["g"]={"source":"USER_SUPPLIED_UNVERIFIED","assumption":"unverified"}
        result=preflight(d)
        self.assertFalse(result["submit_allowed"])
        self.assertTrue(any(x["id"]=="PROVENANCE_G_INVALID" for x in result["blockers"]))

    def test_add_derived_requires_evidence_digest(self):
        d=accepted_test_manifest()
        d["provenance"]["g"]={"source":"ADD_DERIVED","evidence_ref":"analysis/derivation.md"}
        result=preflight(d)
        self.assertFalse(result["submit_allowed"])
        self.assertTrue(any(x["id"]=="PROVENANCE_G_EVIDENCE_DIGEST_MISSING" for x in result["blockers"]))

    def test_runtime_interval_must_be_ordered(self):
        d=accepted_test_manifest()
        d["runtime_gate"]["lower_seconds"]=12.0
        d["runtime_gate"]["forecast_seconds"]=10.0
        result=preflight(d)
        self.assertFalse(result["submit_allowed"])
        self.assertTrue(any(x["id"]=="VM_RUNTIME_INTERVAL_INCONSISTENT" for x in result["blockers"]))


if __name__=="__main__":
    unittest.main()
