#!/usr/bin/env python3
"""Validate declared external sources and inspect upstream metadata; never run it.

Scientific states, accepted source SHAs and tolerances are never changed here.
The existing FOUR_CANDIDATE SOURCE_INDEX is the only source of registrations.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
INDEX = 'analysis/FOUR_CANDIDATE_INTEGRATION_20261108/SOURCE_INDEX.json'
SHA = re.compile(r'[a-f0-9]{40}')
REPO = re.compile(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+')
MODES = {'engineering_check', 'exploratory', 'confirmatory'}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def local(root, name):
    p = Path(name)
    if p.is_absolute() or '..' in p.parts:
        raise ValueError('Only repository-relative paths are allowed')
    out = root / p
    if not out.resolve().is_relative_to(root.resolve()) or out.is_symlink():
        raise ValueError('Path escapes repository or is a symlink')
    return out


def validate_contract(c):
    if c['analysis_mode'] not in MODES or c['state'] not in {'DRAFT', 'READY'}:
        raise ValueError('Unknown analysis mode or contract state')
    if not c.get('question') or not c.get('scope_limit') or not c.get('decision_points'):
        raise ValueError('Question, scope and analysis choices are required')
    if c['analysis_mode'] == 'confirmatory' and c.get('outcomes_already_inspected') is not False:
        raise ValueError('Known outcomes cannot be silently called confirmatory')
    if c.get('acm_badge_awarded') is not False:
        raise ValueError('Internal checks do not award an ACM badge')
    if c['state'] == 'DRAFT':
        if c.get('execution_enabled') is not False:
            raise ValueError('Draft contracts cannot execute')
        return
    if not c.get('criteria') or not c.get('pre_execution_receipt_required'):
        raise ValueError('Ready contracts need frozen criteria and a pre-execution receipt')
    ids = set()
    for row in c['criteria']:
        if row['id'] in ids:
            raise ValueError('Duplicate criterion')
        ids.add(row['id'])
        if not row.get('observable') or not row.get('tolerance_basis') or not row.get('failure_rule'):
            raise ValueError('Criterion must be interpretable before execution')
        for field in ('absolute_tolerance', 'relative_tolerance'):
            v = row[field]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
                raise ValueError('Tolerance must be finite and nonnegative')
    if not 0 < c['budget']['max_seconds'] <= 600:
        raise ValueError('This bounded runner is for <=600 second controls only')
    if len(c.get('numerical_configurations', [])) < 2:
        raise ValueError('Declare two configurations or keep contract in DRAFT')


def validate(root=ROOT):
    index = json.loads((root / INDEX).read_text())
    rows = index['external_integrations']
    ids = set()
    for s in rows:
        if not re.fullmatch(r'[A-Z][A-Z0-9_]*', s['id']) or s['id'] in ids:
            raise ValueError('Invalid or duplicate source ID')
        ids.add(s['id'])
        if s['upstream_update_policy'] != 'REPORT_ONLY_REVIEW_REQUIRED':
            raise ValueError('Scientific sources must not automatically advance')
        if s['kind'] == 'github':
            if not REPO.fullmatch(s['repository']) or not SHA.fullmatch(s['source_sha']) or not SHA.fullmatch(s['source_tree_sha']):
                raise ValueError('Full source commit and tree identities are required')
        elif s['kind'] == 'archive':
            raw = local(root, s['source_archive']).read_bytes()
            if hashlib.sha256(raw).hexdigest() != s['source_archive_sha256']:
                raise ValueError('Archive hash mismatch')
        else:
            raise ValueError('Unknown source kind')
        if s['last_verified_sha'] is not None and not s.get('verification_evidence'):
            raise ValueError('Verification requires evidence, not metadata inspection')
        if not s.get('license_status') or not s.get('links'):
            raise ValueError('License assessment and typed links are required')
        c = json.loads(local(root, s['contract']).read_text())
        if c['source_id'] != s['id']:
            raise ValueError('Contract/source mismatch')
        validate_contract(c)
    return rows


def github_get(path):
    if not path.startswith('/repos/') or '..' in path or '?' in path:
        raise ValueError('Unexpected GitHub API path')
    headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'vm-lab-upstream-monitor', 'X-GitHub-Api-Version': '2022-11-28'}
    token = os.environ.get('GH_TOKEN')
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request('https://api.github.com' + path, headers=headers)
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.load(response)


def inspect(rows, get=github_get):
    changes, errors = [], []
    for s in rows:
        if s['kind'] != 'github' or not s['monitor_enabled']:
            continue
        try:
            repo = get('/repos/' + s['repository'])
            branch = repo['default_branch']
            if not re.fullmatch(r'[A-Za-z0-9_./-]+', branch):
                raise ValueError('Invalid upstream branch')
            head = get('/repos/' + s['repository'] + '/commits/' + branch)
            if not SHA.fullmatch(head['sha']):
                raise ValueError('Invalid upstream SHA')
            if head['sha'] != s['source_sha']:
                comparison = get('/repos/' + s['repository'] + '/compare/' + s['source_sha'] + '...' + head['sha'])
                files = comparison.get('files', [])
                changes.append({'source_id': s['id'], 'repository': s['repository'],
                                'pinned_source_sha': s['source_sha'], 'observed_sha': head['sha'],
                                'observed_tree_sha': head['commit']['tree']['sha'],
                                'compare_url': 'https://github.com/' + s['repository'] + '/compare/' + s['source_sha'] + '...' + head['sha'],
                                'relation': comparison['status'], 'changed_files': [x['filename'] for x in files],
                                'file_list_may_be_truncated': len(files) >= 300,
                                'license_metadata': (repo.get('license') or {}).get('spdx_id'),
                                'affected_registry_nodes': s['links'],
                                'scientific_status_promoted': False})
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as e:
            errors.append({'source_id': s['id'], 'error_type': type(e).__name__, 'message': str(e)[:300]})
    return {'schema': 'vm-lab-upstream-observations-v1', 'changes': changes, 'errors': errors,
            'fingerprint': digest(changes), 'accepted_sources_modified': False}


def markdown(report):
    lines = ['# Изменения внешних источников', '', 'Автоматический отчёт о метаданных; внешний код не исполнялся. Закреплённые SHA и научные статусы не изменены.', '',
             '| Источник | Закреплено → обнаружено | Связанные карточки |', '|---|---|---|']
    for c in report['changes']:
        lines.append(f"| {c['source_id']} | [{c['pinned_source_sha'][:8]} → {c['observed_sha'][:8]}]({c['compare_url']}) | {', '.join(c['affected_registry_nodes'])} |")
    if not report['changes']:
        lines += ['', 'Изменений не обнаружено в успешно опрошенных источниках.']
    if report['errors']:
        lines += ['', 'Ошибки чтения (не трактовать как отсутствие обновлений):', *['- ' + e['source_id'] + ': ' + e['error_type'] for e in report['errors']]]
    return '\n'.join(lines) + '\n'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=['validate', 'monitor'])
    p.add_argument('--output', type=Path, default=Path('external-evidence'))
    a = p.parse_args()
    rows = validate()
    if a.command == 'validate':
        print(json.dumps({'status': 'PASS', 'sources': len(rows), 'scientific_status_promoted': False}))
    else:
        result = inspect(rows)
        a.output.mkdir(parents=True, exist_ok=True)
        (a.output / 'UPSTREAM.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        (a.output / 'UPSTREAM.md').write_text(markdown(result))
        print(json.dumps({'changes': len(result['changes']), 'errors': len(result['errors'])}))
        if result['errors']:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
