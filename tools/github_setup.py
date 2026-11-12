#!/usr/bin/env python3
"""Idempotent repository/Projects setup with an explicitly provided admin token.

No credentials are discovered or stored. Default is a concrete read-only plan.
The connector does not expose these mutations; --apply requires GH_TOKEN locally.
"""
import argparse
import json
import os
from pathlib import Path
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
REPOSITORY='IgorSabirov/vm-lab'


def request(path, method='GET', data=None):
    token=os.environ.get('GH_TOKEN')
    if not token:raise RuntimeError('GH_TOKEN with the requested repository/Projects permissions is required; no token discovered automatically')
    req=urllib.request.Request('https://api.github.com'+path,method=method,
        headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','Content-Type':'application/json','X-GitHub-Api-Version':'2022-11-28'},
        data=None if data is None else json.dumps(data).encode())
    with urllib.request.urlopen(req,timeout=30) as r:
        raw=r.read();return json.loads(raw) if raw else None


def graphql(query,variables):
    result=request('/graphql','POST',{'query':query,'variables':variables})
    if result.get('errors'):raise RuntimeError('GraphQL rejected setup: '+json.dumps(result['errors']))
    return result['data']


def apply_repository(plan):
    base='/repos/'+REPOSITORY
    actual=request(base)
    if not actual.get('permissions',{}).get('admin'):raise RuntimeError('Repository admin permission required')
    request(base,'PATCH',{'has_discussions':True,'delete_branch_on_merge':True})
    existing=request(base+'/rulesets')
    for rule in plan['rulesets']:
        match=next((x for x in existing if x['name']==rule['name']),None)
        request(base+'/rulesets'+('/'+str(match['id']) if match else ''),'PUT' if match else 'POST',rule)
    # No VM credentials, runner registration or scientific execution are enabled.
    for name in plan['environments']:
        request(base+'/environments/'+name,'PUT',{'deployment_branch_policy':{'protected_branches':True,'custom_branch_policies':False}})
    return {'repository':REPOSITORY,'settings_applied':True,'vm_access_created':False}


def apply_project(plan):
    from project_sync import setup_and_sync
    return setup_and_sync(plan, request=request, graphql=graphql)


def main():
    p=argparse.ArgumentParser();p.add_argument('target',choices=['repository','project']);p.add_argument('--apply',action='store_true');a=p.parse_args()
    plan=json.loads((ROOT/'infra/external/GITHUB_SETUP.json').read_text())[a.target]
    if not a.apply:print(json.dumps(plan,ensure_ascii=False,indent=2));return
    result=apply_repository(plan) if a.target=='repository' else apply_project(plan)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
