"""Apply the one-file LINX API extension only to the hash-verified upstream pin."""
from __future__ import annotations
import argparse
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

def apply(root: Path) -> dict:
    manifest = json.loads((HERE / 'UPSTREAM.json').read_text())
    for entry in manifest['files']:
        raw = (root / entry['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry['sha256']:
            raise ValueError('Upstream SHA256 mismatch: ' + entry['path'])
    target = root / 'linx/abundances.py'
    old = target.read_text()
    new = old
    edits = [
        ('        save_history=False\n',
         '        save_history=False, rate_tables_override=None\n'),
        ('        rate_tables = self.nuclear_net.precompute_rate_tables(nuclear_rates_q)\n',
         '        # Low-level override: host validation belongs to the caller.\n'
         '        rate_tables = (\n'
         '            self.nuclear_net.precompute_rate_tables(nuclear_rates_q)\n'
         '            if rate_tables_override is None else rate_tables_override\n'
         '        )\n'),
        ('        nuclear_rates_q : array, optional\n',
         '        rate_tables_override : tuple of arrays, optional\n'
         '            Prevalidated full rate-table tuple in reaction order. Uses\n'
         '            existing Reaction nodes and encoding. Replaces table building\n'
         '            only; nuclear_rates_q is not applied again. See host adapter.\n'
         '        nuclear_rates_q : array, optional\n'),
    ]
    for before, after in edits:
        if new.count(before) != 1:
            raise ValueError('Patch anchor is not unique')
        new = new.replace(before, after, 1)
    target.write_text(new)
    patch = ''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                    fromfile='a/linx/abundances.py', tofile='b/linx/abundances.py'))
    return {'upstream_commit': manifest['commit'],
            'original_sha256': hashlib.sha256(old.encode()).hexdigest(),
            'patched_sha256': hashlib.sha256(new.encode()).hexdigest(),
            'patch': patch}

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('root', type=Path)
    p.add_argument('--receipt', type=Path, required=True)
    args = p.parse_args()
    receipt = apply(args.root)
    args.receipt.write_text(json.dumps(receipt, indent=2) + '\n')
