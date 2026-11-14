"""Single explicit S0-N1 request; serial stages, published admission, hard caps."""
import argparse,json,math,os,resource,signal,subprocess,sys,time,traceback
from pathlib import Path
import common as c
FACTOR={'R_ENV':1.0,'R1':1.6,'R2':2.0,'R3':1.1,'R4':1.15,'R5':1.1,'R6':1.15,'R7':1.8,'R8':2.2,'R_NET_AMAX8':0.45}
def append(root,event):
 with (root/'LEDGER.jsonl').open('a') as f:f.write(json.dumps({'utc':c.now(),**event},allow_nan=False)+'\n');f.flush();os.fsync(f.fileno())
def events(root):return [json.loads(s) for s in (root/'LEDGER.jsonl').read_text().splitlines()] if (root/'LEDGER.jsonl').exists() else []
def spent(root):return sum(e['wall_seconds'] for e in events(root) if e.get('kind')=='PROCESS')
def manifest(root):
 files={str(p.relative_to(root)):c.digest(p) for p in sorted(root.rglob('*')) if p.is_file() and p.name not in ('ARTIFACTS.json','ARTIFACTS_SHA256.json')}
 c.write(root/'ARTIFACTS.json',{'files':files,'scientific_acceptance':False});c.write(root/'ARTIFACTS_SHA256.json',c.digest(root/'ARTIFACTS.json'))
def publish(root):
 if c.git('branch','--show-current')!=c.BRANCH:raise RuntimeError('Wrong publication branch')
 rel=str(root.relative_to(c.REPO));c.git('add','--',rel)
 staged=c.git('diff','--cached','--name-only').splitlines()
 if any(not p.startswith(rel+'/') for p in staged):raise RuntimeError('Unrelated staged files')
 if staged:c.git('commit','-m','Record S0-N1 execution evidence');c.git('push','origin','HEAD:refs/heads/'+c.BRANCH)
 remote=c.git('ls-remote','origin','refs/heads/'+c.BRANCH).split()[0]
 if remote!=c.git('rev-parse','HEAD'):raise RuntimeError('Publication not confirmed at current HEAD')
 return remote

def preflight(root,up,require_committed=True):
 sys.path.insert(0,str(up))
 from primat.config import PRIMATConfig,DEFAULT_PARAMS
 from primat.weak_rates.cache import weak_rate_fingerprint,thermal_fingerprint
 from primat.cache_utils import fingerprint_hash,resolve_cache_file
 c.check_upstream(up)
 pre=c.read(c.PKG/'N1_PREREGISTRATION.json');matrix=c.read(c.PKG/'RUN_MATRIX.json')
 if not pre['execution_enabled'] or not matrix['execution_enabled']:raise RuntimeError('Execution disabled')
 if pre['run_matrix']!=matrix['runs'] or pre['numerical_budget']!=matrix['numerical_budget']:raise RuntimeError('Matrix/preregistration diverge')
 ids=['CACHE_BG2000','CACHE_BG4000','CACHE_BG8000','PROBE',*FACTOR]
 configs={};fps={}
 for rid in ids:
  row=c.row_for(rid);group=row['cache_group'];params=c.config_for(rid,root/'caches'/group);cfg=PRIMATConfig(params)
  c.validate_resolved({k:getattr(cfg,k) for k in DEFAULT_PARAMS},rid)
  configs[rid]={**params,'cache_dir':'N1_CACHE/'+group}
  weak=weak_rate_fingerprint(cfg);thermal=thermal_fingerprint(cfg);wh=fingerprint_hash(weak);th=fingerprint_hash(thermal)
  if th!='cfdb4d324bb5651f':raise RuntimeError('Thermal fingerprint mismatch')
  if group=='BG2000' and wh!='7e3af87bd0404e0a':raise RuntimeError('Baseline typed fingerprint mismatch')
  if group in fps and fps[group]['weak_hash']!=wh:raise RuntimeError('One-factor controls changed cache unexpectedly')
  fps[group]={'weak':weak,'thermal':thermal,'weak_hash':wh,'thermal_hash':th}
  for name,sha in [('nTOp_thermal_'+th+'.txt','e3a8b6782393df73a9140e05bd3941ff135af2c9')]+([('nTOp_'+wh+'.txt','f5111a85112e94a237ed73f28ef860876ee0f8ed')] if group=='BG2000' else []):
   if c.digest(resolve_cache_file(cfg,'weak',name))['git_blob_sha']!=sha:raise RuntimeError('Upstream cache mismatch')
 source=c.git('rev-parse','HEAD');files={}
 inputs=[p for p in c.PKG.iterdir() if p.is_file() and p.name!='.gitignore']+[c.REPO/'.github/workflows/s0-n1-execute.yml']+[c.BASE/n for n in ['RESULT.json','RAW_SOLVER.npz','TRACE.json','S0_EXECUTION_MANIFEST.json']]
 for p in inputs:
  rel=str(p.relative_to(c.REPO));files[rel]=c.digest(p)
  if require_committed and subprocess.check_output(['git','-C',str(c.REPO),'show',source+':'+rel])!=p.read_bytes():raise RuntimeError('Uncommitted input: '+rel)
 c.write(root/'SOURCE_FREEZE.json',{'commit':source,'design_commit':c.DESIGN,'files':files,'scientific_acceptance':False})
 c.write(root/'RESOLVED_CONFIGS.json',configs);c.write(root/'CACHE_PREFLIGHT.json',fps)
 c.write(root/'N1_PREREGISTRATION.json',pre);c.write(root/'RUN_MATRIX.json',matrix)
 c.write(root/'ENVIRONMENT.json',c.env())
 return ids

