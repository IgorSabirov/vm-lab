from __future__ import annotations
import argparse
import collections
import hashlib
import io
import contextlib
import json
import os
import platform
import resource
import time
from pathlib import Path
import numpy as np
import scipy
from .physical import (preflight,prepare_cases,tasks,workload,execute,aggregate,
                       canonical,digest,dump)

def environment():
    def read(p):
        try:return Path(p).read_text().strip()
        except OSError:return None
    with contextlib.redirect_stdout(io.StringIO()) as buf:np.show_config()
    return {'python':platform.python_version(),'platform':platform.platform(),'machine':platform.machine(),
      'numpy':np.__version__,'scipy':scipy.__version__,'cpu_count':os.cpu_count(),
      'affinity':sorted(os.sched_getaffinity(0)),'cpu_max':read('/sys/fs/cgroup/cpu.max'),
      'memory_max':read('/sys/fs/cgroup/memory.max'),'rlimit_as':list(resource.getrlimit(resource.RLIMIT_AS)),
      'blas_build':buf.getvalue(),'thread_environment':{k:os.environ.get(k) for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']},
      'actual_threads':len(list(Path('/proc/self/task').iterdir()))}

def calibration_tasks(ts):
    selected=[]
    for t in ts:
        yes=t['kind']=='spectral'
        if t['kind']=='cycle':
            yes=t['case']=='active_word' or (t['case']=='quiet_word' and t['N']==256 and t['res']==1) or (t['case']=='permuted_word' and t['N']==64 and t['res']==0 and t['route']=='coherent' and t['control']=='active')
        if t['kind']=='ramp':yes=t['duration'] in (.5,8.)
        if yes:selected.append(t)
    return selected

def forecast(m,ts,measurements,setup,finish):
    observed={r['task']['id']:r for r in measurements}
    terms=[]
    for t in ts:
        if t['id'] in observed: refs=[observed[t['id']]];mult=1.
        elif t['kind']=='cycle' and t['case']=='permuted_word':
            refs=[r for r in measurements if r['task']['kind']=='cycle' and r['task']['case']=='permuted_word'];mult=1.
        elif t['kind']=='cycle':
            refs=[r for r in measurements if r['task']['kind']=='cycle' and r['task']['case']=='active_word'
                  and all(r['task'][k]==t[k] for k in ['route','control','N','res'])]
            # Carry observed quiet/active cost ratio from the largest N, separately by control/route.
            qa=[r for r in measurements if r['task']['kind']=='cycle' and r['task']['N']==256 and r['task']['res']==1
                and all(r['task'][k]==t[k] for k in ['route','control'])]
            q=next(r['seconds'] for r in qa if r['task']['case']=='quiet_word')
            p=next(r['seconds'] for r in qa if r['task']['case']=='active_word')
            mult=q/p
        else:
            # Ramp ODE step count grows with duration; same N/accuracy/family.
            refs=[r for r in measurements if r['task']['kind']=='ramp' and all(r['task'][k]==t[k] for k in ['family','N','res'])]
            lo,hi=sorted(refs,key=lambda r:r['task']['duration'])
            f=(t['duration']-lo['task']['duration'])/(hi['task']['duration']-lo['task']['duration'])
            terms.append({'task_id':t['id'],'seconds':lo['seconds']*(1-f)+hi['seconds']*f,
                          'references':[lo['task']['id'],hi['task']['id']],'rule':'linear duration interpolation at fixed N/family/tolerance'})
            continue
        terms.append({'task_id':t['id'],'seconds':max(r['seconds'] for r in refs)*mult,
                      'references':[r['task']['id'] for r in refs],'multiplier':mult})
    report_cost=max(1.,finish)*len(ts)/len(measurements)
    expected=setup+sum(t['seconds'] for t in terms)+report_cost
    return {'status':'FORECAST_READY','manifest_digest':digest(m),'workload_digest':digest(ts),
      'expected_seconds':expected,'lower_seconds':max(.01,expected*.25),
      'upper_seconds':max(expected*2,expected+20),'hard_wall_seconds':m['limits']['hard_wall_seconds'],
      'setup_seconds':setup,'task_seconds':sum(t['seconds'] for t in terms),'report_allowance_seconds':report_cost,
      'range_reason':'Engineering interval: 0.25x lower catches gross early exit; upper max(2x,+20s) covers short-task I/O/solver variability. Not a confidence interval.',
      'formula':'setup + sum(actual task counts times same-dimension measured costs) + report allowance; per-task timing includes state/JSON writes',
      'terms':terms}

def run(mode,m,out,source_digest,gate_path=None):
    start=time.perf_counter();cpu=time.process_time();out=Path(out);out.mkdir(parents=True,exist_ok=True)
    check=preflight(m);dump(out/'PREFLIGHT.json',check)
    if not check['submit_allowed']: raise ValueError(check)
    env=environment();fingerprint=digest(env);dump(out/'ENVIRONMENT.json',{'environment':env,'fingerprint':fingerprint,
       'load_average':list(os.getloadavg()),'observed_epoch':time.time(),
       'available_memory_proc':Path('/proc/meminfo').read_text(),
       'free_disk_bytes':os.statvfs(out).f_bavail*os.statvfs(out).f_frsize})
    ts=tasks(m);dump(out/'WORKLOAD.json',workload(m));cases=prepare_cases(m)
    dump(out/'CASE_PREPARATION.json',[{k:v for k,v in c.items() if k!='parameters'} for c in cases])
    if mode=='main':
        gate=json.loads(Path(gate_path).read_text())
        assert gate['source_digest']==source_digest and gate['manifest_digest']==digest(m)
        assert gate['workload_digest']==digest(ts) and gate['environment_fingerprint']==fingerprint
        assert gate['status']=='TARGET_VM_CALIBRATION_PASS'
        assert gate['upper_seconds']<m['limits']['hard_wall_seconds']
        dump(out/'FROZEN_RUNTIME_GATE.json',gate)
    else:gate=None
    chosen=calibration_tasks(ts) if mode=='calibrate' else ts
    setup=time.perf_counter()-start;measurements=[];rows=[];resumed=0
    for t in chosen:
        t0=time.perf_counter();rp=out/'rows'/(t['id']+'.json');rp.parent.mkdir(exist_ok=True)
        if rp.exists():
            r=json.loads(rp.read_text());assert r['manifest_digest']==digest(m) and r['source_digest']==source_digest
            for key in ['states_file']:
                if key in r:assert hashlib.sha256((rp.parent/r[key]).read_bytes()).hexdigest()==r['states_sha256']
            resumed+=1
        else:
            r=execute(m,cases,t,rp.parent);r['manifest_digest']=digest(m);r['source_digest']=source_digest;dump(rp,r)
        rows.append(r)
        measurements.append({'task':t,'seconds':time.perf_counter()-t0,'technical_pass':bool(r['technical_pass']),
                             'physical_status':r['physical_status'],'resumed':rp.exists() and resumed>0})
        dump(out/'CHECKPOINT.json',{'mode':mode,'source_digest':source_digest,'manifest_digest':digest(m),
             'completed':len(rows),'planned':len(chosen),'last_task':t['id'],'resumed_tasks':resumed})
        if len(rows)%10==0:print(f'{mode}: {len(rows)}/{len(chosen)}',flush=True)
        bytes_used=sum(p.stat().st_size for p in out.rglob('*') if p.is_file())
        if bytes_used>m['limits']['disk_mib']*1024**2:raise RuntimeError('disk limit exceeded; checkpoints preserved')
    task_end=time.perf_counter()
    if mode=='calibrate':
        result={'mode':mode,'technical_pass':all(r['technical_pass'] for r in rows),
          'source_digest':source_digest,'manifest_digest':digest(m),'workload_digest':digest(ts),
          'environment_fingerprint':fingerprint,'measurements':measurements,'setup_seconds':setup}
        dump(out/'CALIBRATION.json',result)
        f=forecast(m,ts,measurements,setup,time.perf_counter()-task_end)
        f.update({'source_digest':source_digest,'environment_fingerprint':fingerprint,
            'status':'TARGET_VM_CALIBRATION_PASS' if result['technical_pass'] else 'CALIBRATION_TECHNICAL_FAIL'})
        dump(out/'FORECAST.json',f)
    else:
        result=aggregate(m,rows);result.update({'source_digest':source_digest,'manifest_digest':digest(m)})
        dump(out/'RESULTS.json',result)
        dump(out/'ROW_INDEX.json',[{'task':r['task'],'technical_pass':r['technical_pass'],
           'physical_status':r['physical_status'],**{k:r[k] for k in ['p_load','p_after','p_final','p_bath_final','P_leak_final','checks','work','resource'] if k in r}} for r in rows])
    dump(out/'TASK_TIMINGS.json',measurements)
    index={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file()}
    dump(out/'OUTPUT_MANIFEST.json',index)
    elapsed=time.perf_counter()-start
    process={'mode':mode,'source_digest':source_digest,'manifest_digest':digest(m),'environment_fingerprint':fingerprint,
      'wall_seconds':elapsed,'cpu_seconds':time.process_time()-cpu,'setup_seconds':setup,
      'task_seconds':sum(r['seconds'] for r in measurements),'finish_seconds':time.perf_counter()-task_end,
      'max_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
      'output_bytes':sum(p.stat().st_size for p in out.rglob('*') if p.is_file()),
      'completed':len(rows),'planned':len(chosen),'resumed':resumed,'technical_pass':result['technical_pass'],
      'runtime_gate':'CALIBRATION' if gate is None else ('PASS' if gate['lower_seconds']<=elapsed<=gate['upper_seconds'] and resumed==0 else 'REVIEW_REQUIRED')}
    dump(out/'PROCESS.json',process)
    print(json.dumps(process),flush=True)
    return 0 if result['technical_pass'] else 3

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--manifest',required=True);ap.add_argument('--outdir',required=True)
    ap.add_argument('--mode',choices=['preflight','calibrate','main'],default='preflight')
    ap.add_argument('--source-digest',default='LOCAL_TEST_ONLY');ap.add_argument('--gate')
    args=ap.parse_args();m=json.loads(Path(args.manifest).read_text())
    if args.mode=='preflight':
        r=preflight(m);dump(Path(args.outdir)/'PREFLIGHT.json',r);print(json.dumps(r));return 0 if r['submit_allowed'] else 2
    return run(args.mode,m,args.outdir,args.source_digest,args.gate)

if __name__=='__main__':raise SystemExit(main())
