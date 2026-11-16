"""Execute precisely eight preregistered full integrations; preserve failures.

Publication and shared ledger CAS are performed by the calling orchestrator.
This runner requires their hashed admission receipt before doing science.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback

HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'infra/autonomy/admit.py').is_file())
PARENT=HERE.parent/'results/S3_DD_RESPONSE_20261115_r1'
sys.path.insert(0,str(ROOT/'analysis/CCC_BBN_NETWORK_20261114/s3_standard/linx_dd_adapter_20261115/full_run_20261115'))
import bounded
sys.path.insert(0,str(ROOT/'infra/autonomy'))
from execution_policy import validate, digest as plan_digest

def read(p): return json.loads(Path(p).read_text())
def write(p,d): Path(p).write_text(json.dumps(d,indent=2,allow_nan=False)+'\n')
def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def now(): return datetime.now(timezone.utc).isoformat()

def aggregate(results):
    parent=read(PARENT/'SUMMARY.json')
    channels=['ddHe3n','ddtp'];outputs={}
    grid=[-1.,-.8,-.5,-.3,0.,.3,.5,.8,1.]
    for obs,old in parent['results'].items():
        derivatives={ch:dict(old['derivatives'][ch]) for ch in channels}
        for ch in channels:
            for h in [.25,.125]:
                suffix=str(h).replace('.','_')
                plus=results[f'{ch}_plus_{suffix}']['observables'][obs]
                minus=results[f'{ch}_minus_{suffix}']['observables'][obs]
                derivatives[ch][str(h)]=(math.log(plus)-math.log(minus))/(2*h)
        step={};rich={};order={}
        for ch in channels:
            a=derivatives[ch];step[ch]={};rich[ch]={}
            for big,small in [(.5,.25),(.25,.125)]:
                x,y=a[str(big)],a[str(small)];scale=max(abs(x),abs(y))
                delta=None if scale<1e-8 else abs(x-y)/scale
                step[ch][f'{big}_to_{small}']={'relative_discrepancy':delta,
                    'status':'NEAR_ZERO_RESPONSE' if delta is None else 'STEP_CONVERGED' if delta<.01 else 'STEP_NOT_CONVERGED'}
                rich[ch][f'{big}_to_{small}']=(4*y-x)/3
            d1=a['0.5']-a['0.25'];d2=a['0.25']-a['0.125']
            order[ch]={'signed_differences':[d1,d2],
                'absolute_ratio':abs(d1/d2) if d2 else None,
                'p':math.log2(abs(d1/d2)) if d1 and d2 else None,
                'status':'DIAGNOSTIC_ONLY_NO_SOLVER_NOISE_BOUND',
                'environment_note':'h=0.5 is historical hosted CPU; 0.25 and 0.125 are this local CPU. Same library lock; no extra bridge integration.'}
        by_h={}
        for h in ['0.25','0.125']:
            v=[derivatives[ch][h] for ch in channels];norm=sum(x*x for x in v)
            k=None if norm<=1e-30 else 2*v[0]*v[1]/norm
            by_h[h]={'a':v,'independent_quadratic_form':norm,'kappa':k,
                'correlated_quadratic_form':{str(r):norm+2*r*v[0]*v[1] for r in grid},
                'sigma_ratio':{str(r):None if k is None else math.sqrt(max(0,1+k*r)) for r in grid}}
        rich_vectors={}
        for pair in ['0.5_to_0.25','0.25_to_0.125']:
            v=[rich[ch][pair] for ch in channels];norm=sum(x*x for x in v)
            rich_vectors[pair]={'a':v,'kappa':None if norm<=1e-30 else 2*v[0]*v[1]/norm,
                'status':'CONDITIONAL_H_SQUARED_EXTRAPOLATION'}
        expected=old['directional_hypothesis'].get('expected')
        signs={ch:'positive' if derivatives[ch]['0.125']>0 else 'negative' if derivatives[ch]['0.125']<0 else 'zero' for ch in channels}
        outputs[obs]={'baseline_observable':old['baseline_observable'],'derivatives':derivatives,
            'step_diagnostics':step,'order_diagnostics':order,'by_step':by_h,
            'richardson':rich_vectors,'original_directional_hypothesis':expected,
            'signs_h0_125':signs,'directional_status':'NO_PREREGISTERED_SIGN' if expected is None else 'MATCH' if signs==expected else 'DEVIATES_FROM_DIRECTIONAL_HYPOTHESIS'}
    passed=all(v['step_diagnostics'][ch]['0.25_to_0.125']['status']=='STEP_CONVERGED' for v in outputs.values() for ch in channels)
    return {'id':'S3_DD_CONVERGENCE_20261116_r1','status':'COMPUTE_COMPLETE','new_integrations':8,
        'parent_result_commit':'1ce668ca5bd1d79a128f0c1f761c1ff93ebe3464','results':outputs,
        'numerical_step_gate':'ALL_EIGHT_COMPONENTS_PASS' if passed else 'PARTIAL_OR_FAILED',
        'scientific_acceptance':False,'rho_status':'UNMEASURED_PARAMETER',
        'propagation_status':'FIRST_ORDER_DELTA_METHOD_ONLY',
        'solver_error_floor':'NOT_MEASURED','causal_reaction_fluxes':'NOT_MEASURED'}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True)
    ap.add_argument('--admission',type=Path,required=True);args=ap.parse_args()
    plan=read(HERE/'EXECUTION_PLAN.json');receipt=read(args.admission)
    report=validate(plan,{'memory_bytes':4*1024**3,'output_bytes':2*1024**3},root=ROOT)
    if receipt.get('admitted') is not True or receipt.get('source_sha')!=plan['source_commit'] or receipt.get('execution_plan_sha256')!=plan_digest(plan):
        raise ValueError('Admission/source/plan mismatch')
    if receipt.get('scientific_acceptance') is not False or not receipt.get('ledger_commit'):
        raise ValueError('Missing shared ledger evidence or incorrect scientific status')
    # Require the committed source tree byte-for-byte, with plan as the sole addition.
    for entry in read(HERE/'INPUT_MANIFEST.json')['files']:
        if digest(ROOT/entry['path'])!=entry['sha256']: raise ValueError('Changed input: '+entry['path'])
    adapter=ROOT/'analysis/CCC_BBN_NETWORK_20261114/s3_standard/linx_dd_adapter_20261115'
    for entry in read(adapter/'UPSTREAM.json')['files']:
        expected=read(adapter/'PATCH_RECEIPT.json')['patched_sha256'] if entry['path']=='linx/abundances.py' else entry['sha256']
        if digest(args.root/entry['path'])!=expected: raise ValueError('Changed LINX input: '+entry['path'])
    out=HERE/'results'/plan['package_id'];out.mkdir(parents=True,exist_ok=False)
    write(out/'ADMISSION.json',receipt);write(out/'EXECUTION_VALIDATION.json',report)
    background=PARENT/'baseline/background.npz';bgsha='e1289712d2c6701ad89269984721e468415a261b559f7f972893cf72324e11f3'
    if digest(background)!=bgsha: raise ValueError('Parent background mismatch')
    cpu_info=Path('/proc/cpuinfo').read_text()
    write(out/'ENVIRONMENT.json',{'python':sys.version,'platform':platform.platform(),
        'machine':platform.machine(),'cpu_model':next((x.split(':',1)[1].strip() for x in cpu_info.splitlines() if x.startswith('model name')),None),
        'cpu_affinity':sorted(os.sched_getaffinity(0)),'historical_runtime_is_transfer_estimate':True})
    started=time.monotonic();results={};conclusion='failure'
    try:
        for index,task in enumerate(plan['tasks']):
            name=task['id']
            command=[sys.executable,str(HERE/'worker.py'),'--role','perturb','--root',str(args.root.resolve()),
                '--out',str(out/name),'--admission',str(out/'ADMISSION.json'),'--source-sha',plan['source_commit'],
                '--background',str(background),'--background-sha256',bgsha,
                '--channel',task['channel'],'--q',str(task['q'])]
            print(json.dumps({'event':'integration_started','task':name,'utc':now()}),flush=True)
            env={k:v for k,v in os.environ.items() if not k.endswith('TOKEN')}
            limits={'wall_seconds':None,'memory_bytes':plan['budget']['memory_bytes']-128*1024**2,'output_bytes':plan['budget']['output_bytes']}
            guard=bounded.run(command,out/(name+'.log'),limits,env=env)
            if guard['exit_code'] or guard['stop']: raise RuntimeError(name+' failed: '+json.dumps(guard))
            result=read(out/name/'RESULT.json');result['supervisor']=guard
            write(out/name/'RESULT.json',result);results[name]=result
            print(json.dumps({'event':'integration_completed','task':name,'wall_seconds':guard['wall_seconds'],'observables':result['observables']}),flush=True)
            if index==0:
                forecast=7*guard['wall_seconds']
                write(out/'LOCAL_FORECAST.json',{'measured_first_full_integration_seconds':guard['wall_seconds'],
                    'remaining_integrations':7,'remaining_forecast_seconds':forecast,'remaining_compute_cap_seconds':None,
                    'recorded_before_remaining_integrations':True,'duration_limit_seconds':None})
        summary=aggregate(results);summary.update(source_sha=plan['source_commit'],
            execution_plan_sha256=plan_digest(plan),wall_seconds_compute_and_analysis=time.monotonic()-started,
            integration_supervisor_wall_seconds=sum(r['supervisor']['wall_seconds'] for r in results.values()),
            completed_utc=now())
        write(out/'SUMMARY.json',summary);conclusion='success'
        print(json.dumps({'event':'complete','numerical_step_gate':summary['numerical_step_gate'],'wall_seconds':summary['wall_seconds_compute_and_analysis']}),flush=True)
    except BaseException:
        write(out/'FAILURE.json',{'status':'FAIL','traceback':traceback.format_exc(),'completed_integrations':len(results),
            'scientific_acceptance':False,'automatic_retry':False,'utc':now()})
        raise
    finally:
        files=[{'path':str(p.relative_to(out)),'sha256':digest(p),'bytes':p.stat().st_size} for p in sorted(out.rglob('*')) if p.is_file() and p.name!='ARTIFACTS.json']
        write(out/'ARTIFACTS.json',{'id':plan['package_id'],'source_sha':plan['source_commit'],'conclusion':conclusion,'files':files})

if __name__=='__main__': main()
