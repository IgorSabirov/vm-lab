#!/usr/bin/env python3
"""Restore published files/chunks from a LOCAL repository checkout into a new directory."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath


def below(root, relative):
    part = PurePosixPath(relative)
    if part.is_absolute() or '..' in part.parts or not part.parts:
        raise ValueError('Unsafe manifest path')
    result = root.joinpath(*part.parts)
    if not result.resolve().is_relative_to(root.resolve()):
        raise ValueError('Path leaves chosen root')
    return result


def restore(repo, manifest, destination):
    data = json.loads(manifest.read_text())
    destination.mkdir(parents=True, exist_ok=False)
    count = 0
    for record in data['files']:
        if record['status'] != 'PUBLISHED':
            continue
        target = below(destination, record['path'])
        target.parent.mkdir(parents=True, exist_ok=True)
        whole = hashlib.sha256()
        size = 0
        with target.open('xb') as output:
            for part in record['parts']:
                raw = below(repo, part['repository_path']).read_bytes()
                if len(raw) != part['bytes'] or hashlib.sha256(raw).hexdigest() != part['sha256'] or size != part['offset']:
                    raise ValueError('Part verification failed: ' + record['path'])
                output.write(raw)
                whole.update(raw)
                size += len(raw)
        if size != record['bytes'] or whole.hexdigest() != record['sha256']:
            raise ValueError('File verification failed: ' + record['path'])
        count += 1
    print('RESTORED', count, 'snapshot status', data['status'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repository', type=Path)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('new_destination', type=Path)
    args = parser.parse_args()
    restore(args.repository.resolve(), args.manifest, args.new_destination.resolve())
