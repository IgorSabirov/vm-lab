import base64
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, unquote

from tools import r135_pipeline as p

SHA = 'ab'*20


def task(key, number, dependencies=()):
    return {'key':key,'issue_number':number,'title':'R135 '+key,'stages':['P1'],'block':'A · Модель X',
            'claims':['X-B'],'depends_on':list(dependencies),'conditional_dependencies':[],
            'initial_status':'Ready','acceptance_checks':[{'id':'balance','criterion':'Saved independent balance check'}],
            'requires_owner_decision':False,'completion_record':None}


def plan():
    return {'schema':p.SCHEMA,'repository':p.REPO,'tracker':155,
            'source_commits':{'implementation':SHA,'design':'cd'*20,'main':'ef'*20},
            'tasks':[task('A',161), task('B',162,['A'])]}


class API:
    def __init__(self):
        self.issues = {n:{'id':n+1000,'number':n,'state':'open'} for n in (155,161,162)}
        self.children, self.dependencies, self.parents = set(), {161:set(),162:set()}, {}
        self.files, self.runs, self.mutations = {}, {}, []
        self.labels, self.issue_labels = {}, {}

    def put(self, path, content, ref=SHA):
        raw = content if isinstance(content,bytes) else json.dumps(content,sort_keys=True).encode()
        self.files[(ref,path)] = raw
        return {'ref':ref,'path':path,'sha256':hashlib.sha256(raw).hexdigest()}

    def __call__(self, path, method='GET', data=None):
        route, _, query = path.partition('?')
        if method!='GET':
            self.mutations.append((path,method,deepcopy(data)))
        if route.startswith(p.BASE+'/contents/'):
            file_path = unquote(route.removeprefix(p.BASE+'/contents/'))
            ref = parse_qs(query)['ref'][0]
            if (ref,file_path) not in self.files:
                raise HTTPError(path,404,'Not found',None,None)
            return {'type':'file','path':file_path,'encoding':'base64',
                    'content':base64.b64encode(self.files[(ref,file_path)]).decode()}
        if route.startswith(p.BASE+'/git/commits/'):
            return {'sha':route.rsplit('/',1)[1]}
        if route.startswith(p.BASE+'/actions/runs/'):
            return deepcopy(self.runs[int(route.rsplit('/',1)[1])])
        if route==p.BASE+'/labels' and method=='POST':
            self.labels[data['name']]={'id':3000+len(self.labels),**deepcopy(data)}
            return deepcopy(self.labels[data['name']])
        if route.startswith(p.BASE+'/labels/'):
            name=unquote(route.removeprefix(p.BASE+'/labels/'))
            if name not in self.labels:
                raise HTTPError(path,404,'No label',None,None)
            return deepcopy(self.labels[name])
        match = re.fullmatch(re.escape(p.BASE)+r'/issues/(\d+)(.*)',route)
        if not match:
            raise AssertionError(path)
        number, suffix = int(match[1]), match[2]
        if suffix=='':
            if method=='PATCH':
                assert data=={'state':'open'} or set(data)=={'body'}
                self.issues[number].update(data)
            return deepcopy(self.issues[number])
        if suffix=='/parent':
            if number in self.parents:
                return deepcopy(self.parents[number])
            if self.issues[number]['id'] in self.children:
                return deepcopy(self.issues[155])
            raise HTTPError(path,404,'No parent',None,None)
        if suffix=='/labels':
            selected=self.issue_labels.setdefault(number,set())
            if method=='POST':
                assert set(data)=={'labels'}
                selected.update(data['labels'])
                return [deepcopy(self.labels[name]) for name in sorted(selected)]
            rows=[deepcopy(self.labels[name]) for name in sorted(selected)]
        elif suffix=='/sub_issues':
            assert number==155
            if method=='POST':
                assert data['replace_parent'] is False
                self.children.add(data['sub_issue_id'])
                return {}
            rows = [{'id':i,'number':i-1000} for i in sorted(self.children)]
        elif suffix=='/dependencies/blocked_by':
            if method=='POST':
                self.dependencies[number].add(data['issue_id'])
                return {}
            rows = [{'id':i,'number':i-1000} for i in sorted(self.dependencies[number])]
        else:
            raise AssertionError(path)
        page = int(parse_qs(query).get('page',['1'])[0])
        return rows[(page-1)*100:page*100]


