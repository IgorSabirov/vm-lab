import json, math, pathlib, hashlib
from decimal import Decimal, getcontext
root = pathlib.Path(__file__).parent
p=json.loads((root/'PLAN.json').read_text()); r=json.loads((root/'results/RESULT.json').read_text())
getcontext().prec=40
for key,x in r['rows'].items():
    assert abs(Decimal(str(x['residual']))-(Decimal(str(x['baseline']))-Decimal(str(x['observed'])))) < Decimal('1e-16')
    assert x['published_observational_sigma']==p['observations'][key]['sigma']
C=r['eta_covariance_per_unit_var_lneta']; J=[r['rows'][k]['J_dY_dlneta_secant'] for k in r['order']]
for i in range(len(J)):
    for j in range(len(J)):
        assert math.isclose(C[i][j],J[i]*J[j],rel_tol=1e-14)
assert C[0][0]>=0 and C[1][1]>=0
assert abs(C[0][0]*C[1][1]-C[0][1]**2)<1e-30
assert r['joint_likelihood'] is None and r['significance'] is None and r['theory_covariance'] is None
s=json.loads((root/'results/SUMMARY.json').read_text()); s['engineering_status']='PASS'; s['verification']='Residual arithmetic, symmetric positive-semidefinite rank-one eta covariance, no unsupported significance'
(root/'results/SUMMARY.json').write_text(json.dumps(s,indent=2)+'\n')
files={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in (root/'results').iterdir() if f.is_file()}
(root/'results/ARTIFACTS.json').write_text(json.dumps(files,indent=2)+'\n')
print(json.dumps(s))
