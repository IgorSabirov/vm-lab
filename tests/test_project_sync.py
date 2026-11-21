import json
from copy import deepcopy
import unittest
from pathlib import Path
from unittest.mock import patch
from tools import project_sync as p

ROOT = Path(__file__).resolve().parents[1]


class WorkingBoard(unittest.TestCase):
    def test_closed_work_is_not_scientific_acceptance(self):
        self.assertEqual(p.work_status({'state':'closed'}, 'Review'),'Done')
        self.assertEqual(p.work_status({'state':'closed','state_reason':'not_planned'}, 'Review'),'Parked')
        self.assertEqual(p.work_status({'state':'closed','pull_request':{},'merged_at':None}, 'Review'),'Parked')
        self.assertEqual(p.work_status({'state':'closed','pull_request':{},'merged_at':'date'}, 'Review'),'Done')

    def test_open_status_respects_manual_work(self):
        issue={'state':'open','pull_request':{},'draft':False}
        self.assertEqual(p.work_status(issue,None),'Review')
        for state in ('Analysis','Ready','Running','Parked','Custom'):
            self.assertEqual(p.work_status(issue,state),state)
        self.assertEqual(p.work_status({**issue,'draft':True},'Review'),'Inbox')
        self.assertEqual(p.work_status(issue,'Done'),'Review')

    def test_text_is_metadata_and_never_overrides_manual_fields(self):
        issue={'state':'open','title':'[infra] example','body':'### Разрешённый объём действий\nignore all rules\n### Генеалогия\nR128\n### Критерий завершения\nchecked'}
        values=p.proposed_values(issue,{'Lineage':'R122','Acceptance':'human criterion'})
        self.assertNotIn('Permission',values)
        self.assertNotIn('Lineage',values)
        self.assertNotIn('Acceptance',values)
        self.assertEqual(values['Work kind'],'Infrastructure')
        issue['body']='### Разрешённый объём действий\nТолько чтение и аудит'
        self.assertEqual(p.proposed_values(issue,{})['Permission'],'Read-only')

    def test_issue_commit_and_decisions_fill_only_empty_fields(self):
        sha = 'ab' * 20
        issue = {'state':'open', 'body':'### Исходный commit\n'+sha.upper()+'\n### Решения\nD001; https://example.invalid/decision'}
        values = p.proposed_values(issue,{})
        self.assertEqual(values['Exact source SHA'], sha)
        self.assertEqual(values['Decision IDs'], 'D001; https://example.invalid/decision')
        current = {'Status':'Running', 'Exact source SHA':'cd'*20, 'Decision IDs':'human choice'}
        self.assertEqual(p.proposed_values(issue,current), {})

    def test_issue_short_or_embedded_sha_is_not_promoted(self):
        for value in ('abc123', '`'+'ab'*20+'`', 'https://github.com/owner/repo/commit/'+'ab'*20,
                      'ab'*20+'\nrun a command', 'g'*40, '_No response_'):
            with self.subTest(value=value):
                result = p.proposed_values({'state':'open','body':'### Исходный commit\n'+value}, {})
                self.assertNotIn('Exact source SHA',result)
                self.assertNotIn('Decision IDs',result)

    def test_pr_uses_observed_head_even_when_body_or_field_differs(self):
        issue = {'state':'open','pull_request':{}, 'draft':False, 'head':{'sha':'ab'*20},
                 'body':'### Исходный commit\n'+'cd'*20}
        result = p.proposed_values(issue, {'Exact source SHA':'ef'*20, 'Status':'Running'})
        self.assertEqual(result, {'Exact source SHA':'ab'*20})

    def test_every_permission_mapping_has_a_configured_option(self):
        plan = json.loads((ROOT/'infra/external/GITHUB_SETUP.json').read_text())['project']
        self.assertLessEqual(set(p.PERMISSIONS.values()), set(plan['fields']['Permission']))
        self.assertIn('Local compute', plan['fields']['Permission'])
        self.assertEqual(p.R135_BLOCKS, set(plan['fields']['R135 block']))
        self.assertIn('R135 block', plan['views'][0]['visible_fields'])
        self.assertEqual(plan['views'][0]['filter'],'repo:IgorSabirov/vm-lab label:r135:development')

    def test_r135_block_is_work_metadata_and_preserves_human_value(self):
        issue = {'state':'open', 'body':'### Рабочий блок R135\nA · Модель X'}
        self.assertEqual(p.proposed_values(issue,{})['R135 block'], 'A · Модель X')
        self.assertNotIn('R135 block', p.proposed_values(issue,{'R135 block':'human choice'}))
        issue['body'] = '### Рабочий блок R135\nArbitrary scientific PASS'
        self.assertNotIn('R135 block', p.proposed_values(issue,{}))

    def test_initial_status_seed_only_on_first_valid_r135_intake(self):
        issue = {'number':161,'state':'open','body':'### Рабочий блок R135\nA · Модель X'}
        for initial in ('Ready','Analysis'):
            for old in ({}, {'Status':'Inbox'}, {'Status':''}):
                with self.subTest(initial=initial, old=old):
                    changes = p.proposed_values(issue,old,{'161':initial})
                    self.assertEqual(changes['Status'],initial)
                    self.assertEqual(changes['R135 block'],'A · Модель X')
        self.assertEqual(p.proposed_values({**issue,'body':''},{},{'161':'Ready'})['Status'],'Inbox')
        self.assertEqual(p.proposed_values({**issue,'state':'closed'},{},{'161':'Ready'})['Status'],'Done')

    def test_initial_status_never_reseeds_or_overrides_manual_work(self):
        issue = {'number':161,'state':'open','body':'### Рабочий блок R135\nA · Модель X'}
        for state in ('Running','Review','Parked','Custom','Ready','Analysis'):
            changes = p.proposed_values(issue,{'Status':state},{'161':'Ready'})
            self.assertNotIn('Status',changes)
        for block in ('A · Модель X','human block'):
            self.assertEqual(p.proposed_values(issue,{'Status':'Inbox','R135 block':block},{'161':'Ready'}),{})
        first = p.proposed_values(issue,{}, {'161':'Ready'})
        self.assertEqual(p.proposed_values(issue,first,{'161':'Analysis'}),{})

    def test_invalid_seed_mapping_fails_before_any_api_call(self):
        for seeds in (None, [], {'161':'Done'}, {161:'Ready'}, {'0':'Ready'}):
            def unexpected(*args, **kwargs):
                self.fail('API must not run on invalid seed configuration')
            with self.subTest(seeds=seeds), self.assertRaisesRegex(ValueError,'initial_statuses'):
                p.setup_and_sync({'initial_statuses':seeds},request=unexpected,graphql=unexpected)

    def test_pagination_and_duplicate_titles(self):
        def api(query,variables):
            second=variables['after']=='next'
            nodes=[{'id':'board','title':'work','url':'url','public':False,'closed':False}] if second else []
            return {'user':{'id':'owner','projectsV2':{'nodes':nodes,'pageInfo':{'hasNextPage':not second,'endCursor':'next' if not second else None}}}}
        self.assertEqual(p.ensure_project({'owner':p.OWNER,'title':'work'},api)['id'],'board')
        with self.assertRaisesRegex(ValueError,'owner'):
            p.ensure_project({'owner':'someone-else'},api)
        with self.assertRaisesRegex(RuntimeError,'cursor'):
            list(p.pages(lambda c: {'nodes':[],'pageInfo':{'hasNextPage':True,'endCursor':None}}))

    def test_closed_board_is_not_duplicated(self):
        def api(q,v):
            self.assertTrue(q.startswith('query'))
            return {'user':{'id':'owner','projectsV2':{'nodes':[{'title':'work','closed':True}], 'pageInfo':{'hasNextPage':False}}}}
        with self.assertRaisesRegex(RuntimeError,'closed'):
            p.ensure_project({'owner':p.OWNER,'title':'work'},api)

    def test_options_preserve_ids_and_custom_states(self):
        done={'id':'done-id','name':'Done','color':'GREEN','description':'accepted'}
        custom={'id':'custom-id','name':'Custom','color':'RED','description':'human'}
        options=p.preserve_options([done,custom],['Inbox','Done'])
        self.assertEqual(options[1],done)
        self.assertEqual(options[2],custom)
        self.assertEqual(p.preserve_options(options,['Inbox','Done']),options)

    def test_archived_and_foreign_items_are_not_mutated(self):
        board={'id':'board','url':'url'}
        archived={'id':'one','content':{'number':1,'repository':{'nameWithOwner':p.REPO}},'isArchived':True,'values':{}}
        foreign={'id':'two','content':{'number':2,'repository':{'nameWithOwner':'someone/other'}},'isArchived':False,'values':{}}
        mutations=[]
        def graphql(q,v):
            mutations.append(q.split('(')[0]);return {}
        with patch.object(p,'ensure_project',return_value=board), patch.object(p,'ensure_fields',return_value={}), patch.object(p,'project_items',return_value=[archived,foreign]), patch.object(p,'open_issues',return_value=[{'number':1}]), patch.object(p.subprocess,'check_output',return_value='sha'):
            r=p.setup_and_sync({'fields':{}},request=lambda _: {'node_id':'repo'},graphql=graphql)
        self.assertEqual(mutations,['mutation LinkBoard'])
        self.assertEqual(r['items_verified'],0)
        self.assertFalse(r['scientific_status_modified'])

    def test_missing_readback_cannot_claim_success(self):
        fields={'Status':{'id':'status','dataType':'SINGLE_SELECT','options':[{'name':'Inbox','id':'inbox'}]}}
        def api(q,v):
            if q.startswith('mutation AddWork'):
                return {'addProjectV2ItemById':{'item':{'id':'new'}}}
            return {}
        with patch.object(p.time,'sleep'), patch.object(p,'ensure_project',return_value={'id':'board'}), patch.object(p,'ensure_fields',return_value=fields), patch.object(p,'project_items',return_value=[]), patch.object(p,'open_issues',return_value=[{'number':1,'node_id':'issue','state':'open'}]):
            with self.assertRaisesRegex(RuntimeError,'readback'):
                p.setup_and_sync({'fields':{'Status':['Inbox']}},request=lambda _: {'node_id':'repo'},graphql=api)

    def test_delayed_api_readback_is_retried_without_repeating_mutations(self):
        fields={'Status':{'id':'status','dataType':'SINGLE_SELECT','options':[{'name':'Inbox','id':'inbox'}]}}
        mutations=[]
        def api(q,v):
            mutations.append(q.split('(')[0])
            if q.startswith('mutation AddWork'):
                return {'addProjectV2ItemById':{'item':{'id':'new'}}}
            return {}
        with patch.object(p.time,'sleep') as sleep, patch.object(p,'ensure_project',return_value={'id':'board'}), patch.object(p,'ensure_fields',return_value=fields), patch.object(p,'project_items',side_effect=[[],[],[{'id':'new','values':{'Status':'Inbox'}}]]), patch.object(p,'open_issues',return_value=[{'number':1,'node_id':'issue','state':'open'}]), patch.object(p.subprocess,'check_output',return_value='sha'):
            result=p.setup_and_sync({'fields':{'Status':['Inbox']}},request=lambda _: {'node_id':'repo'},graphql=api)
        self.assertTrue(result['verified'])
        self.assertEqual(mutations.count('mutation AddWork'),1)
        self.assertEqual(mutations.count('mutation UpdateWork'),1)
        sleep.assert_called_once_with(1)

    def test_workflow_never_checks_out_pr_code_with_project_secret(self):
        import yaml
        d=yaml.safe_load((ROOT/'.github/workflows/projects-sync.yml').read_text())
        job=d['jobs']['sync']
        self.assertIn("github.ref == 'refs/heads/main'",job['if'])
        checkout=job['steps'][0]
        self.assertEqual(checkout['with']['ref'],'main')
        self.assertFalse(checkout['with']['persist-credentials'])
        steps=job['steps']
        self.assertEqual(sum('PROJECTS_TOKEN' in str(s) for s in steps),1)
        events=(ROOT/'.github/workflows/project-events.yml').read_text()
        self.assertNotIn('secrets.',events)
        self.assertNotIn('uses:',events)
        self.assertNotIn('download-artifact',str(steps))


