#!/usr/bin/env python3
"""R135 issue relationships and a guard against closure without saved evidence.

Only trusted main supplies PIPELINE.json and completion records. Issue bodies
are never parsed as commands or acceptance evidence. This is a structural and
byte-integrity check, not a scientific judge or proof of method independence.

completion_record is null or infra/r135/completions/<name>.json. Record shape:
  schema: vm-lab-r135-completion-v1; task_key; source_sha (40 hex)
  scope: {stages: [...], claims: [...]} exactly matching the task
  input_manifest: {ref: <40 hex>, path: <repo path>, sha256: <64 hex>}
  evidence: [{id, ref, path, sha256}, ...]
  checks: [{id: <acceptance_checks id>, status: PASS, evidence_ids: [...]}, ...]
  producer / independent_replay:
    {provider: manifest|github_actions, run_id, report_evidence_id}
  owner_decision_ref: {ref, path, sha256} when requires_owner_decision is true

Both referenced run reports are immutable JSON with schema
vm-lab-r135-run-evidence-v1, task_key, role (producer|independent_replay), run_id,
source_sha, input_manifest_sha256, scope, checks [{id,status:PASS}], result:PASS,
exit_code:0, method (description), and environment (nonempty object).
Run IDs and report artifacts must differ. A manifest provider supports the
owner's chosen compute environment; github_actions additionally verifies the
live completed/success run and its source SHA. Records declare independent
replay; the guard does not prove physical independence or approve a model.
"""
import argparse
import base64
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import time
from urllib.error import HTTPError
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
REPO = 'IgorSabirov/vm-lab'
BASE = '/repos/' + REPO
MANIFEST_PATH = 'infra/r135/PIPELINE.json'
SCHEMA = 'vm-lab-r135-development-pipeline-v1'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def hex_digest(value, length):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{'+str(length)+'}', value) is not None


def repo_path(value):
    return (isinstance(value, str) and bool(value) and not value.startswith('/')
            and '\\' not in value and '\x00' not in value
            and all(x not in ('', '.', '..') for x in value.split('/'))
            and str(PurePosixPath(value)) == value)


def unique_strings(values, label, nonempty=True):
    require(isinstance(values, list) and (bool(values) or not nonempty)
            and all(isinstance(v,str) and v.strip() for v in values)
            and len(set(values)) == len(values), 'Invalid '+label)


