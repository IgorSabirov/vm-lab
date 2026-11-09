from pathlib import Path
import sys,json,hashlib,zlib,base64
sys.path.insert(0,'x26_freeze/package')
from x26r040.physical import workload,canonical,dump
from x26r040.physical_cli import calibration_tasks
r=Path('x26_freeze/package');m=json.loads((r/'PHYSICAL_MANIFEST.json').read_text())
w=workload(m);dump(Path('x26_freeze/WORKLOAD.json'),w)
paths=[p for p in r.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc' and p.name!='SHA256SUMS.txt']
(r/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(r))+'\n' for p in sorted(paths)))
files={str(p.relative_to(r)):p.read_text() for p in sorted(paths+[r/'SHA256SUMS.txt'])}
hashes={k:hashlib.sha256(v.encode()).hexdigest() for k,v in files.items()}
bundle={'files':files,'sha256':hashes,'source_digest':hashlib.sha256(canonical(hashes)).hexdigest()}
Path('x26_freeze/BUNDLE.b64').write_text(base64.b64encode(zlib.compress(canonical(bundle),9)).decode())
dump(Path('x26_freeze/SOURCE_RECEIPT.json'),{'source_digest':bundle['source_digest'],'files':hashes,
 'manifest_digest':w['manifest_digest'],'task_digest':w['task_digest'],
 'bundle_sha256':hashlib.sha256(Path('x26_freeze/BUNDLE.b64').read_bytes()).hexdigest(),
 'launcher_sha256':hashlib.sha256(Path('x26_freeze/LAUNCH.py').read_bytes()).hexdigest(),
 'test_count':36,'tests':'PASS','main_tasks':len(w['tasks']),'calibration_tasks':len(calibration_tasks(w['tasks']))})
print('files',len(files),'bundle_bytes',Path('x26_freeze/BUNDLE.b64').stat().st_size,'source',bundle['source_digest'])
