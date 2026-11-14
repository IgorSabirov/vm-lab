"""Pinned inputs and lossless receipts for S0-N1; no numerical work here."""
import hashlib,json,os,platform,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone
PKG=Path(__file__).resolve().parent
REPO=PKG.parents[2]
PIN='6f7e5680614fb119d65a6c9c65a292240b27c61e'
DESIGN='81e05d4c61b2d14ee7f404707c1bdfb35197ba79'
BRANCH='science/ccc-bbn-pipeline-20261114'
BASE=PKG.parent/'p2_fullnet/results/P2_GHA_20261114_r1/runs/COLD'
AXES=('numerical_precision','rate_grid_npts','sampling_temperature_per_decade')
def read(p):return json.loads(Path(p).read_text())
def write(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False,default=lambda v:v.item())+'\n')
def digest(p):
 b=Path(p).read_bytes();return {'sha256':hashlib.sha256(b).hexdigest(),'git_blob_sha':hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest(),'bytes':len(b)}
def now():return datetime.now(timezone.utc).isoformat()
def git(*args):return subprocess.check_output(['git','-C',str(REPO),*map(str,args)],text=True).strip()
def snapshot(p):return {str(f.relative_to(p)):digest(f) for f in sorted(Path(p).rglob('*')) if f.is_file()}
PARENT_ROOT=PKG.parent/'s0_n1/results/S0_N1_GHA_20261114_r4'
REFERENCE_ROOT=PKG.parent/'s0_n1_followup/results/S0_N1_FOLLOWUP_20261114_r1'
def row_for(run_id):
 rows=read(PKG/'PLAN.json')['runs']
 if run_id=='PROBE':return {**rows[0],'id':'PROBE','numerical_precision':1e-6,'atol_scale':1.0}
 matches=[r for r in rows if r['id']==run_id]
 if len(matches)!=1:raise ValueError('Unknown follow-up run: '+run_id)
 return matches[0]
def config_for(run_id,cache):
 r=row_for(run_id);params=dict(read(PARENT_ROOT/'runs/R8/MANIFEST.json')['config'])
 for k in AXES:params[k]=r[k]
 params['cache_dir']=str(Path(cache).resolve())
 return params

def check_upstream(up):
 up=Path(up).resolve()
 def g(*a):return subprocess.check_output(['git','-C',str(up),*a],text=True).strip()
 if g('rev-parse','HEAD')!=PIN or g('status','--porcelain','--untracked-files=no'):raise RuntimeError('Unclean or unpinned PRIMAT')
 return g('rev-parse','HEAD^{tree}')
def env():
 import numpy,scipy,scipy.linalg,threadpoolctl
 return {'python':platform.python_version(),'numpy':numpy.__version__,'scipy':scipy.__version__,'threadpoolctl':threadpoolctl.__version__,
  'platform':platform.platform(),'machine':platform.machine(),'affinity':sorted(os.sched_getaffinity(0)),
  'threadpools':threadpoolctl.threadpool_info(),'cpuinfo':Path('/proc/cpuinfo').read_text().split('\n\n')[0],
  'meminfo':Path('/proc/meminfo').read_text(),'cgroup_cpu_max':Path('/sys/fs/cgroup/cpu.max').read_text().strip() if Path('/sys/fs/cgroup/cpu.max').exists() else None}
def verify_freeze(root):
 f=read(Path(root)/'SOURCE_FREEZE.json')
 for path,h in f['files'].items():
  if digest(REPO/path)!=h:raise RuntimeError('Frozen input changed: '+path)
 return f

def verify_artifacts(root):
 root=Path(root);receipt=read(root/'ARTIFACTS_SHA256.json')
 if digest(root/'ARTIFACTS.json')!=receipt:raise ValueError('Artifact manifest checksum mismatch')
 entries=read(root/'ARTIFACTS.json')['files']
 for path,identity in entries.items():
  if digest(root/path)!=identity:raise ValueError('Artifact mismatch: '+path)
 return len(entries)

def validate_resolved(resolved,run_id):
 baseline=read(BASE/'S0_EXECUTION_MANIFEST.json')['resolved_defaults']
 allowed=set(AXES)|{'cache_dir'}|({'amax'} if run_id=='R_NET_AMAX8' else set())
 for k,v in resolved.items():
  if k not in allowed and (type(v)!=type(baseline[k]) or v!=baseline[k]):raise RuntimeError('Non-matrix config changed: '+k)

def environment_signature(e):
 return {'python':e['python'],'numpy':e['numpy'],'scipy':e['scipy'],'threadpoolctl':e['threadpoolctl'],'machine':e['machine'],
  'blas':sorted([p['user_api'],p['internal_api'],p['version'],p['architecture'],p['num_threads']] for p in e['threadpools'])}
