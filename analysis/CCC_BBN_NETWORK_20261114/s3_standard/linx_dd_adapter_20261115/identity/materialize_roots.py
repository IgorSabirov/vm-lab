"""Create two hash-checked upstream roots; never run a model."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
from urllib.request import urlopen

PARENT=Path(__file__).resolve().parent.parent

def main():
    p=argparse.ArgumentParser();p.add_argument('out',type=Path);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((PARENT/'UPSTREAM.json').read_text());pristine=a.out/'pristine';patched=a.out/'override'
    for e in manifest['files']:
        with urlopen(f"https://raw.githubusercontent.com/{manifest['repository']}/{manifest['commit']}/{e['path']}",timeout=60) as r:data=r.read()
        if len(data)!=e['size'] or hashlib.sha256(data).hexdigest()!=e['sha256']:
            raise ValueError('Upstream mismatch: '+e['path'])
        f=pristine/e['path'];f.parent.mkdir(exist_ok=True,parents=True);f.write_bytes(data)
    shutil.copytree(pristine,patched)
    sys.path.insert(0,str(PARENT))
    from apply_upstream_patch import apply
    receipt=apply(patched);expected=json.loads((PARENT/'PATCH_RECEIPT.json').read_text())
    if receipt!=expected:raise ValueError('Recorded patch differs')
    (a.out/'PATCH_RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'pristine':str(pristine.resolve()),'override':str(patched.resolve()),'files':len(manifest['files'])}))

if __name__=='__main__':main()
