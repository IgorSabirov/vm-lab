"""Shared package accounting and leased admission, before scientific execution."""
from __future__ import annotations
import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.parse
import urllib.request
try:
    from .execution_policy import digest, validate
except ImportError:  # Direct CLI invocation from repository root.
    from execution_policy import digest, validate

REPOSITORY = 'IgorSabirov/vm-lab'
LEDGER_BRANCH = 'science/autonomous-research-20261114'
LEDGER_PATH = 'infra/autonomy/LEDGER.json'
REQUEST_PATH = 'analysis/CCC_BBN_NETWORK_20261114/pipeline/RUN_REQUEST.json'
ACTIVE = {'RESERVED', 'SUBMITTED', 'QUEUED', 'RUNNING', 'UNKNOWN'}
# Known non-compute workflows do not occupy the scientific package slot.
NON_COMPUTE = {'.github/workflows/' + n + '.yml' for n in (
    'development', 'codeql', 'dependency-review', 'project-events',
    'projects-sync', 'result-pull-request', 'evidence-publication',
    'scorecard', 'freeze-release', 'registry-advisor', 'upstream-monitor',
    'external-validation', 'p2-fullnet-static', 'failure-advisor',
    'anthropic-bh0')}


def moment(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Ledger timestamps must include timezone')
    return result


def package_records(ledger, runs, now, current_run_id=None):
    """Union local/VM/Actions packages; run IDs are evidence, not package IDs."""
    records = {}; mapped = {}
    for row in ledger['packages']:
        key = row['id']
        if key in records:
            raise ValueError('Duplicate package identity in ledger')
        moment(row['started_utc']); records[key] = dict(row)
        ids = list(row.get('workflow_run_ids', []))
        if row.get('workflow_run_id') is not None:
            ids.append(row['workflow_run_id'])
        for run_id in set(ids):
            if run_id in mapped:
                raise ValueError('Workflow run belongs to two packages')
            mapped[run_id] = key
    for run in runs:
        if (run['id'] == current_run_id or run['status'] == 'completed'
                or run.get('path') in NON_COMPUTE
                or not run.get('head_branch', '').startswith('science/autonomous-')):
            continue
        if run['id'] in mapped:
            # Live processes override stale terminal metadata, without rewriting evidence.
            records[mapped[run['id']]]['status'] = 'RUNNING'
            continue
        records['unmapped_actions_' + str(run['id'])] = {
            'id': 'unmapped_actions_' + str(run['id']), 'started_utc': run['created_at'],
            'status': 'RUNNING' if run['status'] != 'completed' else 'UNMAPPED_TERMINAL',
            'workflow_run_id': run['id'], 'executor': 'github_actions'}
    if any(moment(r['started_utc']) > now for r in records.values()):
        raise ValueError('Ledger timestamp is in the future')
    return records


def decision(ledger, runs, candidate, now, limits, current_run_id=None):
    records = package_records(ledger, runs, now, current_run_id)
    if candidate['id'] in records:
        return {'admitted': False, 'reason': 'ALREADY_REGISTERED_NO_RETRY'}
    if any(r.get('status') in ACTIVE for r in records.values()):
        return {'admitted': False, 'reason': 'ACTIVE_PACKAGE'}
    return {'admitted': True, 'reason': 'ADMITTED',
            'registered_packages': sorted(records), 'daily_quota': None}


def reserve(read_ledger, write_ledger, runs, candidate, now, limits, current_run_id=None):
    """CAS is shared by every executor. A conflict requires a fresh decision."""
    for _ in range(3):
        ledger, expected_blob = read_ledger()
        result = decision(ledger, runs, candidate, now, limits, current_run_id)
        if not result['admitted']:
            return result
        updated = {**ledger, 'packages': ledger['packages'] + [candidate]}
        if write_ledger(updated, expected_blob):
            return {**result, 'reservation': candidate}
    raise ValueError('Concurrent ledger updates; no package admitted')


def api(path, data=None):
    headers = {'Accept': 'application/vnd.github+json', 'Authorization': 'Bearer ' + os.environ['GH_TOKEN']}
    request = urllib.request.Request('https://api.github.com/repos/' + REPOSITORY + '/' + path,
                                     headers=headers, data=None if data is None else json.dumps(data).encode(),
                                     method='GET' if data is None else 'PUT')
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def read_ledger():
    data = api('contents/' + LEDGER_PATH + '?ref=' + urllib.parse.quote(LEDGER_BRANCH, safe=''))
    return json.loads(base64.b64decode(data['content'])), data['sha']


def write_ledger(value, expected_blob):
    try:
        api('contents/' + LEDGER_PATH, {
            'branch': LEDGER_BRANCH, 'sha': expected_blob,
            'message': 'Update autonomous package reservation and evidence',
            'content': base64.b64encode((json.dumps(value, indent=2) + '\n').encode()).decode()})
        return True
    except urllib.error.HTTPError as exc:
        if exc.code == 409:
            return False
        # An uncertain write never causes a new submission automatically.
        raise


def actions_runs(now=None):
    """Read ALL nonterminal runs, regardless of age or workflow filename.

    Unknown workflows on autonomous branches are conservatively blocking. No 24-hour history
    is required. API failure or an incomplete page set denies admission.
    """
    runs = {}
    for status in ('queued', 'in_progress', 'waiting', 'requested', 'pending'):
        for page in range(1, 101):
            response = api(f'actions/runs?status={status}&per_page=100&page={page}')
            batch = response['workflow_runs']
            if response.get('total_count', 0) > 10000:
                raise ValueError('Cannot establish complete active Actions inventory')
            for run in batch:
                runs[run['id']] = run
            if len(batch) < 100:
                break
        else:
            raise ValueError('Cannot establish complete active Actions inventory')
    return list(runs.values())


def source_check(plan, path, request):
    if plan['package_id'] != request['id'] or plan['publication_branch'] != os.environ['GITHUB_REF_NAME']:
        raise ValueError('Package/branch does not match request')
    subprocess.run(['git', 'merge-base', '--is-ancestor', plan['source_commit'], 'HEAD'], check=True)
    changed = subprocess.check_output(['git', 'diff', '--name-only', plan['source_commit'], 'HEAD'], text=True).splitlines()
    if set(changed) - {path, REQUEST_PATH}:
        raise ValueError('Source changed after freeze; only request/plan publication may follow')


def receipt(value):
    Path(os.environ['RUNNER_TEMP'], 'autonomy-budget.json').write_text(json.dumps(value, indent=2) + '\n')
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
            output.write('execute=' + str(value.get('execute', False)).lower() + '\n')
    print(json.dumps(value))


def main():
    if os.environ['GITHUB_REPOSITORY'] != REPOSITORY or os.environ['GITHUB_RUN_ATTEMPT'] != '1':
        raise ValueError('Wrong repository or forbidden retry')
    if not os.environ['GITHUB_REF_NAME'].startswith('science/autonomous-'):
        raise ValueError('Wrong autonomous branch')
    request = json.loads(Path(REQUEST_PATH).read_text())
    if not request.get('execution_enabled'):
        receipt({'execute': False, 'reason': 'EXECUTION_DISABLED', 'scientific_acceptance': False})
        return
    control = json.loads(Path('infra/autonomy/CONTROL.json').read_text())
    path = request['execution_plan']; file = (Path.cwd() / path).resolve()
    if not file.is_relative_to(Path.cwd()):
        raise ValueError('Execution plan outside repository')
    plan = json.loads(file.read_text())
    report = validate(plan, control['limits'], root=Path.cwd())
    source_check(plan, path, request)
    pipeline = json.loads(Path('analysis/CCC_BBN_NETWORK_20261114/pipeline/PIPELINE.json').read_text())
    if pipeline['branch'] != plan['publication_branch']:
        raise ValueError('Pipeline and execution-plan publication branches differ')
    if report['executor'] != 'github_actions':
        receipt({**report, 'execute': False, 'reason': 'HANDOFF_' + report['executor'].upper()})
        return
    # The existing CCC dispatcher runs a whole stage package. Do not repeat it
    # per section. Section-aware scientific adapters have their own workflows.
    if len(plan['sections']) != 1:
        raise ValueError('Use a package-specific section workflow; legacy dispatcher is single-section')
    if not control['enabled']:
        raise ValueError('Autonomous execution disabled')
    now = datetime.now(timezone.utc); run_id = int(os.environ['GITHUB_RUN_ID'])
    candidate = {'id': request['id'], 'executor': 'github_actions', 'started_utc': now.isoformat(),
                 'source_sha': plan['source_commit'], 'execution_plan_sha256': digest(plan),
                 'workflow_run_id': run_id, 'status': 'RESERVED', 'budget': plan['budget']}
    result = reserve(read_ledger, write_ledger, actions_runs(now), candidate, now, control['limits'], run_id)
    receipt({**report, **result, 'execute': result['admitted']})


if __name__ == '__main__':
    main()
