"""Evaluate a declared finite baseline/X cosmology grid via real P7/P8/P9 pipelines."""
import csv
import itertools
import math
from pathlib import Path

from .common import InputError, OpenInput, canonical_hash, finite, read_json, sha256, write_json
from .contracts import verify_result
from .observations import CORNERS, bridge_hash
from .pipeline import run_pipeline


def cells_for(spec):
    axes = spec.get("axes", {})
    if "eta_b_gamma" not in axes or set(axes)-{"eta_b_gamma","H0","tau_reio","n_s","A_s","omega_cdm"}:
        raise InputError("grid needs initial eta and supported independent cosmological parameters")
    for axis, values in axes.items():
        if not isinstance(values,list) or not values or len(set(values)) != len(values):
            raise InputError("empty or repeated cosmological grid coordinate")
        for value in values:
            finite(value,axis,nonnegative=True)
    points = spec.get("X_points", [None])
    if (not isinstance(points, list) or not points or len(set(points)) != len(points)
            or ("X_points" in spec and any(not isinstance(p,str) or not p for p in points))):
        raise InputError("X_points must name unique independent preparations")
    axes_order = sorted(axes)
    expected = set(itertools.product(*(axes[k] for k in axes_order), points))
    cells = spec.get("cells", [])
    seen = set()
    for cell in cells:
        if set(cell["coordinates"]) != set(axes) or set(cell["pipelines"]) != {"baseline","X"}:
            raise InputError("grid cell must contain matched coordinates and both models")
        key = (*[cell["coordinates"][k] for k in axes_order], cell.get("X_point_id"))
        if key in seen:
            raise InputError("duplicate cosmological preparation")
        seen.add(key)
    if seen != expected:
        raise InputError("cosmology grid omits or adds a registered coordinate")
    return cells


def evaluate_cell(plan_path, reference, coordinates, output, corner, release):
    path = plan_path.parent/reference["file"]
    if sha256(path) != reference["sha256"]:
        raise InputError("grid pipeline digest differs")
    plan = read_json(path)
    nodes = {n["id"]:n for n in plan["nodes"]}
    p9 = nodes[reference["P9"]]
    def parent(node, artifact, stage, filename):
        records = [x for x in node["inputs"] if x["name"] == artifact]
        if len(records) != 1 or records[0].get("artifact") != filename:
            raise InputError("joint grid requires a computed "+artifact)
        upstream = nodes[records[0]["from_node"]]
        if upstream["stage"] != stage or upstream["key"] != p9["key"]:
            raise InputError("joint grid lacks a common keyed P7/P8/P9 chain")
        return upstream
    if p9["stage"] != "P9" or p9["config"].get("cmb_mode","native_class") != "native_class":
        raise InputError("joint cosmology grid requires a native CLASS producer")
    p8 = parent(p9,"bbn_inputs","P8","bbn_inputs.json")
    if parent(p9,"class_inputs","P8","class_inputs.json") != p8:
        raise InputError("BBN and CMB inputs must derive from the same P8")
    p7 = parent(p8,"channel_history","P7","channel_history.json")
    report = run_pipeline(path,output)
    for n in (p7,p8,p9):
        result = report["nodes"][n["id"]]
        if result["software_status"] == "FAIL":
            raise InputError(str(result["reasons"]))
        if result["software_status"] != "PASS":
            raise OpenInput(str(result["reasons"]))
        verify_result(output/n["id"])
    stages = [output/n["id"] for n in (p7,p8,p9)]
    channel = read_json(stages[0]/"channel_history.json")
    initial = channel["initial_history"]
    initial = initial.get("definition", initial)
    eta = initial.get("eta_b_gamma",initial.get("eta_b"))
    if eta != coordinates["eta_b_gamma"]:
        raise InputError("grid coordinate differs from actual initial baryon ratio")
    if read_json(stages[1]/"bbn_inputs.json")["source_P7_file_sha256"] != sha256(stages[0]/"channel_history.json"):
        raise InputError("joint grid substituted the P7 history")
    root = stages[-1]
    with (root/"likelihood_grid.csv").open() as stream:
        rows = {r["engine"]:r for r in csv.DictReader(stream) if r["corner"] == corner}
    if set(rows) != {"linx","primat"}:
        raise OpenInput("P9 has no complete joint BBN/CMB likelihood at this coordinate")
    results = {}
    for e,r in rows.items():
        receipt = read_json(root/"class"/e/corner/"receipt.json")
        if receipt["source_P7_history_sha256"] != bridge_hash(channel["histories"][corner]):
            raise InputError("CLASS grid spectrum comes from a different physical history")
        actual = receipt["input"]["parameters"]
        if any(actual[k] != v for k,v in coordinates.items() if k != "eta_b_gamma"):
            raise InputError("CLASS did not consume the registered cosmological coordinates")
        likelihood = read_json(root/"class"/e/corner/"likelihood.json")
        posterior, nuisance = r["log_posterior"], likelihood["CMB"]["nuisance"]
        if release != "Planck_PR3":
            external = root / "external_cmb_evaluations.json"
            if not external.is_file():
                raise OpenInput("requested independent CMB release was not evaluated")
            observed = read_json(external)["evaluations"][f"{e}/{corner}"].get(release)
            if observed is None:
                raise OpenInput("requested CMB variant lacks a likelihood for this spectrum")
            if observed["consumed_file_sha256"] != receipt["spectra_sha256"]:
                raise InputError("alternative CMB release read a different spectrum")
            posterior = likelihood["BBN"]["logL_BBN"] + observed["log_posterior"]
            nuisance = observed["nuisance"]
        results[e] = {"log_posterior":finite(posterior,"BBN + CMB with nuisance priors"),
                      "omega_b":actual["omega_b"], "eta_late":receipt["matching"]["eta"],
                      "spectrum_sha256":receipt["spectra_sha256"],"nuisance":nuisance}
    cfg = p9["config"]
    policy = {"release":sha256(root/"data_release_lock.json"),
              "fit":{k:cfg.get(k) for k in ("profile_nuisance","profile_policy","nuisance","class_refinement",
                                             "max_cmb_delta_logL","refinement","theory_covariance_logD_Yp")}}
    policy["fit"]["profile_maxiter"] = cfg.get("profile_maxiter", 1000)
    policy["cmb_release"] = release
    if release != "Planck_PR3":
        policy["external_fit"] = {k:v for k,v in cfg.get("external_cmb", {}).items()
                                  if k not in ("python","cache","offline")}
    for a in read_json(root/"REQUEST.json")["inputs"]:
        if a["name"] == "nuclear_rate_ensemble":
            policy["ensemble"] = a["sha256"]
    return {"engines":results,"policy_sha256":canonical_hash(policy),"p9_manifest_sha256":sha256(root/"MANIFEST.json"),
            "history_sha256": bridge_hash(channel["histories"][corner]), "key":p9["key"],"mode":p9["mode"]}


