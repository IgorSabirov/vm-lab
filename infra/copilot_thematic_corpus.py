#!/usr/bin/env python3
"""Exhaustive registry/schema context, read as data from pinned GitHub objects.

This is a document inventory, not a topic selector or a second science registry.
Every supplied update is paired with every corpus segment. Other evidence is
explicitly inventoried as pointer-only; an unread pointer is never called read.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

from copilot_thematic_events import GitHub, REPOSITORY, REPORT_PREFIX, SHA, dump

SCHEMA = 'vm-lab-thematic-context-v1'
INDEX = 'analysis/REGISTRY_LINKS/INDEX.json'
POLICY = 'infra/copilot/context/requirements.json'
CORE_IDS = {'common_model', 'rho_genesis_specification', 'contact_capacity_result'}
DEFAULT_PAYLOAD_BYTES = 560_000  # Native runner separately checks the actual prompt.
MAX_CONTEXT_BYTES = 90_000_000  # Leave headroom below GitHub's per-blob ceiling.
ARCHIVE_PREFIXES = ('results/VM_WORKSPACE_SNAPSHOTS/',)
RAW_OUTPUT_DIRS = {'rows', 'traces', 'geometry', 'samples', 'trajectories'}
SCANNABLE = {'.md', '.markdown', '.rst', '.adoc', '.org', '.tex', '.txt',
             '.json', '.jsonl', '.yaml', '.yml', '.toml', '.xml', '.svg',
             '.mmd', '.mermaid', '.puml', '.plantuml', '.dot', '.gv', '.drawio'}
DIAGRAMS = {'.svg', '.mmd', '.mermaid', '.puml', '.plantuml', '.dot', '.gv', '.drawio'}
NAME_MARKERS = re.compile(
    r'(?:^|[_. /-])(?:registr(?:y|ies)|register|schema(?:s)?|scheme(?:s)?|diagram(?:s)?|'
    r'architecture|lineage|pipeline|catalog|contract(?:s)?|mapping|map|premises|'
    r'questions|index)(?:$|[_. /-])', re.I)
HEADING_MARKERS = re.compile(
    r'(?im)^\s*(?:#{1,6}\s+|\*\*|title\s*[:=]\s*)[^\n]{0,160}'
    r'(?:registry|register|schema|scheme|diagram|architecture|pipeline|реестр|схем|архитектур)')
DIAGRAM_MARKUP = re.compile(
    r'(?im)(?:^\s*```\s*(?:mermaid|dot|graphviz|plantuml)\b|@startuml\b|<mxfile\b|<svg\b)')
CARD_TABLE = re.compile(
    r'(?im)^\s*\|(?:[^\n]*\|)?\s*(?:id|key|идентификатор|код|ключ)\s*\|[^\n]*\n'
    r'\s*\|[\s:|\-]+\|\s*$')
REGISTRY_KEYS = {'results', 'constructs', 'open_links', 'questions', 'premises',
                 'external_integrations', 'architecture_components', 'deliverables',
                 'criteria', 'registry', 'registries', 'contracts', 'components',
                 'mappings', 'pipeline', 'schemas'}


def compact(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def sha256(raw):
    return hashlib.sha256(raw if isinstance(raw, bytes) else raw.encode()).hexdigest()


def git_blob_sha(text):
    raw = text.encode('utf-8')
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def safe_path(path):
    if (not isinstance(path, str) or not path or '\\' in path or
            PurePosixPath(path).is_absolute() or '..' in PurePosixPath(path).parts):
        raise ValueError('Invalid corpus path: ' + repr(path))
    return str(PurePosixPath(path))


def named_document(path):
    p = PurePosixPath(path)
    return bool(NAME_MARKERS.search(p.name) or any(
        re.fullmatch(r'(?:registr(?:y|ies)|schemas?|diagrams?)', part, re.I)
        for part in p.parts[:-1]) or p.suffix.lower() in DIAGRAMS)


def pointer_role(path, declared=False):
    """Backups and numerical output roles are metadata, unless explicitly cited.

    This never filters changed updates: those arrive independently in EVENTS.
    A new named registry/schema in an output folder is still included.
    """
    if declared:
        return None
    if path.startswith(ARCHIVE_PREFIXES):
        return 'pointer_archival_workspace_backup'
    p = PurePosixPath(path)
    if p.parts[0] == 'results':
        strong_name = re.search(r'(?:^|[_.-])(?:registr(?:y|ies)|register|schemas?|'
                                r'schemes?|diagrams?|contracts?|architecture)(?:$|[_.-])', p.name, re.I)
        if not strong_name and any(part.lower() in RAW_OUTPUT_DIRS for part in p.parts[1:-1]):
            return 'pointer_raw_numerical_output'
        if re.fullmatch(r'(?:ROWS|TRACES|GEOMETRY|SAMPLES)_INDEX\.json', p.name, re.I):
            return 'pointer_raw_output_index'
    return None


def structural_document(path, text):
    """Recognise document structure, never physical subject matter or keywords."""
    if DIAGRAM_MARKUP.search(text) or HEADING_MARKERS.search(text) or CARD_TABLE.search(text):
        return True
    suffix = PurePosixPath(path).suffix.lower()
    if suffix == '.json':
        try:
            value = json.loads(text)
        except ValueError:
            return False
        if isinstance(value, dict):
            keys = set(value)
            return bool(keys & {'$defs', 'definitions', 'properties'} or
                        {'nodes', 'edges'} <= keys or
                        any(registry_collection(value[key]) for key in keys & REGISTRY_KEYS) or
                        (value.get('type') == 'array' and isinstance(value.get('items'), dict)) or
                        any(identified_cards(v) for v in value.values()))
        return identified_cards(value)
    if suffix in {'.yaml', '.yml', '.toml'}:
        keys = set(re.findall(r'(?m)^([A-Za-z_$][A-Za-z0-9_$]*)\s*[:=]', text))
        return bool(keys & {'$defs', 'definitions', 'properties'} or
                    {'nodes', 'edges'} <= keys or (keys & REGISTRY_KEYS and re.search(
                        r'(?m)^\s+(?:-\s*)?(?:id|key|name|title|claim|question|definition|statement)\s*:', text)))
    return False


def identified_cards(value):
    """Standalone/nested identified cards can be registries without a schema key."""
    return (isinstance(value, list) and bool(value) and
            all(isinstance(row, dict) and set(row) & {'id', 'key', 'name'} and
                set(row) & {'title', 'question', 'status', 'claim', 'definition', 'statement', 'requires', 'provides'}
                for row in value))


def registry_collection(value):
    if identified_cards(value):
        return True
    if isinstance(value, list):
        return bool(value) and all(isinstance(v, str) and v.strip() for v in value)
    if isinstance(value, dict) and value:
        return all(isinstance(v, dict) and set(v) & {
            'title', 'description', 'definition', 'claim', 'question', 'statement', 'requires', 'provides'}
            for v in value.values())
    return False


def graph_paths(graph):
    paths = {INDEX}
    for key in ('sources', 'managed_review_sources'):
        values = graph.get(key, {})
        if not isinstance(values, dict):
            raise ValueError('Malformed registry source map: ' + key)
        paths.update(safe_path(p) for p in values)
    for node in graph.get('nodes', []):
        if node.get('path'):
            paths.add(safe_path(node['path']))
    return paths


def core_documents(policy):
    documents = {}
    for rule in policy.get('rules', []):
        for item in rule.get('documents', []):
            if item.get('id') in CORE_IDS:
                path = safe_path(item['path'])
                if item['id'] in documents and documents[item['id']]['path'] != path:
                    raise ValueError('Conflicting shared scientific definition')
                documents[item['id']] = {**item, 'path': path}
    if documents.keys() != CORE_IDS:
        raise ValueError('Context policy must supply full COMMON_MODEL, R128.1 and R129')
    return documents


def source_refs(events):
    primary = events['source_sha']
    refs = {primary: {'sha': primary, 'labels': {'main'}}}
    for row in events.get('source_refs', []):
        sha = row['sha']
        if not SHA.fullmatch(sha):
            raise ValueError('Invalid pinned source ref')
        refs.setdefault(sha, {'sha': sha, 'labels': set()})['labels'].add(str(row.get('label', 'source')))
    if not SHA.fullmatch(primary):
        raise ValueError('Invalid main source SHA')
    return [{**refs[sha], 'id': f'ref:{i:04d}', 'labels': sorted(refs[sha]['labels'])}
            for i, sha in enumerate(sorted(refs, key=lambda x: (x != primary, x)))]


def inventory(api, events, local_root=None, progress=None):
    """Fetch all tree entries, scan structural candidates, deduplicate exact blobs."""
    refs = source_refs(events)
    blobs, documents, audit_rows, graphs, trees = {}, {}, {}, {}, {}
    remote_reads = 0

    def report(message):
        if progress is not None:
            progress(message)

    def record(row, ref):
        row = {k: v for k, v in row.items() if k not in {'source_sha', 'labels'}}
        key = compact(row)
        if key not in audit_rows:
            audit_rows[key] = {**row, 'refs': set()}
        audit_rows[key]['refs'].add(ref['id'])

    def read(entry):
        nonlocal remote_reads
        blob_sha = entry['sha']
        if blob_sha not in blobs:
            value = None
            if local_root is not None:
                root = Path(local_root).resolve()
                candidate = root / safe_path(entry['path'])
                if (candidate.is_file() and not candidate.is_symlink() and
                        candidate.resolve().is_relative_to(root)):
                    raw = candidate.read_bytes()
                    if hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == blob_sha:
                        value = raw.decode('utf-8')
                        # The client caches by immutable blob identity, never by
                        # mutable path, so branch copies can reuse trusted bytes.
                        if hasattr(api, '_blobs'):
                            api._blobs[blob_sha] = value
            if value is None:
                remote_reads += 1
                if remote_reads % 25 == 1:
                    report(f'Corpus remote blob {remote_reads}: {entry["path"]!r}; '
                           f'{len(blobs)} verified unique blobs already available.')
                value = api.blob(blob_sha)
            if not isinstance(value, str) or git_blob_sha(value) != blob_sha:
                raise ValueError('Blob identity mismatch: ' + entry['path'])
            if entry.get('size') is not None and len(value.encode()) != entry['size']:
                raise ValueError('Blob size mismatch: ' + entry['path'])
            blobs[blob_sha] = value
        return blobs[blob_sha]

    for number, ref in enumerate(refs, 1):
        report(f'Corpus tree {number}/{len(refs)}: {ref["sha"]} ({", ".join(ref["labels"])}).')
        rows = api.tree(ref['sha'])
        if not isinstance(rows, list):
            raise ValueError('Expected complete recursive Git tree')
        tree = {}
        for row in rows:
            path = safe_path(row['path'])
            if path in tree:
                raise ValueError('Duplicate Git tree path: ' + path)
            tree[path] = row
        trees[ref['sha']] = tree
        report(f'Corpus tree {number}/{len(refs)} complete: {len(tree)} entries.')

    main_tree = trees[events['source_sha']]
    if INDEX not in main_tree or POLICY not in main_tree:
        raise ValueError('Missing main registry index or scientific context policy')
    policy = core_documents(json.loads(read(main_tree[POLICY])))
    core_paths = {row['path'] for row in policy.values()}
    for row in policy.values():
        entry = main_tree.get(row['path'])
        if not entry or entry.get('type') != 'blob' or entry.get('mode') == '120000':
            raise ValueError('Missing full mandatory definition: ' + row['path'])
        text = read(entry)
        if any(marker not in text for marker in row.get('required_markers', [])):
            raise ValueError('Missing mandatory definition section: ' + row['path'])

    for number, ref in enumerate(refs, 1):
        report(f'Corpus scan {number}/{len(refs)}: {ref["sha"]}; '
               f'{len(documents)} complete unique documents collected.')
        tree = trees[ref['sha']]
        declared = set()
        if INDEX in tree:
            graph = json.loads(read(tree[INDEX]))
            declared = graph_paths(graph)
            graph_blob = tree[INDEX]['sha']
            if graph_blob not in graphs:
                graphs[graph_blob] = {'source_sha': ref['sha'], 'document_id': 'doc:' + graph_blob,
                    'nodes': graph.get('nodes', []), 'edges': graph.get('edges', []),
                    'counts': graph.get('counts', {}), 'source_refs': []}
            graphs[graph_blob]['source_refs'].append(ref['id'])
            missing = sorted(declared - tree.keys())
            if missing:
                raise ValueError('Registry references absent files at ' + ref['sha'] + ': ' + ', '.join(missing))
        if ref['sha'] == events['source_sha']:
            declared |= core_paths | {POLICY}
        else:
            # Branch definitions are variants, not replacements for the shared
            # main definitions. Include each present variant in the ordinary
            # corpus even if the branch index has not learned that path yet.
            declared |= core_paths & tree.keys()
        for path, entry in sorted(tree.items()):
            row = {'path': path, 'source_sha': ref['sha'], 'git_blob_sha': entry.get('sha'),
                   'size_bytes': entry.get('size'), 'type': entry.get('type'),
                   'mode': entry.get('mode'), 'labels': ref['labels']}
            if path.startswith(REPORT_PREFIX):
                row.update(disposition='excluded_own_report', content_read=False)
                record(row, ref); continue
            if entry.get('type') != 'blob':
                row.update(disposition='directory' if entry.get('type') == 'tree' else 'pointer_gitlink',
                           content_read=False)
                record(row, ref); continue
            if entry.get('mode') == '120000':
                if path in declared:
                    raise ValueError('Declared scientific document is a symlink: ' + path)
                row.update(disposition='pointer_symlink_not_followed', content_read=False)
                record(row, ref); continue
            excluded_role = pointer_role(path, path in declared)
            if excluded_role:
                row.update(disposition=excluded_role, content_read=False)
                record(row, ref); continue
            reason = 'declared_registry_source' if path in declared else (
                'named_registry_schema_or_diagram' if named_document(path) else None)
            should_scan = reason or PurePosixPath(path).suffix.lower() in SCANNABLE
            if not should_scan:
                row.update(disposition='pointer_non_document_or_raw_artifact', content_read=False)
                record(row, ref); continue
            try:
                text = read(entry)
            except UnicodeDecodeError:
                if reason:
                    raise ValueError('Registry/schema source is not UTF-8 text: ' + path) from None
                row.update(disposition='pointer_binary_not_text', content_read=False)
                record(row, ref); continue
            if reason is None and structural_document(path, text):
                reason = 'structural_registry_schema_or_embedded_diagram'
            if reason is None:
                row.update(disposition='pointer_scanned_non_registry_document_or_raw_data', content_read=True)
                record(row, ref); continue
            row.update(disposition='full_text', content_read=True, reason=reason)
            record(row, ref)
            doc_id = 'doc:' + entry['sha']
            origin = {'path': path, 'source_sha': ref['sha'], 'labels': ref['labels'], 'reason': reason,
                      'url': f"https://github.com/{api.repository}/blob/{ref['sha']}/{path}"}
            if doc_id not in documents:
                documents[doc_id] = {'id': doc_id, 'path': path, 'source_sha': ref['sha'],
                    'revision': ref['sha'], 'url': origin['url'], 'git_blob_sha': entry['sha'],
                    'sha256': sha256(text), 'size_bytes': len(text.encode()), 'text': text,
                    'origins': [], 'start_line': 1, 'end_line': max(1, len(text.splitlines()))}
            documents[doc_id]['origins'].append(origin)
        report(f'Corpus scan {number}/{len(refs)} complete: {len(documents)} unique documents; '
               f'{remote_reads} remote blob reads in total.')
    shared_ids = {'doc:' + main_tree[path]['sha'] for path in core_paths}
    shared = [documents[k] for k in sorted(shared_ids)]
    ordinary = [documents[k] for k in sorted(documents) if k not in shared_ids]
    ref_sets = sorted({tuple(sorted(row['refs'])) for row in audit_rows.values()})
    set_ids = {values: i for i, values in enumerate(ref_sets)}
    audit = [{**{k: v for k, v in row.items() if k != 'refs'},
              'ref_set': set_ids[tuple(sorted(row['refs']))]}
             for _, row in sorted(audit_rows.items())]
    return shared, ordinary, audit, list(graphs.values()), refs, [list(v) for v in ref_sets]


def split_text(text, byte_limit):
    """Lossless UTF-8 segments, preferring complete lines; offsets are half-open."""
    if byte_limit < 4:
        raise ValueError('Segment byte limit is too small')
    raw = text.encode()
    if not raw:
        return [(0, 0, 1, 1, '')]
    pieces, start, line = [], 0, 1
    while start < len(raw):
        end = min(start + byte_limit, len(raw))
        if end < len(raw):
            while end > start and (raw[end] & 0xC0) == 0x80:
                end -= 1
            newline = raw.rfind(b'\n', start, end)
            if newline >= start:
                end = newline + 1
        if end == start:
            raise ValueError('Cannot split UTF-8 source within budget')
        part = raw[start:end].decode()
        end_line = line + part.count('\n') - (1 if part.endswith('\n') else 0)
        pieces.append((start, end, line, max(line, end_line), part))
        line += part.count('\n')
        start = end
    return pieces


def segments(document, byte_limit, *, event=False):
    base = {k: v for k, v in document.items() if k not in {'text', 'origins', 'id'}}
    # Every alias stays in the inventory. One exact origin suffices in each
    # prompt and prevents open-PR metadata from consuming the content budget.
    identity = ('event:' + sha256(document['id'])[:24]) if event else document['id']
    result = []
    for i, (start, end, line, end_line, text) in enumerate(split_text(document['text'], byte_limit), 1):
        result.append({**base, 'id': f'{identity}:{i:04d}',
            'event_id' if event else 'document_id': document['id'], 'text': text,
            'start_byte': start, 'end_byte': end, 'start_line': line, 'end_line': end_line,
            'full_document_sha256': document['sha256'], 'chunk_sha256': sha256(text)})
    return result


def event_documents(events):
    rows = []
    for source in events.get('changes', []):
        if not isinstance(source.get('text'), str) or not isinstance(source.get('id'), str):
            raise ValueError('Every event must contain its complete text or an explicit empty pointer')
        fingerprint = source.get('content_sha256') or sha256(compact(source))
        identifier = source['id'] + '@' + fingerprint[:16]
        rows.append({**source, 'id': identifier, 'source_event_id': source['id'],
                     'sha256': sha256(source['text']), 'size_bytes': len(source['text'].encode())})
    if len({row['id'] for row in rows}) != len(rows):
        raise ValueError('Duplicate versioned event ID')
    return sorted(rows, key=lambda r: r['id'])


def payload(context, batch):
    """This exact compact JSON is the runner's model payload (before instructions)."""
    return {'package_id': context['package_id'], 'source_sha': context['source_sha'],
            'batch_id': batch['id'], 'events': batch['events'],
            'shared_documents': context['shared_documents'], 'documents': batch['documents']}


