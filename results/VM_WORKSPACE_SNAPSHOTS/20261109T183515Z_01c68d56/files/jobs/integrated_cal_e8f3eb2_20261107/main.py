"""Run the pinned, smoke-tested executor on the target VM; no main execution."""
import argparse
import base64
import hashlib
import json
import lzma
import os
from pathlib import Path, PurePosixPath
import signal
import subprocess
import sys
import time

parser=argparse.ArgumentParser()
parser.add_argument('--bundle',required=True)
parser.add_argument('--bundle-sha256',required=True)
args=parser.parse_args()
started=time.monotonic()
work=Path(os.environ['VM_WORK'])
data=(work/args.bundle).read_bytes()
if hashlib.sha256(data).hexdigest()!=args.bundle_sha256:raise ValueError('bundle hash mismatch')
outer=json.loads(data)
payload=json.loads(lzma.decompress(base64.b64decode(outer['xz_base64'])))
base=Path.cwd()/'input'
base.mkdir(exist_ok=False)
for name,content in payload['files'].items():
 p=PurePosixPath(name)
 if p.is_absolute() or '..' in p.parts:raise ValueError('unsafe input path')
 target=base/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(content)
root=base/'vm-lab/experiments/now_integrated_v1'
env=dict(os.environ)
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):env[key]='1'
reports=[]
for repeat in range(3):
 remaining=600-(time.monotonic()-started)
 if remaining<5:raise TimeoutError('calibration total 600 second budget')
 output=Path.cwd()/('calibration_'+str(repeat))
 command=[sys.executable,str(root/'run.py'),'--phase','calibrate','--output',str(output),
  '--source-commit',payload['source_commit'],'--source-manifest',str(base/'receipts/SOURCE_MANIFEST.json'),
  '--acceptance',str(base/'receipts/CALIBRATION_ACCEPTANCE.json'),
  '--smoke-report',str(base/'receipts/SMOKE_SUITE.json')]
 begin=time.monotonic()
 with (Path.cwd()/('calibration_'+str(repeat)+'.log')).open('w') as log:
  process=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  try:code=process.wait(timeout=remaining)
  except subprocess.TimeoutExpired:
   os.killpg(process.pid,signal.SIGTERM)
   try:process.wait(timeout=2)
   except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
   raise
 elapsed=time.monotonic()-begin
 if code:raise RuntimeError('executor failed; see calibration_'+str(repeat)+'.log')
 run=json.loads((output/'RUN.json').read_text())
 if not run['complete'] or not run['technical_pass']:raise RuntimeError('incomplete calibration')
 rows=[]
 for path in sorted((output/'rows').glob('*.json')):
  row=json.loads(path.read_text())
  rows.append({k:row.get(k) for k in ('case_id','config','sampling_mode','seed','task_compute_seconds','enumeration_nodes','executed_events','scientific_hash')})
 reports.append(dict(repeat=repeat,cli_wall_seconds=elapsed,run=run,rows=rows,
   environment=json.loads((output/'ENVIRONMENT.json').read_text())))
 summary=dict(source_commit=payload['source_commit'],complete=repeat==2,measured_on_target_vm=True,
  repetitions=reports,wall_seconds=time.monotonic()-started,hard_wall_seconds=600,
  main_submitted=False,scientific_confirmation=False)
 (Path.cwd()/'CALIBRATION_SUMMARY.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(dict(repeat=repeat,cli_wall_seconds=elapsed,tasks=run['task_count'],events=run['events']),ensure_ascii=False),flush=True)
 # Total cap covers all three repetitions, including their output files.
 if sum(p.stat().st_size for p in Path.cwd().rglob('*') if p.is_file())>512*1024**2:raise RuntimeError('aggregate calibration disk cap')
print(json.dumps(dict(complete=True,wall_seconds=time.monotonic()-started,main_submitted=False)),flush=True)
