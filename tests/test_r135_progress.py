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


def completion_for(plan, task, check):
    return {'status':'VERIFIED_STRUCTURAL_EVIDENCE','checks':[check['id']],
            'contexts':{check['id']:p.acceptance_context(plan,task,check)}}


class Criteria(unittest.TestCase):
    def test_no_self_approval_or_missing_evidence(self):
        for field,value in [('level','accepted'),('evidence',[]),('scope',''),('level','applied'),
                            ('reviewed_criterion',''),('reviewed_criterion','unbound')]:
            plan,_,check = fixture()
            check['progress']['findings'][0][field]=value
            with self.subTest(field=field,value=value), self.assertRaises(ValueError):
                pipeline.validate_plan(plan)

    def test_scope_and_input_changes_leave_history(self):
        plan,t,c=fixture()
        old=deepcopy(plan)
        f=c['progress']['findings'][0]
        plan['progress_inputs']['donor_models']='a'*40
        self.assertIn('donor_models',p.stale(plan,t,f,c))
        t['progress_target']='Новая область'
        self.assertEqual(p.state(plan,t,c),'open')
        self.assertIn(f['obtained'],p.criterion_block(plan,t))
        diff=next(d for d in p.changed(old,plan) if d['criterion']==c['id'])
        self.assertEqual(diff['changes']['state'],{'before':'control','after':'open'})
        self.assertIn('область подготовки',diff['changes']['needs_review']['after'])
        self.assertEqual(p.changed(plan,plan),[])

    def test_changed_requirement_does_not_reuse_old_control(self):
        plan,t,c=fixture()
        old=deepcopy(plan)
        f=c['progress']['findings'][0]
        c['criterion'] += ' Проверить также другую физическую подготовку.'
        pipeline.validate_plan(plan)
        self.assertEqual(p.state(plan,t,c),'open')
        self.assertIn('критерий',p.stale(plan,t,f,c))
        block=p.criterion_block(plan,t)
        self.assertIn(f['obtained'],block)
        self.assertIn('Требует сверки после изменения: критерий',block)
        delta=next(d for d in p.changed(old,plan) if d['criterion']==c['id'])
        self.assertEqual(delta['changes']['state'],{'before':'control','after':'open'})

    def test_criterion_binding_migration_is_not_a_scientific_promotion(self):
        plan,t,c=fixture()
        old=deepcopy(plan)
        old_task=next(x for x in old['tasks'] if x['key']==t['key'])
        old_check=old_task['acceptance_checks'][0]
        for finding in old_check['progress']['findings']:
            del finding['reviewed_criterion']
        self.assertEqual(p.state(old,old_task,old_check),'open')
        with self.assertRaises(ValueError):
            pipeline.validate_plan(old)
        delta=next(d for d in p.changed(old,plan) if d['criterion']==c['id'])
        self.assertNotIn('state',delta['changes'])
        self.assertEqual(delta['changes']['legacy_unbound'],{'before':True,'after':False})
        self.assertIn('findings',delta['changes'])

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
        proof=completion_for(plan,t,c)
        ct=p.counts(plan,t,proof)
        self.assertEqual(ct['accepted'],1)
        self.assertEqual(ct.total(),len(t['acceptance_checks']))
        self.assertIsNone(t['completion_record'])
        block=p.replace_section('',p.criterion_block(plan,t,proof))
        self.assertEqual(p.visible_passed(block),[c['id']])
        self.assertEqual(p.visible_passed(block.replace(c['id'],'SU3-03')),['SU3-03'])
        self.assertNotIn(c['id'],p.next_action(t,p.visible_passed(block)))

    def test_completion_without_partial_findings_requires_current_scope(self):
        plan,t,c=fixture()
        c['progress']['findings']=[]
        proof=completion_for(plan,t,c)
        self.assertEqual(p.state(plan,t,c,proof),'accepted')
        t['progress_target']='Другая область без сохранённых частичных свидетельств'
        self.assertEqual(p.state(plan,t,c,proof),'open')
        self.assertEqual(p.state(plan,t,c,completion_for(plan,t,c)),'accepted')
        proof.pop('contexts')
        self.assertEqual(p.state(plan,t,c,proof),'open')

    def test_current_completion_is_independent_of_old_partial_findings(self):
        plan,t,c=fixture()
        model_finding = deepcopy(c['progress']['findings'][0])
        model_finding['evidence'] = ['modeldata']
        independent_finding = dict(model_finding, evidence=['contacts'])
        c['progress']['findings'] = [model_finding]
        old_proof=completion_for(plan,t,c)
        plan['progress_inputs']['donor_models']='a'*40
        self.assertEqual(p.state(plan,t,c,old_proof),'open')
        c['progress']['findings'].append(independent_finding)
        self.assertFalse(p.stale(plan,t,independent_finding,c))
        self.assertEqual(p.state(plan,t,c,old_proof),'control')
        proof=completion_for(plan,t,c)
        self.assertEqual(p.state(plan,t,c,proof),'accepted')
        self.assertTrue(p.stale(plan,t,c['progress']['findings'][0],c))
        block=p.criterion_block(plan,t,proof)
        self.assertIn('Требует сверки после изменения',block)
        self.assertIn('по приёмочной записи',block)

    def test_receipt_error_remains_visible_without_promotion(self):
        plan,t,c=fixture()
        proof={'status':'VERIFIED_STRUCTURAL_EVIDENCE','checks':[], 'contexts':{},
               'record_errors':{c['id']:'Completion criterion context mismatch'}}
        block=p.criterion_block(plan,t,proof)
        self.assertIn('Приёмочная запись требует сверки: Completion criterion context mismatch',block)
        self.assertIn(c['progress']['remaining'],block)
        self.assertEqual(p.state(plan,t,c,proof),'control')

    def test_context_and_map_hashes_have_explicit_boundaries(self):
        plan,t,c=fixture()
        self.assertEqual(p.plan_digest({'b':2,'a':1}),p.plan_digest({'a':1,'b':2}))
        context=p.acceptance_context(plan,t,c)
        snapshot=p.plan_digest(plan)
        c['progress']['next_output']+=' Уточнённая организация поставки.'
        self.assertNotEqual(p.plan_digest(plan),snapshot)
        self.assertEqual(p.acceptance_context(plan,t,c),context)
        c['criterion']+=' Новый обязательный результат.'
        self.assertNotEqual(p.acceptance_context(plan,t,c),context)

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

    def test_after_is_a_boolean_not_a_truthy_string(self):
        for value in ('false','true',0,1,None):
            plan,_,c=fixture()
            c['progress']['needs']=[{'task':'EOS','input':'Фазовые ветви','after':value}]
            with self.subTest(value=value), self.assertRaises(ValueError):
                pipeline.validate_plan(plan)
        for value in (False,True):
            plan,_,c=fixture()
            c['progress']['needs']=[{'task':'EOS','input':'Фазовые ветви','after':value}]
            pipeline.validate_plan(plan)
