#!/usr/bin/env python3
"""Review file changes against the exact R135 criteria that cite them.

Warnings request a scoped human review; they do not invalidate old pinned
evidence, infer scientific progress, or require a new physical calculation.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

if __package__:
    from . import r135_pipeline as pipeline
    from . import r135_progress as progress
else:
    import r135_pipeline as pipeline
    import r135_progress as progress

RESEARCH_PREFIXES = ('infra/r135/research/',
                     'analysis/R135_PHYSICAL_SECTOR_X_20261120/')
RESEARCH_FILES = {'RUNTIME_GATE.md'}


def git_bytes(root, *arguments):
    return subprocess.check_output(['git', *arguments], cwd=root)


def changed_paths(root, base_sha, head_sha):
    """Include deleted files and both paths of a rename, without line parsing."""
    raw = git_bytes(root, 'diff', '--name-only', '-z', '--no-renames',
                    base_sha, head_sha, '--')
    return sorted({path.decode('utf-8', errors='surrogateescape')
                   for path in raw.split(b'\0') if path})


def evidence_users(plan):
    """Map pinned repository paths to their explicitly declared consumers."""
    refs = plan.get('progress_evidence', {})
    users = {}
    for task in plan['tasks']:
        for check in task['acceptance_checks']:
            address = (task['issue_number'], check['id'])
            for finding in check.get('progress', {}).get('findings', []):
                for key in finding['evidence']:
                    path = refs[key]['path']
                    users.setdefault(path, set()).add(address)
    return users


def addresses(values):
    return [{'issue':issue, 'criterion':criterion}
            for issue, criterion in sorted(values)]


def updated_record(row):
    """Bookkeeping/focus changes alone do not address a changed source."""
    substantive = {'scope','criterion','remaining','next_output','needs',
                   'criterion_record','artifacts'}
    fields = row['changes']
    if substantive & fields.keys():
        return True
    if 'findings' in fields:
        def without_binding(findings):
            return [{key:value for key,value in finding.items() if key!='reviewed_criterion'}
                    for finding in findings or []]
        value = fields['findings']
        return without_binding(value['before']) != without_binding(value['after'])
    return False


def compare(old, new, paths):
    """Account for every scoped path even when some other criterion changed."""
    changes = progress.changed(old, new)
    changed_addresses = {(row['issue'], row['criterion']) for row in changes if updated_record(row)}
    old_users, new_users = evidence_users(old), evidence_users(new)
    registered_paths = {ref['path'] for plan in (old,new)
                        for ref in plan.get('progress_evidence',{}).values()}
    impacts, warnings = [], []
    for path in sorted(set(paths)):
        affected = old_users.get(path, set()) | new_users.get(path, set())
        if affected:
            updated = affected & changed_addresses
            unchanged = affected - changed_addresses
            impacts.append({'path':path, 'classification':'registered_evidence',
                            'criteria':addresses(affected),
                            'updated_criteria':addresses(updated),
                            'unchanged_criteria':addresses(unchanged)})
            if unchanged:
                warnings.append({'code':'EVIDENCE_WITHOUT_CRITERION_UPDATE',
                                 'path':path, 'criteria':addresses(unchanged)})
        elif path in registered_paths or path.startswith(RESEARCH_PREFIXES) or path in RESEARCH_FILES:
            impacts.append({'path':path, 'classification':'unclassified_research',
                            'criteria':[], 'updated_criteria':[],
                            'unchanged_criteria':[]})
            warnings.append({'code':'UNCLASSIFIED_RESEARCH_CHANGE',
                             'path':path, 'criteria':[]})
    return {'status':'PASS', 'tasks':len(new['tasks']),
            'criteria':sum(len(t['acceptance_checks']) for t in new['tasks']),
            'live_evidence_checked':False, 'scientific_status_modified':False,
            'needs_review':[c['id'] for t in new['tasks'] for c in t['acceptance_checks']
                            if any(progress.stale(new,t,f,c)
                                   for f in c['progress']['findings'])],
            'changes':changes, 'changed_paths':sorted(set(paths)),
            'impacts':impacts, 'warnings':warnings,
            'review_semantics':'Substantive criterion record changes acknowledge an address only; '
                               'they do not prove that a source change is scientifically resolved. '
                               'Focus, derived-state and binding-only migrations do not acknowledge a source change. '
                               'Pinned historical evidence is retained. Editorial changes may be '
                               'explained during review without inventing a result or rerunning science.'}


def warning_message(warning):
    if warning['code']=='UNCLASSIFIED_RESEARCH_CHANGE':
        return ('Changed research path has no declared criterion mapping: '+warning['path']+
                '. Review its effect or record why the change is editorial.')
    names = ', '.join('#%s / %s' % (row['issue'], row['criterion'])
                      for row in warning['criteria'])
    return ('Changed evidence path '+warning['path']+
            ' has unchanged criterion records: '+names+
            '. Review the affected scope; unrelated criterion edits do not cover it.')


def markdown_text(value):
    return str(value).replace('\r',' ').replace('\n',' ').replace('|',r'\|')


def summary(report):
    lines = ['## R135 criterion review', '',
             'Changed criterion records: %s / %s.' % (len(report['changes']), report['criteria']),
             'Changed research/evidence paths: %s. Review warnings: %s.' % (
                 len(report['impacts']), len(report['warnings'])), '',
             'Warnings identify review work. They do not change scientific status or invalidate pinned history.']
    if report['changes']:
        lines += ['', '### Criterion changes']
        for row in report['changes']:
            lines.append('- #%s / %s (%s)' % (row['issue'], markdown_text(row['criterion']),
                         ', '.join(markdown_text(key) for key in row['changes'])))
    if report['needs_review']:
        lines += ['', 'Evidence requiring recheck: '+', '.join(map(markdown_text,report['needs_review']))]
    if report['warnings']:
        lines += ['', '### Source changes requiring review']
        for row in report['warnings']:
            lines.append('- '+markdown_text(warning_message(row)))
    return '\n'.join(lines)+'\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True, help='Exact pull-request base SHA')
    parser.add_argument('--output', type=Path,
                        default=Path('project-evidence/R135_CRITERION_DELTA.json'))
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-fA-F]{40}', args.base):
        parser.error('--base must be a full commit SHA')
    root = pipeline.ROOT
    head = git_bytes(root, 'rev-parse', 'HEAD').decode().strip()
    old = json.loads(git_bytes(root, 'show', args.base+':'+pipeline.MANIFEST_PATH))
    new = json.loads(git_bytes(root, 'show', head+':'+pipeline.MANIFEST_PATH))
    pipeline.validate_plan(new)
    report = compare(old, new, changed_paths(root,args.base,head))
    report.update({'base_sha':args.base.lower(), 'head_sha':head})
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=True,indent=2)+'\n')
    output = summary(report)
    summary_path = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary_path:
        with Path(summary_path).open('a') as handle:
            handle.write(output)
    else:
        print(output,end='')
    for warning in report['warnings']:
        message = warning_message(warning).replace('%','%25').replace('\r','%0D').replace('\n','%0A')
        print('::warning::'+message)


if __name__=='__main__':
    main()
