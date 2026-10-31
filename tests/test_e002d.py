import copy,json,tempfile,time,unittest
from pathlib import Path
import numpy as np
from e002_exp.model import build_liouvillian,make_direct_rhs,maxabs,save_json
from e002c_exp.model import build as old_build
from e002c_exp.diagnostics import node_blocks,certificate
from e002d_exp.model import build,jump_diagonals,damping,consequence_map
from e002d_exp.plan import case,cases,counts,comparison_graph,physics_key,OPERATIONS,TARGETS
from e002d_exp.numerics import estimate,linear,ratio,signed,contrast,sampled_minimum
from e002d_exp.analysis import analyze
from e002d_exp.task import run,save_metrics
from e002d_exp.verify import verify
from e002d_exp.export import compact,write_manifest,export_case

def synthetic_results(horizon=200.):
    names=build(case("QS"))["names"]
    times=np.arange(190.,202.,2.) if horizon==200 else np.r_[np.arange(190.,202.,2.),np.arange(390.,402.,2.)]
    results=[]
    for c in cases():
        h=1. if c["model"]=="QS" else .8
        if c["target"]=="S2a" and c["kind"]=="T":h-=.2 if c["model"]=="QS" else .05
        values=dict.fromkeys(names,0.)
        for m in range(8):
            values[f"p_m{m}"]=1/8
            for n in range(4):
                values[f"p_m{m}_N{n}"]=1/32
                values[f"h_m{m}_N{n}"]=h/32
        if c["phi_over_pi"]==.5:
            e=c["detuning"];j=1+e+e*e
            if c["kind"]=="T" and c["target"]=="M2":j-=.2*e*e
            values["h_m6_N2"]=j/32
            values["h_m0_N0"]+=h-sum(values[f"h_m{m}_N{n}"] for m in range(8) for n in range(4))
        values["h"]=h
        for target in TARGETS:
            values["C_"+target+"_re"]=.01;values["C_"+target+"_im"]=-.02
            values["aunit_"+target]=.05
        for name in ("pL01","pL12","pL02"):values[name]=.5
        for name in ("ell01","ell12","ell02"):values[name]=.1
        series=np.column_stack([times,np.tile([values[n] for n in names],(len(times),1))])
        summary=dict(case=c,horizon=horizon,stationarity={"pass_gate":True},refinement_status="not_refined",
                     failed=None,reference=values,h_extrema=[h,2.,h,200.,1000])
        results.append(dict(summary=summary,names=names,dnames=["dummy"],series=series,
                            diagnostics=np.column_stack([times,np.zeros(len(times))])))
    return results

