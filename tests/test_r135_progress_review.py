from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import r135_pipeline as pipeline
from tools import r135_progress_review as review

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = 'infra/r135/research/review_fixture/source.json'


def fixture():
    plan = json.loads((ROOT/pipeline.MANIFEST_PATH).read_text())
    task = next(t for t in plan['tasks'] if t['key']=='GW_SOURCE')
    check = task['acceptance_checks'][0]
    plan['progress_evidence']['review-fixture'] = {
        'path':EVIDENCE_PATH, 'commit':'a'*40, 'sha256':'b'*64,
        'basis':{'implementation':plan['source_commits']['implementation']}}
    check['progress']['findings'].append({
        'level':'published', 'obtained':'A narrowly scoped review fixture.',
        'scope':'Fixture only.', 'reviewed_for':task['progress_target'],
        'reviewed_criterion':review.progress.criterion_digest(task,check),
        'evidence':['review-fixture']})
    return plan, task, check


class SourceImpact(unittest.TestCase):
    def test_unrelated_delta_does_not_hide_changed_evidence(self):
        old,task,check = fixture()
        new = deepcopy(old)
        unrelated = next(t for t in new['tasks'] if t['key']=='MODEL')
        unrelated['focus_criterion'] = unrelated['acceptance_checks'][1]['id']
        report = review.compare(old,new,[EVIDENCE_PATH])
        self.assertTrue(report['changes'])
        self.assertEqual(report['warnings'],[{
            'code':'EVIDENCE_WITHOUT_CRITERION_UPDATE', 'path':EVIDENCE_PATH,
            'criteria':[{'issue':task['issue_number'], 'criterion':check['id']}]}])

    def test_registered_relevant_delta_is_reported_without_warning(self):
        old,task,check = fixture()
        new = deepcopy(old)
        updated = next(t for t in new['tasks'] if t['key']==task['key'])['acceptance_checks'][0]
        updated['progress']['next_output'] += ' Проверить изменившийся источник.'
        report = review.compare(old,new,[EVIDENCE_PATH])
        self.assertEqual(report['warnings'],[])
        self.assertEqual(report['impacts'][0]['updated_criteria'],[
            {'issue':task['issue_number'],'criterion':check['id']}])
        self.assertFalse(report['scientific_status_modified'])

    def test_other_consumers_remain_visible_when_one_was_updated(self):
        old,task,check = fixture()
        second = task['acceptance_checks'][1]
        second['progress']['findings'].append(deepcopy(check['progress']['findings'][-1]))
        second['progress']['findings'][-1]['reviewed_criterion'] = review.progress.criterion_digest(task,second)
        new = deepcopy(old)
        updated = next(t for t in new['tasks'] if t['key']==task['key'])['acceptance_checks'][0]
        updated['progress']['remaining'] += ' Проверить новую ревизию.'
        report = review.compare(old,new,[EVIDENCE_PATH])
        self.assertEqual(report['warnings'][0]['criteria'],[
            {'issue':task['issue_number'],'criterion':second['id']}])

    def test_old_and_new_evidence_paths_are_both_mapped(self):
        old,task,check = fixture()
        new = deepcopy(old)
        new_path = 'infra/r135/research/review_fixture/renamed.json'
        new['progress_evidence']['review-fixture']['path'] = new_path
        report = review.compare(old,new,[EVIDENCE_PATH,new_path])
        self.assertEqual({x['path'] for x in report['impacts']},{EVIDENCE_PATH,new_path})
        self.assertEqual(report['warnings'],[])
        self.assertTrue(all(x['criteria']==[{'issue':task['issue_number'],'criterion':check['id']}]
                            for x in report['impacts']))

    def test_unregistered_physics_and_research_edits_remain_explicit(self):
        plan,_,_ = fixture()
        paths = ['infra/r135/research/new_model.py',
                 'analysis/R135_PHYSICAL_SECTOR_X_20261120/full_run/software/new_solver.py']
        report = review.compare(plan,deepcopy(plan),paths+['unrelated/README.md'])
        self.assertEqual({x['path'] for x in report['warnings']},set(paths))
        self.assertEqual({x['code'] for x in report['warnings']},{'UNCLASSIFIED_RESEARCH_CHANGE'})
        self.assertIn('do not change scientific status',review.summary(report))

    def test_binding_migration_alone_does_not_acknowledge_a_source_change(self):
        new,task,check = fixture()
        old = deepcopy(new)
        legacy = next(t for t in old['tasks'] if t['key']==task['key'])['acceptance_checks'][0]
        for finding in legacy['progress']['findings']:
            finding.pop('reviewed_criterion')
        report = review.compare(old,new,[EVIDENCE_PATH])
        self.assertTrue(report['changes'])
        self.assertEqual(report['impacts'][0]['updated_criteria'],[])
        self.assertEqual(report['warnings'][0]['criteria'],[
            {'issue':task['issue_number'],'criterion':check['id']}])

    def test_focus_of_affected_criterion_alone_does_not_acknowledge_source(self):
        old,task,check = fixture()
        new = deepcopy(old)
        updated = next(t for t in new['tasks'] if t['key']==task['key'])
        updated['focus_criterion'] = updated['acceptance_checks'][1]['id']
        report = review.compare(old,new,[EVIDENCE_PATH])
        self.assertEqual(report['warnings'][0]['criteria'],[
            {'issue':task['issue_number'],'criterion':check['id']}])


