"""J0 evidence: intervention ratios are distinct from within-model current shares."""
import csv
import json
from pathlib import Path
import numpy as np
from sqrt_exp.model import save_json, sha
from sqrt_exp.report import prepare_report as common_report, series

LEDGER_KEYS=['sink_flux','I_hop_sink','I_form_sink','I_idle_sink','n2','pump_flux','break_flux','inventory']

def prepare_report(root, config, metadata, outcome):
    result,checks=common_report(root,config,metadata,outcome)
    report=root/'report'; full=root/'full'
    manifest=json.loads((report/'data_manifest.json').read_text())
    manifest['selection']=('All 164 observables every .2 on VM; rho every 2. Published ledger CSV retains every .2 sample for 8 declared quantities. Other CSV: 31 quantities every .2 through 20 then 2, plus extrema. All-observable statistics cover all samples. No interpolation claims or reconstructed density matrices.')
    save_json(report/'data_manifest.json',manifest)
    checks.append(dict(name='service_inventory_budget',actual=result['full_file_count'],limit=config['full_inventory_limit'],
                       passed=result['full_file_count']<=config['full_inventory_limit']))
    result['interventions']=[];result['ledger_checks']=[]
    refs={r['model']:r for r in result['comparisons']['refinements']}
    for cid,item in result['cases'].items():
        s=item.get('summary')
        if not s:continue
        t,a,names=series(full,cid)
        folder=report/'ledger';folder.mkdir(exist_ok=True)
        with (folder/(cid+'.csv')).open('w',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['time',*LEDGER_KEYS])
            writer.writerows([[format(x,'.17g'),*[format(a[i,names.index(k)],'.17g') for k in LEDGER_KEYS]] for i,x in enumerate(t)])
        p=config['models'][s['case']['model']]
        expected=s['final_observables']
        if p['J']==0:
            err=max(item['statistics'][k]['max'].__abs__() for k in ['I_hop_sink','I_hop01','I_hop12','I_hop02'])
            err=max(err,max(abs(item['statistics'][k]['min']) for k in ['I_hop_sink','I_hop01','I_hop12','I_hop02']))
            checks.append(dict(name='zero_hop_'+cid,actual=err,limit=config['acceptance']['algebra'],passed=err<=config['acceptance']['algebra']))
            if p['gate_form']=='Q' and p['gate_idle'] in ['Q','S']:
                err=max(abs(item['statistics']['sink_flux'][k]) for k in ['min','max'])
                checks.append(dict(name='null_flux_'+cid,actual=err,limit=config['null_flux_tolerance'],passed=err<=config['null_flux_tolerance']))
        integ=s['integrals'];bound=config['ledger_absolute_tolerance']+config['ledger_relative_tolerance']*abs(integ['sink_flux'])
        row=dict(case_id=cid,residual=integ['sink_balance_residual'],limit=bound,
                 passed=abs(integ['sink_balance_residual'])<=bound)
        result['ledger_checks'].append(row)
        checks.append(dict(name='ledger_'+cid,**row))
        checks.append(dict(name='inventory_ledger_'+cid,actual=abs(integ['inventory_balance_residual']),limit=bound,
                           passed=abs(integ['inventory_balance_residual'])<=bound))
    for variant in ['PP','PQ','PS','QP','QQ','QS']:
        mids=['j0_'+variant,'j1_'+variant];ids=[m+'_mix' for m in mids]
        if not all(result['cases'].get(c,{}).get('summary') for c in ids):continue
        rows=[result['cases'][c]['summary'] for c in ids];vals=[r['final_observables'] for r in rows]
        f0,f1=[v['sink_flux'] for v in vals]
        sensitivities=[refs.get(m,{}).get('per_observable',{}).get('sink_flux') for m in mids]
        bound=10*sum(sensitivities)+1e-10 if all(x is not None for x in sensitivities) else None
        ratio=f0/f1 if abs(f1)>config['ratio_denominator_floor'] else None
        eligible=all(result['cases'].get(m+'_'+label,{}).get('summary',{}).get('stationarity',{}).get('passed',False) for m in mids for label in ['mix','fine']) and all(refs.get(m,{}).get('passed',False) for m in mids)
        result['interventions'].append(dict(variant=variant,F_J0=f0,F_J1=f1,ratio=ratio,delta_F=f0-f1,
          steady_comparison_eligible=eligible,numerical_difference_bound=bound,
          above_numeric_bound=abs(f0-f1)>bound if bound is not None else None,
          above_practical_threshold=abs(f0-f1)>config['practical_relative_effect']*abs(f1),
          J1_machine_current_share=(vals[1]['I_form_sink']+vals[1]['I_idle_sink'])/f1 if abs(f1)>config['ratio_denominator_floor'] else None))
    return result,checks


