"""Repository research state reducer and bounded, allowlisted stage dispatcher."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime,timezone

REPO=Path(__file__).resolve().parents[1]
PKG=REPO/'analysis/CCC_BBN_NETWORK_20261114/pipeline'
IMPLEMENTATIONS={'s1_fullnet':REPO/'analysis/CCC_BBN_NETWORK_20261114/s1_fullnet/launch.py'}

def read(path):return json.loads(Path(path).read_text())
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def git(*args):return subprocess.check_output(['git','-C',str(REPO),*args],text=True).strip()
def safe(path):
    p=(REPO/path).resolve()
    if not p.is_relative_to(REPO):raise ValueError('Path outside repository')
    return p
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def contract_complete(value,stage):
    return value.get('status')=='ENGINEERING_PASS' and value.get(stage['status_field'])==stage['expected_status']

def validate_definition(plan):
    ids=[s['id'] for s in plan['stages']]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate stage')
    nodes={s['id']:s for s in plan['stages']};active=set();done=set()
    def walk(key):
        if key not in nodes:raise ValueError('Unknown dependency '+key)
        if key in active:raise ValueError('Dependency cycle')
        if key in done:return
        active.add(key)
        for dep in nodes[key]['depends']:walk(dep)
        active.remove(key);done.add(key)
    for key in ids:walk(key)
    for s in plan['stages']:
        if s['kind']=='execute' and s.get('implementation') not in IMPLEMENTATIONS:raise ValueError('Unreviewed implementation')
        if s['kind'] in ('contract','theory','separate_line') and s.get('automatic'):raise ValueError('Cannot auto-run a missing scientific contract')
    return nodes

def verify_import(stage):
    for key in ('summary','manifest'):
        ref=stage[key]
        if sha(safe(ref['path']))!=ref['sha256']:raise ValueError('Pinned '+key+' differs')
    manifest=safe(stage['manifest']['path']);root=manifest.parent
    for rel,entry in read(manifest)['files'].items():
        path=(root/rel).resolve()
        if not path.is_relative_to(root) or sha(path)!=entry['sha256']:raise ValueError('Input artifact changed: '+rel)
    return read(safe(stage['summary']['path']))

def evaluate(plan,request):
    nodes=validate_definition(plan);state={}
    def visit(key):
        if key in state:return state[key]
        s=nodes[key];deps={d:visit(d)['status'] for d in s['depends']}
        if s['kind']=='import':
            try:
                value=verify_import(s);ok=contract_complete(value,s)
                row={'status':'COMPLETE' if ok else 'REVIEW_REQUIRED','evidence':s['summary']['path'],'numerical_status':value.get(s['status_field'])}
            except (ValueError,OSError,KeyError) as exc:row={'status':'INTEGRITY_ERROR','error':str(exc)}
        elif s['kind']=='execute':
            result=safe(s['result'])
            if result.exists():
                value=read(result)
                try:
                    manifest=result.parent/'ARTIFACTS.json'
                    receipt=read(result.parent/'ARTIFACTS_SHA256.json')
                    if sha(manifest)!=receipt['sha256']:raise ValueError('Result manifest changed')
                    entries=read(manifest)['files']
                    if result.name not in entries:raise ValueError('Summary absent from artifact manifest')
                    for rel,h in entries.items():
                        path=(result.parent/rel).resolve()
                        if not path.is_relative_to(result.parent) or sha(path)!=h['sha256']:raise ValueError('Result artifact changed')
                    ok=contract_complete(value,s) and all(v=='COMPLETE' for v in deps.values())
                    row={'status':'COMPLETE' if ok else 'REVIEW_REQUIRED','evidence':s['result'],'numerical_status':value.get(s['status_field']),'engineering_status':value.get('status'),'reused':True}
                except (ValueError,OSError,KeyError) as exc:row={'status':'INTEGRITY_ERROR','error':str(exc)}
            elif (result.parent/'LEDGER.jsonl').exists():row={'status':'INTERRUPTED_OR_RUNNING','automatic_retry':False}
            elif any(v!='COMPLETE' for v in deps.values()):row={'status':'WAITING_DEPENDENCY'}
            elif key in request['stages'] and request['execution_enabled']:row={'status':'READY'}
            else:row={'status':'NOT_REQUESTED'}
        else:
            row={'status':'OPEN_THEORY' if s['kind']=='theory' else 'CONTRACT_REQUIRED','missing':s.get('missing',[]),'next_action':s['next']}
            if any(v!='COMPLETE' for v in deps.values()):row['waiting_dependencies']=[d for d,v in deps.items() if v!='COMPLETE']
        row['dependencies']=deps;state[key]=row;return row
    for key in nodes:visit(key)
    return {'schema':'vm-lab-pipeline-state-v1','pipeline':plan['id'],'request':request['id'],'observed_utc':datetime.now(timezone.utc).isoformat(),'source_commit':git('rev-parse','HEAD'),'stages':state,'scientific_acceptance':False,'r_c_l_u_changed':False}

def render(state):
    lines=['# CCC–BBN: состояние общего пайплайна','',f"Запрос: `{state['request']}`. Снимок: {state['observed_utc']}.",'','| Этап | Состояние | Следующее действие / свидетельство |','|---|---|---|']
    for key,row in state['stages'].items():
        detail=row.get('evidence') or row.get('next_action') or row.get('error') or ''
        lines.append(f"| {key} | {row['status']} | {detail} |")
    lines+=['','COMPLETE означает проверенное завершение указанного вычислительного контракта. Научная приёмка и статусы R/C/L/U остаются отдельными. S2/BH1 не блокируют независимые готовые этапы.']
    return '\n'.join(lines)+'\n'

def save_state(state):
    root=PKG/'results'/state['request'];write(root/'STATE.json',state)
    (root/'REPORT.md').write_text(render(state))
    write(PKG/'CURRENT.json',{'request':state['request'],'state':str((root/'STATE.json').relative_to(REPO)),'report':str((root/'REPORT.md').relative_to(REPO)),'observed_utc':state['observed_utc'],'scientific_acceptance':False})
    return root

def publish(root,branch):
    if git('branch','--show-current')!=branch:raise ValueError('Wrong publication branch')
    allowed=[str(root.relative_to(REPO)),str((PKG/'CURRENT.json').relative_to(REPO))]
    git('add','--',*allowed)
    staged=git('diff','--cached','--name-only').splitlines()
    if any(p!=allowed[1] and not p.startswith(allowed[0]+'/') for p in staged):raise ValueError('Unexpected staged file')
    if staged:git('commit','-m','Update research pipeline state and next-stage requirements');git('push','origin','HEAD:refs/heads/'+branch)
    if git('ls-remote','origin','refs/heads/'+branch).split()[0]!=git('rev-parse','HEAD'):raise ValueError('Publication not confirmed')

def stage_checkpoint(stage,phase):
    """Called directly by the executing stage; no workflow-event chaining needed."""
    plan=read(PKG/'PIPELINE.json');request=read(PKG/'RUN_REQUEST.json')
    if stage not in request['stages'] or os.environ.get('GITHUB_ACTIONS')!='true':raise ValueError('Unexpected stage checkpoint')
    state=evaluate(plan,request)
    state['stages'][stage].update(status='RUNNING',phase=phase,workflow_url='https://github.com/IgorSabirov/vm-lab/actions/runs/'+os.environ['GITHUB_RUN_ID'])
    root=save_state(state);publish(root,plan['branch'])

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--execute',action='store_true');ap.add_argument('--upstream');ap.add_argument('--output',type=Path);a=ap.parse_args()
    plan=read(PKG/'PIPELINE.json');req=read(PKG/'RUN_REQUEST.json');nodes=validate_definition(plan)
    if any(k not in nodes or nodes[k]['kind']!='execute' for k in req['stages']):raise ValueError('Unknown/non-executable requested stage')
    state=evaluate(plan,req)
    if not a.execute:
        if a.output:write(a.output,state)
        print(json.dumps({k:v['status'] for k,v in state['stages'].items()}));return 0
    if not a.upstream:raise ValueError('Pinned upstream checkout required')
    if os.environ.get('GITHUB_REPOSITORY')!='IgorSabirov/vm-lab' or os.environ.get('GITHUB_REF')!='refs/heads/'+plan['branch'] or os.environ.get('GITHUB_RUN_ATTEMPT')!='1':raise ValueError('Wrong executor or forbidden retry')
    exit_code=0
    try:
        for key in req['stages']:
            status=state['stages'][key]['status']
            if status=='COMPLETE':continue
            if status!='READY':raise ValueError(key+' cannot start: '+status+'; no automatic repeat')
            entry=IMPLEMENTATIONS[nodes[key]['implementation']]
            proc=subprocess.run([sys.executable,str(entry),'--upstream',str(Path(a.upstream).resolve())],cwd=REPO)
            state=evaluate(plan,req)
            if proc.returncode or state['stages'][key]['status']!='COMPLETE':exit_code=1;break
    except Exception as exc:
        exit_code=1;state=evaluate(plan,req);state['controller_error']=str(exc)
    finally:
        root=save_state(state);publish(root,plan['branch'])
    return exit_code

if __name__=='__main__':raise SystemExit(main())
