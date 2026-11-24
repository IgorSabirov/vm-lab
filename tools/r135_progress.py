"""Criterion-level evidence, remaining work and projections of the R135 map."""
from collections import Counter
from hashlib import sha256
import json
import re

SCHEMA = 'vm-lab-r135-development-pipeline-v2'
LEVELS = ('open', 'published', 'control', 'applied', 'accepted')
LABEL = dict(open='без свидетельства', published='опубликовано', control='проверен контроль',
             applied='применено к подготовке', accepted='по приёмочной записи')
START, END = '<!-- r135-criteria:start -->', '<!-- r135-criteria:end -->'
LEGACY_START, LEGACY_END = '<!-- r135-partial-progress:start -->', '<!-- r135-partial-progress:end -->'
BASE = 'https://github.com/IgorSabirov/vm-lab'


def need(value, message):
    if not value:
        raise ValueError(message)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def version_map(plan):
    return {**plan['source_commits'], **plan['progress_inputs']}


def plan_digest(plan):
    """Hash a JSON snapshot independently of formatting and object-key order."""
    raw = json.dumps(plan, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    return sha256(raw.encode('utf-8')).hexdigest()


def criterion_digest(task, check):
    """Bind a finding to the exact requirement and the task's declared scope."""
    return plan_digest({'task_key':task['key'], 'criterion_id':check['id'],
                        'criterion':check['criterion'], 'stages':sorted(task['stages']),
                        'claims':sorted(task['claims'])})


def acceptance_context(plan, task, check):
    """Snapshot required for receipt applicability, not a scientific judgement."""
    return plan_digest({'criterion_digest':criterion_digest(task, check),
                        'progress_target':task['progress_target'], 'inputs':version_map(plan)})


def validate(plan):
    tasks = {t['key']: t for t in plan['tasks']}
    refs = plan.get('progress_evidence')
    extra = plan.get('progress_inputs')
    need(isinstance(extra, dict) and not (extra.keys() & plan['source_commits'].keys()), 'progress_inputs')
    versions = version_map(plan)
    need(all(re.fullmatch('[0-9a-f]{40}', v or '') for v in versions.values()), 'progress input revision')
    need(isinstance(refs, dict) and refs, 'progress_evidence')
    for key, ref in refs.items():
        path = ref.get('path', '')
        basis = ref.get('basis')
        need(nonempty(key) and all(part not in ('', '.', '..') for part in path.split('/'))
             and not re.search(r'[\\?#\s]', path) and re.fullmatch('[0-9a-f]{40}', ref.get('commit', ''))
             and re.fullmatch('[0-9a-f]{64}', ref.get('sha256', '')), 'invalid pinned evidence: '+key)
        need(isinstance(basis, dict) and basis and all(k in versions and re.fullmatch('[0-9a-f]{40}', v)
             for k, v in basis.items()), 'invalid evidence inputs: '+key)
    for t in tasks.values():
        need(nonempty(t.get('progress_target')), 'missing target: '+t['key'])
        ids = {c['id'] for c in t['acceptance_checks']}
        need(t.get('focus_criterion') in ids, 'unknown focus: '+t['key'])
        for c in t['acceptance_checks']:
            p = c.get('progress', {})
            where = '#%s / %s' % (t['issue_number'], c['id'])
            need(nonempty(p.get('remaining')) and nonempty(p.get('next_output')), 'missing remainder/output: '+where)
            deps = p.get('needs')
            need(isinstance(deps,list) and all(isinstance(d,dict) and d.get('task') in tasks and nonempty(d.get('input'))
                 and ('after' not in d or type(d['after']) is bool)
                 for d in deps), 'invalid next-output input: '+where)
            record = p.get('criterion_record')
            need(record is None or isinstance(record,str) and re.fullmatch(
                r'infra/r135/completions/[A-Za-z0-9_./-]+\.json',record)
                and all(x not in ('','.','..') for x in record.split('/')), 'invalid criterion record: '+where)
            findings = p.get('findings')
            need(isinstance(findings,list), 'missing findings: '+where)
            for f in findings:
                need(f.get('level') in ('published','control','applied') and all(nonempty(f.get(x))
                     for x in ('obtained','scope','reviewed_for')), 'invalid finding or scope: '+where)
                need(isinstance(f.get('reviewed_criterion'),str) and re.fullmatch(
                    '[0-9a-f]{64}',f['reviewed_criterion']), 'missing/invalid reviewed criterion: '+where)
                if f['level']=='applied':
                    need(nonempty(f.get('preparation')), 'missing preparation identifier: '+where)
                ev = f.get('evidence')
                need(isinstance(ev,list) and ev and all(k in refs for k in ev), 'missing evidence: '+where)


def stale(plan, task, finding, check):
    versions = version_map(plan)
    changes = {k for ref in finding['evidence'] for k,v in plan['progress_evidence'][ref]['basis'].items()
               if versions[k] != v}
    if finding['reviewed_for'] != task['progress_target']:
        changes.add('область подготовки')
    if finding.get('reviewed_criterion') != criterion_digest(task, check):
        changes.add('критерий')
    return sorted(changes)


def state(plan, task, check, completion=None):
    if (completion and completion.get('status') == 'VERIFIED_STRUCTURAL_EVIDENCE'
            and check['id'] in completion.get('checks',[])
            and isinstance(completion.get('contexts'),dict)
            and completion['contexts'].get(check['id']) == acceptance_context(plan,task,check)):
        return 'accepted'
    findings = check['progress']['findings']
    return max((f['level'] for f in findings if not stale(plan,task,f,check)), key=LEVELS.index, default='open')


def next_action(task, passed=()):
    checks = [c for c in task['acceptance_checks'] if c['id'] not in passed]
    if not checks:
        return 'Приёмочные записи проверены по всем критериям. Сверить итог поставки.'
    check = next((c for c in checks if c['id']==task['focus_criterion']), checks[0])
    return check['id']+' — '+check['progress']['next_output']


def accepted_ids(plan, task, completion):
    return [c['id'] for c in task['acceptance_checks'] if state(plan,task,c,completion)=='accepted']


def visible_passed(body):
    # Used only to project the API-verified Issue block into a display field.
    if START not in body or END not in body:
        return ()
    section = body.split(START,1)[1].split(END,1)[0]
    return re.findall(r'^#### (\S+) · по приёмочной записи$',section,flags=re.M)


def counts(plan, task, completion=None):
    return Counter(state(plan,task,c,completion) for c in task['acceptance_checks'])


def inputs_text(plan, progress):
    numbers = {t['key']:t['issue_number'] for t in plan['tasks']}
    required, later = [], []
    for n in progress['needs']:
        (later if n.get('after') else required).append(f"#{numbers[n['task']]} {n['input']}")
    text = ', '.join(required) or 'По этой записи внешних входов нет.'
    return text + ('. Затем: '+', '.join(later) if later else '')


def criterion_block(plan, task, completion=None):
    lines = ['### Прогресс и остаток по критериям', '', '**Следующий выход.** '+next_action(task,accepted_ids(plan,task,completion)),
             '', '**Проверяемая область.** '+task['progress_target']]
    for check in task['acceptance_checks']:
        p = check['progress']
        lines += ['', '#### '+check['id']+' · '+LABEL[state(plan,task,check,completion)], '']
        record_error = (completion or {}).get('record_errors',{}).get(check['id'])
        if record_error:
            lines.append('- Приёмочная запись требует сверки: '+' '.join(str(record_error).split())[:400]+'.')
        for f in p['findings']:
            links = []
            for key in f['evidence']:
                ref=plan['progress_evidence'][key]
                links.append(f"[{key}]({BASE}/blob/{ref['commit']}/{ref['path']})")
            lines.append('- '+LABEL[f['level']].capitalize()+'. '+f['obtained']+' Область: '+f['scope']+' '+' · '.join(links))
            if f.get('preparation'):
                lines.append('- Идентификатор подготовки: '+f['preparation'])
            changed = stale(plan,task,f,check)
            if changed:
                lines.append('- Требует сверки после изменения: '+', '.join(changed)+'. Прежняя область сохранена.')
        if state(plan,task,check,completion)=='accepted':
            lines.append('- Приёмочные артефакты и отдельный повтор проверены по записи в main.')
            continue
        if not p['findings']:
            lines.append('- Свидетельство по этому критерию ещё не зарегистрировано.')
        lines += ['- Остаток: '+p['remaining'], '- Следующий выход: '+p['next_output'],
                  '- Для этого выхода: '+inputs_text(plan,p)]
    return '\n'.join(lines)


def summary(plan, completions=None):
    completions = completions or {}
    total = Counter()
    rows = []
    review_total = 0
    for task in plan['tasks']:
        ct = counts(plan, task, completions.get(task['key']))
        total.update(ct)
        errors = (completions.get(task['key']) or {}).get('record_errors',{})
        stale_count = sum(bool(errors.get(c['id'])) or any(stale(plan,task,f,c)
                          for f in c['progress']['findings']) for c in task['acceptance_checks'])
        review_total += stale_count
        action = next_action(task,accepted_ids(plan,task,completions.get(task['key']))).replace('|', r'\|')
        rows.append(f"| #{task['issue_number']} {task['key']} | "+' | '.join(str(ct[k]) for k in LEVELS)
                    +f' | {stale_count} | {action} |')
    return '\n'.join(['### Прогресс по критериям R135', '',
        f"**Поставок: {len(plan['tasks'])}. Критериев: {total.total()}.** В каждой строке критерий учтён один раз по самому глубокому актуальному основанию. «Сверить» — число критериев со свидетельствами или приёмочными записями, требующими сверки после изменения требования, входов или области. Счётчики описывают основания, трудозатраты остаются отдельной оценкой #180.",
        '', '| Поставка | Без свидетельства | Опубликовано | Контроль | На подготовке | По приёмочной записи | Сверить | Следующий выход |',
        '|---|---:|---:|---:|---:|---:|---:|---|', *rows,
        '| **Всего** | '+' | '.join(str(total[k]) for k in LEVELS)+' | '+str(review_total)+' | |',
        '', 'Критерий с несколькими свидетельствами раскрыт в своей Issue. Итоговая научная оценка остаётся в R/U/D.'])


def replace_section(body, block):
    """Replace only our managed region; keep the previously authored map as history."""
    section = START+'\n'+block+'\n'+END
    for begin,end in ((START,END),(LEGACY_START,LEGACY_END)):
        need(body.count(begin)==body.count(end) and body.count(begin)<=1, 'ambiguous progress markers')
        if begin in body:
            need(body.index(begin)<body.index(end), 'reversed progress markers')
    if START in body:
        before, rest = body.split(START)
        _, after = rest.split(END)
        return before+section+after
    if LEGACY_START in body:
        before, rest = body.split(LEGACY_START)
        old, after = rest.split(LEGACY_END)
        return (before+section+'\n\n<details><summary>Предшествующая точка продолжения, 21 ноября 2026</summary>\n\n'
                +LEGACY_START+old+LEGACY_END+'\n\n</details>'+after)
    head, sep, tail = body.partition('### Ответственность')
    if sep:
        return head+section+'\n\n'+sep+tail
    return body.rstrip()+'\n\n'+section+'\n'


def blocks(plan, completions=None):
    completions = completions or {}
    return {plan['tracker']:summary(plan,completions), **{t['issue_number']:criterion_block(plan,t,completions.get(t['key']))
            for t in plan['tasks']}}


def changed(old, new):
    """Compare per-address outputs, including re-scoping and changes in referenced evidence."""
    def snapshot(plan, historical=False):
        result = {}
        for t in plan['tasks']:
            for c in t['acceptance_checks']:
                if 'progress' not in c:
                    continue
                fs = c['progress']['findings']
                reasons = []
                for f in fs:
                    changes = stale(plan,t,f,c)
                    # Legacy snapshots predate requirement bindings. Preserve only
                    # their historical level semantics so migration cannot invent
                    # open -> control progress. Current state/validation stay strict.
                    if historical and 'reviewed_criterion' not in f:
                        changes = [x for x in changes if x != 'критерий']
                    reasons.append(changes)
                historical_level = max((f['level'] for f,why in zip(fs,reasons) if not why),
                                       key=LEVELS.index,default='open')
                result[c['id'],t['issue_number']] = {
                    'state':historical_level if historical else state(plan,t,c),
                    'scope':t['progress_target'], 'criterion':c['criterion'],
                    'focus':c['id']==t['focus_criterion'], **c['progress'],
                    'legacy_unbound':any('reviewed_criterion' not in f for f in fs),
                    'needs_review':sorted({k for why in reasons for k in why}),
                    'artifacts':{e:plan['progress_evidence'][e] for f in fs for e in f['evidence']}}
        return result
    a,b = snapshot(old,historical=True),snapshot(new)
    results = []
    for key in sorted(a.keys() | b.keys(), key=lambda k:(k[1],k[0])):
        before, after = a.get(key,{}), b.get(key,{})
        fields = {k:{'before':before.get(k),'after':after.get(k)} for k in sorted(before.keys()|after.keys())
                  if before.get(k)!=after.get(k)}
        if fields:
            results.append({'issue':key[1],'criterion':key[0],'changes':fields})
    return results


def board_value(action):
    digest = sha256(action.encode()).hexdigest()[:12]
    return f'{action} [R135:{digest}]'


def own_board_value(value):
    match = re.fullmatch(r'(.*) \[R135:([a-f0-9]{12})\]', value or '')
    return bool(match and board_value(match[1])==value)
