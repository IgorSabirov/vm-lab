"""Bounded synthetic I/O projection at the declared main task count; not science."""
import json,os,sys,time,hashlib
from pathlib import Path
started=time.monotonic()
for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[k]='1'
origin=Path(os.environ['VM_WORK'])/'results/integrated_cal_e8f3eb2_20261107'
root=origin/'input/vm-lab/experiments/now_integrated_v1'
sys.path.insert(0,str(root))
from nowexp.runner import make_tasks
from nowexp.provenance import atomic_json,configure_io_budget,read_json,verify_source
receipt=origin/'input/receipts/SOURCE_MANIFEST.json'
verify_source(root,'e8f3eb296f9bdb4491aedcd8a5ca36b5cb781fee',receipt)
plan=read_json(root/'preregistration/PROTOCOL.json');cases=read_json(root/'preregistration/CASES.json')
_,tasks=make_tasks(plan,cases,'main')
rows=[read_json(p) for p in (origin/'calibration_0/rows').glob('*.json')]
lookup={r['case_id']:r for r in rows}
measurements=[]
for repeat in range(2):
 output=Path.cwd()/('io_'+str(repeat));output.mkdir()
 configure_io_budget(output,64*1024**2,2*1024**3)
 begin=time.perf_counter();hashes=[];selected=[];trace_count=0
 for i,task in enumerate(tasks):
  if time.monotonic()-started>60:raise TimeoutError('I/O probe limit 60 seconds')
  c=task['config'];name=task['case_id']
  if name not in lookup:
   name=('forced11' if task['sampling_mode']=='deterministic' else 'base') if c['memory']=='classical' else ('bath_32' if c['bath_modes']>8 else ('finite_static_32' if c['memory']=='finite_static' else 'finite_dark_32'))
  row=dict(lookup[name]);row['synthetic_io_only']=True
  atomic_json(output/'rows'/f'{i:06d}.json',row)
  if task['seed']==0:
   trace=read_json(origin/'calibration_0/traces'/(row['task_id']+'.json'))
   atomic_json(output/'traces'/f'{i:06d}.json',trace);trace_count+=1
  # Main writes an active branch checkpoint every 16 enumeration nodes.
  for branch in range(16,int(row.get('enumeration_nodes',0))+1,16):
   atomic_json(output/'CHECKPOINT.json',dict(cursor=i,active=row,row_hashes=hashes,synthetic_io_only=True))
  hashes.append(row['scientific_hash']);selected.append(row)
  atomic_json(output/'CHECKPOINT.json',dict(cursor=i+1,active=None,row_hashes=hashes,synthetic_io_only=True))
 # Projection includes finalization at full task/contrast count.
 from nowexp.observables import summarize,paired_contrasts,ancestor_report
 # Re-label only the copied benchmark rows: these are not scientific outputs.
 for row,task in zip(selected,tasks):row.update(case_id=task['case_id'],seed=task['seed'],config=task['config'])
 summaries=summarize(selected)
 contrasts=paired_contrasts(selected,cases['contrasts'],plan['acceptance']['profile_equivalence_tv'])
 atomic_json(output/'METRICS_SYNTHETIC.json',dict(summary=summaries,contrasts=contrasts,synthetic_io_only=True))
 atomic_json(output/'ANCESTORS_SYNTHETIC.json',ancestor_report(read_json(root/'preregistration/ANCESTOR_CONTRACTS.json')['contracts'],selected,summaries,contrasts))
 atomic_json(output/'ROWS_INDEX.json',dict(hashes=hashes,synthetic_io_only=True))
 measurements.append(dict(repeat=repeat,seconds=time.perf_counter()-begin,tasks=len(tasks),trace_count=trace_count,
  bytes=sum(p.stat().st_size for p in output.rglob('*') if p.is_file()),files=sum(1 for p in output.rglob('*') if p.is_file())))
 report=dict(complete=repeat==1,synthetic_io_only=True,scientific_confirmation=False,main_submitted=False,
  measurements=measurements,total_wall_seconds=time.monotonic()-started,hard_wall_seconds=60,
  limitation='Copied calibrated row/trace payloads; uncalibrated cases use declared nearest size-family proxy, not measured scientific outcomes.')
 (Path.cwd()/'IO_PROJECTION.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(measurements[-1]),flush=True)