class GitChanges(unittest.TestCase):
    def test_cli_compares_frozen_base_and_head_not_dirty_worktree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.check_output(['git',*args],cwd=root,text=True).strip()
            git('init','-q')
            git('config','user.name','Test fixture')
            git('config','user.email','test@local')
            plan,task,check = fixture()
            manifest = root/pipeline.MANIFEST_PATH
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps(plan))
            git('add','.');git('commit','-qm','base')
            base = git('rev-parse','HEAD')
            check['progress']['next_output'] += ' Frozen head output.'
            manifest.write_text(json.dumps(plan))
            git('add','.');git('commit','-qm','head')
            head = git('rev-parse','HEAD')
            manifest.write_text('{}')
            output = root/'result.json'
            summary = root/'summary.md'
            with patch.object(pipeline,'ROOT',root), patch.object(sys,'argv',[
                    'r135_progress_review.py','--base',base,'--output',str(output)]), patch.dict(
                    os.environ,{'GITHUB_STEP_SUMMARY':str(summary)}), redirect_stdout(io.StringIO()):
                review.main()
            report = json.loads(output.read_text())
            self.assertEqual((report['base_sha'],report['head_sha']),(base,head))
            self.assertEqual([(x['issue'],x['criterion']) for x in report['changes']],
                             [(task['issue_number'],check['id'])])
            self.assertIn('Changed criterion records: 1 /',summary.read_text())

    def test_deletion_and_both_rename_paths_survive_git_diff(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.check_output(['git',*args],cwd=root,text=True).strip()
            git('init','-q')
            git('config','user.name','Test fixture')
            git('config','user.email','test@local')
            deleted = root/EVIDENCE_PATH
            renamed = root/'infra/r135/research/review_fixture/original.json'
            deleted.parent.mkdir(parents=True)
            deleted.write_text('deleted input\n')
            renamed.write_text('renamed input\n')
            git('add','.');git('commit','-qm','before')
            base = git('rev-parse','HEAD')
            deleted.unlink()
            target = root/'infra/r135/research/review_fixture/renamed input\nnew.json'
            renamed.rename(target)
            git('add','-A');git('commit','-qm','after')
            head = git('rev-parse','HEAD')
            paths = review.changed_paths(root,base,head)
            self.assertEqual(set(paths),{
                EVIDENCE_PATH, renamed.relative_to(root).as_posix(), target.relative_to(root).as_posix()})
            plan,task,check = fixture()
            report = review.compare(plan,deepcopy(plan),paths)
            warning = next(x for x in report['warnings'] if x['path']==EVIDENCE_PATH)
            self.assertEqual(warning['criteria'],[
                {'issue':task['issue_number'],'criterion':check['id']}])


if __name__=='__main__':
    unittest.main()
