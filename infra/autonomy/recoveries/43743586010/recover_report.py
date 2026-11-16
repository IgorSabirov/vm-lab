"""Offline publication recovery. No LINX import, solve, or source mutation."""
import json,hashlib,sys
from pathlib import Path
import numpy as np
import importlib.util
p=Path(sys.argv[1]).resolve()
verifier=p/'verify_identity.py'
assert hashlib.sha256(verifier.read_bytes()).hexdigest()=='0436c0f423b2d6dd1f5a54a087d809bb63f9df82840efb0e55ebe2fadcb7f06b'
spec=importlib.util.spec_from_file_location('frozen_verifier',verifier)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
compare=module.compare
read=lambda n:json.loads((p/n).read_text())
digest=lambda n:hashlib.sha256((p/n).read_bytes()).hexdigest()
assert digest('ARTIFACTS.json')=='15f786ad46d61ebccfe0456982ed607bd5f07619715cf1ef64d22901736d98b2'
for e in read('ARTIFACTS.json')['files']:
    assert (p/e['path']).stat().st_size==e['bytes']
    assert digest(e['path'])==e['sha256']
assert digest('BBN_IDENTITY_CONTRACT.json')=='fe148f33e6843a218fddd05375f385d336d176e7a060c99e49b2f656bbfc1716'
n,o,c=read('native/RESULT.json'),read('override/RESULT.json'),read('BBN_IDENTITY_CONTRACT.json')
r=compare(n,o,c)
r['checks']['published_contract_hash']=n['contract_sha256']==o['contract_sha256']==digest('BBN_IDENTITY_CONTRACT.json')
r['checks']['strict_not_calibration']=n.get('calibration_only') is False and o.get('calibration_only') is False
r['checks']['frozen_source']=n['source_sha']==o['source_sha']=='5183eb818d2b3c746d2e919b1f3561a08e7d1b09'
r['checks']['background_content_hash']=digest('native/background.npz')==n['background_sha256']==o['background_sha256']
for arm in ('native','override','calibration'):
 g=read(arm+'.log.guard.json');r['checks'][arm+'_process_exited_successfully']=g['exit_code']==0 and g['stop'] is None and g['process_exited'] is True
r['checks']['strict_settings']=n['effective_bbn_settings']==o['effective_bbn_settings']==c['bbn']
# Convert NumPy scalars only at the serialization boundary; no predicate change.
types={k:type(v).__module__+'.'+type(v).__name__ for k,v in r['checks'].items() if isinstance(v,np.generic)}
r=json.loads(json.dumps(r,default=lambda v:v.item() if isinstance(v,np.generic) else (_ for _ in ()).throw(TypeError(type(v).__name__)),allow_nan=False))
r.update(status='RECOVERED_FROM_COMPLETED_ARTIFACTS',package_id='LINX_BBN_IDENTITY_20261115_r3',workflow_run_id=43743586010,result_sha='b24c7e0cc47ff964d576f903ce7ba507d2dd731e',source_sha=n['source_sha'],original_workflow_engineering_status='FAIL',original_summary_sha256=digest('SUMMARY.json'),original_artifacts_sha256=digest('ARTIFACTS.json'),numerical_status='BBN_IMPLEMENTATION_IDENTITY_PASS' if all(r['checks'].values()) else 'BBN_IMPLEMENTATION_IDENTITY_FAIL',recovery_method='Unchanged frozen compare function on hash-verified saved outputs; NumPy scalar.item() only for JSON serialization',serialization_failure_types=types,verified_manifest_files=21,new_bbn_integrations=0,scientific_acceptance=False,mapping_status='NOT_ESTABLISHED',times_seconds={a:read(a+'.log.guard.json')['wall_seconds'] for a in ('calibration','native','override')})
(p/'RECOVERED_VERIFICATION.json').write_text(json.dumps(r,indent=2,allow_nan=False)+'\n')
print(json.dumps(r,indent=2))
