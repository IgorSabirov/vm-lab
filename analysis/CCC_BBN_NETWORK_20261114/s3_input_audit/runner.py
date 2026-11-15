import hashlib, json, math, pathlib, sys, time, resource, platform
from datetime import datetime, timezone

root = pathlib.Path(__file__).parent
out = root / 'results'
assert not out.exists(), 'No automatic repeat'
source = sys.argv[1]
assert len(source) == 40
resource.setrlimit(resource.RLIMIT_AS, (4*1024**3, 4*1024**3))
resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
out.mkdir()
start = time.monotonic()
def write(name, value):
    (out/name).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')
write('ADMISSION.json', {'status':'ADMITTED','source_commit':source,'executor':'local','utc':datetime.now(timezone.utc).isoformat(),'cap_seconds':60,'memory_bytes':4*1024**3,'output_bytes':2*1024**3})
p = json.loads((root/'PLAN.json').read_text())
raw = (root/'RESPONSE.json').read_bytes()
assert hashlib.sha256(raw).hexdigest() == p['response_sha256']
response = json.loads(raw)
assert response['status'] == 'LOCAL_ETA_RESPONSE_COMPLETE'
rows = {}
for key, obs in p['observations'].items():
    x = response['observables'][key]
    slope = math.log(x['high']/x['low']) / math.log(1.01/.99)
    assert math.isclose(slope, x['dlnY_dlneta_secant'], rel_tol=1e-10, abs_tol=1e-12)
    rows[key] = {'baseline':x['baseline'], 'observed':obs['mean'], 'residual':x['baseline']-obs['mean'], 'published_observational_sigma':obs['sigma'], 'J_dY_dlneta_secant':x['baseline']*slope}
keys = list(rows)
J = [rows[k]['J_dY_dlneta_secant'] for k in keys]
C = [[a*b for b in J] for a in J]
write('RESULT.json', {'rows':rows, 'order':keys, 'eta_covariance_per_unit_var_lneta':C, 'interpretation':'Multiply by independently supplied Var(ln eta); local linearization only. No eta distribution selected.', 'joint_likelihood':None,'theory_covariance':None,'significance':None})
write('SUMMARY.json', {'engineering_status':'COMPLETED_PENDING_VERIFICATION','scientific_status':'INPUT_DIAGNOSTIC_ONLY','parent':'S_ETA_20261114_r1','source_commit':source,'wall_seconds':time.monotonic()-start,'python':platform.python_version(),'scientific_acceptance':False,'remaining':['BBN-independent CMB parameter distribution and assumptions','Nuclear and weak-rate covariance propagated on pinned PRIMAT','Helium mass-fraction convention mapping and dataset update audit','Cross-observable covariance before a joint likelihood']})
