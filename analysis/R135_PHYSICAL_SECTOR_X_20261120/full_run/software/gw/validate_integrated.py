"""Replay actual coupled P7 GW production and pinned PTA/LVK projection.

This is a diagnostic law with assigned coefficients, not an X prediction.
The two P7 source-on resolutions and the zero-source control have the same
source knots and frequency cells. No physical production scan is started.
"""
import argparse
import copy
import json
import platform
import resource
from pathlib import Path
import sys
import time

import numpy as np
import scipy

SOFTWARE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(SOFTWARE),str(SOFTWARE/"tests")]
from test_history import fixture
from test_gravitationalwaves import source_definition,response_policy,KEY
from r135 import history
from r135 import gravitationalwaves as gw
from r135.common import read_json,write_json,sha256


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--cache",type=Path,required=True)
    p.add_argument("--offline",action="store_true")
    args=p.parse_args()
    if args.out.exists():p.error("choose a new output directory")
    args.out.mkdir(parents=True)
    code=[SOFTWARE/name for name in (
        "gw/validate_integrated.py","r135/__init__.py","r135/common.py",
        "r135/gravitationalwaves.py","r135/history.py","r135/collisions.py",
        "r135/nucleation.py","r135/thermodynamics.py","r135/kinetic_history.py",
        "r135/kinetics.py","gw/response.py","donors/fetch.py","donors/extract.py",
        "tests/test_gravitationalwaves.py","tests/test_history.py")]
    sources_before={str(f.relative_to(SOFTWARE)):sha256(f) for f in code}
    data_before={name:sha256(SOFTWARE/name) for name in
                 ("donors/sources.json","p0_snapshot/model_register.json")}
    start=time.monotonic()
    paths=gw.detector_paths(args.cache,offline=args.offline)
    definitions=list(copy.deepcopy(fixture()))
    definitions[0].update(samples=513,rtol=1e-9,atol_relative=1e-12,
                          max_step_H0=.025,gw_source=source_definition())
    key=dict(KEY,thermal_path=definitions[0]["thermal_path"])
    outputs={};summaries={};solves=[]
    for name,rtol,max_step,enabled in (("source_on",1e-9,.025,True),
                                      ("source_on_refined",2e-10,.0125,True),
                                      ("zero_source",1e-9,.025,False)):
        cfg=copy.deepcopy(definitions)
        cfg[0]["rtol"]=rtol
        cfg[0]["max_step_H0"]=max_step
        if not enabled:
            cfg[0]["gw_source"]["power_MeV4_s_per_logq"]=np.zeros((4,4)).tolist()
            cfg[0]["gw_source"]["source"]="assigned diagnostic zero-source control"
        model=history.CoupledModel(*cfg)
        rows,meta=model.solve("11full")
        outputs[name]={**history._payload(rows),**key}
        summaries[name]={**meta,**history.summarize(rows,meta)}
        write_json(args.out/(name+"_P7_input.json"),cfg)
        write_json(args.out/(name+"_P7_history.json"),outputs[name])
        write_json(args.out/(name+"_P7_summary.json"),summaries[name])
        solves.append(dict(name=name,rtol=rtol,max_step_H0=max_step,nfev=meta["nfev"]))
    h=outputs["source_on_refined"]
    policy=response_policy(h)
    policy["bbn_epochs"]=[dict(time_s=float(t),source="selected retained diagnostic P7 epoch")
                          for t in (h["time_s"][0],.5,1.5,h["time_s"][-1])]
    response=gw.response_from_p7(h,key,policy,paths)
    audit=gw.audit_response(h,response,key,paths)
    zero=outputs["zero_source"]
    zero_policy=response_policy(zero)
    zero_policy["bbn_epochs"]=[dict(time_s=float(t),source="selected retained zero-source control epoch")
                               for t in (zero["time_s"][0],.5,1.5,zero["time_s"][-1])]
    zero_response=gw.response_from_p7(zero,key,zero_policy,paths)
    write_json(args.out/"gw_source.json",gw.source_artifact(definitions[0]["gw_source"],key))
    write_json(args.out/"gw_response.json",response)
    write_json(args.out/"gw_audit.json",audit)
    write_json(args.out/"zero_source_response.json",zero_response)
    p0=read_json(SOFTWARE/"p0_snapshot/model_register.json")
    coverage=gw.coverage_status(p0["points"],{})
    write_json(args.out/"gw_channel_status.json",coverage)
    refined=np.asarray(h["gw"]["rho_MeV4_per_logq"])
    coarse=np.asarray(outputs["source_on"]["gw"]["rho_MeV4_per_logq"])
    positive=refined>0
    refinement=float(np.max(abs(refined[positive]-coarse[positive])/refined[positive]))
    phase_delta=float(np.max(abs(np.asarray(h["phase_fraction"])-np.asarray(zero["phase_fraction"]))))
    tx_delta=float(np.max(abs(np.asarray(h["T_X_MeV"])-np.asarray(zero["T_X_MeV"])) ))
    if (solves[1]["nfev"]<=solves[0]["nfev"] or refinement>1e-4 or phase_delta==0 or tx_delta==0
            or response["energy_audit"]["status"]!="RECONSTRUCTED"
            or zero_response["integrated_Omega_GW_today"]!=0
            or zero_response["detectors"]["LVK_O4a_HL"]["conditional_delta_logL_vs_zero"]!=0):
        raise RuntimeError("coupled GW diagnostic control failed")
    sources_after={str(f.relative_to(SOFTWARE)):sha256(f) for f in code}
    data_after={name:sha256(SOFTWARE/name) for name in data_before}
    if sources_before!=sources_after or data_before!=data_after:
        raise RuntimeError("executed source or frozen data changed during the control")
    report=dict(schema="R135-coupled-GW-control-v1",status="PASS",physical_R135_run=False,
                key=key,
                source_model="assigned diagnostic spectral power, weak-field isotropic subhorizon regime",
                actual_P7_solves=solves,python=platform.python_version(),elapsed_seconds=time.monotonic()-start,
                environment=dict(platform=platform.platform(),numpy=np.__version__,scipy=scipy.__version__),
                peak_rss_KiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                maximum_spectral_density_refinement_relative_change=refinement,
                maximum_abs_phase_fraction_change_due_to_GW=phase_delta,
                maximum_abs_T_X_MeV_change_due_to_GW=tx_delta,
                P7_balance=summaries["source_on_refined"],
                GW_cell_energy_audit=response["energy_audit"],
                detector_bin_counts=dict(PTA=len(response["detectors"]["NG15_HD"]["f_Hz"]),
                    LVK=response["detectors"]["LVK_O4a_HL"]["unmasked_bins"]),
                integrated_Omega_GW_today=response["integrated_Omega_GW_today"],
                coverage=dict(points=coverage["points"],open_inputs=sum(x["status"]=="OPEN_INPUT" for x in coverage["rows"])),
                source_sha256=sources_before,source_sha256_after=sources_after,
                frozen_data_sha256=data_before,source_and_data_unchanged_during_run=True,
                remaining=response["remaining"]+["GW scalar CMB applicability not supplied",
                    "this control is not a P0-calibrated point and closes no physical GW path"])
    write_json(args.out/"VALIDATION.json",report)
    print(json.dumps({k:report[k] for k in ("status","elapsed_seconds","maximum_spectral_density_refinement_relative_change",
                 "maximum_abs_phase_fraction_change_due_to_GW","maximum_abs_T_X_MeV_change_due_to_GW",
                 "detector_bin_counts","coverage")},indent=2))


if __name__=="__main__":main()
