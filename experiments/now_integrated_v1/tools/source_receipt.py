#!/usr/bin/env python3
"""Attest a fixed Git checkout without running any model."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT))
from nowexp.provenance import source_manifest, digest


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--commit', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if len(a.commit) != 40 or any(c not in '0123456789abcdef' for c in a.commit):
        raise ValueError('exact commit SHA required')
    def git(*args):
        return subprocess.check_output(['git', '-C', str(REPO), *args])
    files = source_manifest(ROOT)
    blobs = {}
    for name in files:
        committed = git('show', a.commit+':'+name)
        if committed != (REPO/name).read_bytes():
            raise ValueError('working file differs from fixed commit: '+name)
        blobs[name] = hashlib.sha1(b'blob '+str(len(committed)).encode()+b'\0'+committed).hexdigest()
    value = dict(source_commit=a.commit, github_tree_sha=git('rev-parse', a.commit+'^{tree}').decode().strip(),
                 files=files, git_blobs=blobs, source_digest=digest(files))
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(value, indent=2)+'\n')
    print(json.dumps(dict(files=len(files), source_digest=value['source_digest'])))


if __name__ == '__main__':
    main()