def validate_environment(root):
 import numpy,scipy,threadpoolctl
 e=c.env()
 c.write(root/'ENVIRONMENT_CHECK.json',{'actual':e,'baseline':c.read(c.BASE/'S0_EXECUTION_MANIFEST.json')['environment']})
 if (e['python'],e['numpy'],e['scipy'],e['threadpoolctl'])!=('3.12.16','2.3.5','1.17.0','3.6.0'):raise RuntimeError('Pinned dependency mismatch')
 old=c.read(c.BASE/'S0_EXECUTION_MANIFEST.json')['environment']
 def signature(pools):return sorted((p['user_api'],p['internal_api'],p['version'],p['architecture'],p['num_threads']) for p in pools)
 if any(p['num_threads']!=1 or p['internal_api']!='openblas' or p['version']!='0.3.30' for p in e['threadpools']):raise RuntimeError('Unexpected target BLAS implementation/version/threads')
 c.write(root/'TARGET_ENVIRONMENT.json',{'signature':c.environment_signature(e),'historical_R0_signature_matches':signature(e['threadpools'])==signature(old['threadpools']),'anchor':'R_ENV','authorization':'Owner instructed launch after R_ENV proposal'})

def process(root,up,rid,request,controller_start):
 c.verify_freeze(root)
 if any(e.get('run_id')==rid for e in events(root)):raise RuntimeError('Duplicate stage forbidden')
 remaining=request['package_cap_seconds']-max(spent(root),time.monotonic()-controller_start)
 cap=min(request['preparation_cap_seconds'] if rid.startswith('CACHE_') or rid=='PROBE' else request['process_cap_seconds'],remaining)
 if cap<=0:raise RuntimeError('Aggregate package budget exhausted')
 procdir=root/'process';procdir.mkdir(exist_ok=True);before={'utc':c.now(),'run_id':rid,'cap_seconds':cap,'memory_bytes':4*1024**3,'remaining_package_seconds':remaining}
 c.write(procdir/(rid+'.before.json'),before);append(root,{'kind':'START','run_id':rid,'cap_seconds':cap})
 def limits():
  resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3));resource.setrlimit(resource.RLIMIT_FSIZE,(128*1024**2,128*1024**2));resource.setrlimit(resource.RLIMIT_CPU,(math.ceil(cap),math.ceil(cap)+1))
 start=time.monotonic();cpu0=resource.getrusage(resource.RUSAGE_CHILDREN);reason=None;peak=0
 with (procdir/(rid+'.stdout.txt')).open('w') as out,(procdir/(rid+'.stderr.txt')).open('w') as err:
  proc=subprocess.Popen([sys.executable,str(c.PKG/'worker.py'),'--upstream',str(up),'--root',str(root),'--run-id',rid],stdout=out,stderr=err,start_new_session=True,preexec_fn=limits)
  while proc.poll() is None:
   elapsed=time.monotonic()-start
   try:
    for line in Path('/proc/'+str(proc.pid)+'/status').read_text().splitlines():
     if line.startswith(('VmRSS:','VmHWM:')):peak=max(peak,int(line.split()[1]))
   except FileNotFoundError:pass
   size=sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
   if elapsed>cap or size>2*1024**3:
    reason='WALL_CAP' if elapsed>cap else 'DISK_CAP';os.killpg(proc.pid,signal.SIGKILL);proc.wait();break
   time.sleep(.4)
 cpu1=resource.getrusage(resource.RUSAGE_CHILDREN)
 receipt={'kind':'PROCESS','run_id':rid,'exit_code':proc.returncode,'wall_seconds':time.monotonic()-start,'cpu_seconds':cpu1.ru_utime+cpu1.ru_stime-cpu0.ru_utime-cpu0.ru_stime,'peak_rss_mib':peak/1024,'stop_reason':reason,'status':'COMPLETED' if proc.returncode==0 else 'ENGINEERING_FAIL'}
 c.write(procdir/(rid+'.after.json'),receipt);append(root,receipt)
 if proc.returncode!=0:raise RuntimeError('Stage failed: '+rid+'; preserved logs and completed eras')
 return receipt

