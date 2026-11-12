#!/usr/bin/env python3
"""Small repository-specific policy check, not a general security audit."""
from pathlib import Path
import re,yaml
ROOT=Path(__file__).resolve().parents[1]
def check(root=ROOT):
    files=list((root/'.github/workflows').glob('*.yml'))
    if not files:raise ValueError('No workflows')
    for p in files:
        raw=p.read_text();d=yaml.safe_load(raw)
        if not isinstance(d.get('permissions'),dict):raise ValueError('Explicit top-level permissions required: '+p.name)
        if 'pull_request_target:' in raw:raise ValueError('Privileged PR execution forbidden')
        for job in d['jobs'].values():
            if 'uses' in job:
                if not re.fullmatch(r'\./\.github/workflows/[a-z0-9_-]+\.yml',job['uses']):
                    raise ValueError('Only repository-local reusable jobs are allowed')
                if not (root/job['uses']).is_file():raise ValueError('Missing reusable workflow')
                continue  # Runtime bounds belong to each called job.
            if not 1<=job.get('timeout-minutes',0)<=10:raise ValueError('Bound every job runtime')
            for step in job.get('steps',[]):
                use=step.get('uses','')
                if use and not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+@[0-9a-f]{40}',use):raise ValueError('Pin external actions by full SHA')
                if 'run' in step and '${{' in step['run']:raise ValueError('Pass expressions through environment, never shell interpolation')
    d=yaml.safe_load((root/'.github/workflows/development.yml').read_text());triggers=d.get('on',d.get(True))
    if 'pull_request' not in triggers or isinstance(triggers['pull_request'],dict) and 'paths' in triggers['pull_request']:raise ValueError('Stable check must observe every PR')
    if 'merge-gate' not in d['jobs']:raise ValueError('Missing stable merge gate')
    print('Workflow policy PASS (pinning, permissions, timeouts, PR coverage, shell boundaries)')
if __name__=='__main__':check()
