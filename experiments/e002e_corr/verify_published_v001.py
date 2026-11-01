"""Verify locally cached GitHub reports, including lossless large-file transport.

Populate cache ONLY through the GitHub connector at these immutable commits.
This script has no VM reader and never reads unpublished state archives.
"""
import base64
import hashlib
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from infra.github_result_reader import read_github_result
from e002e_corr_exp.verify import verify_report
from e002e_corr_exp.plan import workload
from e002e_exp.runtime import runtime_gate,compare_environment

PINS={
    'E002e_CORR_EXPORT_v001_r001':('42bede68cb59935ee550b12f2c1dd089eed9a050','5603a96eda134719da564b676a0b42f78f24358e'),
    'E002e_CORR_v001_r001':('5654dff87b3b7ca9b32ec2ce2a51454316c7ac78','426b83c7b5544cb953ca0d60b3abf01d1eb4b76e')}

def reader(repo,path,ref):
    assert repo=='IgorSabirov/vm-lab' and path.split('/')[0]=='results'
    assert PINS[path.split('/')[1]][0]==ref and '..' not in Path(path).parts
    return (ROOT/path).read_bytes()

def load_run(name):
    ref,source=PINS[name]
    return read_github_result(reader,repository='IgorSabirov/vm-lab',result_commit=ref,run_id=name,source_commit=source)

def main():
    t=load_run('E002e_CORR_EXPORT_v001_r001')
    tp=ROOT/'results/E002e_CORR_EXPORT_v001_r001/files'
    mapping=json.loads((tp/'transport.json').read_text())
    assert mapping['source_report_commit']==PINS['E002e_CORR_v001_r001'][0]
    assert mapping['original_source_commit']==PINS['E002e_CORR_v001_r001'][1]
    for spec in mapping['files']:
        assert Path(spec['name']).name==spec['name']
        data=bytearray()
        for part in spec['parts']:
            assert Path(part['name']).name==part['name']
            raw=base64.b64decode((tp/part['name']).read_bytes(),validate=True)
            assert len(data)==part['offset'] and len(raw)==part['raw_bytes']
            assert hashlib.sha256(raw).hexdigest()==part['sha256']
            data.extend(raw)
        assert len(data)==spec['size'] and hashlib.sha256(data).hexdigest()==spec['sha256']
        assert hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==spec['git_blob']
        (ROOT/'results/E002e_CORR_v001_r001/files'/spec['name']).write_bytes(data)
    v=load_run('E002e_CORR_v001_r001')
    p=ROOT/'results/E002e_CORR_v001_r001/files'
    start=time.perf_counter();check=verify_report(p);validation=time.perf_counter()-start
    m=json.loads((p/'metrics.json').read_text());cfg=json.loads((p/'config.json').read_text())
    cal=json.loads((ROOT/'experiments/e002e_corr/calibration_verified_v001.json').read_text())
    elapsed=v['report']['job']['finished']-v['report']['job']['started']
    env=compare_environment(cal['environment'],m['environment_after'])
    rt=runtime_gate(cfg['forecast'],elapsed,workload(),m['actual_counts'],env['comparable'],True)
    assert rt['status']=='PASS'
    rt['scope']='ENCLOSING_VM_SERVICE_STARTED_TO_FINISHED'
    primary=[]
    for file in sorted(p.glob('*_case.json')):
        r=json.loads(file.read_text());primary.append(dict(model=r['case']['model'],**r['result']['primary']))
    out=dict(status='VERIFIED_GITHUB',source_commit=v['source_commit'],report_commit=v['result_commit'],run_id=v['run_id'],
        verified_files=len(v['artifacts'])+1,report_verification=check,verification_seconds=validation,full_process_runtime=rt,
        environment=env,memory=dict(max_rss_bytes=m['environment_after']['max_rss_kib']*1024,
        sampled_vm_bytes=m['environment_after']['process_vm_size_bytes']),scientific_acceptance=False,full_archive_accessed=False,
        transport=dict(report_commit=t['result_commit'],source_commit=t['source_commit'],verified_files=len(t['artifacts'])+1,
        elapsed=t['report']['job']['finished']-t['report']['job']['started'],reconstructed_files=len(mapping['files']),
        identity='Original SHA256 and Git blob hashes matched after lossless reconstruction from pinned original Git blobs; no VM archive access'),primary=primary)
    (ROOT/'experiments/e002e_corr/production_verification_v001.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(out))

if __name__=='__main__':main()