def forecast(root):
 probe=c.read(root/'runs/PROBE/RESULT.json');old=c.read(c.BASE/'RESULT.json')
 base=sum(p['solver_seconds']*old['eras'][i]['nfev']/p['nfev'] for i,p in enumerate(probe['eras']))
 setup=probe['timing']['initialization_seconds']+10
 central={rid:base*f+setup for rid,f in FACTOR.items()}
 return {'scope':'Ten strict solves including matched-environment R_ENV; preparation/probe already charged separately','per_run_central':central,'seconds':{'low':.5*sum(central.values()),'central':sum(central.values()),'high':1.8*sum(central.values())},'preparation_seconds_used':spent(root),'factors':FACTOR,'target_probe_per_era_seconds':[p['solver_seconds'] for p in probe['eras']],
  'method':'Measured target-worker time per nfev times R0 strict nfev; declared refinement factors by stratum plus largest-grid initialization/export allowance. Envelope 0.5-1.8 is engineering judgment, not a confidence interval or proven complexity law.','limitations':'Adaptive work and Jacobian counts unknown under refinement; cap bounds overrun. No thresholds/configs change after results.'}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--upstream',required=True);ap.add_argument('--static-check-only',action='store_true');a=ap.parse_args();up=Path(a.upstream).resolve()
 if a.static_check_only:
  import tempfile
  with tempfile.TemporaryDirectory() as d:preflight(Path(d),up,False)
  print('Static configuration/fingerprint checks PASS; no solver executed');return 0
 req=c.read(c.PKG/'RUN_REQUEST.json')
 if os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('GITHUB_REPOSITORY')!='IgorSabirov/vm-lab' or os.environ.get('GITHUB_REF')!='refs/heads/'+c.BRANCH or os.environ.get('GITHUB_RUN_ATTEMPT')!='1':raise RuntimeError('Wrong executor/branch or forbidden retry')
 if req['id']!='S0_N1_GHA_20261114_r3' or req['package_cap_seconds']!=14400 or req['process_cap_seconds']!=2400:raise RuntimeError('Unexpected request')
 if c.git('rev-parse','HEAD')!=os.environ['GITHUB_SHA']:raise RuntimeError('Trigger source mismatch')
 c.git('merge-base','--is-ancestor',c.DESIGN,'HEAD');root=c.PKG/'results'/req['id']
 if root.exists():raise RuntimeError('Existing request; no duplicate run')
 root.mkdir(parents=True);start=time.monotonic();status=1
 try:
  validate_environment(root);preflight(root,up);append(root,{'kind':'AUTHORIZATION','request':req,'workflow_url':'https://github.com/IgorSabirov/vm-lab/actions/runs/'+os.environ['GITHUB_RUN_ID']})
  for rid in ['CACHE_BG2000','CACHE_BG4000','CACHE_BG8000']:process(root,up,rid,req,start)
  groups={g:c.read(root/'runs'/('CACHE_'+g)/'RESULT.json') for g in ('BG2000','BG4000','BG8000')}
  c.write(root/'CACHE_FREEZE.json',{'groups':groups,'frozen_utc':c.now(),'scientific_acceptance':False})
  for f in (root/'caches').rglob('*'):
   if f.is_file():f.chmod(0o444)
  process(root,up,'PROBE',req,start)
  prediction=forecast(root);c.write(root/'FORECAST.json',prediction);manifest(root);forecast_commit=publish(root)
  if prediction['seconds']['high']+max(spent(root),time.monotonic()-start)>req['package_cap_seconds'] or max(prediction['per_run_central'].values())*1.8>req['process_cap_seconds']:raise RuntimeError('Target forecast exceeds reviewed caps; production not admitted')
  c.write(root/'ADMISSION.json',{'utc':c.now(),'authorization':req['user_authorization'],'forecast_commit':forecast_commit,'forecast_sha256':c.digest(root/'FORECAST.json')['sha256'],'package_cap_seconds':req['package_cap_seconds'],'per_run_cap_seconds':req['process_cap_seconds'],'scientific_acceptance':False});manifest(root);publish(root)
  for rid in FACTOR:
   process(root,up,rid,req,start);manifest(root);publish(root)
  import verify
  outcome=verify.analyze(root)
  c.write(root/'SUMMARY.json',{'status':'ENGINEERING_PASS','numerical_status':outcome['status'],'stability_status':outcome['stability_status'],'cache_status':outcome['cache_status'],'executed_strict_runs':list(FACTOR),'R0':'IMMUTABLE_HISTORICAL_REFERENCE','primary_anchor':'R_ENV','process_seconds':spent(root),'controller_seconds_before_final_publication':time.monotonic()-start,'forecast':prediction,'strict_solve_wall_seconds':sum(e['wall_seconds'] for e in events(root) if e.get('kind')=='PROCESS' and e.get('run_id') in FACTOR),'runtime_review':{'forecast_central_seconds':prediction['seconds']['central'],'actual_strict_seconds':sum(e['wall_seconds'] for e in events(root) if e.get('kind')=='PROCESS' and e.get('run_id') in FACTOR),'note':'Preparation/probe charged separately in process_seconds. Queue, setup and publication distinguished from worker wall time. Any out-of-range runtime requires engineering review; it is not a physics verdict.'},'scientific_acceptance':False})
  status=0
 except Exception as exc:
  c.write(root/'EXECUTION_ERROR.json',{'utc':c.now(),'type':type(exc).__name__,'error':str(exc),'traceback':traceback.format_exc(),'scientific_acceptance':False});traceback.print_exc()
  if not (root/'SUMMARY.json').exists():c.write(root/'SUMMARY.json',{'status':'ENGINEERING_FAIL','numerical_status':'NOT_EVALUATED','error':str(exc),'completed_processes':[e['run_id'] for e in events(root) if e.get('status')=='COMPLETED'],'scientific_acceptance':False})
 finally:manifest(root);publish(root)
 return status
if __name__=='__main__':raise SystemExit(main())
