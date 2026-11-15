"""Download only manifest-listed pinned LINX files, verify, apply local patch."""
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent

if __name__ == '__main__':
    manifest = json.loads((HERE/'UPSTREAM.json').read_text())
    root = HERE/'upstream'
    if root.exists():
        raise SystemExit('Refusing to overwrite an existing upstream directory')
    root.mkdir()
    for e in manifest['files']:
        url = f"https://raw.githubusercontent.com/{manifest['repository']}/{manifest['commit']}/{e['path']}"
        with urlopen(url, timeout=60) as r:
            data = r.read()
        blob = hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest()
        if len(data) != e['size'] or blob != e['sha'] or hashlib.sha256(data).hexdigest() != e['sha256']:
            raise SystemExit('Hash/size mismatch: '+e['path'])
        target = root/e['path']
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(data)
    from apply_upstream_patch import apply
    (HERE/'PATCH_RECEIPT.json').write_text(json.dumps(apply(root),indent=2)+'\n')