def pack(items, byte_budget):
    groups, group = [], []
    for item in items:
        if len(compact([item]).encode()) > byte_budget:
            raise ValueError('A source segment cannot fit its declared budget')
        if group and len(compact(group + [item]).encode()) > byte_budget:
            groups.append(group); group = []
        group.append(item)
    if group:
        groups.append(group)
    return groups or [[]]


def pack_corpus(items, byte_budget):
    """Deterministic best-fit decreasing; only move intact source segments.

    Item JSON bytes plus one separator are additive. Reserving the final list
    bracket gives the exact list size, including escaped text and UTF-8 bytes.
    Reordering changes neither source text nor the exhaustive Cartesian pairs.
    """
    capacity = byte_budget - 1
    weighted = [(len(compact(item).encode()) + 1, item) for item in items]
    groups, loads = [], []
    for size, item in sorted(weighted, key=lambda pair: (-pair[0], pair[1]['id'])):
        if size > capacity:
            raise ValueError('A source segment cannot fit its declared budget')
        fitting = [i for i, load in enumerate(loads) if load + size <= capacity]
        if fitting:
            index = max(fitting, key=lambda i: loads[i])
            groups[index].append(item)
            loads[index] += size
        else:
            groups.append([item])
            loads.append(size)
    return groups or [[]]


