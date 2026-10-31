import copy,hashlib,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from scipy.integrate import simpson
from test_e002d import synthetic_results
from e002d_exp.engine import compare_pair,Trajectory
from e002d_exp.analysis import analyze
from e002d_exp.task import execute_cohort,run,validate_provenance
from e002d_exp.verify_analysis import verify_derived

class ReviewRegressionTests(unittest.TestCase):
    def test_nonfinite_comparisons(self):
        a=dict(names=["x","p_m6"],dnames=["W_s0","valid_s0","c01_m6_re"],
            series=np.array([[0.,1.,0.],[2.,1.,0.]]),diagnostics=np.array([[0.,np.nan,0.,np.nan],[2.,np.nan,0.,np.nan]]))
        self.assertTrue(compare_pair(a,copy.deepcopy(a))["pass_gate"])
        for left,right in ((1.,np.inf),(np.inf,np.inf),(1.,np.nan),(np.nan,np.nan)):
            x,y=copy.deepcopy(a),copy.deepcopy(a);x["series"][:,1]=left;y["series"][:,1]=right
            self.assertFalse(compare_pair(x,y)["pass_gate"])
        for col in (2,):
            x,y=copy.deepcopy(a),copy.deepcopy(a)
            x["diagnostics"][:,col]=1.;y["diagnostics"][:,col]=1.
            self.assertFalse(compare_pair(x,y)["pass_gate"])
        x,y=copy.deepcopy(a),copy.deepcopy(a);x["series"][:,2]=.5;y["series"][:,2]=.5
        self.assertFalse(compare_pair(x,y)["pass_gate"])

    def test_provenance_records(self):
        with tempfile.TemporaryDirectory() as tmp,patch("e002d_exp.task.ROOT",Path(tmp)),patch("e002d_exp.task.kernel_hash",return_value="1"*64),patch.dict(os.environ,{"VM_SOURCE_COMMIT":"c"*40}):
            root=Path(tmp)
            def record(name,data):
                raw=json.dumps(data).encode();(root/name).write_bytes(raw)
                return dict(path=name,sha256=hashlib.sha256(raw).hexdigest())
            review=dict(status="REVIEWED_AND_CHECKED",kernel_sha256="1"*64,reviewed_source_commit="a"*40,implementation_commit="b"*40)
            cal=dict(report_commit="d"*40,source_commit="b"*40,kernel_sha256="1"*64)
            cfg=dict(mode="production",calibration=cal,copilot_review=record("review.json",review),
                calibration_verification=record("cal.json",dict(status="VERIFIED_GITHUB",calibration=cal)))
            validate_provenance(cfg) # differing source commits with matching implementation are legitimate
            with patch.dict(os.environ,{"VM_SOURCE_COMMIT":"z"*40}):
                with self.assertRaisesRegex(ValueError,"commit SHA"):validate_provenance(cfg)
            bad=copy.deepcopy(cfg);bad["calibration"]["report_commit"]="e"*40
            with self.assertRaisesRegex(ValueError,"record mismatch"):validate_provenance(bad)
            (root/"review.json").write_text("{}")
            with self.assertRaisesRegex(ValueError,"hash mismatch"):validate_provenance(cfg)
            review["kernel_sha256"]="2"*64;cfg["copilot_review"]=record("review.json",review)
            with self.assertRaisesRegex(ValueError,"running kernel"):validate_provenance(cfg)

    def test_extension_failure_and_resource_abort(self):
        plan=[dict(id=str(i),label=str(i),model="QS",horizon=200.) for i in range(3)]
        class Fake:
            def __init__(self,case,*args,**kw):self.case=case;self.failure=None;self.ends=[]
            def advance(self,horizon):
                if horizon==400. and self.case["id"]=="1":raise ValueError("Invalid observables: injected")
                self.ends.append(horizon);return dict(pass_gate=False)
            def release_kernel(self):pass
            def rebuild_kernel(self,builder):pass
        with patch("e002d_exp.task.Trajectory",Fake):
            runs,timings,failures,extended,fatal=execute_cohort(plan,"production",None)
        self.assertTrue(extended);self.assertIsNone(fatal);self.assertEqual(len(failures),1)
        self.assertEqual(runs[0].ends,[200.,400.]);self.assertEqual(runs[1].ends,[200.]);self.assertEqual(runs[2].ends,[200.,400.])
        class Resource(Fake):
            def advance(self,horizon):raise OSError("injected resource failure")
        with patch("e002d_exp.task.Trajectory",Resource):
            runs,timings,failures,extended,fatal=execute_cohort(plan,"production",None)
        self.assertEqual(len(runs),1);self.assertIsNotNone(fatal);self.assertFalse(extended)
        class Programming(Fake):
            def advance(self,horizon):raise ValueError("unexpected schema")
        with patch("e002d_exp.task.Trajectory",Programming):
            runs,timings,failures,extended,fatal=execute_cohort(plan,"production",None)
        self.assertEqual(len(runs),1);self.assertIsNotNone(fatal)

    def test_partial_case_is_exported(self):
        original=Trajectory.advance;triggered=[]
        def fail_once(self,horizon):
            if not triggered:
                triggered.append(self.case["id"]);original(self,.4)
                raise ValueError("Invalid observables: injected after partial evolution")
            return original(self,horizon)
        with tempfile.TemporaryDirectory() as tmp,patch.object(Trajectory,"advance",fail_once):
            cfg=dict(mode="smoke",run_id="E002d_PARTIAL_TEST",forecast=dict(expected_seconds=90.,lower_seconds=0.,upper_seconds=300.))
            with self.assertRaisesRegex(RuntimeError,"injected"):run(cfg,tmp)
            root=Path(tmp);metrics=json.loads((root/"report/metrics.json").read_text());checks=json.loads((root/"report/checks.json").read_text())
            self.assertEqual(len(metrics["cases"]),10);self.assertEqual(metrics["missing_cases"],[])
            partial=next(s for s in metrics["cases"] if s["case"]["id"]==triggered[0])
            self.assertEqual(partial["horizon"],.4);self.assertIsNotNone(partial["failed"])
            self.assertTrue((root/"full"/triggered[0]/"final.npz").is_file())
            self.assertTrue((root/"report/cases"/(triggered[0]+".npz")).is_file())
            self.assertEqual(checks["technical_status"],"FAILED")
            self.assertEqual(checks["runtime_gate"]["status"],"INTERNAL_REVIEW_REQUIRED")
            self.assertEqual(sum(s["horizon"]==2 for s in metrics["cases"]),9)

    def test_derived_fields_and_semantic_corruption(self):
        for horizon in (200.,400.):
            rs=synthetic_results(horizon);analysis=analyze(rs,"production");stats={}
            for r in rs:
                c=r["summary"]["case"]
                for end in ((200.,) if horizon==200 else (200.,400.)):
                    selected=r["series"][np.isin(r["series"][:,0],end-10+2*np.arange(6))]
                    mean=simpson(selected[:,1:],x=selected[:,0],axis=0)/10
                    key=(c["model"],c["target"],c["kind"],c["gamma"],c["phi_over_pi"],c["detuning"],c["dephasing"],c["dt"],end)
                    stats[key]=dict(id=c["id"],mean=dict(zip(r["names"],mean.tolist())),range=dict(zip(r["names"],np.ptp(selected[:,1:],axis=0).tolist())))
            metrics=dict(mode="production",cases=[r["summary"] for r in rs],analysis=analysis)
            self.assertGreater(verify_derived(metrics,stats),10000)
            paths=[("A",0,"coherences","QS","S2a","T_minus_C","phase_shift"),
                   ("A",0,"coherences","QS","S2a","T","absolute"),
                   ("A",0,"coherences","QS","S2a","T","conditional_re","uncertainty"),
                   ("A",0,"E","uncertainty"),("A",0,"status"),
                   ("A",0,"components",0,"models","QS","decomposition_residual"),
                   ("B",0,"D","lower"),("B",0,"minimum","status"),("C",0,"delta_D","upper")]
            for path in paths:
                changed=copy.deepcopy(metrics);obj=changed["analysis"]
                for key in path[:-1]:obj=obj[key]
                old=obj[path[-1]];obj[path[-1]]="CORRUPTED" if isinstance(old,str) else .123 if old is None else old+.123
                with self.assertRaisesRegex(ValueError,"Derived reconstruction"):verify_derived(changed,stats)

if __name__=="__main__":unittest.main()
