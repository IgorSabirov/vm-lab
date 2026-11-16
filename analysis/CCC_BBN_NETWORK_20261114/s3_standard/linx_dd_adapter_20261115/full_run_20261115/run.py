"""One frozen package: reserve, target calibration, strict pair, publish. No retry."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import traceback

HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'infra/autonomy/admit.py').is_file())
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(HERE.parent/'identity'))
from infra.autonomy import admit, finish, execution_policy
from bounded import run as bounded
PACKAGE=json.loads((HERE/'PACKAGE.json').read_text())
OUT=HERE/'results'/PACKAGE['id']
REL=OUT.relative_to(ROOT)
REQUEST='analysis/CCC_BBN_NETWORK_20261114/pipeline/RUN_REQUEST.json'
CURRENT='analysis/CCC_BBN_NETWORK_20261114/pipeline/CURRENT.json'

def now():return datetime.now(timezone.utc).isoformat()
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def save(p,x):Path(p).parent.mkdir(parents=True,exist_ok=True);Path(p).write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def git(*args,cwd=ROOT):return subprocess.check_output(['git',*args],cwd=cwd,text=True).strip()
def publisher():return Path(os.environ['GITHUB_WORKSPACE'])
def validate_source():
    if os.environ['GITHUB_REPOSITORY']!='IgorSabirov/vm-lab' or os.environ['GITHUB_RUN_ATTEMPT']!='1':raise ValueError('Repository/retry forbidden')
    sha=os.environ['SOURCE_SHA'];request=read(publisher()/REQUEST)
    if not re.fullmatch('[0-9a-f]{40}',sha) or git('rev-parse','HEAD')!=sha:raise ValueError('Wrong source worktree')
    if request.get('source_commit')!=sha or request['id']!=PACKAGE['id'] or request.get('execution_enabled') is not True:raise ValueError('Request/source mismatch')
    if os.environ['GITHUB_REF_NAME']!=PACKAGE['publication_branch']:raise ValueError('Wrong branch')
    if git('diff','--name-only',sha):raise ValueError('Tracked source changed')
    for f in read(HERE/'INPUT_MANIFEST.json')['files']:
        if digest(ROOT/f['path'])!=f['sha256']:raise ValueError('Input changed: '+f['path'])
    return sha

def publish(phase):
    pub=publisher();branch=PACKAGE['publication_branch'];head=git('rev-parse','HEAD',cwd=pub)
    remote=git('ls-remote','origin','refs/heads/'+branch,cwd=pub).split()[0]
    if head!=remote:raise ValueError('Publication branch moved; preserve artifacts, no overwrite')
    shutil.copytree(OUT,pub/REL,dirs_exist_ok=True)
    state={'request':PACKAGE['id'],'status':phase,'source_sha':os.environ['SOURCE_SHA'],
           'workflow_run_id':int(os.environ['GITHUB_RUN_ID']),'scientific_acceptance':False,
           'admission':str(REL/'ADMISSION.json'),'updated_utc':now()}
    if (OUT/'SUMMARY.json').exists():
        summary=read(OUT/'SUMMARY.json')
        state.update(summary=str(REL/'SUMMARY.json'),summary_sha256=digest(OUT/'SUMMARY.json'),
                     artifact_manifest={'path':str(REL/'ARTIFACTS.json'),'sha256':digest(OUT/'ARTIFACTS.json')},
                     engineering_status=summary['engineering_status'],numerical_status=summary['numerical_status'],processes_exited=True)
    save(pub/CURRENT,state)
    subprocess.run(['git','add','-f',str(REL),CURRENT],cwd=pub,check=True)
    changed=git('diff','--cached','--name-only',cwd=pub).splitlines()
    if any(p!=CURRENT and not p.startswith(str(REL)+'/') for p in changed):raise ValueError('Publication would change source')
    if not changed:return head
    subprocess.run(['git','commit','-m',f"Publish {PACKAGE['id']} {phase}; preserve source and science status"],cwd=pub,check=True)
    commit=git('rev-parse','HEAD',cwd=pub)
    result=subprocess.run(['git','push','origin','HEAD:refs/heads/'+branch],cwd=pub)
    # Lost ACK is reconciled against this exact commit; computation is never repeated.
    if result.returncode and git('ls-remote','origin','refs/heads/'+branch,cwd=pub).split()[0]!=commit:
        raise ValueError('Publication failed; completed artifacts retained')
    return commit

def reserve():
    sha=validate_source();control=read(ROOT/'infra/autonomy/CONTROL.json')
    if not control['enabled'] or control['policy_version']!=PACKAGE['policy_version']:raise ValueError('Controller policy not deployed')
    if 'new_packages_per_rolling_24h' in control['limits']:raise ValueError('Stale quota policy')
    # Validate memory/output caps before any target-host numerical work.
    for key in ('memory_bytes','output_bytes'):
        if PACKAGE['budget'][key]>control['limits'][key]:raise ValueError('Resource cap exceeded')
    OUT.mkdir(parents=True,exist_ok=False)
    candidate={'id':PACKAGE['id'],'executor':'github_actions','started_utc':now(),'status':'RESERVED',
               'source_sha':sha,'execution_plan_sha256':execution_policy.digest(PACKAGE),
               'reservation_plan_kind':'frozen_two_phase_package_with_bounded_calibration',
               'workflow_run_id':int(os.environ['GITHUB_RUN_ID']),'budget':PACKAGE['budget'],
               'publication_branch':PACKAGE['publication_branch'],'scientific_acceptance':False}
    decision=admit.reserve(admit.read_ledger,admit.write_ledger,admit.actions_runs(),candidate,
                           datetime.now(timezone.utc),control['limits'],candidate['workflow_run_id'])
    rec={**decision,'execute':decision['admitted'],'phase':'CALIBRATION_RESERVED' if decision['admitted'] else 'NOT_ADMITTED',
         'source_sha':sha,'contract_sha256':digest(HERE/'BBN_IDENTITY_CONTRACT.json'),'observed_utc':now(),
         'ledger_and_actions_checked':True,'policy_version':PACKAGE['policy_version'],'route':'github_actions',
         'bounded_executor':True,'scientific_acceptance':False,'strict_execution_admitted':False}
    save(OUT/'ADMISSION.json',rec);save(OUT/'CALIBRATION_ADMISSION.json',rec)
    save(Path(os.environ['RUNNER_TEMP'])/'autonomy-budget.json',rec)
    with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('execute='+str(rec['execute']).lower()+'\n')
    publish(rec['phase'])

def child(role,out,admission,*,calibration=False,native=None):
    roots=Path(os.environ['RUNNER_TEMP'])/'linx-identity-roots'
    cmd=[sys.executable,str(HERE/'worker.py'),role,'--upstream',str(roots/('pristine' if role=='native_pristine' else 'override')),
         '--out',str(OUT/out),'--source-sha',os.environ['SOURCE_SHA'],'--admission',str(admission),'--execute']
    if calibration:cmd+=['--calibration']
    if native:cmd+=['--native-dir',str(OUT/native)]
    env={k:v for k,v in os.environ.items() if not k.endswith('TOKEN') and k not in ('GH_TOKEN','GITHUB_TOKEN')}
    limits={'wall_seconds':None,'memory_bytes':PACKAGE['budget']['memory_bytes']-128*1024**2,'output_bytes':PACKAGE['budget']['output_bytes']}
    result=bounded(cmd,OUT/(out+'.log'),limits,env=env)
    if result['exit_code']!=0 or result['stop']:raise ValueError(out+' process failed: '+json.dumps(result))
    return result

def calibrated_plan(measured):
    cal=read(HERE/'CALIBRATION_PLAN.json');estimate=max(cal['minimum_arm_forecast_seconds'],cal['strict_forecast_factor']*measured)
    evidence={'path':str((OUT/'CALIBRATION.json').relative_to(ROOT)),'sha256':digest(OUT/'CALIBRATION.json'),
              'executor':'github_actions','environment_reference':f"GitHub run {os.environ['GITHUB_RUN_ID']} ubuntu-24.04; CALIBRATION.json",
              'measured_seconds':measured}
    plan={'schema':'vm-lab-execution-plan-v1','package_id':PACKAGE['id'],'source_commit':os.environ['SOURCE_SHA'],
          'publication_branch':PACKAGE['publication_branch'],'executor':'github_actions','workload_kind':'independent_realizations',
          'checkpoint_policy':'not_required','parallel_sections':1,'scientific_acceptance':False,'automatic_retry':False,
          'input_manifest':{'path':str((HERE/'INPUT_MANIFEST.json').relative_to(ROOT)),'sha256':digest(HERE/'INPUT_MANIFEST.json')},
          'acceptance':{'path':str((HERE/'BBN_IDENTITY_CONTRACT.json').relative_to(ROOT)),'sha256':digest(HERE/'BBN_IDENTITY_CONTRACT.json')},
          'calibration':evidence,'budget':PACKAGE['budget'],
          'tasks':[{'id':x,'forecast_seconds':estimate,'process_seconds':None} for x in PACKAGE['strict_matrix']],
          'sections':[{'id':'full_pair','task_ids':PACKAGE['strict_matrix'],'compute_seconds':None,'setup_seconds':1500,
                       'verification_seconds':60,'publication_seconds':240,'wall_seconds':None,'memory_bytes':PACKAGE['budget']['memory_bytes']}],
          'calibration_accounting':'measured calibration is accounted once; setup is a forecast, not a deadline; one reservation'}
    execution_policy.validate(plan,read(ROOT/'infra/autonomy/CONTROL.json')['limits'],root=ROOT)
    return plan

def execute():
    validate_source();admission=read(OUT/'ADMISSION.json')
    if admission.get('phase')!='CALIBRATION_RESERVED' or not admission.get('execute'):raise ValueError('No calibration reservation')
    try:
        guard=child('native_pristine','calibration',OUT/'ADMISSION.json',calibration=True)
        result=read(OUT/'calibration/RESULT.json')
        save(OUT/'CALIBRATION.json',{'status':'COMPLETE','guard':guard,'result_sha256':digest(OUT/'calibration/RESULT.json'),
             'observed_utc':now(),'runner':os.environ.get('RUNNER_NAME'),'runner_os':os.environ.get('RUNNER_OS'),
             'python':sys.version,'versions':result['versions'],'source_sha':os.environ['SOURCE_SHA'],
             'calibration_only':True,'plan_sha256':digest(HERE/'CALIBRATION_PLAN.json')})
        plan=calibrated_plan(guard['wall_seconds']);save(OUT/'EXECUTION_PLAN.json',plan)
        admission.update(phase='STRICT_ADMITTED',strict_execution_admitted=True,observed_utc=now(),
             calibration_evidence=plan['calibration'],forecast_package_seconds=execution_policy.validate(plan,read(ROOT/'infra/autonomy/CONTROL.json')['limits'],root=ROOT)['forecast_seconds'],
             measured_execution_plan_sha256=execution_policy.digest(plan))
        save(OUT/'ADMISSION.json',admission);save(OUT/'STRICT_ADMISSION.json',admission)
        publish('STRICT_ADMITTED')
        child('native_pristine','native',OUT/'STRICT_ADMISSION.json')
        child('identical_override','override',OUT/'STRICT_ADMISSION.json',native='native')
        from verify_identity import compare
        n=read(OUT/'native/RESULT.json');o=read(OUT/'override/RESULT.json');c=read(HERE/'BBN_IDENTITY_CONTRACT.json')
        result=compare(n,o,c)
        result['checks']['published_contract_hash']=n['contract_sha256']==o['contract_sha256']==digest(HERE/'BBN_IDENTITY_CONTRACT.json')
        result['checks']['strict_not_calibration']=n.get('calibration_only') is False and o.get('calibration_only') is False
        result['engineering_status']='PASS' if all(result['checks'].values()) else 'FAIL'
        result.update(status='COMPLETE',id=PACKAGE['id'],source_sha=os.environ['SOURCE_SHA'],workflow_run_id=int(os.environ['GITHUB_RUN_ID']),
                      numerical_status='BBN_IMPLEMENTATION_IDENTITY_'+result['engineering_status'],processes_exited=True,
                      strict_arms_executed=['native_pristine','identical_override'],calibration_processes=1,scientific_acceptance=False)
        save(OUT/'SUMMARY.json',result)
        return 0 if result['engineering_status']=='PASS' else 1
    except Exception:
        save(OUT/'EXECUTION_FAILURE.json',{'status':'FAIL','traceback':traceback.format_exc(),'source_sha':os.environ['SOURCE_SHA'],'automatic_retry':False})
        raise

def finalize():
    if not (OUT/'CALIBRATION_ADMISSION.json').exists():return
    admission=read(OUT/'CALIBRATION_ADMISSION.json')
    if not admission.get('execute'):return
    if not (OUT/'SUMMARY.json').exists():
        save(OUT/'SUMMARY.json',{'id':PACKAGE['id'],'status':'COMPLETE','engineering_status':'FAIL','numerical_status':'NOT_EVALUATED',
             'source_sha':os.environ['SOURCE_SHA'],'workflow_run_id':int(os.environ['GITHUB_RUN_ID']),
             'failure':'Workflow did not complete both strict arms and verification; see logs/artifacts',
             'strict_arms_completed':[x for x in ('native','override') if (OUT/x/'RESULT.json').exists()],
             'processes_exited':True,'scientific_acceptance':False,'automatic_retry':False})
    files=[{'path':str(p.relative_to(OUT)),'sha256':digest(p),'bytes':p.stat().st_size} for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='ARTIFACTS.json']
    if sum(x['bytes'] for x in files)>PACKAGE['budget']['output_bytes']:raise ValueError('Output budget exceeded')
    save(OUT/'ARTIFACTS.json',{'source_sha':os.environ['SOURCE_SHA'],'package_id':PACKAGE['id'],'files':files})
    conclusion='success' if read(OUT/'SUMMARY.json')['engineering_status']=='PASS' else 'failure'
    publication=publish('COMPLETE')
    for _ in range(3):
        ledger,blob=admit.read_ledger();updated=finish.close(ledger,admission['reservation'],conclusion,publication)
        row=next(x for x in updated['packages'] if x['id']==PACKAGE['id'])
        row.update(result_sha=publication,summary_sha256=digest(OUT/'SUMMARY.json'),artifacts_sha256=digest(OUT/'ARTIFACTS.json'),processes_exited=True)
        if admit.write_ledger(updated,blob):return
    raise ValueError('Cannot close reservation; no resubmission')

if __name__=='__main__':
    command=sys.argv[1]
    if command=='reserve':reserve()
    elif command=='execute':raise SystemExit(execute())
    elif command=='finalize':finalize()
    else:raise ValueError('Unknown command')
