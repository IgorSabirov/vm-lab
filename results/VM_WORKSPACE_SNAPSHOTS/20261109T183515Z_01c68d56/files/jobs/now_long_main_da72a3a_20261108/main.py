"""Run the same pinned NOW CLI; export process time and calibration strata."""
import argparse,json,os,subprocess,sys,time,resource,zipfile,hashlib
from pathlib import Path
for k in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS"):os.environ[k]="1"
p=argparse.ArgumentParser();p.add_argument("--repo",required=True);p.add_argument("--phase",choices=["calibrate","main"],required=True);p.add_argument("--forecast");a=p.parse_args()
repo=Path(a.repo);root=repo/"experiments/now_integrated_v1";receipt=json.loads((repo/"LONG_SOURCE.json").read_text());sha=receipt["source_commit"];out=Path.cwd()/(a.phase+"_output")
cmd=[sys.executable,str(root/"run.py"),"--phase",a.phase,"--output",str(out),"--source-commit",sha,"--source-manifest",str(repo/"LONG_SOURCE.json"),"--acceptance",str(repo/"LONG_ACCEPTANCE.json"),"--smoke-report",str(repo/"LONG_SMOKE.json")]
if a.phase=="main":
    if not a.forecast:raise ValueError("published measured forecast required")
    cmd+=["--calibration",a.forecast]
start=time.perf_counter()
with Path("process.log").open("w") as log:r=subprocess.run(cmd,cwd=root,stdout=log,stderr=subprocess.STDOUT)
elapsed=time.perf_counter()-start
run=json.loads((out/"RUN.json").read_text()) if (out/"RUN.json").exists() else {}
ru=resource.getrusage(resource.RUSAGE_CHILDREN)
result=dict(source_commit=sha,phase=a.phase,exit_code=r.returncode,process_wall_seconds=elapsed,child_cpu_seconds=ru.ru_utime+ru.ru_stime,run=run)
if a.phase=="calibrate" and r.returncode==0:
    case_map={x["id"]:x for x in json.loads((root/"preregistration/CASES.json").read_text())["cases"]}
    rows=[]
    for path in sorted((out/"rows").glob("*.json")):
        x=json.loads(path.read_text());case=case_map.get(x["case_id"],{})
        rows.append(dict(case_id=x["case_id"],stratum=case.get("cost_stratum"),task_compute_seconds=x["task_compute_seconds"],events=x.get("executed_events",x.get("result",{}).get("events",0)),bytes=path.stat().st_size))
    result["rows"]=rows
    result["environment"]=json.loads((out/"ENVIRONMENT.json").read_text())
Path("PROCESS.json").write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps(dict(phase=a.phase,exit_code=r.returncode,wall_seconds=elapsed,child_cpu_seconds=result["child_cpu_seconds"],task_count=run.get("task_count")),ensure_ascii=False),flush=True)
if r.returncode:raise SystemExit(r.returncode)
if a.phase=="main":
    report=json.loads((out/"FOUR_CANDIDATE_RETURN.json").read_text())
    Path("FOUR_CANDIDATE_RETURN.json").write_text(json.dumps(report,indent=2)+"\n")
    with zipfile.ZipFile("FULL_OUTPUT.zip","w",zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for q in sorted(out.rglob("*")):
            if q.is_file():z.write(q,str(q.relative_to(out)))
    archive=Path("FULL_OUTPUT.zip")
    Path("ARCHIVE.json").write_text(json.dumps(dict(size_bytes=archive.stat().st_size,sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),source_commit=sha),indent=2)+"\n")