def completion(api, selected_task):
    scope = {k:selected_task[k] for k in ('stages','claims')}
    inputs = api.put('evidence/inputs.json', {'chosen':'inputs'})
    evidence, runs = [], {}
    for role in ('producer','independent_replay'):
        report = {'schema':'vm-lab-r135-run-evidence-v1','task_key':selected_task['key'],'scope':scope,
                  'role':role,'run_id':role+'-run','source_sha':SHA,'input_manifest_sha256':inputs['sha256'],
                  'checks':[{'id':'balance','status':'PASS'}],'result':'PASS','exit_code':0,
                  'method':'Declared numerical check','environment':{'python':'3.12'}}
        ref = api.put('evidence/'+role+'.json',report)
        evidence.append({'id':role,**ref})
        runs[role] = {'provider':'manifest','run_id':report['run_id'],'report_evidence_id':role}
    record = {'schema':'vm-lab-r135-completion-v1','task_key':selected_task['key'],'source_sha':SHA,
              'scope':scope,'input_manifest':inputs,'evidence':evidence,
              'checks':[{'id':'balance','status':'PASS','evidence_ids':['producer','independent_replay']}],**runs}
    selected_task['completion_record']='infra/r135/completions/'+selected_task['key']+'.json'
    api.put(selected_task['completion_record'], record)
    return record


class ManifestValidation(unittest.TestCase):
    def test_valid_map_and_extra_metadata(self):
        value=plan()
        value['tasks'][0]['explanation']='Human scope detail'
        self.assertEqual(set(p.validate_plan(value)), {'A','B'})

    def test_duplicates_unknown_dependencies_and_cycle_rejected(self):
        cases=[]
        a=plan();a['tasks'][1]['key']='A';cases.append(a)
        a=plan();a['tasks'][1]['issue_number']=161;cases.append(a)
        a=plan();a['tasks'][1]['depends_on']=['missing'];cases.append(a)
        a=plan();a['tasks'][0]['depends_on']=['B'];cases.append(a)
        a=plan();a['tasks'][0]['conditional_dependencies']=[{'key':'missing','when':'X-A'}];cases.append(a)
        a=plan();a['tasks'][0]['completion_record']='../untrusted.json';cases.append(a)
        a=plan();a['tasks'][0]['acceptance_checks']=[];cases.append(a)
        a=plan();a['tracker_completion_key']='missing';cases.append(a)
        a=plan();a['related_pull_requests']=[161];cases.append(a)
        a=plan();a['label']=' ';cases.append(a)
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ValueError):
                p.validate_plan(value)

    def test_check_needs_neither_token_nor_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);dest=root/p.MANIFEST_PATH
            dest.parent.mkdir(parents=True);dest.write_text(json.dumps(plan()))
            with patch.object(p,'ROOT',root), patch('sys.argv',['r135_pipeline.py','--check']), patch('sys.stdout',new_callable=io.StringIO) as output:
                p.main()
            self.assertFalse(json.loads(output.getvalue())['live_evidence_checked'])


