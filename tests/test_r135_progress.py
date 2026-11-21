from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from tools import project_sync as board
from tools import r135_pipeline as pipeline
from tools import r135_progress as p

ROOT = Path(__file__).resolve().parents[1]


def fixture():
    plan = json.loads((ROOT/pipeline.MANIFEST_PATH).read_text())
    task = next(t for t in plan['tasks'] if t['key']=='GW_SOURCE')
    return plan, task, task['acceptance_checks'][0]


class Criteria(unittest.TestCase):
    def test_no_self_approval_or_missing_evidence(self):
        for field,value in [('level','accepted'),('evidence',[]),('scope',''),('level','applied')]:
            plan,_,check = fixture()
            check['progress']['findings'][0][field]=value
            with self.subTest(field=field,value=value), self.assertRaises(ValueError):
                pipeline.validate_plan(plan)

    def test_scope_and_input_changes_leave_history(self):
        plan,t,c=fixture()
        old=deepcopy(plan)
        f=c['progress']['findings'][0]
        plan['progress_inputs']['donor_models']='a'*40
        self.assertIn('donor_models',p.stale(plan,t,f))
        t['progress_target']='Новая область'
        self.assertEqual(p.state(plan,t,c),'open')
        self.assertIn(f['obtained'],p.criterion_block(plan,t))
        diff=next(d for d in p.changed(old,plan) if d['criterion']==c['id'])
        self.assertEqual(diff['changes']['state'],{'before':'control','after':'open'})
        self.assertIn('область подготовки',diff['changes']['needs_review']['after'])
        self.assertEqual(p.changed(plan,plan),[])

    def test_marker_migration_is_idempotent(self):
        old=p.LEGACY_START+'\nРучной текст\n'+p.LEGACY_END
        body='Начало\n'+old+'\n### Ответственность\nХвост'
        first=p.replace_section(body,'A')
        self.assertIn(old,first)
        self.assertEqual(p.replace_section(first,'A'),first)
        self.assertEqual(p.replace_section(first,'B'),first.replace(p.START+'\nA',p.START+'\nB'))
        with self.assertRaises(ValueError):
            p.replace_section(first+p.START,'B')

    def test_accepted_check_does_not_count_its_neighbors(self):
        plan,t,c=fixture()
        proof={'status':'VERIFIED_STRUCTURAL_EVIDENCE','checks':[c['id']]}
        ct=p.counts(plan,t,proof)
        self.assertEqual(ct['accepted'],1)
        self.assertEqual(ct.total(),len(t['acceptance_checks']))
        self.assertIsNone(t['completion_record'])
        block=p.replace_section('',p.criterion_block(plan,t,proof))
        self.assertEqual(p.visible_passed(block),[c['id']])
        self.assertEqual(p.visible_passed(block.replace(c['id'],'SU3-03')),['SU3-03'])
        self.assertNotIn(c['id'],p.next_action(t,p.visible_passed(block)))

    def test_readback_includes_manual_override_and_owned_continuation(self):
        plan,t,_=fixture()
        action=p.next_action(t)
        for current,conflict in [('Ручной приоритет',True),(t['next_action'],False),
                                 (p.board_value('Старый выход'),False),(p.board_value('A')+' правка',True)]:
            item={'id':'one','isArchived':False,'content':{'number':174,'repository':{'nameWithOwner':board.REPO}},
                  'values':{'Status':'Analysis','Next action':current}}
            fields={k:{'id':k,'dataType':'TEXT'} for k in ['Next action','R135 continuation']}
            def graphql(query,variables):
                if 'UpdateWork(' in query:
                    v=variables['input']
                    item['values'][v['fieldId']]=v['value']['text']
                return {}
            with patch.object(board,'project_items',side_effect=lambda *_:[deepcopy(item)]), patch.object(
                    board,'ensure_project',return_value={'id':'project'}), patch.object(board,'ensure_fields',return_value=fields), patch.object(
                    board,'open_issues',return_value=[{'number':174,'state':'open','body':'issue'}]), patch.object(
                    board.subprocess,'check_output',return_value='sha'):
                def sync():
                    return board.setup_and_sync({'fields':{}},request=lambda _: {'node_id':'repo'},graphql=graphql,pipeline=plan)
                result=sync()
                self.assertEqual(item['values']['Next action'],current if conflict else p.board_value(action))
                self.assertEqual(item['values']['R135 continuation'],action)
                self.assertEqual(bool(result['manual_next_action_differences']),conflict)
                self.assertEqual(sync()['field_updates'],[])

    def test_incomplete_output_and_unknown_parent_rejected(self):
        for field,value in [('remaining',''),('next_output',''),('needs',[{'task':'OTHER','input':'X'}])]:
            plan,_,c=fixture()
            c['progress'][field]=value
            with self.assertRaises(ValueError):
                pipeline.validate_plan(plan)
