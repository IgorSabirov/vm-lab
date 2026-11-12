import json
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
        with patch.object(p,'ensure_project',return_value={'id':'board'}), patch.object(p,'ensure_fields',return_value=fields), patch.object(p,'project_items',return_value=[]), patch.object(p,'open_issues',return_value=[{'number':1,'node_id':'issue','state':'open'}]):
            with self.assertRaisesRegex(RuntimeError,'readback'):
                p.setup_and_sync({'fields':{'Status':['Inbox']}},request=lambda _: {'node_id':'repo'},graphql=api)

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


if __name__=='__main__':
    unittest.main()