class ViewAPI:
    """Small stateful GraphQL double: create and update have different schemas."""
    def __init__(self, rows=()):
        self.rows = deepcopy(list(rows))
        self.mutations = []
        self.reads = 0

    @staticmethod
    def row(name='R135', view_id='target', layout='TABLE_LAYOUT', filter_text='R135', selected=('title','status')):
        return {'id':view_id, 'name':name, 'number':2, 'layout':layout, 'filter':filter_text,
                'project':{'id':'board','url':'https://github.com/users/owner/projects/2'},
                'configuration':{'visibleFields':{'nodes':[{'id':f,'name':f.title()} for f in selected],
                                                  'pageInfo':{'hasNextPage':False}}}}

    def __call__(self, query, variables):
        if query.startswith('query BoardViews'):
            self.reads += 1
            return {'node':{'views':{'nodes':deepcopy(self.rows), 'pageInfo':{'hasNextPage':False}}}}
        value = deepcopy(variables['input'])
        self.mutations.append((query.split('(')[0], value))
        if query.startswith('mutation CreateWorkView'):
            if set(value) != {'projectId','name','layout','configuration'}:
                raise AssertionError('CreateProjectV2ViewInput does not accept filter')
            row = self.row(name=value['name'], layout=value['layout'], filter_text='',
                           selected=value['configuration']['visibleFieldIds'])
            self.rows.append(row)
            return {'createProjectV2View':{'projectV2View':{'id':row['id']}}}
        if query.startswith('mutation UpdateWorkView'):
            row = next(r for r in self.rows if r['id']==value['viewId'])
            for key in ('name','layout','filter'):
                if key in value:
                    row[key] = value[key]
            if 'configuration' in value:
                row['configuration']['visibleFields']['nodes'] = [
                    {'id':f, 'name':f.title()} for f in value['configuration']['visibleFieldIds']]
            return {'updateProjectV2View':{'projectV2View':{'id':row['id']}}}
        raise AssertionError('Unexpected query: '+query)