def prepare(api, events, max_payload_bytes=DEFAULT_PAYLOAD_BYTES, local_root=None, progress=None):
    if events.get('schema') != 'vm-lab-thematic-events-v1' or events.get('repository') != api.repository:
        raise ValueError('Event package identity mismatch')
    if not isinstance(max_payload_bytes, int) or max_payload_bytes < 4096:
        raise ValueError('Invalid model payload budget')
    if not events.get('changes'):
        # Polling/reconciliation without new content incurs no corpus fetch or
        # model call. Recovery uses the previously frozen package, not this one.
        return {'schema': SCHEMA, 'status': 'NO_NEW_INPUT', 'repository': api.repository,
            'source_sha': events['source_sha'], 'package_id': events.get('package_id', ''),
            'source_refs': source_refs(events), 'shared_documents': [], 'documents': [],
            'events': [], 'existing_graph': {'nodes': [], 'edges': []}, 'graph_variants': [],
            'batches': [], 'max_payload_bytes': max_payload_bytes,
            'coverage': {'scope': 'NOT_RESCANNED_WITHOUT_NEW_INPUT', 'inventory': [],
                         'planned_model_calls': 0, 'model_payload_bytes': [],
                         'event_collection': events.get('coverage', {}),
                         'scientific_acceptance': 'NOT_GRANTED'}}
    shared, documents, audit, graphs, refs, ref_sets = inventory(api, events, local_root, progress)
    updates = event_documents(events)
    context = {'schema': SCHEMA, 'repository': api.repository, 'source_sha': events['source_sha'],
        'package_id': events['package_id'], 'source_refs': refs,
        'shared_documents': [{k: v for k, v in d.items() if k != 'origins'} for d in shared],
        'documents': [{k: v for k, v in d.items() if k != 'text'} for d in shared + documents],
        'events': [{k: v for k, v in d.items() if k != 'text'} for d in updates],
        'existing_graph': next(g for g in graphs if g['source_sha'] == events['source_sha']),
        'graph_variants': [{k: v for k, v in graph.items() if k not in {'nodes', 'edges'}}
                           for graph in graphs], 'batches': [], 'max_payload_bytes': max_payload_bytes,
        'coverage': {'scope': 'ALL_DECLARED_SOURCES_AND_AUTODISCOVERED_REGISTRIES_SCHEMAS_AT_LISTED_REFS',
            'scientific_acceptance': 'NOT_GRANTED', 'semantic_prefilter': False,
            'inventory': audit, 'inventory_ref_sets': ref_sets,
            'inventory_entries_by_ref': {ref['id']: sum(ref['id'] in ref_sets[row['ref_set']] for row in audit)
                                         for ref in refs},
            'event_collection': events.get('coverage', {}),
            'all_repo_files_are_science': False,
            'pointer_note': 'Only full_text entries are supplied to Copilot. Structural scans are mechanical, not semantic reading. Raw data, outside-corpus prose and external URLs are pointers, not read evidence.',
            'selection_note': 'All tree paths are inventoried; named registry/schema documents, structurally identified registries and embedded diagrams, and every graph-declared source are included. No graph-neighbour or topic ranking.'}}
    empty = {'id': '00000000', 'events': [], 'documents': []}
    fixed_size = len(compact(payload(context, empty)).encode())
    available = max_payload_bytes - fixed_size - 1024
    if available < 4096:
        raise ValueError('Full mandatory shared definitions exceed the model context budget')
    # Split both dimensions exhaustively. JSON may expand ASCII control chars
    # up to sixfold; use an adaptive segment bound, never slice the final prompt.
    segment_limit = max(4, available // 3)
    while True:
        doc_parts = [p for d in documents for p in segments(d, segment_limit)]
        event_parts = [p for d in updates for p in segments(d, segment_limit, event=True)]
        largest_event = max([len(compact(p).encode()) for p in event_parts] or [2])
        largest_doc = max([len(compact(p).encode()) for p in doc_parts] or [2])
        if largest_doc + largest_event + 8 < available:
            break
        if segment_limit <= 4:
            raise ValueError('Source metadata exceeds available model context budget')
        segment_limit = max(4, segment_limit // 2)
    # Prefer a single update group when it fits, so infrequent small updates
    # compare against the entire corpus without unnecessary repeated inference.
    event_budget = min(max(len(compact(event_parts).encode()), largest_event + 2),
                       max(largest_event + 2, available // 3))
    event_groups = pack(event_parts, event_budget)
    doc_budget = available - max(len(compact(g).encode()) for g in event_groups) - 8
    doc_groups = pack_corpus(doc_parts, doc_budget)
    if updates:
        for event_group in event_groups:
            for doc_group in doc_groups:
                context['batches'].append({'id': f"{len(context['batches']) + 1:04d}",
                                          'events': event_group, 'documents': doc_group})
    context['coverage'].update(
        corpus_documents=len(shared) + len(documents),
        corpus_bytes=sum(d['size_bytes'] for d in shared + documents),
        unique_corpus_segments=len(doc_parts), unique_event_segments=len(event_parts),
        event_groups=len(event_groups) if updates else 0, corpus_groups=len(doc_groups),
        planned_model_calls=len(context['batches']),
        model_payload_bytes=[len(compact(payload(context, b)).encode()) for b in context['batches']],
        cartesian_pair_count=len(event_parts) * len(doc_parts),
        every_update_segment_against_every_corpus_segment=True,
        shared_documents_repeated_in_every_batch=True)
    validate_context(context)
    # Publication persists this exact JSON, including the complete audit. Fail
    # before inference if it cannot be frozen; never truncate corpus/metadata.
    context['coverage']['context_json_bytes'] = 0
    for _ in range(3):
        context['coverage']['context_json_bytes'] = len(
            (json.dumps(context, ensure_ascii=False, indent=2) + '\n').encode())
    if context['coverage']['context_json_bytes'] > MAX_CONTEXT_BYTES:
        raise ValueError('Frozen CONTEXT.json exceeds publication size budget; no sources were truncated')
    if progress is not None:
        coverage = context['coverage']
        sizes = coverage['model_payload_bytes']
        progress(f'Corpus ready: {coverage["corpus_documents"]} complete documents, '
                 f'{coverage["corpus_bytes"]} source bytes, {len(refs)} pinned refs, '
                 f'{coverage["unique_corpus_segments"]} corpus segments, '
                 f'{coverage["unique_event_segments"]} update segments, '
                 f'{coverage["planned_model_calls"]} planned model calls; '
                 f'payload bytes {min(sizes, default=0)}..{max(sizes, default=0)}; '
                 f'CONTEXT.json {coverage["context_json_bytes"]} bytes.')
    return context


def validate_context(context):
    """Reject missing bytes/pairs, altered chunks and false full-coverage claims."""
    if context.get('schema') != SCHEMA:
        raise ValueError('Unknown thematic context schema')
    metadata = {d['id']: d for d in context['documents']}
    updates = {e['id']: e for e in context['events']}
    if len(metadata) != len(context['documents']) or len(updates) != len(context['events']):
        raise ValueError('Duplicate source identities')
    shared_ids = set()
    for d in context['shared_documents']:
        expected = metadata.get(d['id'])
        if (expected is None or sha256(d['text']) != expected['sha256'] or
                len(d['text'].encode()) != expected['size_bytes'] or
                any(d.get(k) != expected.get(k) for k in ('path', 'source_sha', 'revision', 'url', 'git_blob_sha'))):
            raise ValueError('Shared document content mismatch')
        shared_ids.add(d['id'])
    refs = {ref['id']: ref['sha'] for ref in context.get('source_refs', [])}
    ref_sets = context['coverage'].get('inventory_ref_sets', [])
    counted_refs = defaultdict(int)
    for group in ref_sets:
        if len(group) != len(set(group)) or not set(group) <= refs.keys():
            raise ValueError('Invalid inventory reference set')
    for entry in context['coverage'].get('inventory', []):
        if type(entry.get('ref_set')) is not int or not 0 <= entry['ref_set'] < len(ref_sets):
            raise ValueError('Invalid inventory ref-set address')
        origins = ref_sets[entry['ref_set']]
        for ref_id in origins:
            counted_refs[ref_id] += 1
        if entry['disposition'] != 'full_text':
            continue
        item = metadata.get('doc:' + entry['git_blob_sha'])
        if item is None or not all(any(o['path'] == entry['path'] and o['source_sha'] == refs[ref_id]
                                      for o in item['origins']) for ref_id in origins):
            raise ValueError('Inventoried source is absent from supplied corpus')
    if dict(counted_refs) != context['coverage'].get('inventory_entries_by_ref', {}):
        raise ValueError('Incomplete reference inventory coverage')
    sources, pairs, batches = {}, set(), set()
    for batch in context['batches']:
        if batch['id'] in batches:
            raise ValueError('Duplicate batch ID')
        batches.add(batch['id'])
        if len(compact(payload(context, batch)).encode()) > context['max_payload_bytes']:
            raise ValueError('Actual model payload exceeds budget')
        for kind, field in [('documents', 'document_id'), ('events', 'event_id')]:
            ids = [p['id'] for p in batch[kind]]
            if len(ids) != len(set(ids)):
                raise ValueError('Duplicate source segment in one batch')
            for part in batch[kind]:
                expected = (metadata if kind == 'documents' else updates).get(part[field])
                if expected is None or part['full_document_sha256'] != expected['sha256']:
                    raise ValueError('Unknown or changed segment source')
                locator_fields = ('path', 'source_sha', 'revision', 'url', 'git_blob_sha') if kind == 'documents' else (
                    'path', 'revision', 'url', 'source_event_id')
                if any(part.get(key) != expected.get(key) for key in locator_fields):
                    raise ValueError('Source segment locator differs from frozen origin')
                if sha256(part['text']) != part['chunk_sha256']:
                    raise ValueError('Corrupt source segment')
                if part['end_byte'] - part['start_byte'] != len(part['text'].encode()):
                    raise ValueError('Invalid segment byte offsets')
                signature = compact(part)
                if part['id'] in sources and sources[part['id']][0] != signature:
                    raise ValueError('Segment identity reused for different bytes')
                sources[part['id']] = (signature, part, kind, field)
        pairs.update((e['id'], d['id']) for e in batch['events'] for d in batch['documents'])
    if not updates:
        if context['batches']:
            raise ValueError('Empty event package must not request inference')
        return {'batches': 0, 'complete': True, 'model_analysis': 'NOT_REQUESTED'}
    by_source = defaultdict(list)
    event_ids, doc_ids = set(), set()
    for _, part, kind, field in sources.values():
        by_source[part[field]].append(part)
        (event_ids if kind == 'events' else doc_ids).add(part['id'])
    for identity, item in {**metadata, **updates}.items():
        if identity in shared_ids:
            continue
        parts = sorted(by_source.get(identity, []), key=lambda p: p['start_byte'])
        if not parts:
            raise ValueError('Source never supplied to model: ' + identity)
        offset, raw, line = 0, [], 1
        for part in parts:
            if part['start_byte'] != offset or part['start_line'] != line:
                raise ValueError('Gap/overlap or invalid line locator in corpus')
            text = part['text']
            end_line = line + text.count('\n') - (1 if text.endswith('\n') else 0)
            if part['end_line'] != max(line, end_line):
                raise ValueError('Invalid end-line locator')
            raw.append(text); offset = part['end_byte']; line += text.count('\n')
        if offset != item['size_bytes'] or sha256(''.join(raw)) != item['sha256']:
            raise ValueError('Incomplete full-text coverage: ' + identity)
        if identity in metadata and git_blob_sha(''.join(raw)) != item['git_blob_sha']:
            raise ValueError('Reconstructed document differs from Git blob identity')
    if pairs != {(e, d) for e in event_ids for d in doc_ids}:
        raise ValueError('Not every update segment was compared with every corpus segment')
    return {'batches': len(batches), 'complete': True,
            'documents': len(metadata), 'events': len(updates), 'pairs': len(pairs)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare'])
    parser.add_argument('--output', type=Path, default=Path('thematic-output'))
    parser.add_argument('--max-payload-bytes', type=int, default=DEFAULT_PAYLOAD_BYTES)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        events = json.loads((args.output / 'EVENTS.json').read_text())
        context = prepare(GitHub(events.get('repository', REPOSITORY)), events, args.max_payload_bytes,
                          local_root=Path(__file__).resolve().parents[1],
                          progress=lambda message: print(message, flush=True))
        dump(args.output / 'CONTEXT.json', context)
        dump(args.output / 'CORPUS_MANIFEST.json', {
            'schema': 'vm-lab-thematic-corpus-manifest-v1', 'package_id': context['package_id'],
            'source_sha': context['source_sha'], 'source_refs': context['source_refs'],
            'documents': context['documents'], 'coverage': context['coverage']})
        print(f"Prepared {len(context['documents'])} complete documents; {len(context['batches'])} exhaustive model batches.")
    except Exception as error:
        dump(args.output / 'PREPARATION_FAILURE.json', {'schema': 'vm-lab-thematic-preparation-failure-v1',
            'error': str(error), 'model_analysis': 'NOT_STARTED', 'scientific_acceptance': 'NOT_GRANTED'})
        raise


if __name__ == '__main__':
    main()