class E002dTests(unittest.TestCase):
    def test_grid_and_comparison_graph(self):
        self.assertEqual(counts("production"),dict(trajectories=184,steps=5920000,rhs_calls=23680000))
        self.assertEqual(counts("production",400.)["steps"],11840000)
        self.assertEqual(counts("calibration"),dict(trajectories=48,steps=72000,rhs_calls=288000))
        self.assertEqual(counts("smoke")["steps"],3000)
        cs=cases();self.assertEqual(sum(c["dt"]==.005 for c in cs),112)
        self.assertEqual(len({physics_key(c) for c in cs}),184)
        ids={c["id"] for c in cs};graph=comparison_graph()
        self.assertEqual(set(graph["extension_cohorts"][0]),ids)
        self.assertTrue(all(set(x["members"])<=ids for x in graph["edges"]))
        c=case("QS")
        varied=[case("QS",phi=.5),case("QS",epsilon=.125),case("QS",noise=.25)]
        self.assertEqual(len({c["id"],*[x["id"] for x in varied]}),4)
        # Six phase-control baselines are shared between B and C (two models, two dt, three eps =>12).
        self.assertEqual(sum(set(c["blocks"])=={"B","C"} for c in cs),12)

    def test_full_map_and_overlapping_composition(self):
        for x in consequence_map().values():self.assertLess(x["difference_error"],1e-12)
        t=damping(jump_diagonals("M2","T",.1));c=damping(jump_diagonals("M2","C",.1))
        # edge ternary 0,L,L belongs to m6.
        e=8
        self.assertAlmostEqual(t[5*27+e,6*27+e],.25)
        self.assertAlmostEqual(c[5*27+e,6*27+e],.05)
        self.assertAlmostEqual(t[5*27+e,3*27+e],.1)
        wrong=damping([("wrong",sum(d for _,d in jump_diagonals("M2","T",.1)))])
        self.assertGreater(np.max(abs(wrong-t)),.05)
        self.assertTrue(np.array_equal(t.diagonal(),np.zeros(216)))
        for op in OPERATIONS:
            ds=jump_diagonals(op,"T",.1);cs=jump_diagonals(op,"C",.1)
            for (_,x),(_,y) in zip(ds,cs):np.testing.assert_allclose(x*x,y*y,atol=0,rtol=0)

    def test_physics_and_independent_rhs(self):
        rng=np.random.default_rng(17);a=rng.normal(size=(216,4))+1j*rng.normal(size=(216,4))
        rho=a@a.conj().T;rho/=np.trace(rho);v=rho.reshape(-1,order="F");blocks=node_blocks(rho)
        for model in ("QS","RR_QS"):
            old=old_build(case(model,phi=.5,epsilon=.125,noise=.25))
            new=build(case(model,phi=.5,epsilon=.125,noise=.25))
            self.assertEqual(maxabs(old["L"]-new["L"]),0.)
            for op in OPERATIONS:
                for branch in ("T","C"):
                    cc=case(model,op,branch,.1,phi=.5,epsilon=.125,noise=.25);m=build(cc)
                    reference=build_liouvillian(m["H"],m["jumps"])
                    self.assertLess(maxabs(m["L"]-reference),1e-12)
                    self.assertEqual(maxabs(m["H"]-old["H"]),0.)
                    self.assertLess(np.max(abs(m["L"]@v-make_direct_rhs(m["H"],m["jumps"])(v))),1e-12)
                    values=m["rows"]@v
                    for key,(mask,a,b) in TARGETS.items():
                        z=values[m["names"].index("C_"+key+"_re")]+1j*values[m["names"].index("C_"+key+"_im")]
                        self.assertLess(abs(z-blocks[mask+1,a,b]),1e-12)
                    self.assertAlmostEqual(sum(values[m["names"].index(f"h_m{mask}_N{n}")].real for mask in range(8) for n in range(4)),values[m["names"].index("h")].real,places=12)

    def test_signed_effect_and_monotone_counterexample(self):
        rs=synthetic_results();a=analyze(rs,"production")
        r=next(x for x in a["A"] if x["target"]=="S2a")
        self.assertAlmostEqual(r["E"]["value"],-.15)
        self.assertAlmostEqual(r["S"]["value"],-.75)
        self.assertEqual(r["status"],"RESOLVED_NEGATIVE")
        self.assertLess(r["component_sum_error"],1e-12)
        b=next(x for x in a["B"] if x["model"]=="QS" and x["phi_over_pi"]==.5 and x["delta"]==.125)
        self.assertLess(b["D"]["value"],0)
        self.assertEqual(b["minimum"]["status"],"SAMPLED_MINIMUM_NOT_RESOLVED")
        self.assertTrue(any(x.get("target")=="M2" and x["status"]=="RESOLVED_POSITIVE" for x in a["C"]))
        # dt failure must block a sign claim.
        r=next(r for r in rs if r["summary"]["case"]["model"]=="QS" and r["summary"]["case"]["target"]=="S2a" and r["summary"]["case"]["kind"]=="T" and r["summary"]["case"]["dt"]==.01)
        r["series"][:,1+r["names"].index("h")]+=.01
        a=analyze(rs,"production")
        self.assertFalse(next(x for x in a["A"] if x["target"]=="S2a")["eligible"])

    def test_envelopes_denominators_and_minimum(self):
        self.assertIsNone(ratio(estimate(1.,.01),estimate(1e-7,1e-9),True)["value"])
        self.assertIsNone(ratio(estimate(1.,.01),estimate(1.,.2),True)["value"])
        self.assertEqual(signed(estimate(.01,.02)),"UNRESOLVED_AT_TOLERANCE")
        d=contrast(estimate(2.,.01),estimate(1.,.01),estimate(3.,.01))
        self.assertEqual(signed(d),"RESOLVED_NEGATIVE")
        self.assertEqual(sampled_minimum(estimate(2.,.01),estimate(1.,.01),estimate(3.,.01))["status"],"CENTER_BELOW_BOTH_SAMPLED_NEIGHBORS")
        self.assertEqual(signed(estimate(1.,None)),"SCREENING_ONLY")

    def test_full_report_size(self):
        results=synthetic_results(400.);analysis=analyze(results,"production")
        metrics=dict(identity=dict(run_id="TEST_REPORT",source_commit="0"*40),mode="production",
            cases=[r["summary"] for r in results],analysis=analysis,work=dict(planned=counts("production",400.),actual=counts("production",400.)),
            environment=dict(kernel_sha256="0"*64))
        checks=dict(runtime_gate=dict(expected_seconds=100.,lower_seconds=60.,upper_seconds=140.,actual_seconds=100.,status="PASS"),failures=[])
        self.assertLessEqual(len(compact(metrics,checks).encode()),24*1024)
        geometry=[x["info"] for x in old_build(case("QS"))["dark"]]
        for s in metrics["cases"]:
            s["transition_reference"]=s["reference"]
            s["reference_horizons"]=[200.,400.]
            s["dark_geometry"]=geometry
            s["node_edge"]=[dict(time=float(i),negativity=.123456789012345,min_eigen=-.123456789012345,
                status="NODE_EDGE_NPT_DETECTED",independent_reconstruction_from_node_export=False) for i in range(14)]
        def wide_numbers(x):
            if isinstance(x,float):return -1.2345678901234567e-123
            if isinstance(x,dict):return {k:wide_numbers(v) for k,v in x.items()}
            if isinstance(x,list):return [wide_numbers(v) for v in x]
            return x
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);save_metrics(root,wide_numbers(metrics))
            self.assertLess((root/"metrics.json").stat().st_size,7*1024**2)
            self.assertLess((root/"analysis.json.gz").stat().st_size,8*1024**2)

    def test_independent_six_point_window_mean(self):
        # Manufactured positive matrix curve: the exact mean is (2*rhoA+rhoB)/3.
        # This verifies the reference-window branch without a long evolution.
        c=next(c for c in cases() if c["model"]=="QS" and c["target"]=="M2" and c["kind"]=="T" and c["dt"]==.005 and c["detuning"]==.125)
        model=build(c);rng=np.random.default_rng(2401);states=[]
        for _ in range(2):
            a=rng.normal(size=(216,3))+1j*rng.normal(size=(216,3));rho=a@a.conj().T
            states.append(rho/np.trace(rho))
        times=np.arange(190.,202.,2.);certs=[];rows=[]
        for t in times:
            x=(t-190)/10;rho=(1-x*x)*states[0]+x*x*states[1]
            certs.append(certificate(node_blocks(rho)))
            rows.append(np.r_[t,np.asarray(model["rows"]@rho.reshape(-1,order="F")).real])
        mean=np.asarray(model["rows"]@((2*states[0]+states[1])/3).reshape(-1,order="F")).real
        reference=dict(zip(model["names"],mean.tolist()))
        summary=dict(case=c,horizon=200.,reference=reference,transition_reference=None,reference_horizons=[200.])
        result=dict(summary=summary,series=np.array(rows),diagnostics=np.column_stack([times,np.zeros(6)]),
            names=model["names"],dnames=["dummy"],certs={k:np.array([s[k] for s in certs]) for k in certs[0]})
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);report=root/"report";full=root/"full";report.mkdir();full.mkdir()
            export_case(report,result,"production")
            save_json(report/"schema.json",dict(series=["time"]+model["names"]))
            save_json(report/"case_registry.json",dict(cases=[c]))
            _,rates=consequence_map(True);np.savez_compressed(report/"intervention_rates.npz",**rates)
            metrics=dict(cases=[summary],work=dict(actual=dict(trajectories=1)),analysis=dict(A=[],B=[],C=[]))
            save_metrics(report,metrics);write_manifest(report,full)
            self.assertEqual(verify(report)["status"],"PASS")
            metrics["cases"][0]["reference"]["h"]+=.001
            save_metrics(report,metrics);write_manifest(report,full)
            with self.assertRaisesRegex(ValueError,"mean"):verify(report)

    def test_end_to_end_and_independent_corruption_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg=dict(mode="smoke",run_id="E002d_LOCAL_v003_SMOKE",local_source_commit="LOCAL_TEST",
                forecast=dict(expected_seconds=60.,lower_seconds=0.,upper_seconds=300.))
            metrics,checks=run(cfg,tmp)
            self.assertEqual(checks["technical_status"],"PASS")
            self.assertEqual(metrics["work"]["actual"]["steps"],3000)
            root=Path(tmp)/"report";self.assertEqual(verify(root)["status"],"PASS")
            path=next((root/"cases").glob("*.npz"));data=path.read_bytes();path.write_bytes(data+b"X")
            with self.assertRaisesRegex(ValueError,"hash mismatch"):verify(root)
            path.write_bytes(data)
            with np.load(path,allow_pickle=False) as z:arrays={k:z[k] for k in z.files}
            schema=json.loads((root/"schema.json").read_text())
            arrays["window_scalar"][-1,schema["series"].index("h")]+=.001
            np.savez_compressed(path,**arrays)
            write_manifest(root,Path(tmp)/"full")
            with self.assertRaisesRegex(ValueError,"Reconstruction failed"):verify(root)

if __name__=="__main__":unittest.main()
