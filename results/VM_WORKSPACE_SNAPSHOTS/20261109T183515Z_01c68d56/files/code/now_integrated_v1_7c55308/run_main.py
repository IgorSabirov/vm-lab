import json, os, subprocess, sys, time
from pathlib import Path
work=Path(os.environ['VM_WORK']).resolve()
repo=work/'code'/'now_integrated_v1_7c55308'
root=repo/'experiments'/'now_integrated_v1'
for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'): os.environ[k]='1'
cal=work/'data'/'now_integrated_v1'/'VM_CALIBRATION_FORECAST_7c55308.json'
out=Path.cwd()/'main_output'
cmd=[sys.executable,str(root/'run.py'),'--phase','main','--output',str(out),'--source-commit','7c55308ce85a1337cbd43d2ab046a344d6bde3cf','--source-manifest',str(repo/'analysis/INTEGRATED_EXPERIMENT_20261107/PATCH_SOURCE_MANIFEST.json'),'--acceptance',str(repo/'analysis/INTEGRATED_EXPERIMENT_20261107/REVIEW_ACCEPTANCE.json'),'--smoke-report',str(repo/'analysis/INTEGRATED_EXPERIMENT_20261107/USER_WAIVER_SMOKE_7c55308.json'),'--calibration',str(cal)]
t0=time.perf_counter()
with (Path.cwd()/'main.log').open('w') as f: p=subprocess.run(cmd,cwd=root,stdout=f,stderr=subprocess.STDOUT)
wall=time.perf_counter()-t0
rp=out/'RUN.json'
result={'phase':'main','source_commit':'7c55308ce85a1337cbd43d2ab046a344d6bde3cf','calibration_reference':str(cal),'process_exit_code':p.returncode,'wall_seconds':wall,'run':json.loads(rp.read_text()) if rp.exists() else None,'output_dir':str(out)}
(Path.cwd()/'MAIN_PROCESS.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'phase':result['phase'],'exit':p.returncode,'wall_seconds':wall,'run':result['run']},ensure_ascii=False))
if p.returncode: raise SystemExit(p.returncode)