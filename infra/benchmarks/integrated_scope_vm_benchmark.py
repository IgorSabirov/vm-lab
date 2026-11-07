"""Pinned source calibration and size-matched I/O projection, never a main run."""
import argparse,base64,copy,hashlib,json,lzma,os,signal,statistics,subprocess,sys,time
from pathlib import Path,PurePosixPath
p=argparse.ArgumentParser();p.add_argument('--bundle',required=True);p.add_argument('--bundle-sha256',required=True);a=p.parse_args()
start=time.monotonic();work=Path(os.environ['VM_WORK']);raw=(work/a.bundle).read_bytes()
if hashlib.sha256(raw).hexdigest()!=a.bundle_sha256:raise ValueError('bundle hash mismatch')
payload=json.loads(lzma.decompress(base64.b64decode(json.loads(raw)['xz_base64'])))
base=Path.cwd()/'input';base.mkdir(exist_ok=False)
for name,content in payload['files'].items():
 q=PurePosixPath(name)
 if q.is_absolute() or '..' in q.parts:raise ValueError('unsafe bundle path')
 target=base/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(content)
root=base/'vm-lab/experiments/now_integrated_v1'
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[key]='1'
sys.path.insert(0,str(root))
from nowexp.provenance import read_json,atomic_json,configure_io_budget,verify_source,digest
from nowexp.runner import make_tasks
verify_source(root,payload['source_commit'],base/'receipts/SOURCE_MANIFEST.json')
plan=read_json(root/'preregistration/PROTOCOL.json');cases=read_json(root/'preregistration/CASES.json');_,tasks=make_tasks(plan,cases,'main')
reports=[];lookup={}
for repeat in range(3):
 output=Path.cwd()/('calibration_'+str(repeat))
 command=[sys.executable,str(root/'run.py'),'--phase','calibrate','--output',str(output),'--source-commit',payload['source_commit'],'--source-manifest',str(base/'receipts/SOURCE_MANIFEST.json'),'--acceptance',str(base/'receipts/CALIBRATION_ACCEPTANCE.json'),'--smoke-report',str(base/'receipts/SMOKE_SUITE.json')]
 begin=time.monotonic()
 with (Path.cwd()/('calibration_'+str(repeat)+'.log')).open('w') as log:
  process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  try:code=process.wait(timeout=max(1,600-(time.monotonic()-start)))
  except subprocess.TimeoutExpired:
   os.killpg(process.pid,signal.SIGTERM)
   try:process.wait(timeout=2)
   except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
   raise
 if code:raise RuntimeError('calibration failed: '+str(repeat))
 run=read_json(output/'RUN.json')
 if not(run['complete'] and run['technical_pass']):raise RuntimeError('incomplete calibration')
 rows=[read_json(q) for q in sorted((output/'rows').glob('*.json'))]
 reports.append(dict(cli_wall_seconds=time.monotonic()-begin,run=run,rows=[{k:r.get(k) for k in ('case_id','sampling_mode','config','seed','task_compute_seconds','enumeration_nodes','executed_events')} for r in rows]))
 if repeat==0:
  for row in rows:
   if row['seed']==0:lookup[row['case_id']]=dict(row=row,trace=read_json(output/'traces'/(row['task_id']+'.json')))
 print(json.dumps(dict(phase='calibration',repeat=repeat,seconds=reports[-1]['cli_wall_seconds'],tasks=run['task_count'])),flush=True)
# Full-size outputs use real measured same-family payloads. No results are interpreted.
def family(task):
 cfg=task['config']
 return (task['sampling_mode'],cfg['memory'],bool(cfg.get('separate_apparatus')),cfg['bath_modes'])
def reference(task):
 if task['case_id'] in lookup:return task['case_id']
 candidates=[k for k,v in lookup.items() if family(v['row'])==family(task)]
 if not candidates:candidates=[k for k,v in lookup.items() if v['row']['sampling_mode']==task['sampling_mode'] and v['row']['config']['memory']==task['config']['memory']]
 if not candidates:raise ValueError('uncalibrated family: '+str(family(task)))
 return max(candidates,key=lambda k:len(json.dumps(lookup[k]['row'])))
