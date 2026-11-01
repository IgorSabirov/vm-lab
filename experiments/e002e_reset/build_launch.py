"""Assemble a small immutable GitHub launch tree; no calculations or submission."""
import argparse,hashlib,json,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from e002e_reset_exp.plan import implementation_manifest,implementation_hash,protocol_hash,workload
from e002e_exp.runtime import kernel_hash


def pin(path):
    return dict(path=path,sha256=hashlib.sha256((ROOT/path).read_bytes()).hexdigest())


def build(mode,destination):
    destination=Path(destination)
    if destination.exists():raise FileExistsError(destination)
    prefix='experiments/e002e_reset/'
    review=json.loads((ROOT/(prefix+'technical_review.json')).read_text())
    if review['status']!='REVIEWED_AND_CHECKED' or review['implementation_sha256']!=implementation_hash():
        raise ValueError('Unreviewed implementation')
    names=['science_freeze.json','evidence.json','technical_review.json']
    evidence=json.loads((ROOT/(prefix+'evidence.json')).read_text())
    files={e['path'] for e in implementation_manifest()}|{prefix+n for n in names}
    files|={item[k]['path'] for item in evidence['cases'] for k in ('baseline','corr')}
    config=dict(mode=mode,source_commit='FROM_VERIFIED_VM_LAUNCHER',protocol_sha256=protocol_hash(),
        implementation_sha256=implementation_hash(),**{n:pin(prefix+n+'.json') for n in ('science_freeze','evidence','technical_review')})
    if mode=='calibration':
        plan=json.loads((ROOT/(prefix+'CALIBRATION_PLAN_v001.json')).read_text())
        config.update(forecast=plan['forecast'],memory_budget=plan['memory_budget'])
    else:
        path=prefix+'calibration_reviewed.json';cal=json.loads((ROOT/path).read_text())
        if cal['status']!='CALIBRATION_REVIEWED':raise ValueError('Calibration not reviewed')
        files.add(path);config.update(calibration=pin(path),forecast=cal['production_forecast'],memory_budget=cal['memory_budget'])
    destination.mkdir(parents=True)
    for name in sorted(files):
        target=destination/'reset_payload'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
    shutil.copyfile(ROOT/(prefix+'vm_entry.py'),destination/'run.py')
    outer=dict(address_space_limit_bytes=8589934592,kernel_sha256=kernel_hash(),worker_config=config)
    (destination/'config.json').write_text(json.dumps(outer,indent=2)+'\n')
    manifest=[]
    for p in sorted(destination.rglob('*')):
        if p.is_file():
            data=p.read_bytes();manifest.append(dict(path=str(p.relative_to(destination)),size=len(data),
                sha256=hashlib.sha256(data).hexdigest(),git_blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()))
    return dict(mode=mode,counts=workload(mode),files=manifest,implementation_sha256=implementation_hash(),protocol_sha256=protocol_hash())


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['calibration','production']);p.add_argument('destination');a=p.parse_args()
    print(json.dumps(build(a.mode,a.destination),indent=2))
