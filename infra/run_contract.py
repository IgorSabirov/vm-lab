"""Shared offline run-plan/receipt validation; never submits a job or approves science."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re

SHA = re.compile(r'[0-9a-f]{40}')
DIGEST = re.compile(r'[0-9a-f]{64}')
RUN_ID = re.compile(r'[A-Za-z0-9_-]{12,64}')
STATES = {'PREPARED','SUBMITTED','QUEUED','RUNNING','COMPLETED','FAILED','CANCELLED','INTERRUPTED','UNKNOWN'}
TRANSITIONS = {'PREPARED':{'SUBMITTED','CANCELLED'},'SUBMITTED':{'QUEUED','RUNNING','FAILED','UNKNOWN','CANCELLED'},'QUEUED':{'RUNNING','FAILED','CANCELLED','UNKNOWN'},'RUNNING':{'COMPLETED','FAILED','CANCELLED','INTERRUPTED','UNKNOWN'},'UNKNOWN':STATES-{'PREPARED'}}

def canonical_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()

def safe_path(path):
    if not isinstance(path,str): raise ValueError('Path must be text')
    p=PurePosixPath(path)
    if not isinstance(path,str) or p.is_absolute() or not p.parts or '..' in p.parts or '\\' in path:
        raise ValueError('Unsafe relative path')
    return p

def validate_plan(plan, *, now=None, enforce_expiry=True):
    if plan.get('schema')!='vm-lab-run-plan-v1' or not RUN_ID.fullmatch(plan.get('run_id','')):
        raise ValueError('Invalid plan schema/run_id')
    src=plan['source']
    if not SHA.fullmatch(src.get('commit','')) or not SHA.fullmatch(src.get('tree_sha','')):
        raise ValueError('Source commit/tree must be frozen full SHAs')
    for k in ('input_manifest_sha256','config_sha256'):
        if not DIGEST.fullmatch(src.get(k,'')):raise ValueError('Missing source digest '+k)
    safe_path(plan['command']['entrypoint'])
    if plan['command'].get('args')!=[]:raise ValueError('v1 supports declared Python entrypoint without arguments')
    auth=plan['authorization']
    if auth.get('authority')!='user' or not auth.get('reference') or not auth.get('scope'):
        raise ValueError('Missing user authorization reference/scope')
    expiry=auth.get('expires_at')
    if expiry:
        dt=datetime.fromisoformat(expiry.replace('Z','+00:00'))
        if dt.tzinfo is None or enforce_expiry and dt <= (now or datetime.now(timezone.utc)):raise ValueError('Expired or timezone-less authorization')
    elif auth.get('duration')!='persistent':raise ValueError('Declare an expiry or explicit persistent authorization')
    b=plan['budget']
    for k in ('forecast_seconds','hard_wall_seconds','memory_limit_mib','disk_limit_mib'):
        v=b.get(k)
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<=0:raise ValueError('Invalid positive budget '+k)
    if b['hard_wall_seconds']<b['forecast_seconds']:raise ValueError('Wall cap below forecast')
    expected='sandbox' if b['forecast_seconds']<=600 else 'vm'
    if plan['executor'].get('kind')!=expected or not plan['executor'].get('id'):
        raise ValueError('Executor violates the 600-second routing rule')
    if not plan['acceptance'].get('required_artifacts'):raise ValueError('Declare required artifacts')
    for path in plan['acceptance']['required_artifacts']:safe_path(path)
    if plan.get('scientific_acceptance')!='SEPARATE_USER_REVIEW':raise ValueError('Scientific acceptance must remain separate')
    return canonical_hash(plan)

def check_authorization(plan, approval, *, now=None):
    digest=validate_plan(plan,now=now)
    if approval.get('authority')!='user' or approval.get('plan_sha256')!=digest or approval.get('run_id')!=plan['run_id']:
        raise ValueError('Trusted approval does not bind this exact plan')
    if approval.get('reference')!=plan['authorization']['reference']:raise ValueError('Authorization reference mismatch')
    return digest

def verify_receipt(folder, plan):
    validate_plan(plan,enforce_expiry=False)
    folder=Path(folder);m=json.loads((folder/'RESULT_MANIFEST.json').read_text())
    if m.get('run_id')!=plan['run_id'] or m.get('source_commit')!=plan['source']['commit'] or m.get('plan_sha256')!=canonical_hash(plan):
        raise ValueError('Result identity differs from plan')
    paths=set()
    for row in m['files']:
        path=row['path'];safe_path(path)
        if path=='RESULT_MANIFEST.json' or path in paths:raise ValueError('Self-referential or duplicate manifest entry')
        paths.add(path);f=folder/path
        if not f.is_file() or any(q.is_symlink() for q in [f,*f.parents] if q!=folder.parent):raise ValueError('Missing or symlink result')
        data=f.read_bytes()
        if len(data)!=row['size_bytes'] or hashlib.sha256(data).hexdigest()!=row['sha256']:raise ValueError('Result hash mismatch '+path)
    if not ({'PROCESS.json'} | set(plan['acceptance']['required_artifacts']))<=paths:raise ValueError('Required output missing')
    process=json.loads((folder/'PROCESS.json').read_text())
    if process.get('run_id')!=plan['run_id'] or process.get('source_commit')!=plan['source']['commit']:raise ValueError('Process identity mismatch')
    if process.get('state') not in STATES:raise ValueError('Unknown process state')
    if process.get('technical_gate') not in {'PASS','REVIEW_REQUIRED','NOT_EVALUABLE'}:raise ValueError('Invalid technical gate')
    if process.get('scientific_confirmation') is not False:raise ValueError('Execution cannot certify science')
    return {'integrity':'PASS','process_state':process['state'],'technical_gate':process['technical_gate'],'scientific_confirmation':False}

def validate_events(events):
    if not events or events[0].get('state')!='PREPARED': raise ValueError('Event stream must start PREPARED')
    last=None; previous_time=None
    for i,e in enumerate(events):
        if e.get('sequence')!=i or e.get('state') not in STATES:raise ValueError('Invalid event sequence/state')
        moment=datetime.fromisoformat(e['observed_at'].replace('Z','+00:00'))
        if moment.tzinfo is None or previous_time and moment<previous_time:raise ValueError('Nonmonotone event timestamps')
        if last and e['state']!=last and e['state'] not in TRANSITIONS.get(last,set()):raise ValueError('Invalid execution transition')
        last=e['state'];previous_time=moment
    return last

def main():
    ap=argparse.ArgumentParser();ap.add_argument('plan',type=Path);ap.add_argument('--receipt',type=Path);a=ap.parse_args()
    p=json.loads(a.plan.read_text());result={'plan_sha256':validate_plan(p,enforce_expiry=not bool(a.receipt)),'scientific_confirmation':False}
    if a.receipt:result.update(verify_receipt(a.receipt,p))
    print(json.dumps(result))
if __name__=='__main__':main()
