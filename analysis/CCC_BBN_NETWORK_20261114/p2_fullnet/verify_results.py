"""Read-only independent verification and report for completed P2 artifacts."""
import hashlib,json,re,sys
from pathlib import Path
import numpy as np
root=Path(sys.argv[1]); out=Path(sys.argv[2])
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def A(n):return 1 if n in ('n','p') else int(re.search(r'\d+$',n).group())
manifest=read(root/'ARTIFACTS.json')
for p,info in manifest['files'].items():
    f=root/p
    assert f.stat().st_size==info['bytes'] and sha(f)==info['sha256'],p
summary=read(root/'SUMMARY.json')
assert summary['status']=='ENGINEERING_PASS'
raws={}; results={}; traces={}; diagnostics={}
for mode in ('COLD','WARM'):
    p=root/'runs'/mode
    r=read(p/'RESULT.json'); results[mode]=r
    assert r['status']=='ENGINEERING_PASS'
    a=np.load(p/'RAW_SOLVER.npz'); raws[mode]={k:a[k] for k in a.files}
    t=read(p/'TRACE.json');traces[mode]=t
    ds=[]
    for e in r['eras']:
        tag=e['era']; names=a[tag+'_species'].tolist(); times=a[tag+'_t_seconds']; y=a[tag+'_Y']
        assert y.shape==(len(names),len(times)) and np.isfinite(y).all()
        assert np.isfinite(times).all() and np.all(np.diff(times)>0)
        mass=np.array([A(n) for n in names]); residual=float(np.max(np.abs(mass@y-1)))
        assert residual<=1e-10 and float(y.min())>=-1e-12
        dense=next(q for q in t['eras'] if q['era']==tag)
        dy=np.asarray(dense['Y']); assert len(dy)==401 and np.isfinite(dy).all()
        ds.append({'era':tag,'species':len(names),'raw_nodes':len(times),'nfev':e['nfev'],
            'max_baryon_residual':residual,'raw_min':float(y.min()),'dense_baryon_residual':float(np.max(np.abs(dy@mass-1)))})
    assert ds[-1]['species']==59 and r['checks']['LT_has_428_channels_including_weak'] is True
    yf=r['result']['Y_final']; lt=raws[mode]['LT_Y'][:,-1]; names=raws[mode]['LT_species'].tolist()
    assert all(yf[n]==max(float(v),0) for n,v in zip(names,lt))
    # Independently reconstruct two key observables from the abundance vector.
    yp=4*yf['He4']; dh=yf['H2']/yf['p']
    assert abs(yp-r['result']['YPBBN'])<1e-15 and abs(dh-r['result']['DoH'])<1e-19
    diagnostics[mode]={'eras':ds,'YPBBN':yp,'DoH':dh,'weak_unchanged':r['checks']['weak_cache_unchanged'],'worker_status':r['status']}
assert traces['COLD']==traces['WARM']
assert results['COLD']['result']['Y_final']==results['WARM']['result']['Y_final']
assert all(np.array_equal(v,raws['WARM'][k]) for k,v in raws['COLD'].items())
freeze=read(root/'FREEZE.json');f=read(root/'FORECAST.json');approval=read(root/'APPROVAL.json')
assert sha(root/'FORECAST.json')==approval['forecast_sha256']
assert freeze['source_commit']==f['source_commit']
assert read(root/'PRODUCTION_CONFIG.json')['numerical_precision']==1e-10
assert read(root/'PRODUCTION_CONFIG.json')['rate_grid_npts']==4000
assert summary['budget']['total_package_wall_seconds']<=3000
assert summary['budget']['cold_wall_seconds']<=1400 and summary['budget']['warm_wall_seconds']<=1400
report={'status':'INDEPENDENT_ARTIFACT_CHECK_PASS','source_commit':freeze['source_commit'],
 'files_hash_verified':len(manifest['files']),'raw_and_dense_bit_identical':True,
 'diagnostics':diagnostics,'runtime':summary['budget'],'scientific_acceptance':False,
 'boundary':'Independent arithmetic/hash audit of one solver; not an independent BBN solver or validation of CCC/S2.'}
out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'status':report['status'],'hash_files':report['files_hash_verified'],'raw_bit_identical':True,
 'cold':diagnostics['COLD'],'wall_seconds':summary['budget']['total_wall_seconds'],
 'package_seconds':summary['budget']['total_package_wall_seconds'],'runtime_status':summary['budget']['runtime_status']},ensure_ascii=False))
