"""Publish an event even if setup fails before the scientific launcher starts."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess

branch=os.environ['GITHUB_REF_NAME']
if os.environ['GITHUB_REPOSITORY']!='IgorSabirov/vm-lab' or not branch.startswith('science/autonomous-'):
    raise ValueError('Unexpected failure-publication context')
def git(*args):return subprocess.check_output(['git',*args],text=True).strip()
p=Path('infra/autonomy/events')/(os.environ['GITHUB_RUN_ID']+'.json')
p.parent.mkdir(parents=True,exist_ok=True)
p.write_text(json.dumps({'utc':datetime.now(timezone.utc).isoformat(),
    'workflow_run_id':int(os.environ['GITHUB_RUN_ID']),'status':'WORKFLOW_FAILURE',
    'source_commit':os.environ['GITHUB_SHA'],
    'url':'https://github.com/IgorSabirov/vm-lab/actions/runs/'+os.environ['GITHUB_RUN_ID'],
    'next':'Read job logs and any scientific ledger before deciding; no blind retry.'},indent=2)+'\n')
git('add','--',str(p))
staged=git('diff','--cached','--name-only').splitlines()
if staged!=[str(p)]:raise ValueError('Unexpected staged paths')
git('commit','-m','Publish autonomous workflow failure for follow-up')
git('push','origin','HEAD:refs/heads/'+branch)