def run(path, output):
    path,output=Path(path).resolve(),Path(output).resolve()
    spec=read_json(path)
    if spec.get("schema") != "r135-joint-grid-v1" or spec.get("corner") not in CORNERS:
        raise InputError("unsupported joint-grid schema or history")
    release = spec.get("cmb_release", "Planck_PR3")
    if release not in {"Planck_PR3", "ACT_DR6_CMBONLY", "SPT3G_D1_LITE"}:
        raise InputError("choose one independent CMB likelihood per grid")
    cells=cells_for(spec)
    output.mkdir(exist_ok=True,parents=True)
    frozen=output/"GRID.json"
    if frozen.exists() and read_json(frozen) != spec:
        raise InputError("output already belongs to another registered grid")
    write_json(frozen,spec)
    results, policies, missing = [],set(),[]
    for i,cell in enumerate(cells):
        pair={}
        if cell["pipelines"]["baseline"]["sha256"] == cell["pipelines"]["X"]["sha256"] and cell["pipelines"]["baseline"]["P9"] == cell["pipelines"]["X"]["P9"]:
            raise InputError("a single preparation was substituted for both hypotheses")
        for model,ref in cell["pipelines"].items():
            try:
                pair[model]=evaluate_cell(path,ref,cell["coordinates"],output/str(i)/model,spec["corner"],release)
                if model == "X" and "X_point_id" in cell and pair[model]["key"]["point_id"] != cell["X_point_id"]:
                    raise InputError("the executed X preparation is not the registered grid point")
                policies.add(pair[model]["policy_sha256"])
            except OpenInput as exc:
                missing.append({"cell":i,"model":model,"reason":str(exc)})
        if len(pair) == 2 and pair["baseline"]["key"] == pair["X"]["key"] and pair["baseline"]["history_sha256"] == pair["X"]["history_sha256"]:
            raise InputError("two identical keyed histories supplied for the paired fit")
        results.append({"coordinates":cell["coordinates"],"X_point_id":cell.get("X_point_id"),"models":pair})
    if len(policies)>1:
        raise InputError("baseline and X do not use one observational/nuisance policy")
    profiles={}
    if not missing:
        for e in ("linx","primat"):
            winners={}
            for model in ("baseline","X"):
                best=max(results,key=lambda cell:cell["models"][model]["engines"][e]["log_posterior"])
                winners[model]={"coordinates":best["coordinates"],"model_key":best["models"][model]["key"],**best["models"][model]["engines"][e]}
            profiles[e]={**winners,"twice_delta_log_posterior":2*(winners["X"]["log_posterior"]-winners["baseline"]["log_posterior"])}
    answer={"status":"OPEN_INPUT" if missing else "CONDITIONAL_FINITE_GRID","cmb_release":release,"statistic":"BBN + one CMB likelihood plus declared nuisance priors",
            "confidence_calibrated":False,"scientific_acceptance":"owner_review","grid_sha256":sha256(path),
            "cells":results,"missing":missing,"profiles":profiles}
    write_json(output/"joint_grid.json",answer)
    return answer
