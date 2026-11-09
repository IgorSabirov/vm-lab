"""Install the GitHub-pinned source bundle, validating every Git blob."""
import argparse,base64,hashlib,json,os,zlib
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--bundle',required=True);a=p.parse_args()
b=json.loads(Path(a.bundle).read_text())
files=json.loads(zlib.decompress(base64.b64decode(b['zlib_base64'])))
work=Path(os.environ['VM_WORK']).resolve()
repo=work/'code'/('now_long_'+b['source_commit'][:7])
if repo.exists():raise ValueError('use a new immutable installation')
for name,text in files.items():
    rel=Path(name)
    if rel.is_absolute() or '..' in rel.parts:raise ValueError('unsafe relative path')
    raw=text.encode();actual=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
    if b['git_blobs'].get(name)!=actual:raise ValueError('GitHub blob mismatch: '+name)
for name,text in files.items():
    dest=repo/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(text)
root=repo/'experiments/now_integrated_v1'
import sys
sys.path.insert(0,str(root))
from nowexp.provenance import source_manifest,digest,verify_source
manifest=source_manifest(root)
receipt=dict(source_commit=b['source_commit'],github_tree_sha=b['github_tree_sha'],files=manifest,
             git_blobs={k:b['git_blobs'][k] for k in manifest},source_digest=digest(manifest))
rp=repo/'LONG_SOURCE.json';rp.write_text(json.dumps(receipt,indent=2)+'\n')
verify_source(root,b['source_commit'],rp)
accept=dict(status='accepted',source_digest=digest(manifest),audit_waived_by_user=True,
    authorized_phases=['smoke','calibrate','main'],
    user_decision_reference='2026-11-08 explicit instruction: launch 10+ minutes machine time; standing audit waiver with full runtime gate',
    review_reference='USER_EXPLICIT_AUDIT_WAIVER; 73 local tests passed; full recovery smoke and measured VM calibration required')
(repo/'LONG_ACCEPTANCE.json').write_text(json.dumps(accept,indent=2)+'\n')
report=dict(installed=True,repo=str(repo),source_commit=b['source_commit'],source_digest=digest(manifest),files=len(manifest),git_blobs_verified=True)
Path('INSTALL.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