def validate_plan(plan):
    require(isinstance(plan,dict) and plan.get('schema') == SCHEMA, 'Pipeline schema')
    require(plan.get('repository') == REPO, 'Unexpected repository')
    require(type(plan.get('tracker')) is int and plan['tracker'] == 155, 'Unexpected R135 tracker')
    sources = plan.get('source_commits',{})
    require(isinstance(sources,dict) and all(hex_digest(sources.get(k),40)
            for k in ('implementation','design','main')), 'Missing exact source commits')
    tasks = plan.get('tasks')
    require(isinstance(tasks,list) and tasks, 'Empty task map')
    by_key, numbers = {}, set()
    for task in tasks:
        require(isinstance(task,dict), 'Invalid task')
        key, number = task.get('key'), task.get('issue_number')
        require(isinstance(key,str) and key.strip() and key not in by_key, 'Duplicate/invalid task key')
        require(type(number) is int and number > 0 and number != plan['tracker']
                and number not in numbers, 'Duplicate/invalid issue number')
        require(isinstance(task.get('title'),str) and task['title'].strip(), 'Missing task title')
        unique_strings(task.get('stages'), 'stages')
        unique_strings(task.get('claims'), 'claims', nonempty=False)
        unique_strings(task.get('depends_on'), 'dependencies', nonempty=False)
        require(task.get('initial_status') in ('Ready','Analysis','Inbox'), 'Invalid initial status')
        checks = task.get('acceptance_checks')
        require(isinstance(checks,list) and checks and all(isinstance(c,dict)
                and isinstance(c.get('id'),str) and c['id'].strip()
                and isinstance(c.get('criterion'),str) and c['criterion'].strip() for c in checks),
                'Missing acceptance checks: '+key)
        require(len({c['id'] for c in checks}) == len(checks), 'Duplicate acceptance check: '+key)
        require(type(task.get('requires_owner_decision',False)) is bool, 'Invalid owner decision flag')
        record = task.get('completion_record')
        require('completion_record' in task and (record is None or (repo_path(record)
                and record.startswith('infra/r135/completions/') and record.endswith('.json'))),
                'Completion must be a reviewed-main record path or null')
        by_key[key], numbers = task, numbers | {number}
    if 'tracker_completion_key' in plan:
        require(isinstance(plan['tracker_completion_key'],str)
                and plan['tracker_completion_key'] in by_key, 'Unknown tracker completion key')
    if 'label' in plan:
        label = plan['label']
        require(isinstance(label,str) and 0 < len(label) <= 50 and label == label.strip()
                and all(ord(char) >= 32 and ord(char) != 127 for char in label), 'Invalid pipeline label')
    related = plan.get('related_pull_requests',[])
    require(isinstance(related,list) and all(type(n) is int and n > 0
            and n not in numbers and n != plan['tracker'] for n in related)
            and len(set(related)) == len(related), 'Invalid related pull requests')
    for key, task in by_key.items():
        for parent in task['depends_on']:
            require(parent in by_key and parent != key, 'Unknown/self dependency: '+key)
        conditional = task.get('conditional_dependencies',[])
        require(isinstance(conditional,list), 'Invalid conditional dependencies')
        for dep in conditional:
            require(isinstance(dep,dict) and dep.get('key') in by_key and dep['key'] != key
                    and isinstance(dep.get('when'),str) and dep['when'].strip(), 'Invalid conditional dependency: '+key)
    active, finished = set(), set()
    def visit(key):
        require(key not in active, 'Cycle in mandatory dependencies: '+key)
        if key in finished:
            return
        active.add(key)
        for dependency in by_key[key]['depends_on']:
            visit(dependency)
        active.remove(key)
        finished.add(key)
    for key in by_key:
        visit(key)
    return by_key


def paginated(request, path):
    rows, ids = [], set()
    for page in range(1,101):
        result = request(path+'?per_page=100&page='+str(page))
        require(isinstance(result,list) and len(result) <= 100, 'Invalid paginated API response')
        for row in result:
            require(isinstance(row,dict) and type(row.get('id')) is int and row['id'] not in ids,
                    'Duplicate/incomplete pagination')
            ids.add(row['id'])
            rows.append(row)
        if len(result) < 100:
            return rows
    raise ValueError('Pagination budget exceeded; partial readback rejected')


def ensure_label(request, name):
    try:
        existing = request(BASE+'/labels/'+quote(name,safe=''))
    except HTTPError as error:
        if error.code != 404:
            raise
        request(BASE+'/labels','POST',{'name':name,'color':'1D76DB',
                'description':'Operational R135 work; scientific statuses remain in existing registers.'})
        return True
    require(existing.get('name')==name, 'Pipeline label case/name mismatch')
    return False  # Keep an existing label's description and color unchanged.


def read_file_at(request, ref, path):
    require(hex_digest(ref,40) and repo_path(path), 'Evidence needs immutable ref and repository path')
    try:
        obj = request(BASE+'/contents/'+quote(path,safe='/')+'?ref='+ref)
        require(isinstance(obj,dict) and obj.get('type') == 'file' and obj.get('path') == path,
                'Evidence path does not identify a file')
        if obj.get('encoding') == 'none' and hex_digest(obj.get('sha'),40):
            obj = request(BASE+'/git/blobs/'+obj['sha'])
        require(obj.get('encoding') == 'base64' and isinstance(obj.get('content'),str),
                'Evidence bytes unavailable')
        return base64.b64decode(''.join(obj['content'].split()),validate=True)
    except HTTPError as error:
        if error.code == 404:
            raise ValueError('Evidence file missing: '+path) from error
        raise  # An API outage/permission problem is not evidence of bad physics.


def pinned_bytes(request, reference):
    require(isinstance(reference,dict) and hex_digest(reference.get('sha256'),64), 'Missing evidence SHA256')
    raw = read_file_at(request,reference.get('ref'),reference.get('path'))
    require(hashlib.sha256(raw).hexdigest() == reference['sha256'], 'Evidence SHA256 mismatch: '+reference['path'])
    return raw


