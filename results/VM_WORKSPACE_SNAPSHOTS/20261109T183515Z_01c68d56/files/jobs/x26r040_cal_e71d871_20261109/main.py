import os,time,json,hashlib,pathlib,sys,base64,tarfile,io,signal,resource,platform
T0=time.perf_counter(); C0=time.process_time()
for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[key]='1'
signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('120s hard cap')));signal.alarm(120)
resource.setrlimit(resource.RLIMIT_AS,(2048*1024**2,2048*1024**2))
work=pathlib.Path(os.environ['VM_WORK']); data=work/'data/x26r040_20261109'
mode=sys.argv[1]; out=pathlib.Path.cwd(); raw=base64.b64decode((data/'archive.b64').read_text())
assert hashlib.sha256(raw).hexdigest()=='96aec2703f921d280e0fe5bc5915bc04b03cc8af31df9d4b0183d3c647807d0b'
with tarfile.open(fileobj=io.BytesIO(raw),mode='r:xz') as tf:
    for member in tf.getmembers():
        q=pathlib.PurePosixPath(member.name)
        assert not q.is_absolute() and '..' not in q.parts and (member.isfile() or member.isdir())
    tf.extractall(out,filter='data')
root=out/'X26_R040_ANALYTIC_BATH';sys.path.insert(0,str(root))
import numpy as np,scipy
from x26r040.runner import run_spectral
from x26r040.provenance import preflight
from x26r040.workload import workload_inventory
from threadpoolctl import threadpool_info

def read_optional(p):
    try:return pathlib.Path(p).read_text().strip()
    except OSError:return None

def dump(name,obj):
    text=json.dumps(obj,indent=2,allow_nan=False)+'\n';(out/name).write_text(text)
    return hashlib.sha256(text.encode()).hexdigest()

def environment():
    env={'python':platform.python_version(),'platform':platform.platform(),'machine':platform.machine(),'numpy':np.__version__,'scipy':scipy.__version__,'cpu_count':os.cpu_count(),'affinity':sorted(os.sched_getaffinity(0)),'cpu_max':read_optional('/sys/fs/cgroup/cpu.max'),'memory_max':read_optional('/sys/fs/cgroup/memory.max'),'blas':threadpool_info(),'threads_env':{k:os.environ[k] for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']},'rlimit_as':list(resource.getrlimit(resource.RLIMIT_AS))}
    return env
m=json.loads((data/('INPUT_PRECALIBRATION.json' if mode=='calibrate' else 'INPUT.json')).read_text())
assert hashlib.sha256((data/'FREEZE.json').read_bytes()).hexdigest()==m['freeze_record_sha256']
f=json.loads((data/'FREEZE.json').read_text())
for key in ['model','energy_unit','time_unit','continuum_scan','pole_search','diagnostics','numerics','loading']:assert m[key]==f[key],key
for entry in (root/'SHA256SUMS.txt').read_text().splitlines():
    h,rel=entry.split(maxsplit=1); rel=rel.lstrip('*')
    assert hashlib.sha256((root/rel).read_bytes()).hexdigest()==h,rel
env=environment(); fingerprint=hashlib.sha256(json.dumps(env,sort_keys=True).encode()).hexdigest()
dump('ENVIRONMENT.json',{'environment':env,'fingerprint':fingerprint,'observed_epoch':time.time(),'load_average':list(os.getloadavg()),'disk_available_bytes':os.statvfs(out).f_bavail*os.statvfs(out).f_frsize})
dump('WORKLOAD.json',workload_inventory(m))
setup=time.perf_counter()-T0
if mode=='calibrate':
    timings=[]
    for i in range(2):
        t=time.perf_counter();r=run_spectral(m);timings.append(time.perf_counter()-t)
        assert r['technical_checks']['overall_technical_pass'],r['technical_checks']
        dump('CHECKPOINT.json',{'phase':'calibration','completed':i+1,'planned':2})
    dump('CALIBRATION.json',{'mode':'EXACT_WORKLOAD_TARGET_VM_CALIBRATION','setup_seconds':setup,'workload_wall_seconds':timings,'full_process_wall_seconds':time.perf_counter()-T0,'cpu_seconds':time.process_time()-C0,'environment_fingerprint':fingerprint,'workload':workload_inventory(m),'source_archive_sha256':hashlib.sha256(raw).hexdigest(),'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss})
else:
    g=m['runtime_gate'];assert g['environment_fingerprint']==fingerprint,'environment mismatch'
    for key,filename in [('calibration','CALIBRATION.json'),('forecast','FORECAST.json')]:assert hashlib.sha256((data/filename).read_bytes()).hexdigest()==g[key+'_sha256']
    gate=preflight(m);dump('PREFLIGHT.json',gate);assert gate['submit_allowed'],gate
    t=time.perf_counter();r=run_spectral(m);kernel=time.perf_counter()-t
    r['input_manifest_sha256']=hashlib.sha256((data/'INPUT.json').read_bytes()).hexdigest()
    dump('X26_REPORT.json',r)
    dump('CHECKPOINT.json',{'phase':'main_complete','completed':1,'planned':1})
    wall=time.perf_counter()-T0
    dump('PROCESS.json',{'wall_seconds':wall,'kernel_wall_seconds':kernel,'cpu_seconds':time.process_time()-C0,'setup_seconds':setup,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'environment_fingerprint':fingerprint,'runtime_gate':'PASS' if g['lower_seconds']<=wall<=g['upper_seconds'] else 'REVIEW_REQUIRED','forecast':g,'technical_pass':r['technical_checks']['overall_technical_pass'],'output_bytes_before_process_record':sum(p.stat().st_size for p in out.rglob('*') if p.is_file())})
    print(json.dumps({'status':r['status'],'wall_seconds':wall,'BIC':r['direct_bic']['verdict']}),flush=True)
    assert r['technical_checks']['overall_technical_pass']
signal.alarm(0)
