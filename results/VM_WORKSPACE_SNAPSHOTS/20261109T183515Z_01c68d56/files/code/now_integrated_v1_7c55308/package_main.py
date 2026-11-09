import os, zipfile, hashlib, json
from pathlib import Path
work=Path(os.environ['VM_WORK']).resolve()
src=work/'results'/'now_waiver_main_7c55308_20261108'/'main_output'
out=Path.cwd()/'FULL_MAIN_OUTPUT_7c55308.zip'
with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for p in sorted(src.rglob('*')):
  if p.is_file(): z.write(p,p.relative_to(src.parent))
print(json.dumps({'path':str(out),'size_bytes':out.stat().st_size,'sha256':hashlib.sha256(out.read_bytes()).hexdigest()}))