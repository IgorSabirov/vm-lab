"""Bounded target-VM cost sample for extending the existing NOW dispatcher.
No waiting, external model, new physics, or inference gate.
"""
import argparse,hashlib,json,os,sys,time,resource,signal
from pathlib import Path
for key in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS"):os.environ[key]="1"
p=argparse.ArgumentParser();p.add_argument("--plan",required=True);a=p.parse_args()
plan=json.loads(Path(a.plan).read_text())
root=Path(os.environ["VM_WORK"])/"code/now_integrated_v1_7c55308/experiments/now_integrated_v1"
for name,want in plan["model_git_blobs"].items():
    raw=(root/name).read_bytes()
    got=hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
    if got!=want:raise ValueError("pinned GitHub model mismatch: "+name)
sys.path.insert(0,str(root))
from nowexp.state import Config
from nowexp.enumeration import FiniteEnumeration
from nowexp.provenance import environment,digest
records=[];start=time.perf_counter()
def timeout(*_):raise TimeoutError("bounded calibration exceeded 240 seconds")
signal.signal(signal.SIGALRM,timeout);signal.alarm(240)
for item in plan["calibration_cases"]:
    cfg=Config(**item["config"]).validate()
    b=time.perf_counter();cpu=time.process_time()
    job=FiniteEnumeration(cfg,max_nodes=4096)
    while job.pending:job.advance()
    result=job.result()
    seconds=time.perf_counter()-b
    record=dict(id=item["id"],family=item["family"],generations=cfg.generations,
        wall_seconds=seconds,cpu_seconds=time.process_time()-cpu,
        nodes=job.nodes,events=job.executed_events,outcomes=len(result["outcomes"]),
        probability_mass=result["probability_mass"],
        serialized_result_bytes=len(json.dumps(result).encode()),
        max_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
        science=dict(mean_task_success=sum(x["weight"]*x["result"].get("mean_task_success",x["result"]["final_function"]) for x in result["outcomes"]),
          full_reserve_mass=sum(x["weight"]*sum(bool(t.get("full_reserve")) for t in x["result"].get("task_results",[]))/cfg.generations for x in result["outcomes"])))
    records.append(record)
    out=dict(status="RUNNING",records=records,wall_seconds=time.perf_counter()-start,environment=environment(),source=plan["model_commit"])
    Path("CALIBRATION.json").write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps(record),flush=True)
signal.alarm(0)
out.update(status="COMPLETED",wall_seconds=time.perf_counter()-start)
Path("CALIBRATION.json").write_text(json.dumps(out,indent=2)+"\n")
