"""Build a prelaunch budget from an already GitHub-verified calibration, no evolution."""
import argparse,hashlib,json,math
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from e002d_exp.plan import cases,counts
from e002d_exp.task import kernel_hash

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--cache",required=True);parser.add_argument("--verified",required=True)
    args=parser.parse_args();cache=Path(args.cache);checked=json.loads(Path(args.verified).read_text())
    assert checked["status"]=="VERIFIED_GITHUB" and checked["runtime"]["status"]=="PASS" and checked["execution_succeeded"]
    metrics=json.loads((cache/"files/metrics.json").read_text());manifest=json.loads((cache/"files/data_manifest.json").read_text())
    assert metrics["environment"]["kernel_sha256"]==kernel_hash()
    summaries={s["case"]["id"]:s for s in metrics["cases"]};groups={}
    for t in metrics["timing"]:
        dt=summaries[t["id"]]["case"]["dt"];key=(t["model"],dt);groups.setdefault(key,[]).append(t)
    costs={}
    for key,rows in groups.items():
        costs[key]=dict(calibration_cases=len(rows),calibration_steps=sum(r["steps"] for r in rows),
            setup_per_case=sum(r["setup_seconds"] for r in rows)/len(rows),
            advance_per_step=sum(r["advance_seconds"] for r in rows)/sum(r["steps"] for r in rows),
            integrator_per_step=sum(r["integrator_seconds"] for r in rows)/sum(r["steps"] for r in rows),
            finish_per_case=sum(r["finish_seconds"] for r in rows)/len(rows))
    full={r["path"]:r["bytes"] for r in manifest["full"]}
    sample_id=next(iter(summaries));base={Path(p).name:n for p,n in full.items() if p.startswith(sample_id+"/")}
    finish_names=("series.npz","diagnostics.npz","certificates.npz","final.npz","summary.json")
    finish_base=sum(base[n] for n in finish_names)
    array_spec=next(r["arrays"] for r in manifest["exported"] if r["path"].startswith("cases/"))
    itemsize={"float64":8,"complex128":16,"int64":8,"bool":1}
    def payload_bytes(horizon):
        nseries=51+len(range(12,int(horizon)+1,4));ndiag=11+len(range(24,int(horizon)+1,4))
        total=0
        for name,spec in array_spec.items():
            shape=list(spec["shape"])
            if horizon!=10:
                if name=="series":shape[0]=nseries
                elif name=="diagnostics":shape[0]=ndiag
                elif name.startswith("window_"):shape[0]=6 if horizon==200 else 12
                elif name.startswith("e_") and not name.startswith("e_extreme"):shape[0]=3
            total+=math.prod(shape)*itemsize[spec["dtype"]]
        return total
    measured_core=sum(sum(t[k] for k in ("setup_seconds","advance_seconds","finish_seconds")) for t in metrics["timing"])
    phases=metrics["phase_timing"]
    residual=max(0.,checked["runtime"]["actual_seconds"]-measured_core-sum(phases.values()))
    branches={};plan=cases("production")
    for horizon in (200.,400.):
        series_factor=(horizon/.2+1)/51;diag_factor=(horizon/2+1)/6
        finish_bytes=base["series.npz"]*series_factor+(base["diagnostics.npz"]+base["certificates.npz"])*diag_factor+base["final.npz"]+2*base["summary.json"]
        finish_factor=finish_bytes/finish_base
        snapshots=sum(t<=horizon for t in (0.,.2,1.,2.,5.,10.,20.,50.,100.,190.,200.,300.,390.,400.))
        full_per_case=finish_bytes+snapshots*base["rho_0.npz"]+base["model.json"]+base["checkpoint.json"]
        full_estimate=len(plan)*full_per_case
        components=dict(setup_seconds=0.,advance_seconds=0.,finish_seconds=0.)
        for c in plan:
            cost=costs[c["model"],c["dt"]]
            components["setup_seconds"]+=(2 if horizon==400 else 1)*cost["setup_per_case"]
            components["advance_seconds"]+=round(horizon/c["dt"])*cost["advance_per_step"]
            components["finish_seconds"]+=cost["finish_per_case"]*finish_factor
        components["export_seconds"]=phases["export_seconds"]*len(plan)/48*payload_bytes(horizon)/payload_bytes(10.)
        components["verification_seconds"]=phases["verification_seconds"]*len(plan)/48*(1.5 if horizon==200 else 2.)
        components["assembly_seconds"]=residual*max(len(plan)/48,full_estimate/manifest["full_bytes"])
        # Calibration omits production A/B/C arithmetic. Existing regression checks
        # exercise both horizons repeatedly; 30s is an explicit engineering allowance.
        components["production_analysis_allowance_seconds"]=30.
        raw=sum(components.values());expected=60*math.ceil(raw/60);delta=max(.30*expected,60.)
        branches["T"+str(int(horizon))]=dict(expected_seconds=expected,lower_seconds=max(0.,expected-delta),upper_seconds=expected+delta,
            components=components,raw_estimate_seconds=raw,work=counts("production",horizon),estimated_full_bytes=math.ceil(full_estimate),
            report_hard_limit_bytes=30*1024**2,range_basis="RUNTIME_GATE base tolerance +/-30%; not a statistical confidence interval")
    forecast=dict(source="Verified "+checked["run_id"]+" at "+checked["report_commit"]+"; stratified model/dt full advance cost including diagnostics and IO; final assembly scaled separately",branches=branches)
    cal=dict(run_id=checked["run_id"],kernel_sha256=kernel_hash(),numpy=metrics["environment"]["numpy"],scipy=metrics["environment"]["scipy"],
        review_status="VERIFIED_GITHUB",report_commit=checked["report_commit"],source_commit=checked["source_commit"],run_manifest_sha256=checked["run_manifest_sha256"])
    record=dict(status="VERIFIED_GITHUB",calibration=cal,verification=checked)
    directory=Path("experiments/e002d");path=directory/"calibration_verification.json";path.write_text(json.dumps(record,indent=2)+"\n")
    current=json.loads(Path("config.json").read_text())
    production=dict(run_id="E002d_PROD_v003_r001",mode="production",forecast=forecast,calibration=cal,
        calibration_verification=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest()),
        copilot_review=current["copilot_review"],copilot_review_status="REVIEWED_AND_CHECKED")
    (directory/"production_config_v003.json").write_text(json.dumps(production,indent=2)+"\n")
    # Preparation only: no VM queue request is emitted by this script.
    Path("config.json").write_text(json.dumps(production,indent=2)+"\n")
    detail=dict(forecast=forecast,calibration_costs={f"{m}:{dt:g}":v for (m,dt),v in costs.items()},
        measured_finalization_residual_seconds=residual,case_payload_bytes={str(t):payload_bytes(t) for t in (10.,200.,400.)},
        accounting="advance already includes integrator, diagnostics, snapshots and progress IO; these are never added again. Rebuild estimated by full initial setup, conservatively. Finish scaled by retained array bytes, export by selected payload bytes, verification by windows/evidence, residual by file inventory bytes. Production-only arithmetic gets30s. Queue/publication excluded.",
        limitations=["Short T10 timing extrapolated toT200/T400; drift/load may change cost.","Compression stress is not a guarantee of the actual report size. Hard 30MiB gate remains; no samples dropped.","This script prepares configuration only; production is not queued."])
    (directory/"BUDGET_v003.json").write_text(json.dumps(detail,indent=2)+"\n")
    print(json.dumps(detail,indent=2))
if __name__=="__main__":main()
