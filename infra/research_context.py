#!/usr/bin/env python3
"""Resolve declared research dependencies; no inference, execution or status promotion."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import registry_links as registry

POLICY = 'infra/copilot/context/requirements.json'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read(root, path):
    p = root / path
    if Path(path).is_absolute() or '..' in Path(path).parts or p.is_symlink() or not p.resolve().is_relative_to(root.resolve()):
        raise ValueError('Invalid context path')
    return p.read_bytes()


def resolve(root, roots):
    raw_policy = read(root, POLICY)
    policy = json.loads(raw_policy)
    stale, graph = registry.run(root)
    if stale:
        raise ValueError('Stale research graph: ' + ', '.join(stale))
    nodes = {n['key']: n for n in graph['nodes']}
    if not roots or set(roots) - nodes.keys():
        raise ValueError('Unknown or empty context roots')
    selected = set(roots)
    expand = set(roots) & set(policy['expand_roots'])
    reasons = {k: ['task_root'] for k in roots}
    # One declared graph hop. Navigation/analogies are not transitive dependencies.
    for e in graph['edges']:
        key = None
        if e['target'] in expand and e['relation'] in policy['incoming_relations']:
            key = e['source']
        if e['source'] in expand and e['relation'] in policy['outgoing_relations']:
            key = e['target']
        if key:
            selected.add(key)
            reasons.setdefault(key, []).append(e)
    documents = {}
    for rule in policy['rules']:
        triggers = sorted(set(rule['when_any']) & selected)
        if triggers:
            for key in rule.get('required_nodes', []):
                if key not in nodes:
                    raise ValueError('Missing mandatory node: ' + key)
                selected.add(key); reasons.setdefault(key, []).append({'rule': rule['id'], 'triggers': triggers})
            for item in rule['documents']:
                raw = read(root, item['path'])
                for marker in item.get('required_markers', []):
                    if marker not in raw.decode():
                        raise ValueError('Missing required definition: ' + marker)
                entry = documents.setdefault(item['id'], {
                    'id': item['id'], 'path': item['path'], 'sha256': digest(raw),
                    'text': raw.decode(), 'required': True, 'partial': False,
                    'category': item['category'], 'required_by': []})
                if entry['path'] != item['path']:
                    raise ValueError('Ambiguous document identity')
                entry['required_by'].append({'rule': rule['id'], 'triggers': triggers})
    main = json.loads(read(root, registry.MAIN))
    questions = json.loads(read(root, registry.QUESTIONS))
    premises = read(root, registry.PREMISES).decode()
    groups = {'result': main['results'], 'construct': main['constructs'],
              'link': main['open_links'], 'question': questions['questions'],
              'review': main.get('external_reviews', []),
              'premise': registry.parse_premises(premises),
              'obligation': registry.parse_obligations(premises),
              'external': json.loads(read(root, registry.EXTERNAL))['external_integrations']}
    sources = {k: registry.MAIN for k in ('result', 'construct', 'link', 'review')}
    sources.update(question=registry.QUESTIONS, premise=registry.PREMISES,
                   obligation=registry.PREMISES, external=registry.EXTERNAL)
    cards = []
    for key in sorted(selected):
        node = nodes[key]; kind, ident = key.split(':', 1)
        if kind == 'decision':
            path = 'decisions/' + ident + '.json'; data = json.loads(read(root, path))
        else:
            if kind not in groups:
                raise ValueError('Unsupported mandatory card: ' + key)
            path = sources[kind]; data = next(r for r in groups[kind] if r['id'] == ident)
        cards.append({'key': key, 'source': path, 'source_sha256': digest(read(root, path)),
                      'card_sha256': digest(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()),
                      'required_by': reasons[key], 'status': node['status'], 'data': data})
    edges = [e for e in graph['edges'] if e['source'] in selected and e['target'] in selected]
    frontier = [e for e in graph['edges'] if (e['source'] in selected) != (e['target'] in selected)]
    return {'schema': 'vm-lab-research-context-v1', 'policy': POLICY,
            'policy_sha256': digest(raw_policy), 'roots': sorted(roots), 'expanded_roots': sorted(expand),
            'documents': [documents[k] for k in sorted(documents)], 'cards': cards,
            'nodes': [{field: value for field, value in nodes[k].items() if field != 'title'}
                      for k in sorted(selected)], 'edges': edges,
            'frontier_not_expanded': frontier,
            'coverage': 'DECLARED_REQUIREMENTS_COMPLETE_NOT_ALL_SCIENCE',
            'selection': 'One typed dependency hop plus explicit rules; missing mandatory input is an error; no silent truncation.',
            'scientific_acceptance': 'NOT_GRANTED'}


def reconcile(connections, graph):
    """Mechanical identity check, not semantic equivalence or scientific review."""
    keys = {n['key'] for n in graph['nodes']}
    rows = []
    for i, c in enumerate(connections):
        if c['source'] not in keys or c['target'] not in keys:
            raise ValueError('Unknown proposed graph endpoint')
        matches = [e for e in graph['edges'] if e['source'] == c['source'] and e['target'] == c['target']]
        exact = any(e['relation'] == c['relation'] for e in matches)
        rows.append({'index': i, 'source': c['source'], 'target': c['target'],
            'proposed_relation': c['relation'],
            'classification': 'EXISTING_TYPED_EDGE' if exact else 'EXISTING_ENDPOINT_PAIR_DIFFERENT_TYPE' if matches else 'NEW_ENDPOINT_PAIR',
            'existing_edges': matches,
            'allowed_as_external_review_relation': c['relation'] in registry.REVIEW_RELATIONS,
            'semantic_equivalence': 'NOT_EVALUATED', 'automatic_import': False})
    return {'rows': rows, 'counts': {k: sum(r['classification'] == k for r in rows) for k in
        ('EXISTING_TYPED_EDGE', 'EXISTING_ENDPOINT_PAIR_DIFFERENT_TYPE', 'NEW_ENDPOINT_PAIR')},
        'allowed_external_review_relations': sorted(registry.REVIEW_RELATIONS),
        'note': 'Same endpoints or type do not establish equivalent claims. No new registry edges are accepted.'}