def finalize_report(root,result,checks,timing):
    report=root/'report';cfg=result['protocol'];result['timing']=timing
    checks.append(dict(name='runtime_gate',**timing['gate'],passed=timing['gate']['status']=='PASS'))
    save_json(report/'metrics.json',result);save_json(report/'checks.json',checks)
    g=timing['gate']
    lines=['# J=0 — проверка переноса без hop','',
      f'Время: прогноз {g["expected_seconds"]:.1f} с; диапазон {g["lower_seconds"]:.1f}–{g["upper_seconds"]:.1f} с; внутренний факт {g["actual_seconds"]:.1f} с; гейт {g["status"]}.',
      'Первым сверить полное время процесса по run.json: внутренний замер исключает финальную запись/выход; очередь и публикация отдельно. Вне диапазона — сначала разбор, затем научные выводы.',
      f'Запуск {result["run_id"]}; код {result["source_commit"]}.',
      f'Выполнено {result["actual_cases"]}/{result["planned_cases"]} случаев, {result["actual_steps"]}/{result["planned_steps"]} RK4-шагов; preflight отдельно {sum(r["rk4_steps"] for r in result["preflight"])}.',
      f'Полные данные: {result["full_file_count"]} файлов, {result["full_bytes"]} байт. Проверить также full_data_inventory_errors и export_errors в run.json; внутренний манифест не заменяет независимую опись службы.','',
      'Вопрос: сколько выходного потока остаётся при выключении hop? Шесть вариантов × J=0/1 × dt=.01/.005, T=200. Все остальные коэффициенты одинаковы. P=Π=|ψ+><ψ+|, Q=diag Π; первая буква — образование, вторая — фактор idle: P:I−Π, Q:I−Q, S:sqrt(I−Q).',
      'Три узла и три ребра 0/R/L, размерность 216. g=.5, η=.25, δ=.1, κin=κout=.5, φn=φe=.05, γr=.05, γbg=.01. Время в единицах исходного Jref=1 (не 1/J при J=0). Начало RRR, равная смесь |100> и |010>; n2(0)=0.',
      'Ожидание до запуска: hop=0 при J0; для QQ/QS_J0 весь F=0 при данном начале (для произвольного начала n2=n2(0)exp(−κout t)). Остальные J0-потоки могут остаться ненулевыми; знак и размер не критерий корректности.',
      'F(J0)/F(J1) — ответ на выключение канала с перестройкой состояния, НЕ доля машинного канала в исходной сети. J0 не удаляет связи. Саморемонт, BIC и квантовое преимущество здесь не проверяются.','',
      '## Главный результат','',
      '| Вариант | F J0 | F J1 | J0/J1 | (form+idle)/F в J1 | стационарное сравнение допустимо |',
      '|---|---:|---:|---:|---:|---|']
    fmt=lambda x:'не определено' if x is None else format(x,'.10g')
    for r in result['interventions']:
        lines.append('| '+r['variant']+' | '+' | '.join(fmt(r[k]) for k in ['F_J0','F_J1','ratio','J1_machine_current_share'])+' | '+str(r['steady_comparison_eligible'])+' |')
    lines += ['','Допуск означает конечное окно стационарности плюс dt/2 обеих моделей, не единственность стационара. При False сравнение остаётся только конечновременным. Практический порог |ΔF|>0.001|F_J1|; численный 10×сумма чувствительностей F к шагу +1e−10.','',
      '## Канальный баланс и все случаи','',
      'Для каждой строки dn2/dt = hop + form + idle − F. Числа позволяют проверить тождество без истории чата. Стац. — окно последних 10 единиц.','',
      '| Случай | F | hop | form | idle | dn2/dt | стац. |', '|---|---:|---:|---:|---:|---:|---|']
    for cid,item in result['cases'].items():
        s=item.get('summary')
        if not s:lines.append(f'| {cid} | {item["status"]} | — | — | — | — | — |');continue
        v=s['final_observables'];lines.append('| '+cid+' | '+' | '.join(format(v[k],'.16g') for k in ['sink_flux','I_hop_sink','I_form_sink','I_idle_sink','dn2_dt'])+' | '+str(s['stationarity']['passed'])+' |')
    lines += ['','## Динамика и проверки','', '| Случай | min F | max F @ t | среднее ± SD | max RHS |', '|---|---:|---:|---:|---:|']
    for cid,item in result['cases'].items():
        if not item.get('summary'):continue
        f=item['statistics']['sink_flux'];s=item['summary']
        lines.append(f'| {cid} | {f["min"]:.5g} | {f["max"]:.7g} @ {f["max_time"]:g} | {f["mean"]:.6g} ± {f["stddev"]:.5g} | {s["stationarity"]["max_relative_rhs"]:.4g} |')
    for r in result['comparisons']['refinements']:
        lines.append(f'dt/2 {r["model"]}: max Δ всех наблюдаемых {r["max_all_observable_difference"]:.6g}; порог {cfg["acceptance"]["refinement_observables"]:g}; PASS={r["passed"]}.')
    failures=[r['name'] for r in checks if not r['passed']]
    nonstat=[cid for cid,r in result['cases'].items() if r.get('summary') and not r['summary']['stationarity']['passed']]
    lines += [f'Численные/служебные проверки: {len(checks)-len(failures)}/{len(checks)}. Провалы: '+(', '.join(failures) or 'нет')+'.',
      'Не прошли стационарность (не скрываются и не продлеваются автоматически): '+(', '.join(nonstat) or 'нет')+'.',
      'Стационарность: max ||Lρ||/||ρ||≤1e−6, ΔF≤1e−10+1e−4|Fкон|, относительное изменение ρ≤1e−5. Абсолютный допуск необходим для нулевых контролей.',
      'trace/hermiticity≤1e−8, min sampled eigenvalue≥−1e−7; алгебра≤1e−10; preflight прямой RHS<1e−12 и RK4/expm≤2e−6. Позитивность проверена только на сетке каждые 10.']
    qualities=[r['summary']['state_quality'] for r in result['cases'].values() if r.get('summary')]
    if qualities:lines.append(f'Факт: max trace {max(q["max_trace_error"] for q in qualities):.6g}, max hermiticity {max(q["max_hermiticity_error"] for q in qualities):.6g}, min eigen {min(q["min_sampled_eigenvalue"] for q in qualities):.6g}.')
    if result['failure']:lines.append('Ошибка исполнения: '+json.dumps(result['failure'],ensure_ascii=False))
    lines += ['','## Интегральная проверка','',
      'QF=Qhop+Qform+Qidle+n2(0)−n2(T). Слагаемые знаковые, не обрезаются и не нормируются при почти нулевом QF. Полные регулярные ledger/*.csv (.2) позволяют независимо пересчитать Simpson и сверить integrals в metrics.json. Допуск остатка 1e−4+1e−5|QF| — ошибка квадратуры, не шага RK4.',
      '| Случай mix | QF | Qhop | Qform | Qidle | запас | остаток |', '|---|---:|---:|---:|---:|---:|---:|']
    for cid,item in result['cases'].items():
        if not cid.endswith('_mix') or not item.get('summary'):continue
        r=item['summary']['integrals'];lines.append('| '+cid+' | '+' | '.join(format(r[k],'.12g') for k in ['sink_flux','I_hop_sink','I_form_sink','I_idle_sink','stored_sink','sink_balance_residual'])+' |')
    lines += ['','## Покрытие и граница вывода','',
      'Матрицы каждые 2 и все 164 ряда каждые .2 остаются на ВМ. GitHub: все отсчёты восьми ledger-величин; 31 величина series — .2 до 20, далее 2 плюс экстремумы; все 164 статистики по всем исходным отсчётам. Размеры/хеши/покрытие в data_manifest.json. Ни одного случая не отбираем по знаку результата.',
      'Нет четырёхфазной серии или дополнительных φn: это парный базовый интервенционный тест. Снижение или сохранение F после J0 само по себе не доказывает необходимость/ненужность сети или способность к ремонту. Следующий E002 требует отдельного протокола.',
      'Приёмка: сначала время из run.json, затем SHA и размеры всех опубликованных файлов, отсутствие ошибок обеих описей, затем проверки содержания. Один exit_code=0 не означает научный успех.']
    text='\n'.join(lines)+'\n'
    if len(text.encode())>24576:raise ValueError('RESULT exceeds 24 KiB; no truncation')
    (report/'RESULT.md').write_text(text)
    (report/'README.md').write_text('# J0\n\nОсновной самодостаточный файл: [RESULT.md](RESULT.md).\n')
    files=[p for p in report.rglob('*') if p.is_file()];sizes=[p.stat().st_size for p in files]
    if len(files)>500 or max(sizes,default=0)>8*1024**2 or sum(sizes)>30*1024**2:raise ValueError('Export budget exceeded')
    return dict(files=len(files),bytes=sum(sizes),result_bytes=len(text.encode()))
