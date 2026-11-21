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


def encoded(value):
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n'


def digest(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def blob_sha(value):
    raw = value.encode()
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encoded(value))


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
    if item.get('encoding') == 'base64':
        return base64.b64decode(item['content']).decode('utf-8')
    return api.blob(item['sha'])


def head(api):
    item = optional(api, 'git/ref/heads/' + BRANCH)
    return item['object']['sha'] if item else None


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
    for path, value in sorted(files.items()):
        # Git blobs avoid inline tree request limits for full context packages.
        blob = api.request('POST', 'git/blobs', {'content': value, 'encoding': 'utf-8'})
        if blob['sha'] != blob_sha(value):
            raise ValueError('Created blob digest mismatch')
        entries.append({'path': path, 'mode': '100644', 'type': 'blob', 'sha': blob['sha']})
    tree = api.request('POST', 'git/trees', {'base_tree': commit['tree']['sha'], 'tree': entries})
    made = api.request('POST', 'git/commits', {'message': message, 'tree': tree['sha'], 'parents': [parent]})
    if previous is None:
        api.request('POST', 'git/refs', {'ref': 'refs/heads/' + BRANCH, 'sha': made['sha']})
    else:
        if head(api) != previous:
            raise ValueError('Report branch moved; preserve this artifact and retry publication')
        api.request('PATCH', 'git/refs/heads/' + BRANCH, {'sha': made['sha'], 'force': False})
    if head(api) != made['sha']:
        raise ValueError('Published branch readback failed')
    for path, value in files.items():
        row = api.get('contents/' + quote(path, safe='/') + '?ref=' + made['sha'])
        if row.get('sha') != blob_sha(value):
            raise ValueError('Published file readback failed: ' + path)
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
    prefix = PREFIX + '/' + package + '/'
    files = {}
    for item in api.tree(ref):
        if item.get('type') != 'blob' or not item['path'].startswith(prefix):
            continue
        name = item['path'][len(prefix):]
        if name in ROOT_FILES or BATCH_FILE.fullmatch(name):
            files[name] = api.blob(item['sha'])
    return files


def restore_inputs(api, package, directory):
    files = archived_files(api, package)
    for name in ('EVENTS.json', 'CONTEXT.json', 'ATTEMPT.json'):
        if name not in files:
            raise ValueError('Reserved input missing: ' + name)
    for name, raw in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(raw)


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
    files = {PREFIX + '/' + package + '/' + name: (directory / name).read_text()
             for name in ('EVENTS.json', 'CONTEXT.json', 'ATTEMPT.json')}
    if 'manifest_sha256' in attempt:
        files[PREFIX + '/' + package + '/CORPUS_MANIFEST.json'] = (directory / 'CORPUS_MANIFEST.json').read_text()
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
            files[name] = path.read_text(encoding='utf-8')
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
