"""E002d v003 orchestration. No networking or Copilot inside scientific jobs."""
import gc,gzip,hashlib,json,os,platform,re,shutil,sys,time,traceback
from pathlib import Path
import numpy as np
import scipy
from e002_exp.model import save_json
from e002c_exp.engine import stationarity
from e002c_exp.windows import integral_mean
from .engine import Trajectory
from .model import build,consequence_map
from .plan import cases,counts,CONTRACT,VERSION,CALIBRATION_FORECAST,comparison_graph
from .analysis import analyze
from .export import export_case,write_manifest,compact
ROOT=Path(__file__).resolve().parents[1]

def save_metrics(report,metrics):
    # The two-horizon scientific analysis exceeds the per-file cap as pretty JSON.
    # Keep all numbers, compress the detail and leave a verified pointer in metrics.json.
    path=report/"analysis.json.gz"
    with gzip.open(path,"wt",encoding="utf-8") as stream:
        json.dump(metrics["analysis"],stream,ensure_ascii=False,allow_nan=False,separators=(",",":"))
    public=dict(metrics,analysis=dict(file=path.name,encoding="gzip+json",
                                    sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    # Whitespace is not scientific data; retain every field/float without pretty-print inflation.
    path=report/"metrics.json";temporary=path.with_suffix(".json.tmp")
    with temporary.open("w",encoding="utf-8") as stream:
        json.dump(public,stream,ensure_ascii=False,allow_nan=False,separators=(",",":"));stream.write("\n")
        stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)

def kernel_files():
    return [ROOT/"e002_exp/model.py",*[ROOT/"e002c_exp"/f for f in
        ("model.py","engine.py","diagnostics.py","windows.py","export.py")],
        *sorted((ROOT/"e002d_exp").glob("*.py")),ROOT/"run.py"]

def kernel_hash():
    h=hashlib.sha256()
    for p in kernel_files():h.update(p.relative_to(ROOT).as_posix().encode()+b"\0"+p.read_bytes())
    return h.hexdigest()

def execute_cohort(plan,mode,full):
    runs=[];timings=[];failures=[];extended=False;fatal=None
    def failed(exc,tr,case,stage):
        nonlocal fatal
        record=dict(id=case["id"],stage=stage,type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc())
        failures.append(record)
        if tr is not None:tr.failure=stage+": "+str(exc)
        # A bad numerical case need not prevent independent cases from completing.
        # Resource/infrastructure failures abort further work; partial records remain.
        numerical=isinstance(exc,np.linalg.LinAlgError) or (isinstance(exc,ValueError) and
            str(exc).startswith(("Unphysical state:","Invalid observables")))
        if not numerical:fatal=record
    for case in plan:
        print("START",case["label"],case["id"],flush=True);t=time.monotonic();tr=None
        try:
            tr=Trajectory(case,full,disk_floor=0 if mode=="smoke" else 1.5*1024**3,builder=build)
        except Exception as exc:
            failed(exc,tr,case,"setup")
            if fatal:break
            continue
        timing=dict(id=case["id"],model=case["model"],setup_seconds=time.monotonic()-t,
                    rebuild_seconds=0.,advance_seconds=0.)
        tr.initial_stationarity=dict(pass_gate=False,reason="advance_failed")
        runs.append(tr);timings.append(timing);t=time.monotonic()
        try:tr.initial_stationarity=tr.advance(case["horizon"])
        except Exception as exc:failed(exc,tr,case,"advance")
        finally:timing["advance_seconds"]+=time.monotonic()-t;tr.release_kernel()
        print("DONE",case["label"],"failed",tr.failure,"stationary",tr.initial_stationarity["pass_gate"],flush=True)
        if fatal:break
    if mode=="production" and not fatal and any(tr.failure is None and not tr.initial_stationarity["pass_gate"] for tr in runs):
        extended=True
        for tr,timing in zip(runs,timings):
            if tr.failure is not None:continue
            print("EXTEND",tr.case["label"],flush=True);t=time.monotonic()
            try:
                tr.rebuild_kernel(build);timing["rebuild_seconds"]+=time.monotonic()-t;t=time.monotonic()
                try:tr.advance(400.)
                finally:timing["advance_seconds"]+=time.monotonic()-t
            except Exception as exc:failed(exc,tr,tr.case,"extension")
            finally:tr.release_kernel()
            if fatal:break
    return runs,timings,failures,extended,fatal

def pinned_record(spec):
    path=Path(spec["path"])
    if path.is_absolute() or ".." in path.parts:raise ValueError("Unsafe verification record path")
    data=(ROOT/path).read_bytes()
    if hashlib.sha256(data).hexdigest()!=spec["sha256"]:raise ValueError("Verification record hash mismatch")
    return json.loads(data)

def validate_provenance(config):
    def commit(value):
        if not isinstance(value,str) or not re.fullmatch("[0-9a-f]{40}",value):raise ValueError("Invalid commit SHA")
    commit(os.environ.get("VM_SOURCE_COMMIT"))
    review=pinned_record(config["copilot_review"])
    if review["status"]!="REVIEWED_AND_CHECKED" or review["kernel_sha256"]!=kernel_hash():
        raise ValueError("Review does not match running kernel")
    for key in ("reviewed_source_commit","implementation_commit"):commit(review[key])
    if config["mode"]=="production":
        cal=config["calibration"];record=pinned_record(config["calibration_verification"])
        for key in ("report_commit","source_commit"):commit(cal[key])
        if record.get("status")!="VERIFIED_GITHUB" or record.get("calibration")!=cal:
            raise ValueError("Calibration verification record mismatch")
    return review

def preflight(config):
    mode=config["mode"];cs=cases(mode)
    if len({c["id"] for c in cs})!=len(cs):raise ValueError("Duplicate case IDs")
    expected={"production":(184,5920000),"calibration":(48,72000),"smoke":(10,3000)}
    n,s=expected[mode]
    if counts(mode)!=dict(trajectories=n,steps=s,rhs_calls=4*s):raise ValueError("Invalid work volume")
    if mode!="smoke":validate_provenance(config)
    if mode=="production":
        cal=config["calibration"]
        if cal["kernel_sha256"]!=kernel_hash():raise ValueError("Kernel changed since calibration")
        if cal["numpy"]!=np.__version__ or cal["scipy"]!=scipy.__version__:raise ValueError("Library version changed")
        if cal.get("review_status")!="VERIFIED_GITHUB":raise ValueError("Unverified calibration")
        if config.get("copilot_review_status")!="REVIEWED_AND_CHECKED":raise ValueError("Copilot findings not closed")
        if set(config["forecast"]["branches"])!={"T200","T400"}:raise ValueError("Missing extension budget")
    elif mode=="calibration":
        if config["forecast"]!=CALIBRATION_FORECAST:raise ValueError("Unregistered calibration forecast")
    if os.environ.get("VM_SOURCE_DIR") and Path(os.environ["VM_SOURCE_DIR"]).name!=config["run_id"]:
        raise ValueError("Run identity differs from source directory")
    minimum=(6 if mode=="production" else 3)*1024**3
    if mode!="smoke" and shutil.disk_usage(".").free<minimum:raise ValueError("Insufficient disk reserve")
    return cs

def run(config,workdir=None):
    started=time.monotonic();root=Path.cwd() if workdir is None else Path(workdir)
    report=root/"report";full=root/"full";report.mkdir(parents=True,exist_ok=False);full.mkdir(parents=True,exist_ok=False)
    identity=dict(run_id=config["run_id"],source_commit=os.environ.get("VM_SOURCE_COMMIT",config.get("local_source_commit","LOCAL_TEST")))
    mode=config["mode"];runs=[];results=[];timings=[];fatal=None;case_failures=[];extended=False;phase={}
    plan=cases(mode)
    try:
        plan=preflight(config);maps,arrays=consequence_map(True)
        save_json(report/"intervention_map.json",maps);np.savez_compressed(report/"intervention_rates.npz",**arrays)
        save_json(report/"operation_contract.json",CONTRACT)
        save_json(report/"case_registry.json",dict(cases=plan,graph=comparison_graph()))
        runs,timings,case_failures,extended,fatal=execute_cohort(plan,mode,full)
    except Exception as exc:
        fatal=dict(type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc())
        save_json(full/"failure.json",fatal)
    for i,(tr,timing) in enumerate(zip(runs,timings)):
        t=time.monotonic();r=tr.finish();timing["finish_seconds"]=time.monotonic()-t
        timing.update(steps=tr.step,integrator_seconds=tr.integrator_seconds,diagnostic_seconds=tr.diagnostic_seconds)
        r["summary"]["initial_stationarity"]=tr.initial_stationarity
        if r["summary"]["horizon"]==200:r["summary"]["transition_reference"]=None
        results.append(r);runs[i]=None
    del runs
    gc.collect();t=time.monotonic();analysis=analyze(results,"failed" if fatal or case_failures else mode);phase["analysis_seconds"]=time.monotonic()-t
    if fatal or case_failures:analysis["scope"]="incomplete/failed cohort; scientific comparisons withheld"
    all_extrema={};t=time.monotonic()
    for r in results:
        s=r["summary"];cid=s["case"]["id"];all_extrema[cid]=export_case(report,r,mode)
        s["h_extrema"]=all_extrema[cid]["h_t_positive"]
        s["reference_horizons"]=[]
        for horizon in sorted(set([200.,s["horizon"]])):
            ref=integral_mean(r["series"],r["names"],horizon)
            if ref is not None:s["reference_horizons"].append(float(horizon))
    phase["export_seconds"]=time.monotonic()-t
    with gzip.open(report/"extrema.json.gz","wt",encoding="utf-8") as f:json.dump(all_extrema,f,allow_nan=False,separators=(",",":"))
    planned=counts(mode,400. if extended else None);steps=sum(r["summary"]["steps"] for r in results)
    volume=len(results)==planned["trajectories"] and steps==planned["steps"] and all(
        r["summary"]["rhs_calls"]==4*r["summary"]["steps"] and
        r["summary"]["scalar_records"]==round(r["summary"]["horizon"]/.2)+1 and
        r["summary"]["diagnostic_records"]==int(r["summary"]["horizon"]//2)+1 for r in results)
    failures=([fatal["message"]] if fatal else [])+[x["id"]+":"+x["stage"]+":"+x["message"] for x in case_failures]+([] if volume else ["work_volume_mismatch"])
    failures += [cid+":refinement_failed" for cid,pair in analysis["pairs"].items() if not pair["pass_gate"]]
    baseline=[]
    if mode=="production":
        for r in results:
            c=r["summary"]["case"]
            if not(c["target"]=="base" and c["dt"]==.005 and c["phi_over_pi"]==0 and c["detuning"]==0 and c["dephasing"]==.05):continue
            ref=integral_mean(r["series"],r["names"],200.)
            expected={"QS":.1098400932168605,"RR_QS":.0850336762}[c["model"]]
            err=None if ref is None else abs(ref["h"]-expected);passed=err is not None and err<=1e-6
            baseline.append(dict(model=c["model"],expected_h=expected,actual_h=None if ref is None else ref["h"],
                absolute_error=err,tolerance=1e-6,pass_gate=passed,source="E002c_WINDOW_EXPORT_v001_r001 [190,200]"))
            if not passed:failures.append(c["id"]+":baseline_reproduction_failed")
    branch="T400" if extended else "T200"
    f=config["forecast"]["branches"][branch] if mode=="production" else config["forecast"]
    runtime=dict(expected_seconds=f["expected_seconds"],lower_seconds=f["lower_seconds"],upper_seconds=f["upper_seconds"],
        actual_seconds=time.monotonic()-started,status="PENDING_FINAL_ASSEMBLY",branch=branch if mode=="production" else mode,
        measured_interval="entry to before final metadata rewrite; complete process checked via run.json",source=config["forecast"].get("source"))
    metrics=dict(identity=identity,version=VERSION,mode=mode,cases=[r["summary"] for r in results],analysis=analysis,
        work=dict(planned=planned,actual=dict(trajectories=len(results),steps=steps,rhs_calls=4*steps)),
        timing=timings,phase_timing=phase,fatal=fatal,case_failures=case_failures,
        missing_cases=[c["id"] for c in plan if c["id"] not in {r["summary"]["case"]["id"] for r in results}],
        environment=dict(kernel_sha256=kernel_hash(),
            numpy=np.__version__,scipy=scipy.__version__,python=sys.version,platform=platform.platform(),
            threads={k:os.environ.get(k) for k in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS")}))
    checks=dict(runtime_gate=runtime,work_volume_pass=bool(volume),baseline_reproduction=baseline,failures=failures,
        technical_status="FAILED" if failures else "PASS",scientific_acceptance="USER_REVIEW_REQUIRED")
    if results:
        save_json(report/"schema.json",dict(series=["time"]+results[0]["names"],diagnostics=["time"]+results[0]["dnames"],
            states=["unconditional"]+[f"mask_{m}" for m in range(8)],node_basis="000,001,010,011,100,101,110,111",
            mask_bits=["01","12","02"],window="six even-time points [T-10,T], plus [190,200] when extended",
            coherence="C_key=rho_node_mask[a,b], unnormalised; full_target_norm includes all edge microstate pairs",
            mean="Simpson on six points, ratios of means",Fano_status="NOT_AUTOMATIC"))
    save_json(report/"config.json",config);save_metrics(report,metrics);save_json(report/"checks.json",checks)
    (report/"README.md").write_text("E002d v003: RESULT.md, metrics.json, checks.json, schema.json; cases/*.npz.xz: XZ-decompress before np.load. Manifest verifies compressed and uncompressed bytes.\n")
    (report/"RESULT.md").write_text(compact(metrics,checks));write_manifest(report,full)
    if not fatal and not case_failures and volume:
        from .verify import verify
        t=time.monotonic();verification=verify(report);phase["verification_seconds"]=time.monotonic()-t
        save_json(report/"verification.json",verification)
    runtime["actual_seconds"]=time.monotonic()-started
    runtime["actual_over_expected"]=runtime["actual_seconds"]/runtime["expected_seconds"]
    runtime["status"]="INTERNAL_PASS_AWAITING_PROCESS" if runtime["lower_seconds"]<=runtime["actual_seconds"]<=runtime["upper_seconds"] and volume and not failures else "INTERNAL_REVIEW_REQUIRED"
    save_metrics(report,metrics);save_json(report/"checks.json",checks)
    (report/"RESULT.md").write_text(compact(metrics,checks));budget=write_manifest(report,full)
    print(json.dumps(dict(runtime=runtime,work=metrics["work"],report_budget=budget,failures=failures),ensure_ascii=False),flush=True)
    if failures:raise RuntimeError("; ".join(failures))
    return metrics,checks
