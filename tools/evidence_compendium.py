#!/usr/bin/env python3
"""Deterministic, explicitly scoped research packages; no scientific attestation.

Explicit files only. No recursive archive of the repository or operator machine.
Signatures produced in Actions attest this packaging activity, not prior VM runs.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
from external_sources import local


def build(root, descriptor, target):
    spec = json.loads(local(root, descriptor).read_text())
    names = sorted(set(spec['files'] + [descriptor]))
    if len(names) != len(spec['files']) + (descriptor not in spec['files']):
        raise ValueError('Duplicate files in compendium')
    payload = {}
    for name in names:
        p = local(root, name)
        if not p.is_file() or p.stat().st_size > 20_000_000:
            raise ValueError('Missing or oversized compendium file: ' + name)
        payload[name] = p.read_bytes()
    inventory = {name: {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)} for name, data in payload.items()}
    manifest = {'schema': 'vm-lab-compendium-v1', 'scope': spec['scope'],
                'reproduce': spec['reproduce'], 'raw_data': spec['raw_data'],
                'limitations': spec['limitations'], 'files': inventory,
                'scientific_acceptance': False, 'vm_execution_attested': False}
    payload['MANIFEST.json'] = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
    if 'MANIFEST.json' in inventory:
        raise ValueError('Reserved manifest filename')
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, data in sorted(payload.items()):
            item = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            item.external_attr = 0o100644 << 16
            archive.writestr(item, data)
    return {'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'files': len(payload), 'bytes': target.stat().st_size}


def verify(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or any(Path(n).is_absolute() or '..' in Path(n).parts for n in names):
            raise ValueError('Unsafe or duplicate archive member')
        m = json.loads(archive.read('MANIFEST.json'))
        if set(names) != set(m['files']) | {'MANIFEST.json'}:
            raise ValueError('Incomplete or unexpected inventory')
        for name, row in m['files'].items():
            raw = archive.read(name)
            if len(raw) != row['bytes'] or hashlib.sha256(raw).hexdigest() != row['sha256']:
                raise ValueError('Compendium content mismatch')
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--descriptor', default='infra/external/COMPENDIUM.json')
    p.add_argument('--output', type=Path, default=Path('external-evidence/compendium.zip'))
    p.add_argument('--verify', type=Path)
    a = p.parse_args()
    if a.verify:
        verify(a.verify)
        print('Compendium integrity PASS')
    else:
        print(json.dumps(build(Path(__file__).resolve().parents[1], a.descriptor, a.output)))
        verify(a.output)


if __name__ == '__main__':
    main()
