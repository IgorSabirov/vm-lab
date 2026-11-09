#!/usr/bin/env python3
"""Offline plan/actual audit. Does not execute the experimental engine.

Run from the analysis workspace; inputs are preserved in EFFICIENCY_BUNDLE.zip.
The raw long-run archive supplies analysis_input/; prior science bundle supplies
deliverables/. Old baseline metrics come from the pinned GitHub MAIN_RUN.
"""
import collections
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'efficiency_output'
OUT.mkdir(exist_ok=True)
def read(path): return json.loads((ROOT / path).read_text())
def dump(path, obj):
    (OUT / path).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')
def sha(path): return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
def cell(x): return str(x).replace('|', '\\|').replace('\n', ' ')

contracts = read('efficiency_input/ANCESTOR_CONTRACTS.json')
returns = read('analysis_input/ANCESTOR_RETURN.json')
oldrun = read('efficiency_input/OLD_MAIN_RUN.json')
old = read('efficiency_input/OLD_METRICS_COMPACT.json')
new = read('analysis_input/METRICS.json')
current = read('repo_updates/CURRENT_RUN.json')
forecast = read('efficiency_input/FORECAST.json')
summary = read('deliverables/SUMMARY.json')
followup = read('deliverables/FOLLOWUP.json')
partition = read('efficiency_input/TIMING_PARTITION.json')

same_contrasts = [k for k, v in old['contrasts'].items() if new['contrasts'].get(k) == v]
same_summaries = [k for k, v in old['summary'].items()
                  if {a:b for a,b in new['summary'].get(k, {}).items() if a != 'joint_profile'} == v]
assert len(same_contrasts) == len(old['contrasts']) == 160
assert len(same_summaries) == len(old['summary']) == 213
hash_comparison = {}
for name in ['ANCESTOR_RETURN.json', 'SCOPE_ANCESTOR_RETURN.json', 'MONTE_CARLO_VALIDATION.json']:
    h = sha('analysis_input/' + name)
    prior = oldrun['artifacts'][name]['sha256']
    assert h == prior
    hash_comparison[name] = {'old_sha256': prior, 'new_sha256': h, 'byte_identical': True}
by_id = {a['id']: a for a in returns}
supported = [a for a in returns if a['status'] == 'SUPPORTED']
groups = collections.defaultdict(list)
for a in supported: groups[a['contrast_id']].append(a['ancestor'])
all_measures = set(groups)
full_contracts = []
for c in contracts['contracts']:
    a = by_id[c['id']]
    r = {'contract': c, 'measured_return': a,
         'baseline_return_identical': True,
         'increment_in_original_contract_from_long_extension': 'NONE',
         'status_change_to_original_ancestor': False,
         'allocated_cost': None,
         'cost_note': 'Shared evidence; individual ancestor cost was not measured. Do not duplicate panel cost.'}
    r['additional_requirements_actual'] = []
    for e in c.get('additional_requirements', []):
        if 'contrast' in e:
            all_measures.add(e['contrast'])
            value = new['contrasts'][e['contrast']][e.get('field', 'mean')]
            r['additional_requirements_actual'].append({**e, 'actual': value, 'in_band': e['lower'] <= value <= e['upper']})
    full_contracts.append(r)
constructs = []
for c in contracts['construct_returns']:
    related = [by_id[x] for x in c['result_contracts']]
    constructs.append({**c, 'supported_contracts': [a['id'] for a in related if a['status']=='SUPPORTED'],
                       'scope_only_contracts': [a['id'] for a in related if a['status']!='SUPPORTED'],
                       'new_contract_return_from_long_extension': 'NONE',
                       'interpretation': 'Existing links only; no independent experiments or automatic promotion.'})
wall = current['result']['process_wall_seconds']
expected = current['expected_seconds']
for v in partition.values():
    v['minutes'] = v['seconds']/60
    v['share_of_summed_task_timers_percent'] = 100*v['seconds']/sum(x['seconds'] for x in partition.values())
