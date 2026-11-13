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
from pathlib import Path, PurePosixPath
import re
import urllib.error
import urllib.request
from urllib.parse import quote, urlsplit

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
        elif s['kind'] == 'publication':
            validate_publication(s, root)
        else:
            raise ValueError('Unknown source kind')
        if s['last_verified_sha'] is not None and not s.get('verification_evidence'):
            raise ValueError('Verification requires evidence, not metadata inspection')
        if not s.get('license_status') or not s.get('links'):
            raise ValueError('License assessment and typed links are required')
        if s.get('resource_manifest'):
            if s['resource_manifest'] not in s.get('managed_sources', []):
                raise ValueError('Resource manifest must be tracked in the registry graph')
            resolve_resources(s, root)
        c = json.loads(local(root, s['contract']).read_text())
        if c['source_id'] != s['id']:
            raise ValueError('Contract/source mismatch')
        if s.get('resource_manifest') and c.get('resource_manifest') != s['resource_manifest']:
            raise ValueError('Contract/resource manifest mismatch')
        validate_contract(c)
    return rows


def resolve_resources(source, root=ROOT):
    """Resolve metadata to immutable upstream URLs; never fetch or execute code."""
    if (source.get('kind') != 'github'
            or not REPO.fullmatch(source.get('repository', ''))
            or not SHA.fullmatch(source.get('source_sha', ''))
            or not SHA.fullmatch(source.get('source_tree_sha', ''))):
        raise ValueError('Resources require a pinned GitHub source')
    path = source.get('resource_manifest')
    if not path:
        raise ValueError('Source has no resource manifest')
    manifest = json.loads(local(root, path).read_text())
    if manifest.get('schema') != 'vm-lab-external-resources-v1':
        raise ValueError('Unknown resource manifest schema')
    identity = {'source_id': source['id'], 'repository': source['repository'],
                'source_sha': source['source_sha'], 'source_tree_sha': source['source_tree_sha']}
    if any(manifest.get(key) != value for key, value in identity.items()):
        raise ValueError('Resource manifest identity differs from source pin')
    if manifest.get('storage_policy') != 'UPSTREAM_LINKS_ONLY_NO_VENDORED_CODE_OR_DATA':
        raise ValueError('Resources must be references, not vendored data')
    resources = manifest.get('resources')
    if not isinstance(resources, list) or not resources:
        raise ValueError('Resources must be a nonempty list')
    seen_ids, seen_paths, resolved = set(), set(), []
    for resource in resources:
        if set(resource) != {'id', 'path', 'role', 'type', 'git_sha'}:
            raise ValueError('Resource fields must contain only identity and role')
        ident, name = resource['id'], resource['path']
        if not isinstance(ident, str) or not re.fullmatch(r'[a-z][a-z0-9_]*', ident) or ident in seen_ids:
            raise ValueError('Invalid or duplicate resource ID')
        if not isinstance(name, str) or not name or name != name.strip():
            raise ValueError('Invalid resource path')
        p = PurePosixPath(name)
        if (p.is_absolute() or '..' in p.parts or '.' in p.parts
                or str(p) != name or any(c in name for c in '\\?#%')
                or any(ord(c) < 32 for c in name) or name in seen_paths):
            raise ValueError('Invalid or duplicate resource path')
        if resource['type'] not in {'blob', 'tree'} or not isinstance(resource['git_sha'], str) or not SHA.fullmatch(resource['git_sha']):
            raise ValueError('Resource needs an exact Git blob/tree identity')
        if not isinstance(resource['role'], str) or not resource['role'].strip():
            raise ValueError('Resource role is required')
        seen_ids.add(ident); seen_paths.add(name)
        url = 'https://github.com/' + source['repository'] + '/' + resource['type'] + '/' + source['source_sha'] + '/' + quote(name, safe='/')
        resolved.append({**resource, 'url': url})
    for ref in manifest.get('project_references', []):
        if not local(root, ref).is_file():
            raise ValueError('Missing local project reference')
    return {'schema': 'vm-lab-resolved-resources-v1', **identity,
            'resource_manifest': path, 'resources': resolved,
            'interface': manifest.get('interface', {}),
            'project_references': manifest.get('project_references', []),
            'execution_performed': False, 'scientific_status_promoted': False}


def validate_publication(s, root):
    """Pin publication metadata without inventing an upstream Git commit/archive."""
    url = urlsplit(s['paper'])
    version = s.get('publication_version')
    if (url.scheme != 'https' or not url.hostname or url.username or url.password
            or not version or version not in url.path):
        raise ValueError('Publication needs an explicit versioned HTTPS URL')
    if any(s.get(k) is not None for k in ('source_sha', 'source_tree_sha', 'source_archive', 'source_archive_sha256', 'last_verified_sha')):
        raise ValueError('Publication record is not an upstream Git commit or archive')
    if s.get('monitor_enabled') is not False:
        raise ValueError('GitHub upstream monitor cannot monitor publication versions')
    raw = local(root, s['source_record']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != s['source_record_sha256']:
        raise ValueError('Publication source record hash mismatch')
    record = json.loads(raw)
    if (record.get('source_id') != s['id'] or record.get('version') != version
            or record.get('url') != s['paper']):
        raise ValueError('Publication identity differs from its source record')


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
    p.add_argument('command', choices=['validate', 'monitor', 'resources'])
    p.add_argument('source_id', nargs='?', help='Registered source ID for resources')
    p.add_argument('--output', type=Path, default=Path('external-evidence'))
    a = p.parse_args()
    if (a.command == 'resources') != (a.source_id is not None):
        p.error('resources requires SOURCE_ID; validate/monitor take no source ID')
    rows = validate()
    if a.command == 'validate':
        print(json.dumps({'status': 'PASS', 'sources': len(rows), 'scientific_status_promoted': False}))
    elif a.command == 'resources':
        source = next((row for row in rows if row['id'] == a.source_id), None)
        if source is None:
            p.error('Unknown registered source ID')
        print(json.dumps(resolve_resources(source), ensure_ascii=False, indent=2))
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