refs=[reference(t) for t in tasks]
measurements=[]
for repeat in range(2):
 output=Path.cwd()/('synthetic_io_'+str(repeat));output.mkdir();configure_io_budget(output,128*1024**2,2*1024**3)
 begin=time.monotonic();hashes=[]
 for i,(task,name) in enumerate(zip(tasks,refs)):
  if time.monotonic()-start>600:raise TimeoutError('combined benchmark cap')
  row=copy.deepcopy(lookup[name]['row']);row['synthetic_io_only']=True
  atomic_json(output/'rows'/f'{i:06d}.json',row)
  if task['seed']==0:atomic_json(output/'traces'/f'{i:06d}.json',dict(synthetic_io_only=True,payload=lookup[name]['trace']))
  for branch in range(16,int(row.get('enumeration_nodes',0) or 0)+1,16):atomic_json(output/'CHECKPOINT.json',dict(synthetic_io_only=True,cursor=i,active=row,row_hashes=hashes))
  hashes.append(row['scientific_hash']);atomic_json(output/'CHECKPOINT.json',dict(synthetic_io_only=True,cursor=i+1,active=None,row_hashes=hashes))
 # Final smoke reports have the full 84-comparison/16-design shapes, copied for I/O only.
 for name,value in payload['finalization_templates'].items():atomic_json(output/(name+'.json'),dict(synthetic_io_only=True,payload=value))
 atomic_json(output/'ROWS_INDEX.json',dict(synthetic_io_only=True,hashes=hashes))
 measurements.append(dict(seconds=time.monotonic()-begin,bytes=sum(q.stat().st_size for q in output.rglob('*') if q.is_file()),files=sum(q.is_file() for q in output.rglob('*'))))
 print(json.dumps(dict(phase='synthetic_io',repeat=repeat,**measurements[-1])),flush=True)
configure_io_budget(Path.cwd(),512*1024**2,2*1024**3)
by={}
for repeat in reports:
 for row in repeat['rows']:by.setdefault(row['case_id'],[]).append(row['task_compute_seconds'])
allocation=[dict(case=t['case_id'],seed=t['seed'],reference=n,direct=t['case_id']==n,seconds=statistics.median(by[n])) for t,n in zip(tasks,refs)]
compute=sum(x['seconds'] for x in allocation);io=statistics.median(x['seconds'] for x in measurements)
startup=statistics.median(x['cli_wall_seconds']-x['run']['current_worker_seconds'] for x in reports)
central=compute+io+startup
# Wide prospective engineering envelope; not a statistical interval and not fitted to main.
low=max(1,central*.5);high=max(30,central*3);hard=max(120,high*2)
run=reports[0]['run']
forecast=dict(schema=1,complete=True,measured_on_target_vm=True,source_commit=payload['source_commit'],source_digest=run['source_digest'],config_digest=run['config_digest'],environment_fingerprint=run['environment_fingerprint'],task_count=len(tasks),expected_seconds=round(central,2),lower_seconds=round(low,2),upper_seconds=round(high,2),hard_wall_seconds=round(hard),memory_limit_mib=2048,disk_limit_mib=256,processes=1,blas_threads=1,components=dict(compute_seconds=compute,synthetic_io_seconds=io,startup_seconds=startup),main_submitted=False,scientific_confirmation=False,scope='123 finite cases, 84 contrasts, 11 controls and 192 MC validation trajectories; not complete physical theory',limitations=['Unmeasured same-family cases use the largest calibrated payload; branch expansion remains bounded by 4096 nodes and may exceed proxy timing.','I/O uses synthetic copies of real calibrated payloads and full smoke finalization shapes.','Engineering interval, not confidence interval; new code, workload or hardware invalidates this forecast.'])
report=dict(complete=True,source_commit=payload['source_commit'],repetitions=reports,io_measurements=measurements,allocation=allocation,forecast=forecast,total_wall_seconds=time.monotonic()-start,hard_wall_seconds=600,main_submitted=False)
atomic_json(Path.cwd()/'BENCHMARK.json',report);atomic_json(Path.cwd()/'FORECAST.json',forecast)
print(json.dumps(dict(complete=True,forecast=forecast,total_wall_seconds=time.monotonic()-start)),flush=True)