class Relationships(unittest.TestCase):
    def labeled_plan(self, api):
        value=plan();value.update({'label':'r135:development','related_pull_requests':[159,160]})
        for number in (159,160):
            api.issues[number]={'id':number+1000,'number':number,'state':'open','pull_request':{}}
        return value

    def test_criterion_records_reconcile_without_closing_whole_task(self):
        api=API()
        value=plan()
        value['schema']=p.progress.SCHEMA
        artifact=api.put('evidence/control.json',{'input':'A','output':1})
        value.update(progress_inputs={},progress_evidence={'test':{
            'commit':SHA,'path':artifact['path'],'sha256':artifact['sha256'],'basis':{'implementation':SHA}}})
        for issue in api.issues.values():
            issue['body']='Ручное примечание'
        api.issues[161]['state']='closed'
        for task_row in value['tasks']:
            task_row.update(progress_target='test',focus_criterion='balance')
            for c in task_row['acceptance_checks']:
                c['progress']={'remaining':'physical input','next_output':'one trace','needs':[],'findings':[
                    {'level':'control','obtained':'unit control','scope':'synthetic','reviewed_for':'test','evidence':['test']}]}
        task_row=value['tasks'][0]
        completion(api,task_row)
        task_row['acceptance_checks'][0]['progress']['criterion_record']=task_row['completion_record']
        task_row['completion_record']=None
        second=deepcopy(task_row['acceptance_checks'][0])
        second['id']='second'
        del second['progress']['criterion_record']
        task_row['acceptance_checks'].append(second)
        result=p.apply_pipeline(value,request=api,source_sha=SHA)
        self.assertEqual(result['criterion_verified_checks']['A'],['balance'])
        self.assertEqual(result['completion_evidence']['A']['status'],'OPEN_EVIDENCE')
        self.assertEqual(api.issues[161]['state'],'open')
        self.assertIn('#### balance · по приёмочной записи',api.issues[161]['body'])
        self.assertIn('#### second · проверен контроль',api.issues[161]['body'])
        self.assertIn('Ручное примечание',api.issues[161]['body'])
        self.assertEqual(result['criterion_sections_expected'],3)
        self.assertEqual(p.apply_pipeline(value,request=api,source_sha=SHA)['criterion_sections_updated'],[])
        api.files[SHA,artifact['path']]=b'changed'
        with self.assertRaisesRegex(ValueError,'SHA256'):
            p.apply_pipeline(value,request=api,source_sha=SHA)

    def test_pipeline_label_created_and_added_without_removing_other_labels(self):
        api=API();value=self.labeled_plan(api)
        api.labels['manual']={'id':1,'name':'manual','color':'000000','description':'owner label'}
        api.issue_labels[161]={'manual'}
        result=p.apply_pipeline(value,request=api,source_sha=SHA)
        self.assertTrue(result['label_created'])
        self.assertEqual(result['labeled'],[155,159,160,161,162])
        self.assertEqual(api.labels['r135:development']['color'],'1D76DB')
        self.assertEqual(api.issue_labels[161],{'manual','r135:development'})
        mutations=len(api.mutations)
        again=p.apply_pipeline(value,request=api,source_sha=SHA)
        self.assertFalse(again['label_created'])
        self.assertEqual(again['labeled'],[])
        self.assertEqual(len(api.mutations),mutations)

    def test_existing_label_definition_is_preserved_and_related_items_must_be_prs(self):
        api=API();value=self.labeled_plan(api)
        existing={'id':7,'name':'r135:development','color':'ffffff','description':'human description'}
        api.labels['r135:development']=deepcopy(existing)
        p.apply_pipeline(value,request=api,source_sha=SHA)
        self.assertEqual(api.labels['r135:development'],existing)
        self.assertFalse(any(x[0]==p.BASE+'/labels' for x in api.mutations))
        unsafe=API();value=self.labeled_plan(unsafe);del unsafe.issues[160]['pull_request']
        with self.assertRaisesRegex(ValueError,'not a pull request'):
            p.apply_pipeline(value,request=unsafe,source_sha=SHA)
        self.assertEqual(unsafe.mutations,[])

    def test_label_readback_failure_is_not_reported_as_success(self):
        api=API();value=self.labeled_plan(api)
        def hidden(path,method='GET',data=None):
            result=api(path,method,data)
            if method=='GET' and '/issues/155/labels?' in path:
                return []
            return result
        with patch.object(p.time,'sleep'), self.assertRaisesRegex(ValueError,'label 155'):
            p.apply_pipeline(value,request=hidden,source_sha=SHA)
        self.assertEqual(sum(x[0]==p.BASE+'/labels' and x[1]=='POST' for x in api.mutations),1)
        self.assertEqual(sum('/issues/155/labels' in x[0] and x[1]=='POST' for x in api.mutations),1)

    def test_label_case_mismatch_is_not_silently_renamed(self):
        calls=[]
        def existing(path,method='GET',data=None):
            calls.append(method)
            return {'name':'R135:Development'}
        with self.assertRaisesRegex(ValueError,'case/name'):
            p.ensure_label(existing,'r135:development')
        self.assertEqual(calls,['GET'])

    def test_native_relationships_idempotent_and_manual_extras_preserved(self):
        api=API();api.children.add(999);api.dependencies[162].add(998)
        result=p.apply_pipeline(plan(),request=api,source_sha=SHA)
        self.assertTrue(result['verified'])
        self.assertEqual(api.children,{999,1161,1162})
        self.assertEqual(api.dependencies[162],{998,1161})
        mutations=len(api.mutations)
        result=p.apply_pipeline(plan(),request=api,source_sha=SHA)
        self.assertEqual(len(api.mutations),mutations)
        self.assertEqual(result['added_sub_issues'],[])
        self.assertFalse(result['scientific_status_modified'])

    def test_conditional_dependency_is_not_a_global_blocker(self):
        value=plan();value['tasks'][1]['depends_on']=[]
        value['tasks'][1]['conditional_dependencies']=[{'key':'A','when':'only X-A marker validation'}]
        api=API();p.apply_pipeline(value,request=api,source_sha=SHA)
        self.assertEqual(api.dependencies[162],set())

    def test_foreign_parent_never_replaced_even_same_issue_number(self):
        api=API();api.parents[161]={'number':155,'id':99999}
        with self.assertRaisesRegex(ValueError,'another parent'):
            p.apply_pipeline(plan(),request=api,source_sha=SHA)
        self.assertEqual(api.mutations,[])

    def test_missing_record_reopens_closed_task_without_comment_or_scientific_changes(self):
        api=API();api.issues[162]['state']='closed'
        result=p.apply_pipeline(plan(),request=api,source_sha=SHA)
        self.assertEqual(result['reopened'],[162])
        self.assertIn('No reviewed-main', result['completion_evidence']['B']['reason'])
        self.assertEqual(api.issues[162]['state'],'open')
        self.assertFalse(any('/comments' in x[0] for x in api.mutations))

    def test_tracker_cannot_close_without_its_declared_completion_evidence(self):
        value=plan();value['tracker_completion_key']='A'
        api=API();api.issues[155]['state']='closed'
        result=p.apply_pipeline(value,request=api,source_sha=SHA)
        self.assertEqual(result['reopened'],[155])
        self.assertEqual(result['tracker_completion_evidence'],'OPEN_EVIDENCE')
        self.assertEqual(api.issues[155]['state'],'open')

    def test_tracker_with_valid_completion_record_is_not_reopened_or_auto_closed(self):
        for state in ('open','closed'):
            with self.subTest(state=state):
                value=plan();value['tracker_completion_key']='A'
                api=API();completion(api,value['tasks'][0]);api.issues[155]['state']=state
                result=p.apply_pipeline(value,request=api,source_sha=SHA)
                self.assertEqual(result['reopened'],[])
                self.assertEqual(result['tracker_completion_evidence'],'VERIFIED_STRUCTURAL_EVIDENCE')
                self.assertEqual(api.issues[155]['state'],state)
                self.assertFalse(result['scientific_acceptance_inferred'])

    def test_partial_readback_fails_without_repeating_mutations(self):
        api=API()
        def hidden(path,method='GET',data=None):
            value=api(path,method,data)
            if method=='GET' and '/sub_issues?' in path:
                return []
            return value
        with patch.object(p.time,'sleep'), self.assertRaisesRegex(ValueError,'readback'):
            p.apply_pipeline(plan(),request=hidden,source_sha=SHA)
        self.assertEqual(sum(x[1]=='POST' and x[0].endswith('/sub_issues') for x in api.mutations),2)

    def test_pagination_complete_and_duplicate_page_rejected(self):
        calls=[]
        def pages(path):
            calls.append(path)
            page=parse_qs(path.partition('?')[2])['page'][0]
            return [{'id':i} for i in range(100)] if page=='1' else [{'id':100}]
        self.assertEqual(len(p.paginated(pages,'/items')),101)
        self.assertEqual(len(calls),2)
        with self.assertRaisesRegex(ValueError,'pagination'):
            p.paginated(lambda _: [{'id':i} for i in range(100)],'/items')


