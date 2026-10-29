"""Verify a cache downloaded from ONE pinned GitHub report commit, never from VM."""
import argparse
import json
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from github_result_reader import read_github_result
from e002c_exp.verify import verify

p=argparse.ArgumentParser()
p.add_argument('--github-cache',required=True)
p.add_argument('--report-commit',required=True)
p.add_argument('--source-commit',required=True)
p.add_argument('--run-id',required=True)
a=p.parse_args();cache=Path(a.github_cache)
prefix='results/'+a.run_id+'/'
def fetch(repository,path,ref):
    if ref!=a.report_commit or not path.startswith(prefix):raise ValueError('Wrong pinned report')
    return (cache/path[len(prefix):]).read_bytes()
r=read_github_result(fetch,repository='IgorSabirov/vm-lab',result_commit=a.report_commit,
                     run_id=a.run_id,source_commit=a.source_commit)
if not r['execution_succeeded']:raise ValueError('VM execution did not succeed')
with tempfile.TemporaryDirectory() as d:
    root=Path(d)
    for path,data in r['artifacts'].items():
        if path.startswith('files/'):
            target=root/path[6:];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    metrics=json.loads((root/'metrics.json').read_text())
    if metrics['identity']!={'run_id':a.run_id,'source_commit':a.source_commit}:raise ValueError('Wrong experiment identity')
    if r['report'].get('full_data_inventory_errors') != []:raise ValueError('Incomplete full data inventory')
    checks=json.loads((root/'checks.json').read_text());rt=checks['runtime_gate'];job=r['report']['job']
    actual=job['finished']-job['started'];lo=rt['lower_seconds'];hi=rt['upper_seconds']
    status='NOT_EVALUABLE' if lo is None or hi is None else ('PASS' if lo<=actual<=hi and checks['work_volume_pass'] else 'REVIEW_REQUIRED')
    print(json.dumps(dict(time_first=True,expected=rt['expected_seconds'],actual=actual,lower=lo,upper=hi,status=status,queue_seconds=job['started']-job['created']),ensure_ascii=False))
    print(json.dumps(dict(package=verify(root),report_commit=a.report_commit,source_commit=a.source_commit,
                         external_job=r['report']['job'],time_first=True),ensure_ascii=False,indent=2))
