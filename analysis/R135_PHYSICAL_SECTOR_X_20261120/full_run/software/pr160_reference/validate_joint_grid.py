"""Run two post-BBN radiation controls through the paired P7/P8/BBN/CLASS/Planck grid."""
import argparse
import math
import sys
from pathlib import Path

SOFTWARE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SOFTWARE), str(SOFTWARE/"tests")]
from test_history import fixture
from test_observations import class_model
from r135.backends import prepare_native_rates
from r135.common import read_json, sha256, write_json
from r135.contracts import _commit, source_inventory
from r135.joint_grid import run
from r135.observations import CORNERS


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("out","class-root","planck-root","planck-python"):
        p.add_argument("--"+arg,type=Path,required=True)
    args = p.parse_args()
    out = args.out.resolve()
    out.mkdir(exist_ok=False,parents=True)
    rates,reverse = prepare_native_rates()
    write_json(out/"rates.json",{"rates":rates,"reverse_alpha_beta_gamma":reverse})
    weak = {"unit":"s^-1","source":"assigned post-BBN free neutron decay calibration",
            "time_s":[0.,1e12],"lambda_n_to_p_s_inv":[1/879.4]*2,"lambda_p_to_n_s_inv":[0.,0.]}
    write_json(out/"weak.json",{"histories":dict.fromkeys(CORNERS,weak)})
    source = source_inventory()["sha256"]
    release = SOFTWARE/"p0_snapshot/data_release_lock.json"
    def file(name,path):
        return {"name":name,"path":str(path),"sha256":sha256(path)}
    plans = {}
    for branch,tx in (("baseline",.00025),("X",.001)):
        cfg,eos,kernel,wall,coll,init=fixture()
        cfg.pop("_mode")
        for phase in eos["phases"].values():
            phase["T_range_MeV"][0]=1e-8
        eos["phases"]["hot"]["coefficients"][0] = -tx**4
        eos["transitions"][0].update(T_c_MeV=tx, latent_heat_MeV4=4*tx**4)
        kernel["T_MeV"][0]=1e-8
        wall["T_range_MeV"][0]=1e-8
        coll["thermal_channels"][0].update(amplitudes=[0]*3,T_range_MeV=[1e-8,2])
        init.update(T_X_MeV=tx,T_gamma_MeV=.009,T_nu_MeV=.009*(4/11)**(1/3),T_free_MeV=1e-5,
                    surface="postconfinement",phase_fraction=1.)
        cfg["recipient_eos"]["gamma"]["rho_over_T4"] = math.pi**2/15
        cfg["recipient_eos"]["nu"]["rho_over_T4"] = 3.044*7/8*math.pi**2/15
        cfg.update(samples=33, atol_relative=1e-12, eos_bundle=eos,nucleation_definition=kernel, wall_transport=wall,
                   collision_model=coll, initial_history=init)
        ident={"claim_id":"XB_SU3_cosmology","model_id":"post-BBN-control","point_id":branch,"thermal_path":cfg["thermal_path"]}
        def node(name,config,inputs):
            return {"id":name,"stage":name,"config":config,"inputs":inputs,"mode":"validation","key":ident,
                    "applicability":{"description":"late-time manufactured radiation and abundances, paired software control"}}
        def edge(name,parent,artifact):
            return {"name":name,"from_node":parent,"artifact":artifact}
        cmb=class_model()
        cmb["matching"]={"source":"post-annihilation radiation control","transfer_finished":True,"electron_annihilation_finished":True}
        p8={"class":cmb,"common_initial_abundances":[0.,.75998,1e-5,0.,0.,.06,0.,0.]}
        p9={"relative_floor":1e-6,"refinement":[{"rtol":10.**-i,"atol":10.**(-i-3)} for i in (11,12,13)],
            "theory_covariance_logD_Yp":[[0,0],[0,0]],"class_source_root":str(args.class_root.absolute()),
            "planck_data_root":str(args.planck_root.absolute()),"planck_python":str(args.planck_python.absolute()),
            "planck_python_sha256":sha256(args.planck_python),"profile_nuisance":False}
        nodes=[node("P7",cfg,[]),node("P8",p8,[edge("channel_history","P7","channel_history.json"),
               file("weak_rates",out/"weak.json"),file("nuclear_rates",out/"rates.json")]),
               node("P9",p9,[edge("bbn_inputs","P8","bbn_inputs.json"),edge("class_inputs","P8","class_inputs.json"),
                              edge("channel_history","P7","channel_history.json"),file("data_release_lock",release)])]
        path=out/(branch+".json")
        write_json(path,{"schema":"r135-pipeline-v1","source_sha256":source,"execution_sha":_commit(),"nodes":nodes})
        plans[branch]={"file":path.name,"sha256":sha256(path),"P9":"P9"}
    cells = []
    etas = [6e-10, 6.2e-10]
    for eta in etas:
        paired = {}
        for model, ref in plans.items():
            plan = read_json(out/ref["file"])
            plan["nodes"][0]["config"]["initial_history"]["eta_b_gamma"] = eta
            path = out/(model+"-"+str(eta)+".json")
            write_json(path,plan)
            paired[model] = {"file":path.name,"sha256":sha256(path),"P9":"P9"}
        cells.append({"coordinates":{"eta_b_gamma":eta},"X_point_id":"X","pipelines":paired})
    spec=out/"grid_input.json"
    write_json(spec,{"schema":"r135-joint-grid-v1","axes":{"eta_b_gamma":etas},"X_points":["X"],"corner":"11full",
                    "cells":cells})
    result=run(spec,out/"evaluated")
    if result["missing"]:
        raise RuntimeError(str(result["missing"]))
    receipts = [read_json(folder)["result"]["metrics"] for folder in
                (out/"evaluated").glob("*/*/P9/EXECUTION_RECEIPT.json")]
    if len(receipts) != 2*len(cells):
        raise RuntimeError("missing native P9 consumption receipts")
    write_json(out/"VALIDATION.json",{"scope":"two initial baryon ratios, two fixed late preparations, assigned abundances",
               "physical_point":False,"confidence_calibrated":False,"cmb_release":result["cmb_release"],
               "eta_b_gamma":etas, "native_BBN_integrations":sum(r["new_bbn_integrations"] for r in receipts),
               "native_CLASS_integrations":sum(r["new_class_integrations"] for r in receipts),
               "status":result["status"],"grid_sha256":result["grid_sha256"],"profiles":result["profiles"]})


if __name__=="__main__":
    main()
