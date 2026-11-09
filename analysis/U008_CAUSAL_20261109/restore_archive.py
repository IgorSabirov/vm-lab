"""Reassemble the unchanged VM ZIP and verify all hashes; no simulation."""
import hashlib, json
from pathlib import Path
root = Path(__file__).resolve().parent
manifest = json.loads((root / 'ARCHIVE_PARTS.json').read_text())
chunks = []
for part in manifest['parts']:
    data = (root / part['path']).read_bytes()
    if len(data) != part['bytes'] or hashlib.sha256(data).hexdigest() != part['sha256']:
        raise SystemExit('Invalid archive part: ' + part['path'])
    chunks.append(data)
data = b''.join(chunks)
if len(data) != manifest['bytes'] or hashlib.sha256(data).hexdigest() != manifest['sha256']:
    raise SystemExit('Invalid assembled archive')
out = root / manifest['output']
if out.exists() and out.read_bytes() != data:
    raise SystemExit('Refusing to overwrite a different archive')
out.write_bytes(data)
print(str(out) + ': SHA256 PASS ' + manifest['sha256'])
