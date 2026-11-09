"""Byte-level admission and final output sealing; no numerical evolution."""
import hashlib
import json
from pathlib import Path

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def admit(data, expected_binding_sha256):
    """The binding digest must come from the pinned submission, not the file itself.

    Avoid self-hashing forecasts: an external admission record binds both the
    final forecast bytes and the calibration bytes. The launcher argument pins
    that record. All checks precede calling the numerical executor.
    """
    data=Path(data);binding_path=data/'ADMISSION_BINDING.json'
    if not isinstance(expected_binding_sha256,str) or len(expected_binding_sha256)!=64:
        raise ValueError('pinned admission binding SHA256 is required')
    if sha(binding_path)!=expected_binding_sha256: raise ValueError('admission binding changed')
    binding=json.loads(binding_path.read_text())
    for name in ['CALIBRATION.json','RUNTIME_GATE.json']:
        if sha(data/name)!=binding['artifact_sha256'][name]: raise ValueError(name+' changed')
    cal=json.loads((data/'CALIBRATION.json').read_text())
    gate=json.loads((data/'RUNTIME_GATE.json').read_text())
    if gate['calibration_sha256']!=sha(data/'CALIBRATION.json'): raise ValueError('calibration chain broken')
    if gate['status']!='TARGET_VM_CALIBRATION_PASS' or cal['technical_pass'] is not True:
        raise ValueError('non-passing calibration')
    for key in ['source_digest','manifest_digest','workload_digest','environment_fingerprint']:
        if cal[key]!=gate[key] or gate[key]!=binding[key]: raise ValueError(key+' mismatch')
    if not 0<gate['lower_seconds']<=gate['expected_seconds']<=gate['upper_seconds']<gate['hard_wall_seconds']:
        raise ValueError('invalid runtime interval')
    return binding

def final_manifest(directory, output_name='OUTPUT_MANIFEST.json'):
    """Call last, after FORECAST, PROCESS and LAUNCH_PROCESS are final.

    This file is the sole self-exclusion. No report can be mutated after this
    call without invalidating its hash. External worker times cover sealing.
    """
    directory=Path(directory)
    result={str(p.relative_to(directory)):sha(p) for p in sorted(directory.rglob('*'))
            if p.is_file() and str(p.relative_to(directory))!=output_name and not p.name.endswith('.tmp')}
    path=directory/output_name;tmp=directory/(output_name+'.tmp')
    tmp.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');tmp.replace(path)
    return result

def audit_manifest(directory, manifest):
    directory=Path(directory);bad=[]
    for rel,expected in manifest.items():
        q=Path(rel)
        if q.is_absolute() or '..' in q.parts: raise ValueError('unsafe manifest path')
        p=directory/q;actual=sha(p) if p.is_file() else None
        if actual!=expected:bad.append({'path':rel,'expected':expected,'actual':actual})
    return bad


"""Immutable bootstrap: published bundle -> receipt verification -> v3 CLI."""
import os,sys,time,json,hashlib,pathlib,base64,zlib,resource,signal
T0=time.perf_counter();C0=time.process_time()
for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
mode=sys.argv[1];data=pathlib.Path(os.environ['VM_WORK'])/'data/x26_v3_20261109'
binding=admit(data,sys.argv[2]) if mode=='main' else None
raw=(data/'BUNDLE.b64').read_text();bundle=json.loads(zlib.decompress(base64.b64decode(raw)))
def canon(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
assert hashlib.sha256(canon(bundle['sha256'])).hexdigest()==bundle['source_digest']
if binding is not None:assert binding['source_digest']==bundle['source_digest']
root=pathlib.Path.cwd()/'source';root.mkdir(exist_ok=True)
for name,content in bundle['files'].items():
    q=pathlib.PurePosixPath(name)
    assert not q.is_absolute() and '..' not in q.parts
    assert hashlib.sha256(content.encode()).hexdigest()==bundle['sha256'][name]
    p=root/name;p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists():assert p.read_text()==content
    else:p.write_text(content)
m=json.loads((root/'PHYSICAL_MANIFEST.json').read_text())
cap=m['limits']['calibration_cap_seconds'] if mode=='calibrate' else m['limits']['hard_wall_seconds']
signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('frozen wall limit; checkpoints preserved')))
signal.alarm(cap)
resource.setrlimit(resource.RLIMIT_AS,(m['limits']['memory_mib']*1024**2,)*2)
sys.path.insert(0,str(root))
from x26r040.physical_cli import run
out=pathlib.Path.cwd()/'output'
import_start=time.perf_counter()
code=run(mode,m,out,bundle['source_digest'],data/'RUNTIME_GATE.json' if mode=='main' else None)
wall=time.perf_counter()-T0
process=json.loads((out/'PROCESS.json').read_text())
if mode=='calibrate':
    p=out/'FORECAST.json';f=json.loads(p.read_text())
    overhead=import_start-T0
    f['launcher_overhead_seconds']=overhead
    f['expected_seconds']+=overhead;f['lower_seconds']+=overhead;f['upper_seconds']+=overhead
    f['calibration_job_id']=pathlib.Path.cwd().name
    f['calibration_sha256']=hashlib.sha256((out/'CALIBRATION.json').read_bytes()).hexdigest()
    p.write_text(json.dumps(f,indent=2,allow_nan=False)+'\n')
else:
    gate=json.loads((data/'RUNTIME_GATE.json').read_text())
    process['runtime_gate']='PASS' if gate['lower_seconds']<=wall<=gate['upper_seconds'] and process['resumed']==0 else 'REVIEW_REQUIRED'
process.update({'full_launcher_wall_seconds':wall,'launcher_cpu_seconds':time.process_time()-C0,
                'launcher_overhead_seconds':import_start-T0,'exit_code':code,
                'measurement_boundary':'bootstrap, import, preflight, all tasks, reports and output hash manifest; final timing write and final output sealing excluded; worker status covers the whole process'})
(out/'LAUNCH_PROCESS.json').write_text(json.dumps(process,indent=2,allow_nan=False)+'\n')
final_manifest(out)  # Final operation affecting files; reports are no longer mutated.
signal.alarm(0)
print(json.dumps({'mode':mode,'exit_code':code,'full_wall_seconds':wall,'technical_pass':process['technical_pass']}),flush=True)
raise SystemExit(code)
