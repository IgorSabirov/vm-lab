"""Verify GitHub bytes and independently reconstruct E002d exported observables.

Usage: python verify_report.py /path/to/GitHub_download_cache
Cache must be downloaded exclusively at RESULT_COMMIT; no VM fallback.
"""
import hashlib,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from infra.github_result_reader import read_github_result
from e002d_exp.verify import verify
RESULT_COMMIT='071e15ebc37227b1549e660121bc735a1d86cb13'
SOURCE_COMMIT='1f12d2f56145a30d2066f4b9f53592ebdc8a96e9'
RUN='E002d_PROD_v003_r001'
def main(cache):
    start=time.monotonic();cache=Path(cache);report=json.loads((cache/'run.json').read_text())
    checked=[]
    for name in ('infra/github_result_reader.py','e002d_exp/verify.py','e002d_exp/verify_analysis.py'):
        digest=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
        if name in report['input_sha256']:
            assert digest==report['input_sha256'][name],name
        checked.append(dict(path=name,sha256=digest,pinned_in_run=name in report['input_sha256']))
    def fetch(repository,path,ref):
        assert repository=='IgorSabirov/vm-lab' and ref==RESULT_COMMIT
        prefix='results/'+RUN+'/'
        assert path.startswith(prefix)
        return (cache/path[len(prefix):]).read_bytes()
    verified=read_github_result(fetch,repository='IgorSabirov/vm-lab',result_commit=RESULT_COMMIT,run_id=RUN,source_commit=SOURCE_COMMIT)
    job=report['job'];actual=job['finished']-job['started']
    assert 7812<=actual<=14508
    independent=verify(cache/'files')
    elapsed=time.monotonic()-start
    out=dict(result_commit=RESULT_COMMIT,source_commit=SOURCE_COMMIT,run_id=RUN,
      downloaded_artifacts=len(verified['artifacts']),downloaded_bytes=sum(map(len,verified['artifacts'].values())),
      export_errors=report['export_errors'],execution_succeeded=verified['execution_succeeded'],
      runtime=dict(expected_seconds=11160,actual_seconds=actual,deviation_seconds=actual-11160,
       deviation_percent=100*(actual/11160-1),lower_seconds=7812,upper_seconds=14508,status='PASS',queue_seconds=job['started']-job['created']),
      verifier_source=checked,independent=independent,
      audit_runtime=dict(expected_seconds=60,lower_seconds=0,upper_seconds=600,actual_seconds=elapsed,status='PASS' if elapsed<=600 else 'INVESTIGATE'))
    (Path(__file__).parent/'verification.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__':main(sys.argv[1])
