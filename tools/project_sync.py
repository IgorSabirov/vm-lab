#!/usr/bin/env python3
"""Reconcile one owner's working board from vm-lab metadata, never scientific status.

Executed only from trusted main by Actions. Issue/PR text is data, not code or
execution authority. The credential remains in the Actions step environment.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = 'IgorSabirov/vm-lab'
OWNER = 'IgorSabirov'
PAGE = 'pageInfo{hasNextPage endCursor}'


def pages(fetch):
    cursor = None
    for _ in range(100):
        block = fetch(cursor)
        yield from block['nodes']
        info = block['pageInfo']
        if not info['hasNextPage']:
            return
        if not info['endCursor'] or info['endCursor'] == cursor:
            raise RuntimeError('Invalid pagination cursor')
        cursor = info['endCursor']
    raise RuntimeError('Pagination budget exceeded; no partial success')


def ensure_project(plan, graphql):
    if plan['owner'] != OWNER:
        raise ValueError('Unexpected project owner')
    user_id = None
    def fetch(cursor):
        nonlocal user_id
        d = graphql('query ProjectList($owner:String!,$after:String){user(login:$owner){id projectsV2(first:100,after:$after){nodes{id title url public closed} '+PAGE+'}}}', {'owner':OWNER,'after':cursor})['user']
        user_id = d['id']
        return d['projectsV2']
    matches = [p for p in pages(fetch) if p['title'] == plan['title']]
    if len(matches) > 1:
        raise RuntimeError('Ambiguous project title; refusing to choose or create another board')
    if matches:
        if matches[0]['closed']:
            raise RuntimeError('Working board is closed; refusing to reopen or duplicate it')
        return matches[0]
    return graphql('mutation CreateBoard($owner:ID!,$title:String!){createProjectV2(input:{ownerId:$owner,title:$title}){projectV2{id title url public closed}}}', {'owner':user_id,'title':plan['title']})['createProjectV2']['projectV2']


def project_fields(pid, graphql):
    query = 'query ProjectFields($id:ID!,$after:String){node(id:$id){... on ProjectV2{fields(first:100,after:$after){nodes{... on ProjectV2Field{id name dataType} ... on ProjectV2SingleSelectField{id name dataType options{id name color description}}} '+PAGE+'}}}}'
    rows = list(pages(lambda c: graphql(query, {'id':pid,'after':c})['node']['fields']))
    names = [r['name'] for r in rows if r.get('name')]
    if len(names) != len(set(names)):
        raise RuntimeError('Duplicate field names')
    return {r['name']:r for r in rows if r.get('name')}


def preserve_options(existing, desired):
    old = {x['name']:x for x in existing}
    return [old.get(x, {'name':x,'color':'GRAY','description':x}) for x in desired] + [x for x in existing if x['name'] not in desired]


def ensure_fields(pid, plan, graphql):
    fields = project_fields(pid, graphql)
    for name, options in plan.items():
        kind = 'SINGLE_SELECT' if options else 'TEXT'
        existing = fields.get(name)
        if existing:
            if existing['dataType'] != kind:
                raise RuntimeError('Existing field has incompatible type: '+name)
            if options:
                choices = preserve_options(existing['options'], options)
                if choices != existing['options']:
                    graphql('mutation UpdateOptions($field:ID!,$options:[ProjectV2SingleSelectFieldOptionInput!]!){updateProjectV2Field(input:{fieldId:$field,singleSelectOptions:$options}){projectV2Field{... on ProjectV2SingleSelectField{id}}}}', {'field':existing['id'],'options':choices})
            continue
        value = {'projectId':pid,'name':name,'dataType':kind}
        if options:
            value['singleSelectOptions'] = preserve_options([], options)
        graphql('mutation CreateField($input:CreateProjectV2FieldInput!){createProjectV2Field(input:$input){projectV2Field{... on ProjectV2FieldCommon{id}}}}', {'input':value})
    result = project_fields(pid, graphql)
    for name, options in plan.items():
        if name not in result or (options and not set(options) <= {o['name'] for o in result[name]['options']}):
            raise RuntimeError('Field setup readback failed: '+name)
    return result


def project_items(pid, graphql):
    query = '''query BoardItems($id:ID!,$after:String){node(id:$id){... on ProjectV2{items(first:100,after:$after){nodes{id isArchived
      fieldValues(first:100){nodes{... on ProjectV2ItemFieldTextValue{text field{... on ProjectV2FieldCommon{name}}} ... on ProjectV2ItemFieldSingleSelectValue{name field{... on ProjectV2FieldCommon{name}}}} pageInfo{hasNextPage}}
      content{__typename ... on Issue{id number repository{nameWithOwner}} ... on PullRequest{id number repository{nameWithOwner}}}}
      pageInfo{hasNextPage endCursor}}}}}'''
    rows = list(pages(lambda c: graphql(query, {'id':pid,'after':c})['node']['items']))
    for row in rows:
        if row['fieldValues']['pageInfo']['hasNextPage']:
            raise RuntimeError('Too many field values for complete readback')
        row['values'] = {v['field']['name']:v.get('text',v.get('name')) for v in row['fieldValues']['nodes'] if v.get('field')}
    return rows


def work_status(issue, current):
    pr = 'pull_request' in issue
    if issue['state'] == 'closed':
        done = bool(issue.get('merged_at')) if pr else issue.get('state_reason') != 'not_planned'
        return 'Done' if done else 'Parked'
    default = 'Inbox' if not pr or issue.get('draft') else 'Review'
    if not current or current == 'Done' or pr and current in ('Inbox','Review'):
        return default
    return current  # Preserve manual Analysis/Ready/Running/Parked and custom options.


def sections(body):
    chunks = re.split(r'^###\s+(.+?)\s*$', body or '', flags=re.M)
    return {chunks[i].strip():chunks[i+1].strip() for i in range(1,len(chunks)-1,2)}


KINDS = {'Научный вопрос или гипотеза':'Science','Аналитический вывод или аудит доказательства':'Analysis',
         'Код, тест или воспроизведение':'Code','Инфраструктура GitHub/ВМ/публикация':'Infrastructure',
         'Документация и синхронизация реестра':'Documentation'}
PERMISSIONS = {'Только чтение и аудит':'Read-only','Редактирование документации/реестра':'Docs',
               'Изменение кода и тестов':'Code','Локальный расчёт в пределах действующего лимита':'Local compute',
               'Запуск на ВМ — только в пределах уже выданного разрешения':'VM-authorized'}


def proposed_values(issue, current):
    s = sections(issue.get('body'))
    values = {'Status':work_status(issue,current.get('Status'))}
    candidate = {'Work kind':KINDS.get(s.get('Тип работы')), 'Permission':PERMISSIONS.get(s.get('Разрешённый объём действий')),
                 'Lineage':s.get('Генеалогия'), 'Acceptance':s.get('Критерий завершения'),
                 'Budget':s.get('Бюджет и ограничения'), 'Next action':s.get('Ближайшее действие')}
    if not candidate['Work kind'] and issue.get('title','').lower().startswith('[infra]'):
        candidate['Work kind'] = 'Infrastructure'
    for name, value in candidate.items():
        if value and value != '_No response_' and not current.get(name):
            values[name] = value[:1024]  # Fill empty fields only; retain human edits.
    if 'pull_request' in issue and issue.get('head',{}).get('sha'):
        values['Exact source SHA'] = issue['head']['sha']
    return {k:v for k,v in values.items() if current.get(k) != v}


def open_issues(request):
    rows = []
    for page in range(1,101):
        batch = request('/repos/'+REPO+'/issues?state=open&per_page=100&page='+str(page))
        rows.extend(batch)
        if len(batch) < 100:
            return rows
    raise RuntimeError('Issue pagination budget exceeded')


def setup_and_sync(plan, *, request, graphql):
    project = ensure_project(plan, graphql)
    pid = project['id']
    fields = ensure_fields(pid, plan['fields'], graphql)
    repo = request('/repos/'+REPO)
    graphql('mutation LinkBoard($project:ID!,$repo:ID!){linkProjectV2ToRepository(input:{projectId:$project,repositoryId:$repo}){repository{id}}}', {'project':pid,'repo':repo['node_id']})
    tracked = {i['content']['number']:i for i in project_items(pid,graphql)
               if i.get('content') and i['content'].get('repository',{}).get('nameWithOwner') == REPO}
    active = {i['number']:i for i in open_issues(request)}
    for number, item in tracked.items():
        if not item['isArchived'] and number not in active:
            active[number] = request('/repos/'+REPO+'/issues/'+str(number))
    added, updates, expected = [], [], {}
    for number, issue in sorted(active.items()):
        item = tracked.get(number)
        if item and item['isArchived']:
            continue
        if 'pull_request' in issue:
            pr = request('/repos/'+REPO+'/pulls/'+str(number))
            issue = {**issue, **pr, 'pull_request':issue['pull_request']}
        if not item:
            item = graphql('mutation AddWork($project:ID!,$content:ID!){addProjectV2ItemById(input:{projectId:$project,contentId:$content}){item{id}}}', {'project':pid,'content':issue['node_id']})['addProjectV2ItemById']['item']
            item['values'] = {}
            added.append(number)
        values = proposed_values(issue,item['values'])
        for name, value in values.items():
            field = fields[name]
            encoded = {'text':value}
            if field['dataType'] == 'SINGLE_SELECT':
                encoded = {'singleSelectOptionId':next(o['id'] for o in field['options'] if o['name'] == value)}
            graphql('mutation UpdateWork($input:UpdateProjectV2ItemFieldValueInput!){updateProjectV2ItemFieldValue(input:$input){projectV2Item{id}}}', {'input':{'projectId':pid,'itemId':item['id'],'fieldId':field['id'],'value':encoded}})
            updates.append({'number':number,'field':name})
        expected[item['id']] = {'Status':work_status(issue,item['values'].get('Status')),**values}
    # Projects may expose new items/field values after the mutation response.
    mismatches = []
    for delay in (0, 1, 2, 4, 8, 16):
        if delay:
            time.sleep(delay)
        actual = {i['id']:i for i in project_items(pid,graphql)}
        mismatches = [{'item_id':iid,'field':k,'expected':v,'observed':actual.get(iid,{}).get('values',{}).get(k)}
                      for iid, values in expected.items() for k,v in values.items()
                      if actual.get(iid,{}).get('values',{}).get(k) != v]
        if not mismatches:
            break
    if mismatches:
        safe = [{**m, **({} if m['field']=='Status' else {k:hashlib.sha256(str(m[k]).encode()).hexdigest() for k in ('expected','observed')})} for m in mismatches]
        details = {'project_url':project.get('url'),'mismatches':safe}
        raise RuntimeError('Project item readback failed: '+json.dumps(details,ensure_ascii=False))
    return {'schema':'vm-lab-project-sync-v1','project':project,'repository':REPO,
            'fields_verified':sorted(plan['fields']),'items_verified':len(expected),'added':added,'field_updates':updates,
            'items':[{'number':(actual[i].get('content') or {}).get('number'),'status':actual[i]['values'].get('Status')} for i in expected],
            'verified':True,'scientific_status_modified':False,'permissions_are_descriptive_not_authorization':True,
            'source_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(), 'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}


def main():
    p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true');p.add_argument('--output',type=Path,default=Path('project-evidence/PROJECTS_STATUS.json'));args=p.parse_args()
    plan=json.loads((ROOT/'infra/external/GITHUB_SETUP.json').read_text())['project']
    if not args.apply:
        print(json.dumps(plan,ensure_ascii=False,indent=2));return
    from github_setup import request, graphql
    result=setup_and_sync(plan,request=request,graphql=graphql)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:
            f.write(f"Project: {result['project']['url']}\n\nReadback PASS: {result['items_verified']} items, {len(result['fields_verified'])} fields. Scientific registers unchanged.\n")


if __name__ == '__main__':
    main()
