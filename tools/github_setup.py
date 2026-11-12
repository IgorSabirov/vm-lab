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
    owner,title=plan['owner'],plan['title']
    data=graphql('query($owner:String!){user(login:$owner){id projectsV2(first:100){nodes{id title}}}}',{'owner':owner})['user']
    project=next((p for p in data['projectsV2']['nodes'] if p['title']==title),None)
    if project is None:
        project=graphql('mutation($owner:ID!,$title:String!){createProjectV2(input:{ownerId:$owner,title:$title}){projectV2{id title}}}',{'owner':data['id'],'title':title})['createProjectV2']['projectV2']
    pid=project['id']
    fields=graphql('query($id:ID!){node(id:$id){... on ProjectV2{fields(first:100){nodes{... on ProjectV2Field{id name} ... on ProjectV2SingleSelectField{id name options{id name color description}}}}}}}',{'id':pid})['node']['fields']['nodes']
    for name,options in plan['fields'].items():
        found=next((f for f in fields if f.get('name')==name),None)
        choices=[{'name':x,'color':'GRAY','description':x} for x in options] if options else None
        if found:
            if options and [x['name'] for x in found.get('options',[])]!=options:
                # Keep IDs for existing options so populated items do not silently lose state.
                old={o['name']:o for o in found.get('options',[])}
                choices=[old.get(x,{'name':x,'color':'GRAY','description':x}) for x in options]
                choices += [value for name,value in old.items() if name not in options]
                graphql('mutation($field:ID!,$options:[ProjectV2SingleSelectFieldOptionInput!]!){updateProjectV2Field(input:{fieldId:$field,singleSelectOptions:$options}){projectV2Field{... on ProjectV2SingleSelectField{id}}}}',{'field':found['id'],'options':choices})
            continue
        graphql('mutation($input:CreateProjectV2FieldInput!){createProjectV2Field(input:$input){projectV2Field{... on ProjectV2Field{id} ... on ProjectV2SingleSelectField{id}}}}',{'input':{'projectId':pid,'name':name,'dataType':'SINGLE_SELECT' if options else 'TEXT',**({'singleSelectOptions':choices} if options else {})}})
    repo=request('/repos/'+REPOSITORY)
    graphql('mutation($project:ID!,$repo:ID!){linkProjectV2ToRepository(input:{projectId:$project,repositoryId:$repo}){repository{id}}}',{'project':pid,'repo':repo['node_id']})
    # addProjectV2ItemById returns an existing item if it is already present.
    page=1;count=0
    while True:
        items=request('/repos/'+REPOSITORY+'/issues?state=open&per_page=100&page='+str(page))
        for item in items:
            graphql('mutation($project:ID!,$content:ID!){addProjectV2ItemById(input:{projectId:$project,contentId:$content}){item{id}}}',{'project':pid,'content':item['node_id']});count+=1
        if len(items)<100:break
        page+=1
    return {'project_id':pid,'open_items_added_or_existing':count,'built_in_auto_add':'Configure once in Projects UI; not claimed enabled by this script'}


def main():
    p=argparse.ArgumentParser();p.add_argument('target',choices=['repository','project']);p.add_argument('--apply',action='store_true');a=p.parse_args()
    plan=json.loads((ROOT/'infra/external/GITHUB_SETUP.json').read_text())[a.target]
    if not a.apply:print(json.dumps(plan,ensure_ascii=False,indent=2));return
    result=apply_repository(plan) if a.target=='repository' else apply_project(plan)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
