"""Offline verifier for an exact cache fetched only through GitHub connector."""
import argparse,json,time
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from infra.github_result_reader import read_github_result
from e002e_reset_exp.verify import verify_report
from e002e_reset_exp.plan import workload
from e002e_exp.runtime import runtime_gate,compare_environment


def main(run_id,report_commit,source_commit):
    started=time.perf_counter()
    def reader(repo,path,ref):
        if repo!='IgorSabirov/vm-lab' or ref!=report_commit or not path.startswith('results/'+run_id+'/') or '..' in Path(path).parts:
            raise ValueError('Unpinned cache read')
        return (ROOT/path).read_bytes()
    result=read_github_result(reader,repository='IgorSabirov/vm-lab',result_commit=report_commit,run_id=run_id,source_commit=source_commit)
    report=ROOT/'results'/run_id/'files';cfg=json.loads((report/'config.json').read_text())
    job=result['report']['job'];elapsed=job['finished']-job['started'];forecast=cfg['forecast']
    mode=cfg['mode']
    timing=dict(expected_seconds=forecast['expected_seconds'],actual_seconds=elapsed,
        relative_deviation=elapsed/forecast['expected_seconds']-1,
        within_declared_range=forecast['lower_seconds']<=elapsed<=forecast['upper_seconds'],
        scope='ENCLOSING_SERVICE_PROCESS_NO_QUEUE_OR_PUBLICATION')
    if mode=='calibration':timing['first_calibration_status']='NOT_EVALUABLE_RETAINED'
    else:
        metrics=json.loads((report/'metrics.json').read_text())
        cal=json.loads((ROOT/'experiments/e002e_reset/calibration_reviewed.json').read_text())
        environment=compare_environment(cal['environment'],metrics['environment_after'])
        timing.update(runtime_gate(forecast,elapsed,workload('production'),metrics['counts'],environment['comparable'],True))
        timing['scope']='ENCLOSING_SERVICE_PROCESS_NO_QUEUE_OR_PUBLICATION'
    print(json.dumps(dict(full_process_time=timing)),flush=True)
    if mode=='production' and timing['status']!='PASS':raise ValueError('Time/volume/environment review required before science')
    if not result['execution_succeeded']:raise ValueError('Job failed')
    check=verify_report(report)
    manifest=json.loads((ROOT/('experiments/e002e_reset/'+mode+'_payload_manifest.json')).read_text())
    if result['report']['input_sha256']!={e['path']:e['sha256'] for e in manifest['files']}:
        raise ValueError('Service input differs from frozen launch payload')
    out=dict(status='VERIFIED_GITHUB_NOT_SCIENTIFIC_ACCEPTANCE',run_id=run_id,source_commit=source_commit,
        report_commit=report_commit,files_verified=len(result['artifacts'])+1,full_process_time=timing,
        verification=check,offline_verification_seconds=time.perf_counter()-started,full_archive_accessed=False)
    destination=ROOT/('experiments/e002e_reset/'+mode+'_verification.json')
    destination.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run_id');p.add_argument('report_commit');p.add_argument('source_commit');a=p.parse_args()
    main(a.run_id,a.report_commit,a.source_commit)
