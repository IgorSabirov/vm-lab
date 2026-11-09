"""Immutable bootstrap: published bundle -> receipt verification -> v3 CLI."""
import os,sys,time,json,hashlib,pathlib,base64,zlib,resource,signal
T0=time.perf_counter();C0=time.process_time()
for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
mode=sys.argv[1];data=pathlib.Path(os.environ['VM_WORK'])/'data/x26_v3_20261109'
raw=(data/'BUNDLE.b64').read_text();bundle=json.loads(zlib.decompress(base64.b64decode(raw)))
def canon(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
assert hashlib.sha256(canon(bundle['sha256'])).hexdigest()==bundle['source_digest']
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
                'measurement_boundary':'bootstrap, import, preflight, all tasks, reports and output hash manifest; final timing write excluded'})
(out/'LAUNCH_PROCESS.json').write_text(json.dumps(process,indent=2,allow_nan=False)+'\n')
signal.alarm(0)
print(json.dumps({'mode':mode,'exit_code':code,'full_wall_seconds':wall,'technical_pass':process['technical_pass']}),flush=True)
raise SystemExit(code)
