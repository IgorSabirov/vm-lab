"""Coordinator started exclusively by the native GitHub Copilot MCP invocation."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results"
OUT.mkdir(exist_ok=True)
started = time.monotonic()
timings, errors, cases, cmb = {}, {}, {}, {}


def write(name, obj):
    tmp = OUT/(name+".tmp")
    tmp.write_text(json.dumps(obj,indent=2,allow_nan=False)+"\n")
    tmp.replace(OUT/name)


def run(label, fn, *args, **kw):
    t0 = time.monotonic()
    try:
        return fn(*args, **kw)
    except Exception:
        errors[label] = traceback.format_exc()
        print(label, errors[label], file=sys.stderr, flush=True)
    finally:
        timings[label] = time.monotonic()-t0
        write("PROGRESS.json", dict(timings=timings,errors=errors))
        print(label, round(timings[label],2), flush=True)


def main():
    from science import Pair, CHANNELS, native_primat, cosmology, dd_summary, yields
    import numpy as np
    import importlib.metadata
    write("ENVIRONMENT.json", dict(upstream={n:subprocess.check_output(["git","-C",
        str(Path(os.environ["GITHUB_WORKSPACE"])/"vendor"/n),"rev-parse","HEAD"],text=True).strip()
        for n in ("class","primat","linx")}, packages={d.metadata["Name"]:d.version for d in importlib.metadata.distributions()},
        commit=os.environ["GITHUB_SHA"], run_id=os.environ["GITHUB_RUN_ID"]))
    native = run("PRIMAT_native", native_primat)
    if native:
        cmb["primat_native"] = run("CLASS_primat_native", cosmology, "primat_native",
                                  native["YPCMB"],native["Neff"],0.02242)
    pair = Pair()
    def legacy():
        t,a,rg,rn,rx,px,*_ = pair.background(0.,None,1.)
        sol = pair.model(*map(pair.jp.asarray,(rg,rn,rx,px)),a_vec=pair.jp.asarray(a),
                         t_vec=pair.jp.asarray(t),save_history=True)
        result=yields(np.asarray(sol.evaluate(sol.t1)),pair.cfg)
        result["S3_reference_D_H"]=2.435998685e-5
        result["reference_pass"]=abs(result["D_H"]/2.435998685e-5-1)<1.e-4
        write("LINX_NATIVE.json",result)
        return result
    linx = run("LINX_native",legacy)
    def add(name, **kw):
        value = run("pair_"+name,pair.case,name,**kw)
        if value:
            cases[name] = value
            if name in ("baseline","early","late","extra"):
                cmb[name] = run("CLASS_"+name,cosmology,name,value["linx"]["YHe_CMB"],
                                value["Neff"],value["omega_b"])
    add("baseline")
    write("FORECAST.json",dict(calibration_s={k:v for k,v in timings.items() if "native" in k or "baseline" in k},
          remaining_pairs=16, forecast_s_range=[3*timings["pair_baseline"],17*timings["pair_baseline"]],
          basis="baseline includes JIT compilation; shared JIT and background reuse make upper bound conservative"))
    add("baseline_tight",tight=True)
    for w in ("early","late"):
        add(w,window=w)
        add(w+"_half",window=w,amplitude=.5)
    for ch in CHANNELS:
        for h in (.25,-.25,.125,-.125):
            add(f"{ch}_{h:+g}",channel=ch,q=h)
    for h in (.125,-.125):
        add(f"tight_ddtp_{h:+g}",channel="ddtp",q=h,tight=True)
    # Choose the pre-existing radiation reservoir that supplies the frozen 4% late control.
    # At fixed a it is transferred to photons and residual free-streaming radiation.
    from scipy.optimize import brentq
    def reservoir(delta):
        _,_,rg,rn,rx,*_ = pair.background(float(delta),None,1.)
        return float(rx[-1]/(rg[-1]+3*rn[-1]))
    d = run("reserve_calibration",brentq,lambda x:reservoir(x)-.04,0.,5.)
    if d is not None:
        add("extra",delta=d)
        if "extra" in cases:
            v = cases["extra"]
            dfrac = reservoir(d)
            _,_,rg,rn,rx,*_ = pair.background(d,None,1.)
            rad = (7./8)*(4./11)**(4./3)
            nfinal = float((3*rn[-1]+rx[-1]-dfrac*rg[-1])/((1+dfrac)*rg[-1]*rad))
            eta_ratio = (1+dfrac)**(-.75)
            assert abs((3*rn[-1]/rg[-1]/rad)-nfinal)<1.e-10
            cmb["compensated"] = run("CLASS_compensated",cosmology,"compensated",v["linx"]["YHe_CMB"],
                                     nfinal,v["omega_b"]*eta_ratio)
            write("LATE_TRANSFER.json",dict(delta_init=d, heating=dfrac, eta_CMB_over_eta_BBN=eta_ratio,
                  N_pre=v["Neff"],N_post=nfinal, omega_b_BBN_convention=v["omega_b"],
                  omega_b_CLASS=v["omega_b"]*eta_ratio,
                  relative_energy_closure=float(((1+dfrac)*rg[-1]*(1+nfinal*rad)
                                                      -(rg[-1]+3*rn[-1]+rx[-1]))/(rg[-1]+3*rn[-1]+rx[-1]))))
    derivatives = run("DD_jacobian",dd_summary,cases)
    numerical = (native and native["reference_pass"] and linx and linx["reference_pass"]
                 and all(v["control_pass"] for v in cases.values()))
    write("SUMMARY.json", dict(cases=cases, CLASS=cmb, DD=derivatives, timings=timings,
                                 errors=errors, numerical_controls_pass=bool(numerical)))
    if errors or len(cases)!=17 or len(cmb)!=6 or not all(cmb.values()):
        return "INCOMPLETE"
    return "COMPLETE_CONTROLS_PASS" if numerical else "COMPLETE_CONTROL_DISCREPANCY"


status = "INCOMPLETE"
write("STARTED.json",dict(commit=os.environ.get("GITHUB_SHA")))
try:
    status=main()
except BaseException:
    errors["coordinator"]=traceback.format_exc()
    print(errors["coordinator"],file=sys.stderr,flush=True)
finally:
    write("EXECUTION_RECEIPT.json",dict(status=status,completed_pairs=len(cases),
          completed_CLASS=sum(bool(v) for v in cmb.values()),errors=errors,
          code_wall_seconds=time.monotonic()-started,timings=timings))
sys.exit(0 if status.startswith("COMPLETE_") else 1)
