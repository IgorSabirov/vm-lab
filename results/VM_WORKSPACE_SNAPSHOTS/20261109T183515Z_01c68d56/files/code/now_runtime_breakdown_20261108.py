import json, statistics
from pathlib import Path
root=Path("/var/lib/vm-compute/work")
run=root/"results/now_long_main_da72a3a_20261108"
src=root/"code/now_long_da72a3a/experiments/now_integrated_v1"
cases={c["id"]:c.get("cost_stratum") for c in json.loads((src/"preregistration/CASES.json").read_text())["cases"]}
cal=json.loads((run/"CALIBRATION_PROCESS.json").read_text()) if (run/"CALIBRATION_PROCESS.json").exists() else None
# Calibration report is held beside main in the original calibration job directory.
if cal is None:
    calpath=root/"results/now_long_cal_da72a3a_20261108/PROCESS.json"
    cal=json.loads(calpath.read_text())
actual={}; sizes={}; count=0
for p in (run/"main_output/rows").glob("*.json"):
    x=json.loads(p.read_text()); key=x.get("cost_stratum") or cases.get(x.get("case_id")) or "unstratified_base_and_controls"
    actual.setdefault(key,[]).append(x["task_compute_seconds"]);sizes[key]=sizes.get(key,0)+p.stat().st_size;count+=1
measured={}
for x in cal.get("rows",[]):
    key=x.get("stratum")
    if key:measured.setdefault(key,[]).append(x["task_compute_seconds"])
parts={}
for key,vals in actual.items():
    xs=sorted(vals); expected=sum(measured.get(key,[]))/len(measured[key])*len(vals) if key in measured else None
    parts[key]={"n":len(vals),"sum_s":sum(vals),"predicted_s":expected,"ratio":sum(vals)/expected if expected else None,"median_s":statistics.median(vals),"p90_s":xs[int(.9*(len(xs)-1))],"max_s":max(vals),"output_bytes":sizes[key]}
sumtasks=sum(sum(v) for v in actual.values())
out={"tasks":count,"actual_task_timers_s":sumtasks,"actual_process_wall_s":json.loads((run/"PROCESS.json").read_text())["process_wall_seconds"],"unstratified_and_controls_task_timer_s":sum(sum(v) for k,v in actual.items() if k=="unstratified_base_and_controls"),"calibration_stratified_prediction_s":sum(v["predicted_s"] for v in parts.values() if v["predicted_s"] is not None),"unstratified_and_controls_rows":len(actual.get("unstratified_base_and_controls",[])),"strata":parts}
Path("results.json").write_text(json.dumps(out,indent=2)+"\n")
print(json.dumps(out,separators=(",",":")))