def evidence_object(request, path):
    try:
        return request(path)
    except HTTPError as error:
        if error.code == 404:
            raise ValueError('Referenced evidence object missing: '+path) from error
        raise


def same_scope(scope, task):
    if not isinstance(scope,dict) or set(scope) != {'stages','claims'}:
        return False
    for key in ('stages','claims'):
        if (not isinstance(scope[key],list) or not all(isinstance(x,str) for x in scope[key])
                or len(scope[key]) != len(task[key]) or set(scope[key]) != set(task[key])):
            return False
    return True


def verify_completion(task, record, request):
    require(isinstance(record,dict) and record.get('schema') == 'vm-lab-r135-completion-v1', 'Completion schema')
    require(record.get('task_key') == task['key'] and same_scope(record.get('scope'),task), 'Completion scope mismatch')
    require(hex_digest(record.get('source_sha'),40), 'Completion source SHA')
    commit = evidence_object(request,BASE+'/git/commits/'+record['source_sha'])
    require(commit.get('sha')==record['source_sha'], 'Completion source commit unavailable')
    pinned_bytes(request,record.get('input_manifest'))
    items = record.get('evidence')
    require(isinstance(items,list) and items, 'Missing evidence artifacts')
    artifacts = {}
    for item in items:
        require(isinstance(item,dict) and isinstance(item.get('id'),str) and item['id']
                and item['id'] not in artifacts, 'Duplicate/invalid evidence id')
        artifacts[item['id']] = pinned_bytes(request,item)
    required = {check['id'] for check in task['acceptance_checks']}
    checks = record.get('checks')
    require(isinstance(checks,list) and len(checks)==len(required)
            and all(isinstance(c,dict) and c.get('status')=='PASS' for c in checks)
            and {c.get('id') for c in checks} == required, 'Incomplete acceptance checks')
    for check in checks:
        evidence_ids = check.get('evidence_ids')
        require(isinstance(evidence_ids,list) and evidence_ids
                and all(isinstance(x,str) and x in artifacts for x in evidence_ids), 'Acceptance check missing artifact')
    runs, report_ids = [], []
    for role in ('producer','independent_replay'):
        run = record.get(role)
        require(isinstance(run,dict) and run.get('provider') in ('manifest','github_actions'), 'Missing replay provider')
        run_id, evidence_id = run.get('run_id'), run.get('report_evidence_id')
        require(type(run_id) in (int,str) and str(run_id).strip() and evidence_id in artifacts, 'Missing run identity/report')
        report = json.loads(artifacts[evidence_id])
        require(isinstance(report,dict) and report.get('schema') == 'vm-lab-r135-run-evidence-v1'
                and report.get('task_key')==task['key'] and report.get('role')==role
                and str(report.get('run_id'))==str(run_id) and same_scope(report.get('scope'),task), 'Run report scope/identity mismatch')
        require(report.get('source_sha')==record['source_sha']
                and report.get('input_manifest_sha256')==record['input_manifest']['sha256'], 'Run report source/input mismatch')
        require(report.get('result')=='PASS' and type(report.get('exit_code')) is int and report['exit_code']==0
                and isinstance(report.get('method'),str) and report['method'].strip()
                and isinstance(report.get('environment'),dict) and report['environment'], 'Replay report missing result/environment')
        observed = report.get('checks')
        require(isinstance(observed,list) and len(observed)==len(required)
                and all(isinstance(c,dict) and c.get('status')=='PASS' for c in observed)
                and {c.get('id') for c in observed}==required, 'Replay did not verify all checks')
        if run['provider']=='github_actions':
            require(type(run_id) is int and run_id > 0, 'Invalid Actions run id')
            actual = evidence_object(request,BASE+'/actions/runs/'+str(run_id))
            require(actual.get('status')=='completed' and actual.get('conclusion')=='success'
                    and actual.get('head_sha')==record['source_sha']
                    and actual.get('repository',{}).get('full_name')==REPO, 'Actions run not successful on declared source')
        runs.append(str(run_id))
        report_ids.append(evidence_id)
    require(runs[0]!=runs[1] and report_ids[0]!=report_ids[1]
            and artifacts[report_ids[0]] != artifacts[report_ids[1]], 'Producer and replay must be distinct saved runs')
    if task.get('requires_owner_decision',False):
        pinned_bytes(request,record.get('owner_decision_ref'))
    return {'status':'VERIFIED_STRUCTURAL_EVIDENCE', 'source_sha':record['source_sha'],
            'checks':sorted(required), 'scientific_acceptance_inferred':False,
            'method_independence_proven':False}


