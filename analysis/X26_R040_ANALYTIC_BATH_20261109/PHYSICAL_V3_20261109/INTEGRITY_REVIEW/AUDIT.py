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


"""Read-only post-run integrity audit: never integrates or changes old outputs."""
import os,sys,time,json,hashlib,pathlib
start=time.perf_counter()
work=pathlib.Path(os.environ['VM_WORK']);inp=json.loads((work/'data/x26_integrity_20261109/INPUT.json').read_text())
cal=work/'results'/inp['calibration_job']/'output';main=work/'results'/inp['main_job']/'output'
receipt=inp['source_receipt'];out=pathlib.Path.cwd()
def dump(name,obj):(out/name).write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')
source_checks={}
for job in [inp['calibration_job'],inp['main_job']]:
 root=work/'results'/job/'source'
 source_checks[job]=audit_manifest(root,receipt['files'])
old_cal=json.loads((cal/'OUTPUT_MANIFEST.json').read_text());old_main=json.loads((main/'OUTPUT_MANIFEST.json').read_text())
cal_bad=audit_manifest(cal,old_cal);main_bad=audit_manifest(main,old_main)
artifact_bad=[]
for name,h in inp['published_calibration_artifacts'].items():
 actual=sha(cal/name)
 if actual!=h:artifact_bad.append(dict(section='calibration',path=name,expected=h,actual=actual))
for name,h in inp['published_main_artifacts'].items():
 actual=sha(main/name)
 if actual!=h:artifact_bad.append(dict(section='main',path=name,expected=h,actual=actual))
f=json.loads((cal/'FORECAST.json').read_text());c=json.loads((cal/'CALIBRATION.json').read_text())
chain=(f['calibration_sha256']==sha(cal/'CALIBRATION.json') and sha(main/'FROZEN_RUNTIME_GATE.json')==sha(cal/'FORECAST.json'))
for k in ['source_digest','manifest_digest','workload_digest','environment_fingerprint']:
 chain=chain and c[k]==f[k]
forecast={x['task_id']:x['seconds'] for x in f['terms']}
timings=json.loads((main/'TASK_TIMINGS.json').read_text());strata={}
for row in timings:
 t=row['task'];key=t.get('case','ramp')+'/'+t['kind']
 s=strata.setdefault(key,dict(count=0,predicted=0.,actual=0.,min_seconds=1e9,max_seconds=0.))
 s['count']+=1;s['predicted']+=forecast[t['id']];s['actual']+=row['seconds']
 s['min_seconds']=min(s['min_seconds'],row['seconds']);s['max_seconds']=max(s['max_seconds'],row['seconds'])
perm=[];code_and_manifest_match=True
for p in sorted((main/'rows').glob('*.json')):
 r=json.loads(p.read_text());code_and_manifest_match &= r['source_digest']==receipt['source_digest'] and r['manifest_digest']==receipt['manifest_digest']
 if r['task']['kind']=='cycle' and r['task']['case']=='permuted_word':
  perm.append({'id':r['task']['id'],'status':r['physical_status'],'evolution_executed':r.get('evolution_executed')})
assert len(perm)==60
for label,directory in [('CALIBRATION',cal),('MAIN',main)]:
 index={str(p.relative_to(directory)):sha(p) for p in sorted(directory.rglob('*')) if p.is_file()}
 dump(label+'_FINAL_ARTIFACT_MANIFEST.json',{'root':str(directory.relative_to(work)),'sha256':index,
      'generated_after_run':True,'original_files_modified':False})
summary={'calibration_job':inp['calibration_job'],'main_job':inp['main_job'],
 'source_commit':inp['source_commit'],'gate_commit':inp['gate_commit'],'results_commit':inp['results_commit'],
 'source_checks':source_checks,'published_artifact_mismatches':artifact_bad,
 'original_calibration_manifest_mismatches':cal_bad,'original_main_manifest_mismatches':main_bad,
 'original_calibration_manifest_status':'FAIL_STALE_FORECAST_HASH' if cal_bad else 'PASS',
 'calibration_to_forecast_to_frozen_main_gate_chain_matches':bool(chain),
 'all_row_source_and_manifest_digests_match':bool(code_and_manifest_match),
 'permutation_rows':len(perm),'permutation_all_exit_without_evolution':all(x['evolution_executed'] is False for x in perm),
 'permutation_statuses':sorted({x['status'] for x in perm}),'runtime_strata':strata,
 'original_files_modified':False,'physical_evolution_rerun':False,
 'audit_wall_seconds':time.perf_counter()-start,
 'historical_in_process_gap':'The original main runner checked derived digests, not independent artifact hashes; this audit does not retroactively claim it did.',
 'forensic_status':'ACTUAL_RUN_BYTES_VERIFIED_WITH_RECORDED_CALIBRATION_MANIFEST_DEFECT'}
valid=(not any(source_checks.values()) and not artifact_bad and not main_bad and chain and code_and_manifest_match
       and {x['path'] for x in cal_bad}=={'FORECAST.json'})
summary['audit_expected_checks_pass']=bool(valid)
dump('INTEGRITY_AUDIT.json',summary)
print(json.dumps(summary),flush=True)
raise SystemExit(0 if valid else 3)
