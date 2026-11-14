"""Enforce the rolling Actions package cap before any new scientific process."""
from datetime import datetime,timezone,timedelta
import json
import os
from pathlib import Path
import urllib.request

def count(runs,now):
    since=now-timedelta(hours=24)
    return {r['id'] for r in runs if (r.get('head_branch') or '').startswith('science/autonomous-')
            and datetime.fromisoformat(r['created_at'].replace('Z','+00:00'))>=since}

def main():
    if os.environ['GITHUB_REPOSITORY']!='IgorSabirov/vm-lab' or os.environ['GITHUB_RUN_ATTEMPT']!='1':raise ValueError('Wrong repository or forbidden retry')
    if not os.environ['GITHUB_REF_NAME'].startswith('science/autonomous-'):raise ValueError('Wrong autonomous branch')
    now=datetime.now(timezone.utc);runs=[];covered=False
    for page in range(1,4):
        url=f'https://api.github.com/repos/IgorSabirov/vm-lab/actions/workflows/research-pipeline.yml/runs?per_page=100&page={page}'
        req=urllib.request.Request(url,headers={'Accept':'application/vnd.github+json','Authorization':'Bearer '+os.environ['GH_TOKEN']})
        with urllib.request.urlopen(req,timeout=20) as response:batch=json.load(response)['workflow_runs']
        runs.extend(batch)
        if len(batch)<100 or datetime.fromisoformat(batch[-1]['created_at'].replace('Z','+00:00'))<now-timedelta(hours=24):covered=True;break
    if not covered:raise ValueError('Cannot establish 24-hour package count')
    ids=count(runs,now)|{int(os.environ['GITHUB_RUN_ID'])}
    limit=2
    receipt={'observed_utc':now.isoformat(),'run_ids_last_24h':sorted(ids),'limit':limit,'admitted':len(ids)<=limit}
    Path(os.environ['RUNNER_TEMP'],'autonomy-budget.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))
    if not receipt['admitted']:raise ValueError('Two autonomous packages per rolling 24 hours already used')

if __name__=='__main__':main()
