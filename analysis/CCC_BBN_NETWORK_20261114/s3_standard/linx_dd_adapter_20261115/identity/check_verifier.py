"""Synthetic verifier controls only. No upstream import or BBN execution."""
from copy import deepcopy
import json
from pathlib import Path
from verify_identity import compare

def main():
    c=json.loads((Path(__file__).parent/'BBN_IDENTITY_CONTRACT.json').read_text())
    n={'role':'native_pristine','Y_final':[0.1]*8,'Y_initial':[0.1]*8,'upstream_integrity':'PRISTINE',
       'background_sha256':'fixture','contract_sha256':'fixture','source_sha':'fixture','versions':{'v':'fixture'},
       'reaction_order':['fixture'],'effective_q':[0.0],'table_sha256':['fixture'],'integration_interval':[1.,2.]}
    o=deepcopy(n);o.update(role='identical_override',upstream_integrity='ONLY_RECORDED_ABUNDANCES_PATCH',all_tables_bitwise_native=True)
    assert compare(n,o,c)['engineering_status']=='PASS'
    failures={}
    for defect in ['excess_delta','nan','missing_species','different_background','changed_initial','nan_initial']:
        a=deepcopy(n);b=deepcopy(o)
        if defect=='excess_delta':b['Y_final'][2]+=1e-6
        if defect=='nan':b['Y_final'][2]=float('nan')
        if defect=='missing_species':b['Y_final'].pop()
        if defect=='different_background':b['background_sha256']='other'
        if defect=='changed_initial':b['Y_initial'][0]+=1e-5
        if defect=='nan_initial':a['Y_initial'][0]=b['Y_initial'][0]=float('nan')
        r=compare(a,b,c);assert r['engineering_status']=='FAIL';failures[defect]='rejected'
    print(json.dumps({'status':'PASS','synthetic_identity':'accepted','negative_controls':failures,'bbn_integrations':0},indent=2))

if __name__=='__main__':main()
