#!/usr/bin/env python3
"""Durable, data-only thematic review delivery; never execute model output."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import quote

from copilot_thematic_events import GitHub

BRANCH = 'copilot/thematic-reports'
PREFIX = 'infra/copilot/reports/thematic'
STATE = PREFIX + '/MONITOR.json'
MARKER = '<!-- vm-lab:copilot-thematic-report -->'
SCHEMA = 'vm-lab-thematic-attempt-v1'
ROOT_FILES = {'EVENTS.json', 'CONTEXT.json', 'COVERAGE.json', 'ATTEMPT.json',
              'CORPUS_MANIFEST.json', 'PREPARATION_FAILURE.json',
              'REPORT.md', 'ANALYSIS.json', 'RECEIPT.json'}
BATCH_FILE = re.compile(r'batches/[0-9]{4,6}/(?:RAW_RESPONSE\.txt|RESPONSE\.json|RECEIPT\.json|PROMPT\.txt|STDERR\.txt)$')
HEX40 = re.compile(r'[a-f0-9]{40}')
HEX64 = re.compile(r'[a-f0-9]{64}')
STORAGE_SCHEMA = 'vm-lab-split-utf8-v1'
STORAGE_PART_BYTES = 1_000_000
STORAGE_PART_WIRE_BYTES = 1_500_000


def encoded(value):
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n'


def digest(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def blob_sha(value):
    raw = value.encode()
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def exact_text(path):
    return Path(path).read_bytes().decode('utf-8')


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encoded(value))


def storage_parts(text):
    """Split exact UTF-8 bytes, also bounding JSON escaping in API requests."""
    raw = text.encode('utf-8')
    start = 0
    while start < len(raw):
        end = min(start + STORAGE_PART_BYTES, len(raw))
        while True:
            while end < len(raw) and end > start and raw[end] & 0xC0 == 0x80:
                end -= 1
            if end <= start:
                raise ValueError('Storage transport cannot fit one UTF-8 character')
            part = raw[start:end].decode('utf-8')
            if len(json.dumps(part, ensure_ascii=False).encode()) <= STORAGE_PART_WIRE_BYTES:
                break
            end = start + (end - start) // 2
        yield part
        start = end


def storage_files(files):
    """Map logical files to small physical files without changing logical bytes.

