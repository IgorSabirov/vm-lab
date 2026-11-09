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