def apply_pipeline(plan, *, request, source_sha, report=None):
    tasks = validate_plan(plan)
    require(hex_digest(source_sha,40), 'Expected trusted main SHA')
    tracker_path = BASE+'/issues/'+str(plan['tracker'])
    tracker = request(tracker_path)
    require(type(tracker.get('id')) is int and 'pull_request' not in tracker
            and tracker.get('state') in ('open','closed'), 'Invalid tracker issue')
    issues = {key:request(BASE+'/issues/'+str(task['issue_number'])) for key,task in tasks.items()}
    for key, issue in issues.items():
        require(issue.get('number')==tasks[key]['issue_number'] and type(issue.get('id')) is int
                and 'pull_request' not in issue and issue.get('state') in ('open','closed'), 'Invalid managed issue: '+key)
    related = plan.get('related_pull_requests',[])
    for number in related:
        pr = request(BASE+'/issues/'+str(number))
        require(pr.get('number')==number and type(pr.get('id')) is int
                and 'pull_request' in pr, 'Related item is not a pull request: '+str(number))
    completions, reopened = {}, []
    result = report if report is not None else {}
    result.update({'schema':'vm-lab-r135-pipeline-status-v1', 'source_sha':source_sha,
                   'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(), 'repository':REPO,
                   'tracker':plan['tracker'], 'verified':False, 'reopened':reopened,
                   'completion_evidence':completions, 'scientific_status_modified':False,
                   'scientific_acceptance_inferred':False, 'method_independence_proven':False})
    for key, task in tasks.items():
        record_path = task['completion_record']
        try:
            require(record_path is not None, 'No reviewed-main completion record')
            record = json.loads(read_file_at(request,source_sha,record_path))
            completions[key] = verify_completion(task,record,request)
        except (ValueError, TypeError, KeyError) as error:
            completions[key] = {'status':'OPEN_EVIDENCE', 'reason':str(error), 'scientific_acceptance_inferred':False}
        if issues[key]['state']=='closed' and completions[key]['status']!='VERIFIED_STRUCTURAL_EVIDENCE':
            request(BASE+'/issues/'+str(task['issue_number']),'PATCH',{'state':'open'})
            reopened.append(task['issue_number'])
    tracker_key = plan.get('tracker_completion_key')
    if tracker_key:
        result['tracker_completion_key'] = tracker_key
        result['tracker_completion_evidence'] = completions[tracker_key]['status']
        if tracker['state']=='closed' and completions[tracker_key]['status']!='VERIFIED_STRUCTURAL_EVIDENCE':
            request(tracker_path,'PATCH',{'state':'open'})
            reopened.append(plan['tracker'])
    children = paginated(request,tracker_path+'/sub_issues')
    child_ids = {row['id'] for row in children}
    # Check parents before relationship mutations; never steal a child.
    for key, issue in issues.items():
        if issue['id'] in child_ids:
            continue
        try:
            parent = request(BASE+'/issues/'+str(issue['number'])+'/parent')
        except HTTPError as error:
            if error.code != 404:
                raise
            parent = None
        require(parent is None or parent.get('id')==tracker['id'], 'Managed issue has another parent: '+key)
    added_children, added_dependencies = [], []
    result.update({'added_sub_issues':added_children,'added_dependencies':added_dependencies})
    label = plan.get('label')
    label_members = sorted({plan['tracker'], *[t['issue_number'] for t in tasks.values()], *related})
    if label:
        result.update({'label':label,'label_created':ensure_label(request,label),'labeled':[],
                       'related_pull_requests':related})
        for number in label_members:
            target = BASE+'/issues/'+str(number)+'/labels'
            current = {row['name'] for row in paginated(request,target)}
            if label not in current:
                request(target,'POST',{'labels':[label]})
                result['labeled'].append(number)
    for key, issue in issues.items():
        if issue['id'] not in child_ids:
            request(tracker_path+'/sub_issues','POST',{'sub_issue_id':issue['id'],'replace_parent':False})
            added_children.append(issue['number'])
        target = BASE+'/issues/'+str(issue['number'])+'/dependencies/blocked_by'
        current = {row['id'] for row in paginated(request,target)}
        for dependency in tasks[key]['depends_on']:
            parent = issues[dependency]
            if parent['id'] not in current:
                request(target,'POST',{'issue_id':parent['id']})
                added_dependencies.append({'issue':issue['number'],'blocked_by':parent['number']})
    mismatches = []
    for delay in (0,1,2,4,8,16):
        if delay:
            time.sleep(delay)
        child_ids = {row['id'] for row in paginated(request,tracker_path+'/sub_issues')}
        mismatches = []
        for key, issue in issues.items():
            if issue['id'] not in child_ids:
                mismatches.append('sub-issue '+key)
            current = {row['id'] for row in paginated(request,BASE+'/issues/'+str(issue['number'])+'/dependencies/blocked_by')}
            if not {issues[d]['id'] for d in tasks[key]['depends_on']} <= current:
                mismatches.append('dependencies '+key)
            if issue['number'] in reopened and request(BASE+'/issues/'+str(issue['number'])).get('state')!='open':
                mismatches.append('reopen '+key)
        if plan['tracker'] in reopened and request(tracker_path).get('state')!='open':
            mismatches.append('reopen tracker')
        if label:
            try:
                actual_label = request(BASE+'/labels/'+quote(label,safe=''))
            except HTTPError as error:
                if error.code != 404:
                    raise
                actual_label = {}
            if actual_label.get('name') != label:
                mismatches.append('label definition')
            for number in label_members:
                names = {row['name'] for row in paginated(request,BASE+'/issues/'+str(number)+'/labels')}
                if label not in names:
                    mismatches.append('label '+str(number))
        if not mismatches:
            break
    require(not mismatches, 'Pipeline readback failed: '+', '.join(mismatches))
    result.update({'tasks_verified':len(tasks), 'verified':True, 'conditional_dependencies_materialized':False})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check',action='store_true')
    mode.add_argument('--apply',action='store_true')
    parser.add_argument('--output',type=Path,default=Path('project-evidence/R135_PIPELINE_STATUS.json'))
    args = parser.parse_args()
    raw = (ROOT/MANIFEST_PATH).read_bytes()
    plan = json.loads(raw)
    tasks = validate_plan(plan)
    if args.check:
        for task in tasks.values():
            if task['completion_record'] is not None:
                require((ROOT/task['completion_record']).is_file(), 'Missing reviewed completion record')
                record = json.loads((ROOT/task['completion_record']).read_bytes())
                require(isinstance(record,dict) and record.get('schema')=='vm-lab-r135-completion-v1'
                        and record.get('task_key')==task['key'] and same_scope(record.get('scope'),task), 'Completion scope/schema')
        print(json.dumps({'status':'PASS','tasks':len(tasks),'live_evidence_checked':False,'scientific_status_modified':False}))
        return
    from github_setup import request
    source_sha = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    require(request(BASE+'/git/ref/heads/main')['object']['sha']==source_sha, '--apply requires current trusted main')
    require(subprocess.check_output(['git','show','HEAD:'+MANIFEST_PATH],cwd=ROOT)==raw, 'Pipeline differs from committed main')
    if os.environ.get('GITHUB_ACTIONS')=='true':
        require(os.environ.get('GITHUB_REPOSITORY')==REPO and os.environ.get('GITHUB_REF')=='refs/heads/main', 'Untrusted workflow context')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    result = {}
    try:
        apply_pipeline(plan,request=request,source_sha=source_sha,report=result)
    except Exception as error:
        result.update({'verified':False,'error':str(error),'scientific_status_modified':False})
        raise
    finally:
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    main()
