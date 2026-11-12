#!/usr/bin/env python3
"""Bounded, read-only context from existing registries; no extra science registry."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
INDEX = 'analysis/REGISTRY_LINKS/INDEX.json'
SOURCES = 'analysis/FOUR_CANDIDATE_INTEGRATION_20261108/SOURCE_INDEX.json'


def context(command, key=None, limit=20, root=ROOT):
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise ValueError('limit must be 1..100')
    raw = (root / INDEX).read_bytes()
    graph = json.loads(raw)
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    envelope = {'source_sha': sha, 'index_sha256': hashlib.sha256(raw).hexdigest(),
                'source': INDEX, 'read_only': True,
                'note': 'Working-tree snapshot; source_sha identifies HEAD, index_sha256 identifies actual bytes.'}
    if command == 'summary':
        data = {'counts': graph['counts'], 'semantics': graph['semantics']}
    elif command in {'card', 'neighbors'}:
        matches = [n for n in graph['nodes'] if key in (n['key'], n['id'])]
        if len(matches) != 1:
            raise ValueError('Use one exact typed key; unknown or ambiguous ID: ' + str(key))
        node = matches[0]
        url = f"https://github.com/IgorSabirov/vm-lab/blob/{sha}/{node['path']}"
        if node.get('fragment'):
            url += '#' + node['fragment']
        data = {'node': node, 'locator': url}
        if command == 'neighbors':
            edges = [e for e in graph['edges'] if node['key'] in (e['source'], e['target'])]
            data.update(edges=edges[:limit], total=len(edges), truncated=len(edges) > limit)
    elif command == 'sources':
        rows = json.loads((root / SOURCES).read_text())['external_integrations']
        if key:
            rows = [s for s in rows if s['id'] == key]
            if not rows:
                raise ValueError('Unknown external source')
        data = {'sources': rows[:limit], 'total': len(rows), 'truncated': len(rows) > limit}
    else:
        raise ValueError('Unknown context command')
    return {**envelope, 'data': data}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['summary', 'card', 'neighbors', 'sources'])
    parser.add_argument('key', nargs='?')
    parser.add_argument('--limit', type=int, default=20)
    args = parser.parse_args()
    print(json.dumps(context(args.command, args.key, args.limit), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
