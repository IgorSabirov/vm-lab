"""Verify every pinned file, allowing only the recorded one-file API patch."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

def verify():
    manifest = json.loads((HERE/'UPSTREAM.json').read_text())
    receipt = json.loads((HERE/'PATCH_RECEIPT.json').read_text())
    if manifest['commit'] != receipt['upstream_commit']:
        raise ValueError('Patch provenance mismatch')
    for e in manifest['files']:
        digest = hashlib.sha256((HERE/'upstream'/e['path']).read_bytes()).hexdigest()
        expected = receipt['patched_sha256'] if e['path']=='linx/abundances.py' else e['sha256']
        if digest != expected:
            raise ValueError('Unexpected upstream modification: '+e['path'])
    return {'files_verified':len(manifest['files']), 'modified_files':['linx/abundances.py'],
            'upstream_commit':manifest['commit']}

if __name__ == '__main__':
    print(json.dumps(verify(),indent=2))
