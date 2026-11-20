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
    from resume import recover, solve, read_class
    recover()
    cmb["primat_native"] = read_class("primat_native")
    native,linx=[json.loads((OUT/(k+"_NATIVE.json")).read_text()) for k in ("PRIMAT","LINX")]
    pair = Pair()
    def add(name, **kw):
        saved=OUT/"cases"/name/"observables.json"
        value = json.loads(saved.read_text()) if saved.exists() else run("pair_"+name,solve,pair,name)
        if value:
            cases[name] = value
            if name in ("baseline","early","late","extra"):
                cmb[name] = read_class(name) if (OUT/"class"/name).exists() else run("CLASS_"+name,cosmology,name,value["linx"]["YHe_CMB"],
                                value["Neff"],value["omega_b"])
    add("baseline")
    import shutil
    from resume import PREVIOUS
    shutil.copy2(PREVIOUS/"FORECAST.json", OUT/"FORECAST.json")
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
    with np.load(OUT/"cases"/"extra"/"plasma.npz") as z:
        rg,rn,rx=[z[k].copy() for k in ("rho_gamma_MeV4","rho_one_nu_MeV4","rho_extra_MeV4")]
    rad = (7./8)*(4./11)**(4./3)
    d=float(rx[0]/(rad*rg[0]))
    dfrac=float(rx[-1]/(rg[-1]+3*rn[-1]))
    # Use the measured energy available at the background endpoint. The LINX
    # termination event samples a slightly different final temperature across
    # backgrounds. Retain the failed nominal-target diagnostic without adding
    # energy, changing the input history, or discarding the CLASS calculation.
    assert 0 < dfrac < 1
    nominal_residual = dfrac - .04
    add("extra",delta=d)
    if "extra" in cases:
            v = cases["extra"]
            nfinal = float((3*rn[-1]+rx[-1]-dfrac*rg[-1])/((1+dfrac)*rg[-1]*rad))
            eta_ratio = (1+dfrac)**(-.75)
            assert abs((3*rn[-1]/rg[-1]/rad)-nfinal)<1.e-10
            cmb["compensated"] = run("CLASS_compensated",cosmology,"compensated",v["linx"]["YHe_CMB"],
                                     nfinal,v["omega_b"]*eta_ratio)
            write("LATE_TRANSFER.json",dict(delta_init=d, heating=dfrac, target_heating=.04, target_residual=nominal_residual,
                  target_within_1e_minus10=abs(nominal_residual)<1.e-10, eta_CMB_over_eta_BBN=eta_ratio,
                  N_pre=v["Neff"],N_post=nfinal, omega_b_BBN_convention=v["omega_b"],
                  omega_b_CLASS=v["omega_b"]*eta_ratio,
                  relative_energy_closure=float(((1+dfrac)*rg[-1]*(1+nfinal*rad)
                                                      -(rg[-1]+3*rn[-1]+rx[-1]))/(rg[-1]+3*rn[-1]+rx[-1]))))
    derivatives = run("DD_jacobian",dd_summary,cases)
    numerical = (native and native["reference_pass"] and linx and linx["reference_pass"]
                 and all(v["control_pass"] for v in cases.values()))
    write("SUMMARY.json", dict(cases=cases, CLASS=cmb, DD=derivatives, timings=timings,
                                 errors=errors, numerical_controls_pass=bool(numerical),
                                 reservoir_target_within_1e_minus10=abs(nominal_residual)<1.e-10))
    if errors or len(cases)!=17 or len(cmb)!=6 or not all(cmb.values()):
        return "INCOMPLETE"
    return "COMPLETE_CONTROLS_PASS" if numerical and abs(nominal_residual)<1.e-10 else "COMPLETE_CONTROL_DISCREPANCY"


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
