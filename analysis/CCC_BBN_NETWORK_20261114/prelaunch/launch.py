"""Bounded single-process launcher; package ledger prevents cap splitting."""
import argparse
import datetime
import json
import os
from pathlib import Path
import platform
import resource
import shutil
import signal
import subprocess
import sys
import time


def main():
    p = argparse.ArgumentParser()
    for k in ('upstream','config','cache','out','ledger','source-commit'):
        p.add_argument('--'+k, required=True)
    p.add_argument('--estimate',type=float,required=True)
    p.add_argument('--lower',type=float,required=True)
    p.add_argument('--upper',type=float,required=True)
    p.add_argument('--basis',required=True)
    p.add_argument('--cap',type=float,default=240)
    p.add_argument('--mode',default='S0')
    p.add_argument('--alpha',default='0')
    p.add_argument('--f0',default='3.66')
    a=p.parse_args()
    repo=Path(__file__).resolve().parents[3]
    source_files=[Path(__file__).resolve(),Path(__file__).with_name('run.py').resolve(),Path(__file__).with_name('s1_adapter.py').resolve(),Path(a.config).resolve()]
    for file in source_files:
        recorded=subprocess.check_output(['git','-C',str(repo),'show',a.source_commit+':'+str(file.relative_to(repo))])
        if recorded!=file.read_bytes(): raise RuntimeError('Execution source differs from frozen GitHub commit: '+str(file))
    out=Path(a.out).resolve(); ledger=Path(a.ledger).resolve()
    records=json.loads(ledger.read_text()) if ledger.exists() else []
    used=sum(r['wall_seconds'] for r in records)
    cap=min(a.cap,600-used)
    if a.upper>cap or cap<=0: raise RuntimeError('Insufficient package budget; reevaluate route before execution')
    if out.exists(): raise RuntimeError('No overwrite/retry of existing run')
    out.parent.mkdir(parents=True,exist_ok=True)
    prefix=out.parent/(out.name+'_PROCESS')
    env=os.environ.copy()
    for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
        env[k]='1'
    env['PYTHONDONTWRITEBYTECODE']='1'
    command=[sys.executable,str(Path(__file__).with_name('run.py')),'--upstream',a.upstream,'--config',a.config,'--cache',a.cache,'--out',str(out),'--mode',a.mode,'--alpha='+a.alpha,'--f0',a.f0]
    def limits():
        resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
        resource.setrlimit(resource.RLIMIT_FSIZE,(128*1024**2,128*1024**2))
        resource.setrlimit(resource.RLIMIT_CPU,(int(cap)+1,int(cap)+2))
    before={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_commit':a.source_commit,
            'command':command,'forecast':{'central':a.estimate,'lower':a.lower,'upper':a.upper,'basis':a.basis},
            'limits':{'wall_seconds':cap,'package_seconds':600,'used_seconds':used,'address_space_bytes':4*1024**3,'individual_file_bytes':128*1024**2,'output_tree_bytes':512*1024**2},
            'machine':{'platform':platform.platform(),'affinity':sorted(os.sched_getaffinity(0)),
                       'cpuinfo':Path('/proc/cpuinfo').read_text().split('\n\n')[0],
                       'memory':Path('/proc/meminfo').read_text(),'loadavg':list(os.getloadavg()),
                       'cgroup_cpu_quota':None,'cgroup_memory_limit':None,'cgroup_reason':'quota files not exposed in this container',
                       'disk_free':shutil.disk_usage(out.parent).free},
            'threads':{k:env[k] for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')},
            'checkpoint':'Each completed run retained; no solver checkpoint or automatic retry',
            'resume':'New run only with explicit revised manifest; completed runs never repeated for report repair'}
    prefix.with_suffix('.before.json').write_text(json.dumps(before,indent=2)+'\n')
    t=time.monotonic(); cpu0=resource.getrusage(resource.RUSAGE_CHILDREN)
    reason=None
    with prefix.with_suffix('.stdout.txt').open('w') as stdout, prefix.with_suffix('.stderr.txt').open('w') as stderr:
        proc=subprocess.Popen(command,env=env,stdout=stdout,stderr=stderr,start_new_session=True,preexec_fn=limits)
        while proc.poll() is None:
            size=sum(f.stat().st_size for f in out.rglob('*') if f.is_file()) if out.exists() else 0
            if time.monotonic()-t>cap or size>512*1024**2:
                reason='TIME_CAP' if time.monotonic()-t>cap else 'DISK_CAP'
                os.killpg(proc.pid,signal.SIGKILL); proc.wait(); break
            time.sleep(.2)
    elapsed=time.monotonic()-t; cpu1=resource.getrusage(resource.RUSAGE_CHILDREN)
    receipt={'run':out.name,'source_commit':a.source_commit,'exit_code':proc.returncode,'stop_reason':reason,
             'wall_seconds':elapsed,'cpu_seconds':cpu1.ru_utime+cpu1.ru_stime-cpu0.ru_utime-cpu0.ru_stime,
             'forecast':before['forecast'],'runtime_status':'FORECAST_IN_RANGE' if a.lower<=elapsed<=a.upper else 'REVIEW_REQUIRED',
             'execution_status':'COMPLETED' if proc.returncode==0 else 'FAILED',
             'output_bytes':sum(f.stat().st_size for f in out.rglob('*') if f.is_file()) if out.exists() else 0}
    prefix.with_suffix('.after.json').write_text(json.dumps(receipt,indent=2)+'\n')
    ledger.parent.mkdir(parents=True,exist_ok=True); ledger.write_text(json.dumps(records+[receipt],indent=2)+'\n')
    print(json.dumps(receipt),flush=True)
    sys.exit(proc.returncode or 0)


if __name__=='__main__': main()