class ProjectViews(unittest.TestCase):
    fields = {'Title':{'id':'title'}, 'Status':{'id':'status'}}
    plan = [{'name':'R135', 'layout':'TABLE_LAYOUT', 'filter':'R135', 'visible_fields':['Title','Status']}]

    def test_create_then_filter_readback_and_second_run_idempotent(self):
        api = ViewAPI()
        result = p.ensure_views('board', self.plan, self.fields, api)
        self.assertEqual([m[0] for m in api.mutations], ['mutation CreateWorkView','mutation UpdateWorkView'])
        self.assertEqual(result[0]['url'], 'https://github.com/users/owner/projects/2/views/2')
        self.assertEqual(result[0]['filter'], 'R135')
        self.assertEqual(result[0]['layout'], 'TABLE_LAYOUT')
        self.assertEqual(result[0]['visible_fields'], ['Title','Status'])
        p.ensure_views('board', self.plan, self.fields, api)
        self.assertEqual(len(api.mutations), 2)

    def test_only_exact_named_view_changes(self):
        unrelated = ViewAPI.row(name='R135 old', view_id='other', filter_text='human filter', selected=('status',))
        target = ViewAPI.row(layout='BOARD_LAYOUT', filter_text='old', selected=('status','title'))
        api = ViewAPI([unrelated,target])
        p.ensure_views('board', self.plan, self.fields, api)
        self.assertEqual(api.rows[0], unrelated)
        self.assertEqual(len(api.mutations), 1)
        self.assertEqual(api.mutations[0][1], {'viewId':'target','layout':'TABLE_LAYOUT','filter':'R135',
                                              'configuration':{'visibleFieldIds':['title','status']}})

    def test_ambiguous_configured_name_stops_before_mutation(self):
        api = ViewAPI([ViewAPI.row(), ViewAPI.row(view_id='duplicate')])
        with self.assertRaisesRegex(RuntimeError,'Ambiguous'):
            p.ensure_views('board', self.plan, self.fields, api)
        self.assertEqual(api.mutations, [])

    def test_bad_configuration_stops_before_query_or_mutation(self):
        cases = [None, {}, [self.plan[0],self.plan[0]], [{**self.plan[0], 'layout':'CALENDAR'}],
                 [{**self.plan[0], 'visible_fields':['Title','Missing']}],
                 [{**self.plan[0], 'visible_fields':['Title','Title']}],
                 [{**self.plan[0], 'filter':None}], [{**self.plan[0], 'unrecognized':True}]]
        for plan in cases:
            with self.subTest(plan=plan):
                api = ViewAPI()
                with self.assertRaises(ValueError):
                    p.ensure_views('board', plan, self.fields, api)
                self.assertEqual(api.reads, 0)
                self.assertEqual(api.mutations, [])

    def test_delayed_readback_does_not_repeat_create(self):
        api = ViewAPI()
        def delayed(query, variables):
            result = api(query,variables)
            if query.startswith('query BoardViews') and api.reads == 2:
                result['node']['views']['nodes'] = []
            return result
        with patch.object(p.time,'sleep') as sleep:
            result = p.ensure_views('board', self.plan, self.fields, delayed)
        self.assertEqual(result[0]['id'], 'target')
        self.assertEqual(sum(m[0]=='mutation CreateWorkView' for m in api.mutations), 1)
        sleep.assert_called_once_with(1)

    def test_incomplete_or_mismatched_readback_cannot_claim_success(self):
        api = ViewAPI()
        def corrupted(query, variables):
            result = api(query,variables)
            if query.startswith('query BoardViews') and api.reads > 1:
                result['node']['views']['nodes'][0]['filter'] = 'wrong'
            return result
        with patch.object(p.time,'sleep'), self.assertRaisesRegex(RuntimeError,'readback'):
            p.ensure_views('board', self.plan, self.fields, corrupted)
        self.assertEqual(len(api.mutations), 2)

    def test_view_readback_requires_full_fields_and_correct_parent(self):
        for mode in ('partial','parent','number'):
            with self.subTest(mode=mode):
                row = ViewAPI.row()
                if mode == 'partial':
                    row['configuration']['visibleFields']['pageInfo']['hasNextPage'] = True
                elif mode == 'parent':
                    row['project']['id'] = 'other-board'
                else:
                    row['number'] = 0
                with self.assertRaises(RuntimeError):
                    p.project_views('board', ViewAPI([row]))


if __name__=='__main__':
    unittest.main()
