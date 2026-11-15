"""Compare the two full solutions without executing LINX."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent

def compare(native, override, contract):
    checks={}
    for key in ('background_sha256','contract_sha256','source_sha','versions','reaction_order','effective_q','table_sha256','integration_interval'):
        checks[key]=native.get(key) is not None and native.get(key)==override.get(key)
    checks['roles']=native.get('role')=='native_pristine' and override.get('role')=='identical_override'
    n=np.asarray(native['Y_final'],dtype=np.float64);o=np.asarray(override['Y_final'],dtype=np.float64)
    checks['shape']=n.shape==o.shape==(len(contract['species']),)
    checks['finite']=bool(np.all(np.isfinite(n)) and np.all(np.isfinite(o)))
    ni=np.asarray(native['Y_initial'],dtype=np.float64);oi=np.asarray(override['Y_initial'],dtype=np.float64)
    checks['finite_initial']=bool(np.all(np.isfinite(ni)) and np.all(np.isfinite(oi)))
    interval=np.asarray(native.get('integration_interval',[]),dtype=np.float64)
    checks['interval_valid']=interval.shape==(2,) and bool(np.all(np.isfinite(interval))) and interval[0]<interval[1]
    checks['initial_identity']=ni.shape==oi.shape==n.shape and ni.tobytes()==oi.tobytes()
    checks['native_pristine']=native.get('upstream_integrity')=='PRISTINE'
    checks['override_patch_only']=override.get('upstream_integrity')=='ONLY_RECORDED_ABUNDANCES_PATCH'
    checks['override_identity']=override.get('all_tables_bitwise_native') is True
    rows=[]
    if checks['shape'] and checks['finite']:
        c=contract['criteria'];allowed=c['output_atol']+c['output_rtol']*np.maximum(np.abs(n),np.abs(o))
        for name,a,b,lim in zip(contract['species'],n,o,allowed):
            rows.append({'species':name,'native':float(a),'override':float(b),'delta':float(b-a),
                         'allowed_abs':float(lim),'scaled_residual':float(abs(b-a)/lim),
                         'pass':bool(abs(b-a)<=lim)})
    checks['all_species']=len(rows)==len(contract['species']) and all(r['pass'] for r in rows)
    return {'id':contract['id'],'engineering_status':'PASS' if all(checks.values()) else 'FAIL',
            'checks':checks,'rows':rows,'final_bitwise_equal':n.shape==o.shape and n.tobytes()==o.tobytes(),
            'solver_stats':{'native':native.get('solver_stats'),'override':override.get('solver_stats')},
            'scientific_acceptance':False,'claim':'Full BBN implementation equivalence at the frozen operating point only'}

def main():
    p=argparse.ArgumentParser();p.add_argument('native',type=Path);p.add_argument('override',type=Path)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    c=json.loads((HERE/'BBN_IDENTITY_CONTRACT.json').read_text())
    n=json.loads(a.native.read_text());o=json.loads(a.override.read_text())
    result=compare(n,o,c)
    actual=hashlib.sha256((HERE/'BBN_IDENTITY_CONTRACT.json').read_bytes()).hexdigest()
    if n.get('contract_sha256')!=actual or o.get('contract_sha256')!=actual:
        result['checks']['published_contract_hash']=False;result['engineering_status']='FAIL'
    with a.out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    return 0 if result['engineering_status']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