class CompletionEvidence(unittest.TestCase):
    def test_manifest_replay_valid_but_does_not_close_open_issue_or_infer_science(self):
        value=plan();api=API();completion(api,value['tasks'][0])
        result=p.apply_pipeline(value,request=api,source_sha=SHA)
        self.assertEqual(api.issues[161]['state'],'open')
        check=result['completion_evidence']['A']
        self.assertEqual(check['status'],'VERIFIED_STRUCTURAL_EVIDENCE')
        self.assertFalse(check['scientific_acceptance_inferred'])
        self.assertFalse(check['method_independence_proven'])

    def test_valid_evidence_allows_existing_closed_work_to_remain_closed(self):
        value=plan();api=API();completion(api,value['tasks'][0]);api.issues[161]['state']='closed'
        result=p.apply_pipeline(value,request=api,source_sha=SHA)
        self.assertEqual(result['reopened'],[])
        self.assertEqual(api.issues[161]['state'],'closed')

    def test_bad_hash_or_missing_file_reopens_closed_work(self):
        for missing in (False,True):
            value=plan();api=API();completion(api,value['tasks'][0]);api.issues[161]['state']='closed'
            key=(SHA,'evidence/independent_replay.json')
            if missing:
                del api.files[key]
            else:
                api.files[key]+=b'corruption'
            result=p.apply_pipeline(value,request=api,source_sha=SHA)
            self.assertEqual(result['reopened'],[161])
            self.assertEqual(result['completion_evidence']['A']['status'],'OPEN_EVIDENCE')

    def test_scope_and_source_mismatch_missing_replay_and_owner_decision_rejected(self):
        for mode in ('scope','source','replay','owner','check'):
            with self.subTest(mode=mode):
                value=plan();api=API();selected=value['tasks'][0];record=completion(api,selected)
                if mode=='scope':record['scope']['claims']=['X-A']
                elif mode=='source':record['source_sha']='cd'*20
                elif mode=='replay':del record['independent_replay']
                elif mode=='owner':selected['requires_owner_decision']=True
                else:record['checks'][0]['status']='OPEN_INPUT'
                api.put(selected['completion_record'],record);api.issues[161]['state']='closed'
                result=p.apply_pipeline(value,request=api,source_sha=SHA)
                self.assertEqual(result['reopened'],[161])

    def test_same_run_not_independent_replay(self):
        selected=task('A',161);api=API();record=completion(api,selected)
        record['independent_replay']['run_id']=record['producer']['run_id']
        report=json.loads(api.files[(SHA,'evidence/independent_replay.json')])
        report['run_id']=record['producer']['run_id']
        replacement=api.put('evidence/independent_replay.json',report)
        record['evidence'][1].update(replacement)
        with self.assertRaisesRegex(ValueError,'distinct'):
            p.verify_completion(selected,record,api)

    def test_actions_provider_checks_actual_result_and_source(self):
        selected=task('A',161);api=API();record=completion(api,selected)
        for index,role in enumerate(('producer','independent_replay'),1):
            run_id=100+index
            record[role].update({'provider':'github_actions','run_id':run_id})
            report=json.loads(api.files[(SHA,'evidence/'+role+'.json')]);report['run_id']=run_id
            record['evidence'][index-1].update(api.put('evidence/'+role+'.json',report))
            api.runs[run_id]={'status':'completed','conclusion':'success','head_sha':SHA,'repository':{'full_name':p.REPO}}
        self.assertEqual(p.verify_completion(selected,record,api)['status'],'VERIFIED_STRUCTURAL_EVIDENCE')
        api.runs[102]['head_sha']='cd'*20
        with self.assertRaisesRegex(ValueError,'Actions run'):
            p.verify_completion(selected,record,api)

    def test_api_permission_failure_does_not_relabel_valid_evidence_as_false(self):
        value=plan();api=API();completion(api,value['tasks'][0]);api.issues[161]['state']='closed'
        def denied(path,method='GET',data=None):
            if '/contents/' in path:
                raise HTTPError(path,403,'Forbidden',None,None)
            return api(path,method,data)
        with self.assertRaises(HTTPError):
            p.apply_pipeline(value,request=denied,source_sha=SHA)
        self.assertEqual(api.issues[161]['state'],'closed')
        self.assertEqual(api.mutations,[])


if __name__=='__main__':
    unittest.main()