costs = {
    'main_expected_seconds': expected, 'main_actual_wall_seconds': wall,
    'main_actual_child_cpu_seconds': current['result']['child_cpu_seconds'],
    'actual_minus_expected_seconds': wall-expected,
    'actual_over_expected_percent': 100*(wall/expected-1),
    'above_upper_seconds': wall-current['upper_seconds'],
    'task_timer_partition': partition,
    'wall_minus_task_timers_seconds': wall-sum(v['seconds'] for v in partition.values()),
    'original_run_wall_seconds': oldrun['main']['process_wall_seconds'],
    'calibration_wall_seconds': 55.516777126002125,
    'smoke_wall_seconds_rounded': 60.57,
    'currency_cost': None, 'assistant_credit_cost': None,
    'end_to_end_project_cost': None,
    'missing_cost_reason': 'No measured billing/model-credit ledger or complete end-to-end stage accounting available.',
    'no_per_ancestor_cost_allocation': True,
    'timing_caveat': 'Task timers are not CPU-only and do not equal process wall. Separate phases are not a billing estimate.'
}
audit = {
    'schema': 1, 'date': '2026-11-09', 'type': 'RETROSPECTIVE_PLAN_ACTUAL_REVIEW',
    'source_commit': current['source_commit'], 'baseline_commit': oldrun['source_commit'],
    'baseline_run': oldrun['main']['job_id'], 'long_run': current['job_id'],
    'policy': 'RESEARCH_LINEAGE.md sections 1, 4, 5; no retrospective forecast or synthetic efficiency score',
    'status': 'REPORTING_GAP_REPAIRED; LONG_EXTENSION_SCIENTIFIC_RETURN_PLAN_INCOMPLETE',
    'baseline_comparison': {'same_contrasts': len(same_contrasts), 'same_summary_records_excluding_joint_profile': len(same_summaries), 'hash_comparison': hash_comparison},
    'contract_counts': dict(collections.Counter(a['status'] for a in returns)),
    'unique_primary_contrasts': len(groups),
    'unique_measures_including_additional_conditions': len(all_measures),
    'new_primary_contract_results_from_extension': 0,
    'original_questions_resolved': sum(a['original_question_resolved'] for a in returns),
    'scientific_status_promotions': sum(a['scientific_status_promoted'] for a in returns),
    'extension_planning_gap': 'In inspected contracts, amendment and protocol there is no separate numerical ancestor-return contract or decision threshold for the 1560 added contrasts. Descriptive coverage and runtime were planned.',
    'scientific_efficiency_percent': None,
    'efficiency_interpretation': 'No new result on origin of organization; conditional operating bounds mapped. No aggregate score defined or invented.',
    'costs': costs, 'primary_contrast_groups': dict(groups),
    'ancestor_returns': full_contracts, 'construct_returns': constructs,
    'open_links': contracts['open_links'],
    'extended_results': {'summary': summary, 'continuation': followup['continuation'],
                         'final_task_positive': followup['final_task_positive'],
                         'eight_carrier_final_positive': followup['eight_carrier_final_positive'],
                         'fuel_plateau_192_288_384': followup['fuel_plateau_192_288_384']},
    'posthoc_analysis_not_incremental_simulation_return': ['U001 event schedule explanation from unchanged baseline cases', 'Damage/repair/transfer causal ordering from existing source'],
    'source_files_sha256': {p:sha(p) for p in [
        'efficiency_input/ANCESTOR_CONTRACTS.json','efficiency_input/OLD_MAIN_RUN.json',
        'efficiency_input/OLD_METRICS_COMPACT.json','efficiency_input/FORECAST.json',
        'efficiency_input/TIMING_PARTITION.json','analysis_input/ANCESTOR_RETURN.json',
        'analysis_input/METRICS.json','deliverables/SUMMARY.json','deliverables/FOLLOWUP.json']}
}
dump('EFFICIENCY.json', audit)

lines = ['# Возврат по всем 125 исходным контрактам', '',
 'Ретроспективная сверка 2026-11-09. Исходные обещания не изменены. Полные before, prediction, preserved_limit, positive/negative/unresolved_return сохранены в EFFICIENCY.json.', '',
 'Во всех строках возврат побайтно совпадает с выполненным ранее 413-задачным прогоном. Приращение длинного прогона по этим контрактам отсутствует. Это не обнуляет отдельные карты расширения. Затраты на каждого предка отдельно не измерены; общие сравнения нельзя считать несколько раз.', '',
 '| Контракт / предок | Было | Обещано | Прогноз | Измерено | Оценка контракта / стало | Ограничение |',
 '|---|---|---|---|---|---|---|']
for r in full_contracts:
    c,a=r['contract'],r['measured_return']
    pred = {'primary': c.get('evaluation', c['prediction']), 'additional': c.get('additional_requirements', [])}
    if a['status']=='SUPPORTED':
        measured=f"{a['contrast_id']} = {a['actual']:.12g}; интервал {a.get('interval')}; доп.: {json.dumps(r['additional_requirements_actual'],ensure_ascii=False)}"
        state='SUPPORTED в кандидате; исходный вопрос не закрыт; нового приращения нет'
    else:
        measured='Исходный объект этим ядром не измеряется'
        state='NOT_EVALUABLE_IN_THIS_KERNEL; граница сохранена, не отрицательный результат'
    lines.append('| '+' | '.join(map(cell,[c['id']+' / '+c['ancestor'],c['before_status']+'; '+c['before'],c['promised_delta'],json.dumps(pred,ensure_ascii=False),measured,state,c['preserved_limit']]))+' |')
(OUT/'EFFICIENCY_ANCESTORS.md').write_text('\n'.join(lines)+'\n')
lines=['# Возврат по 42 конструкциям и 10 открытым связям','',
       'Связи взяты из исходного ANCESTOR_CONTRACTS.json. Число ссылок не является научной отдачей. Все исходные вопросы сохраняют ограничения; автоматического повышения статуса нет. Новые ограничения расширения в основном отчёте отмечены отдельно.', '',
       '| Конструкция | Исходные контракты | Уже поддержанные в кандидате | Сохранённый предел |', '|---|---|---|---|']
for c in constructs:
    lines.append('| '+' | '.join(map(cell,[c['id']+' '+c['title'],', '.join(c['result_contracts']),', '.join(c['supported_contracts']) or 'нет',c['original_limit']]))+' |')
lines+=['','## Открытые связи','','| Связь | Было | Условие закрытия | Стало |','|---|---|---|---|']
for l in contracts['open_links']:
    lines.append('| '+' | '.join(map(cell,[l['id'],l['before'],l['closure_condition'],'Открыто; условие закрытия не получено']))+' |')
(OUT/'EFFICIENCY_CONSTRUCTS.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({'baseline_same_contrasts':len(same_contrasts),'baseline_same_summary':len(same_summaries),'contracts':len(full_contracts),'constructs':len(constructs),'primary_measures':len(groups),'all_measures':len(all_measures),'costs':costs},ensure_ascii=False,indent=2))
