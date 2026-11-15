#!/usr/bin/env python3
"""Read-only operational view. Pinned reads; never imports branch code or submits work."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ('queued', 'in_progress', 'waiting', 'pending', 'requested')
TERMINAL = {'COMPLETED', 'FAILED', 'CANCELLED', 'COMPLETE'}


def pages(get, path, key=None):
    for page in range(1, 101):
        result = get(path + ('&' if '?' in path else '?') + f'per_page=100&page={page}')
        rows = result[key] if key else result
        yield from rows
        if len(rows) < 100:
            return
    raise ValueError('Pagination incomplete; refusing a partial operational snapshot')


def blob(get, base, path, sha):
    if not re.fullmatch('[0-9a-f]{40}', sha):
        raise ValueError('Read requires an exact commit')
    if path.startswith('/') or '..' in path.split('/'):
        raise ValueError('Unsafe repository path')
    obj = get(base + '/contents/' + urllib.parse.quote(path, safe='/') + '?ref=' + sha)
    if obj.get('encoding') != 'base64':
        raise ValueError('Missing complete file bytes: ' + path)
    raw = base64.b64decode(obj['content'])
    if obj.get('size', len(raw)) != len(raw):
        raise ValueError('Incomplete file: ' + path)
    return raw


def head(get, base, branch):
    return get(base + '/branches/' + urllib.parse.quote(branch, safe=''))['commit']['sha']


def check_state(checks):
    # Latest check of each name/app wins; a newer pending run supersedes old green.
    latest = {}
    for c in checks:
        key = (c['name'], (c.get('app') or {}).get('id'))
        if c['id'] > latest.get(key, {}).get('id', -1):
            latest[key] = c
    rows = list(latest.values())
    if any(c['status'] != 'completed' for c in rows):
        return 'RUNNING'
    if any(c.get('conclusion') in {'failure', 'timed_out', 'action_required', 'cancelled', 'stale'} for c in rows):
        return 'BLOCKED'
    gate = [c for c in rows if c['name'] == 'merge-gate' and (c.get('app') or {}).get('slug') == 'github-actions']
    return 'TECHNICAL_PASS' if gate and all(c.get('conclusion') == 'success' for c in gate) else 'NOT_VERIFIED'


def collect(get, config):
    repo = config['repository']
    if repo != 'IgorSabirov/vm-lab':
        raise ValueError('Wrong repository')
    base = '/repos/' + repo
    anchor = config['anchor_branch']
    a_sha = head(get, base, anchor)
    read = lambda path, sha: json.loads(blob(get, base, path, sha))
    control = read(config['control_path'], a_sha)
    active = control['active_branch']
    b_sha = head(get, base, active)
    active_control = read(config['control_path'], b_sha)
    ledger = read(config['ledger_path'], a_sha)
    pipe = config['pipeline_directory']
    pipeline, request, current = [read(pipe + '/' + name + '.json', b_sha)
                                  for name in ('PIPELINE', 'RUN_REQUEST', 'CURRENT')]
    blockers = []
    for key in ('policy_version', 'controller_source_commit', 'limits', 'active_branch', 'active_pr'):
        if control.get(key) != active_control.get(key):
            blockers.append('CONTROL mismatch: ' + key)
    if control.get('policy_version') != ledger.get('policy_version'):
        blockers.append('Ledger policy mismatch')
    if control.get('limits', {}).get('new_packages_per_rolling_24h') is not None:
        blockers.append('Obsolete daily quota still configured')
    runs = {}
    for status in ACTIVE:  # All ages, all workflows. No rolling time window.
        for run in pages(get, base + '/actions/runs?status=' + status, 'workflow_runs'):
            runs[run['id']] = {k: run.get(k) for k in ('id', 'name', 'head_sha', 'head_branch', 'status', 'html_url')}
    reservations = [p for p in ledger['packages'] if p.get('status') not in TERMINAL and not p.get('result_sha')]
    evidence, pending = [], []
    for stage in pipeline['stages']:
        if stage['kind'] != 'import':
            pending.append({'id': stage['id'], 'missing': stage.get('missing', []), 'next': stage.get('next'),
                            'execution_enabled': stage.get('execution_enabled', False)})
            continue
        record = {'id': stage['id'], 'ref': b_sha, 'receipt_hashes_match': True,
                  'raw_artifacts_reverified': False, 'scientific_acceptance': None}
        for kind, field in (('summary', 'summary'), ('manifest', 'manifest')):
            pin = stage[field]
            raw = blob(get, base, pin['path'], b_sha)
            digest = hashlib.sha256(raw).hexdigest()
            record[kind] = {'path': pin['path'], 'sha256': digest, 'expected_sha256': pin['sha256']}
            if digest != pin['sha256']:
                record['receipt_hashes_match'] = False
                blockers.append('Receipt hash mismatch: ' + stage['id'] + '/' + kind)
            if kind == 'summary':
                summary = json.loads(raw)
                record.update(engineering=summary.get('engineering_status', summary.get('status')),
                              science=summary.get('scientific_status', summary.get('numerical_status')),
                              scientific_acceptance=summary.get('scientific_acceptance'),
                              contract_status=summary.get(stage['status_field']))
                record['expected_status'] = stage['expected_status']
        evidence.append(record)
    prs = []
    for pr in pages(get, base + '/pulls?state=open'):
        sha = pr['head']['sha']
        checks = list(pages(get, base + '/commits/' + sha + '/check-runs', 'check_runs'))
        state = check_state(checks)
        scientific = pr['head']['ref'].startswith(('science/', 's0-'))
        next_action = ('Finish current checks' if state == 'RUNNING' else
                       'Inspect failed or blocked checks' if state == 'BLOCKED' else
                       'Review contract/evidence; owner decides scientific acceptance' if scientific else
                       'Review proposal and decide integration')
        prs.append({'number': pr['number'], 'title': pr['title'], 'sha': sha, 'branch': pr['head']['ref'],
                    'base': pr['base']['ref'], 'draft': pr['draft'], 'url': pr['html_url'],
                    'technical': state, 'scientific_acceptance': 'NOT_INFERRED', 'next_action': next_action})
    active_pr = next((p for p in prs if p['number'] == control['active_pr']), None)
    if not active_pr or active_pr['sha'] != b_sha or active_pr['branch'] != active:
        blockers.append('Active PR does not match CONTROL branch/head')
    # Branches can advance while reading. Never present a mixed snapshot as stable.
    if head(get, base, anchor) != a_sha or head(get, base, active) != b_sha:
        blockers.append('Control branch moved during observation; collect again')
    return {'schema': 'vm-lab-operations-view-v1', 'observed_utc': datetime.now(timezone.utc).isoformat(),
            'anchor': {'branch': anchor, 'sha': a_sha}, 'active': {'branch': active, 'sha': b_sha, 'pr': control['active_pr']},
            'policy_version': control.get('policy_version'), 'queue': control['queue'],
            'request': request, 'current': current, 'ledger': ledger['packages'],
            'active_reservations': reservations, 'active_actions': list(runs.values()),
            'evidence': evidence, 'pending_science': pending, 'pull_requests': prs,
            'blockers': blockers, 'snapshot_consistent': not blockers,
            'dispatch_authority': False, 'scientific_status_modified': False}


def cell(value):
    return str(value).replace('|', '\\|').replace('\n', ' ').replace('<', '&lt;').replace('>', '&gt;')


def render(value):
    rows = ['# Research operations', '', 'Observed: ' + value['observed_utc'], '',
            f"Active: PR #{value['active']['pr']} · `{value['active']['sha']}`.",
            'Queue: **' + cell(value['queue']['status']) + '** — ' + cell(value['queue'].get('reason', '')), '',
            f"Active Actions (all workflows): {len(value['active_actions'])}; outstanding reservations: {len(value['active_reservations'])}.",
            'This view cannot admit work, merge science or change acceptance.', '',
            '## Published evidence', '',
            'Receipt hashes are checked here; raw artifact/domain checks remain in the linked evidence.', '',
            '| Stage | Receipt hashes | Engineering | Scientific result | Evidence |', '|---|---|---|---|---|']
    for e in value['evidence']:
        url = 'https://github.com/IgorSabirov/vm-lab/blob/' + e['ref'] + '/' + e['summary']['path']
        rows.append(f"| {cell(e['id'])} | {'MATCH' if e['receipt_hashes_match'] else 'MISMATCH'} | {cell(e['engineering'])} | {cell(e['science'])} | [SUMMARY]({url}) |")
    rows += ['', '## Work in progress', '', '| PR | Base | Technical checks at exact HEAD | Next action |', '|---|---|---|---|']
    for p in value['pull_requests']:
        rows.append(f"| [#{p['number']}]({p['url']}){' draft' if p['draft'] else ''} | {cell(p['base'])} | {p['technical']} · `{p['sha'][:12]}` | {cell(p['next_action'])} |")
    rows += ['', '## Unfinished scientific contracts', '']
    rows += ['- ' + cell(s['id']) + ': ' + cell('; '.join(s['missing']) or s['next']) for s in value['pending_science']]
    rows += ['', '## Operational inconsistencies', '']
    rows += ['- ' + cell(b) for b in value['blockers']] or ['None detected in this snapshot. This is not scientific acceptance.']
    return '\n'.join(rows) + '\n'


def request(path):
    headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}
    if os.environ.get('GH_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['GH_TOKEN']
    with urllib.request.urlopen(urllib.request.Request('https://api.github.com' + path, headers=headers), timeout=30) as r:
        return json.load(r)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--output', type=Path, default=Path('project-evidence'))
    args = ap.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + 240
    def bounded_request(path):
        if time.monotonic() >= deadline:
            raise TimeoutError('Observation budget exhausted')
        return request(path)
    try:
        value = collect(bounded_request, json.loads((ROOT / 'infra/OPERATIONS.json').read_text()))
        text = render(value)
    except Exception as exc:
        value = {'snapshot_consistent': False, 'error_type': type(exc).__name__, 'dispatch_authority': False}
        text = '# Research operations\n\nINCOMPLETE: ' + type(exc).__name__ + '. No admission or acceptance inferred.\n'
    (args.output / 'OPERATIONS_STATUS.json').write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    (args.output / 'OPERATIONS_STATUS.md').write_text(text)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream: stream.write(text)
    print(text)
    if not value['snapshot_consistent']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