The original path contains either its ordinary text or an explicit storage
manifest. Replacing that same path makes small/large transitions unambiguous;
old immutable parts can remain in history without shadowing the current file.
"""
    physical = {}
    for path, text in sorted(files.items()):
        raw = text.encode('utf-8')
        if (len(raw) <= STORAGE_PART_BYTES and
                len(json.dumps(text, ensure_ascii=False).encode()) <= STORAGE_PART_WIRE_BYTES and
                not text.startswith('{\n  "schema": "' + STORAGE_SCHEMA + '"')):
            physical[path] = text
            continue
        full_digest = digest(raw)
        parts = []
        for number, part in enumerate(storage_parts(text), 1):
            part_path = path + '.parts/' + full_digest + f'/{number:06d}.txt'
            if part_path in files:
                raise ValueError('Logical file overlaps generated storage parts')
            physical[part_path] = part
            parts.append({'path': part_path, 'size_bytes': len(part.encode('utf-8')),
                          'sha256': digest(part), 'git_blob_sha': blob_sha(part)})
        # Keep schema first: readers identify the small manifest before parsing
        # an ordinary (possibly historical and large) JSON document.
        manifest = {'schema': STORAGE_SCHEMA, 'logical_path': path, 'encoding': 'utf-8',
                    'size_bytes': len(raw), 'sha256': full_digest, 'git_blob_sha': blob_sha(text),
                    'parts': parts}
        physical[path] = json.dumps(manifest, ensure_ascii=False, indent=2) + '\n'
    return physical


def restore_stored(api, path, text):
    """Verify every part and reconstruct the original logical file as UTF-8."""
    if not text.startswith('{\n  "schema": "' + STORAGE_SCHEMA + '"'):
        return text
    manifest = json.loads(text)
    if (manifest.get('schema') != STORAGE_SCHEMA or manifest.get('logical_path') != path or
            manifest.get('encoding') != 'utf-8' or type(manifest.get('size_bytes')) is not int or
            manifest['size_bytes'] < 0 or not HEX64.fullmatch(manifest.get('sha256', '')) or
            not HEX40.fullmatch(manifest.get('git_blob_sha', '')) or
            not isinstance(manifest.get('parts'), list) or not manifest['parts']):
        raise ValueError('Invalid UTF-8 storage manifest: ' + path)
    parts = []
    total = 0
    for number, item in enumerate(manifest['parts'], 1):
        expected = path + '.parts/' + manifest['sha256'] + f'/{number:06d}.txt'
        if (not isinstance(item, dict) or item.get('path') != expected or
                type(item.get('size_bytes')) is not int or not 0 < item['size_bytes'] <= STORAGE_PART_BYTES or
                not HEX40.fullmatch(item.get('git_blob_sha', '')) or not HEX64.fullmatch(item.get('sha256', ''))):
            raise ValueError('Invalid UTF-8 storage part identity: ' + path)
        part = api.blob(item['git_blob_sha'])
        raw = part.encode('utf-8')
        if (len(raw) != item['size_bytes'] or digest(raw) != item['sha256'] or
                blob_sha(part) != item['git_blob_sha']):
            raise ValueError('Stored UTF-8 part digest mismatch: ' + path)
        parts.append(part)
        total += len(raw)
        if total > manifest['size_bytes']:
            raise ValueError('Stored UTF-8 parts exceed logical size: ' + path)
    result = ''.join(parts)
    if (total != manifest['size_bytes'] or digest(result) != manifest['sha256'] or
            blob_sha(result) != manifest['git_blob_sha']):
        raise ValueError('Reconstructed logical file digest mismatch: ' + path)
    return result


def optional(api, path):
    try:
        return api.get(path)
    except Exception as exc:
        if getattr(exc, 'code', getattr(exc, 'status', None)) == 404:
            return None
        raise


def file_at(api, ref, path):
    item = optional(api, 'contents/' + quote(path, safe='/') + '?ref=' + quote(ref, safe=''))
    if item is None:
        return None
    text = (base64.b64decode(item['content']).decode('utf-8')
            if item.get('encoding') == 'base64' else api.blob(item['sha']))
    return restore_stored(api, path, text)


def head(api):
    item = optional(api, 'git/ref/heads/' + BRANCH)
    return item['object']['sha'] if item else None


def report_entries(api, ref):
    """Read only the report subtree, avoiding huge historical experiment trees."""
    cursor = ref
    for component in PREFIX.split('/'):
        tree = api.get('git/trees/' + cursor)
        row = next((x for x in tree['tree'] if x['path'] == component), None)
        if not row or row.get('type') != 'tree':
            raise ValueError('Published report tree is missing: ' + component)
        cursor = row['sha']
    tree = api.get('git/trees/' + cursor)
    if tree.get('truncated'):
        raise ValueError('Incomplete report directory listing')
    return tree['tree']


def verify_written(api, commit_sha, files):
    physical = storage_files(files)
    entries = report_entries(api, commit_sha)
    actual = {PREFIX + '/' + row['path']: row['sha'] for row in entries if row['type'] == 'blob'}
    packages = {path[len(PREFIX) + 1:].split('/')[0] for path in physical
                if path != STATE and not path.startswith(STATE + '.parts/')}
    for package in packages:
        row = next((x for x in entries if x['path'] == package and x['type'] == 'tree'), None)
        if row is None:
            raise ValueError('Missing published package directory')
        for item in api.tree(row['sha']):
            if item['type'] == 'blob':
                actual[PREFIX + '/' + package + '/' + item['path']] = item['sha']
    # MONITOR may eventually need parts too. It is directly under PREFIX rather
    # than inside an immutable package directory.
    if any(path.startswith(STATE + '.parts/') for path in physical):
        row = next((x for x in entries if x['path'] == 'MONITOR.json.parts' and x['type'] == 'tree'), None)
        if row is None:
            raise ValueError('Missing published monitor parts')
        for item in api.tree(row['sha']):
            if item['type'] == 'blob':
                actual[STATE + '.parts/' + item['path']] = item['sha']
    for path, value in physical.items():
        if actual.get(path) != blob_sha(value):
            raise ValueError('Published file readback failed: ' + path)


def write_commit(api, files, source_sha, message):
    """Only append report data. A changed parent is an error, never a force push."""
    if not HEX40.fullmatch(source_sha):
        raise ValueError('Exact trusted source SHA required')
    for path, value in files.items():
        if not path.startswith(PREFIX + '/') or '..' in Path(path).parts:
            raise ValueError('Publisher path outside fixed report directory')
        if not isinstance(value, str):
            raise ValueError('Publisher accepts only UTF-8 report data')
        if re.search(r'(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]+', value):
            raise ValueError('Credential-shaped report data')
    previous = head(api)
    parent = previous or source_sha
    commit = api.get('git/commits/' + parent)
    entries = []
    for path, value in sorted(storage_files(files).items()):
        entry = {'path': path, 'mode': '100644', 'type': 'blob'}
        # Both ordinary small files and storage parts fit bounded tree requests;
        # never send a large logical CONTEXT through POST /git/blobs again.
        entry['content'] = value
        entries.append(entry)
    tree_sha, group, byte_count = commit['tree']['sha'], [], 0
    for entry in entries:
        size = len(json.dumps(entry, ensure_ascii=False).encode())
        if group and byte_count + size > 3_000_000:
            tree_sha = api.request('POST', 'git/trees', {'base_tree': tree_sha, 'tree': group})['sha']
            group, byte_count = [], 0
        group.append(entry)
        byte_count += size
    if group:
        tree_sha = api.request('POST', 'git/trees', {'base_tree': tree_sha, 'tree': group})['sha']
    made = api.request('POST', 'git/commits', {'message': message, 'tree': tree_sha, 'parents': [parent]})
    if previous is None:
        api.request('POST', 'git/refs', {'ref': 'refs/heads/' + BRANCH, 'sha': made['sha']})
    else:
        if head(api) != previous:
            raise ValueError('Report branch moved; preserve this artifact and retry publication')
        api.request('PATCH', 'git/refs/heads/' + BRANCH, {'sha': made['sha'], 'force': False})
    if head(api) != made['sha']:
        raise ValueError('Published branch readback failed')
    verify_written(api, made['sha'], files)
    return made['sha']


def output_fields(values):
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
            for key, value in values.items():
                value = str(value)
                if '\n' in value or '\r' in value:
                    raise ValueError('Multiline workflow output')
                stream.write(key + '=' + value + '\n')
    print(json.dumps(values, ensure_ascii=False))


def monitor(api):
    raw = file_at(api, BRANCH, STATE)
    return json.loads(raw) if raw else {}


def archived_files(api, package):
    ref = head(api)
    if ref is None:
        raise ValueError('Reserved report branch is missing')
    files = {}
    row = next((x for x in report_entries(api, ref) if x['path'] == package and x['type'] == 'tree'), None)
    if row is None:
        raise ValueError('Reserved package directory is missing')
    for item in api.tree(row['sha']):
        if item.get('type') != 'blob':
            continue
        name = item['path']
        if name in ROOT_FILES or BATCH_FILE.fullmatch(name):
            files[name] = restore_stored(api, PREFIX + '/' + package + '/' + name, api.blob(item['sha']))
    return files


def restore_inputs(api, package, directory):
    files = archived_files(api, package)
    for name in ('EVENTS.json', 'CONTEXT.json', 'ATTEMPT.json'):
        if name not in files:
            raise ValueError('Reserved input missing: ' + name)
    for name, raw in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw.encode('utf-8'))


def reserve(api, directory, run_id, source_sha):
    directory = Path(directory)
    events = load(directory / 'EVENTS.json')
    state = monitor(api)
    next_state = {**state, **events.get('next_state', {})}
    next_state['attempts'] = state.get('attempts', {})
    package = events.get('package_id') or ''
    if package and not HEX64.fullmatch(package):
        raise ValueError('Invalid content package identity')
    if not package:
        pending = [(key, value) for key, value in next_state['attempts'].items()
                   if value.get('status') in ('RESERVED', 'GENERATED') or
                   value.get('status') == 'PUBLISHED_INCOMPLETE' and
                   value.get('last_recovery_source_sha') != source_sha]
        if pending:
            # A recovery never supplies the Copilot token and never repeats inference.
            package, old = sorted(pending, key=lambda item: str(item[1].get('run_id', '')))[0]
            restore_inputs(api, package, directory)
            return {'mode': 'recover', 'package_id': package, 'original_run_id': old['run_id'],
                    'base_sha': old['source_sha']}
        if next_state != state:
            write_commit(api, {STATE: encoded(next_state)}, source_sha, 'Copilot thematic monitor: record observed baseline')
        return {'mode': 'skipped', 'package_id': '', 'original_run_id': '', 'base_sha': source_sha}
    old = next_state['attempts'].get(package)
    if old:
        if old.get('status') == 'DELIVERED' or (old.get('status') == 'PUBLISHED_INCOMPLETE' and
                                               old.get('last_recovery_source_sha') == source_sha):
            if next_state != state:
                write_commit(api, {STATE: encoded(next_state)}, source_sha, 'Copilot thematic monitor: deduplicate observed update')
            return {'mode': 'skipped', 'package_id': package, 'original_run_id': old['run_id'], 'base_sha': old['source_sha']}
        restore_inputs(api, package, directory)
        return {'mode': 'recover', 'package_id': package, 'original_run_id': old['run_id'], 'base_sha': old['source_sha']}
    context = load(directory / 'CONTEXT.json')
    if context.get('package_id') != package or events.get('source_sha') != source_sha:
        raise ValueError('Package/source identity mismatch before inference')
    attempt = {'schema': SCHEMA, 'package_id': package, 'source_sha': source_sha,
               'run_id': str(run_id), 'status': 'RESERVED',
               'events_sha256': digest((directory / 'EVENTS.json').read_bytes()),
               'context_sha256': digest((directory / 'CONTEXT.json').read_bytes()),
               'reserved_before_inference': True, 'scientific_acceptance': False}
    if (directory / 'CORPUS_MANIFEST.json').is_file():
        attempt['manifest_sha256'] = digest((directory / 'CORPUS_MANIFEST.json').read_bytes())
    save(directory / 'ATTEMPT.json', attempt)
    next_state['attempts'][package] = {key: attempt[key] for key in ('run_id', 'source_sha', 'status')}
    files = {PREFIX + '/' + package + '/' + name: exact_text(directory / name)
             for name in ('EVENTS.json', 'CONTEXT.json', 'ATTEMPT.json')}
    if 'manifest_sha256' in attempt:
        files[PREFIX + '/' + package + '/CORPUS_MANIFEST.json'] = exact_text(directory / 'CORPUS_MANIFEST.json')
    files[STATE] = encoded(next_state)
    write_commit(api, files, source_sha, 'Copilot thematic review: reserve ' + package[:16] + ' before inference')
    return {'mode': 'generate', 'package_id': package, 'original_run_id': str(run_id), 'base_sha': source_sha}


def collected_files(directory):
    files = {}
    for path in Path(directory).rglob('*'):
        if path.is_symlink():
            raise ValueError('Symlink in saved model output')
        if not path.is_file():
            continue
        name = path.relative_to(directory).as_posix()
        if name in ROOT_FILES or BATCH_FILE.fullmatch(name):
            files[name] = exact_text(path)
    return files


def ensure_pr(api, repository, run_id, package, commit_sha, complete):
    owner = repository.split('/')[0]
    prs = api.pages('pulls?state=open&head=' + quote(owner + ':' + BRANCH, safe='') + '&per_page=100')
    if len(prs) > 1:
        raise ValueError('Ambiguous thematic report PR')
    url = 'https://github.com/' + repository
    body = (MARKER + '\n\nАвтоматические тематические отчёты Copilot по обновлениям научного корпуса. '
            'Документы передаются без ручного тематического отбора. Связи, противоречия и новые вопросы '
            'остаются предложениями до научной приёмки владельцем.\n\n'
            'Последний пакет: `' + package + '`. Полный проход: **' + ('да' if complete else 'нет; см. квитанцию') + '**.\n\n'
            '[Отчёт](' + url + '/blob/' + commit_sha + '/' + PREFIX + '/' + package + '/REPORT.md) · '
            '[Квитанция](' + url + '/blob/' + commit_sha + '/' + PREFIX + '/' + package + '/RECEIPT.json)\n\n'
            'Run: ' + url + '/actions/runs/' + str(run_id) + '\n\n'
            'Ветка хранит исходные пакеты, сырые ответы и историю отчётов; не меняет научные статусы и исходные реестры.')
    fields = {'title': '[Copilot] Тематическая проверка научных обновлений', 'body': body}
    if prs:
        pr = api.request('PATCH', 'pulls/' + str(prs[0]['number']), fields)
    else:
        pr = api.request('POST', 'pulls', {**fields, 'head': BRANCH, 'base': 'main', 'draft': True})
    live = api.get('pulls/' + str(pr['number']))
    if live['head']['sha'] != commit_sha or live['body'] != body:
        raise ValueError('Thematic PR readback failed')
    return live


def publish(api, directory, repository, run_id):
    directory = Path(directory)
    attempt = load(directory / 'ATTEMPT.json')
    package = attempt['package_id']
    if attempt.get('schema') != SCHEMA or not HEX64.fullmatch(package):
        raise ValueError('Invalid reserved attempt')
    frozen = file_at(api, BRANCH, PREFIX + '/' + package + '/ATTEMPT.json')
    if frozen is None or json.loads(frozen) != attempt:
        raise ValueError('Attempt was not durably reserved')
    for name, field in [('EVENTS.json', 'events_sha256'), ('CONTEXT.json', 'context_sha256')]:
        if digest((directory / name).read_bytes()) != attempt[field]:
            raise ValueError('Frozen model input changed: ' + name)
    if 'manifest_sha256' in attempt and digest((directory / 'CORPUS_MANIFEST.json').read_bytes()) != attempt['manifest_sha256']:
        raise ValueError('Frozen corpus manifest changed')
    files = collected_files(directory)
    # Even a killed generator has a durable failure report, never a false completion.
    if 'RECEIPT.json' not in files:
        files['RECEIPT.json'] = encoded({'package_id': package, 'status': 'INCOMPLETE',
            'complete': False, 'reason': 'Generator did not produce a final receipt; saved raw files retained.',
            'scientific_acceptance': False})
    receipt = json.loads(files['RECEIPT.json'])
    if receipt.get('package_id') != package:
        raise ValueError('Generated receipt belongs to another package')
    complete = receipt.get('complete') is True
    if complete:
        from copilot_thematic_review import validate_saved
        validate_saved(directory)
    if 'REPORT.md' not in files:
        files['REPORT.md'] = ('# Тематическая проверка не завершена\n\n'
            'Пакет `' + package + '` сохранён. Копилот не подтвердил полный проход; '
            'промежуточные ответы и квитанция доступны рядом. Повтор публикации использует сохранённый ответ.\n')
    manifest = {name: digest(raw) for name, raw in sorted(files.items())}
    publication = {'schema': 'vm-lab-thematic-publication-v1', 'package_id': package,
                   'generation_run_id': attempt['run_id'], 'publication_run_id': str(run_id),
                   'files': manifest, 'complete': complete, 'scientific_acceptance': False}
    state = monitor(api)
    if package not in state.get('attempts', {}):
        raise ValueError('Missing reserved monitor identity')
    state['attempts'][package]['status'] = 'GENERATED' if complete else 'PUBLISHED_INCOMPLETE'
    dest = PREFIX + '/' + package + '/'
    payload = {dest + name: value for name, value in files.items()}
    payload[dest + 'PUBLICATION.json'] = encoded(publication)
    payload[STATE] = encoded(state)
    commit = write_commit(api, payload, attempt['source_sha'], 'Copilot thematic review: preserve ' + package[:16] + ' and raw responses')
    pr = ensure_pr(api, repository, run_id, package, commit, complete)
    delivery = {'schema': 'vm-lab-thematic-delivery-v1', 'package_id': package,
                'data_commit': commit, 'pr_number': pr['number'], 'pr_url': pr['html_url'],
                'file_hashes_verified': True, 'pr_readback_verified': True, 'complete': complete}
    state['attempts'][package].update(status='DELIVERED' if complete else 'PUBLISHED_INCOMPLETE',
                                     delivery=delivery, last_publication_run_id=str(run_id),
                                     last_recovery_source_sha=os.environ.get('GITHUB_SHA', attempt['source_sha']))
    write_commit(api, {STATE: encoded(state), dest + 'DELIVERY.json': encoded(delivery)},
                 attempt['source_sha'], 'Copilot thematic review: record verified delivery ' + package[:16])
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream:
            stream.write('## Copilot thematic review\n\n[Report PR](' + pr['html_url'] + ')\n\n'
                         'Complete: **' + str(complete).lower() + '**; no scientific acceptance.\n')
    return {'pr_url': pr['html_url'], 'package_id': package, 'complete': complete}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['reserve', 'publish'])
    parser.add_argument('--output', default='thematic-output')
    args = parser.parse_args()
    repository = os.environ.get('GITHUB_REPOSITORY', '')
    if repository != 'IgorSabirov/vm-lab':
        raise SystemExit('This reviewed publisher is scoped to IgorSabirov/vm-lab')
    api = GitHub(repository)
    if args.command == 'reserve':
        output_fields(reserve(api, args.output, os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_SHA']))
    else:
        output_fields(publish(api, args.output, repository, os.environ['GITHUB_RUN_ID']))


if __name__ == '__main__':
    main()
