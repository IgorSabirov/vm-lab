"""Compact report plus all matching inputs, no hidden omissions."""
import csv
from pathlib import Path
import numpy as np
from e002_exp.model import save_json,sha
from sqrt_exp.report import KEYS,stats
from .matching import EDGES,match,loss


def csv_file(path, header, rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(header)
        writer.writerows([[format(float(x),'.17g') for x in row] for row in rows])


def prepare_report(root,cfg,targets,meta,outcome,arrays):
    report=root/'report';report.mkdir(exist_ok=True);checks=list(outcome['checks'])
    cases={s['case']['id']:s for s in outcome['cases']}
    selected=list(KEYS)+['pR'+e for e in EDGES]+['event_rate__'+k+'_'+e for e in EDGES for k in ['break','background','idle']]
    comparisons={}
    for cid,s in cases.items():
        a,names=arrays[cid];t=a[:,0];v=a[:,1:];columns=[names.index(k) for k in selected]
        # RR-only renew columns are included where defined, never fake zeros.
        extra=[k for k in names if k.startswith('event_rate__renew_')]
        columns += [names.index(k) for k in extra]
        csv_file(report/'series'/f'{cid}.csv',['time',*selected,*extra],np.column_stack((t,v[:,columns])))
        take=t>=cfg['horizon']-cfg['baseline_window']-1e-9
        csv_file(report/'pre'/f'{cid}.csv',['time',*names],a[take])
        s['statistics']={n:stats(t,v[:,i]) for i,n in enumerate(names)}
        expected=round(cfg['horizon']/s['case']['dt'])
        count_ok=s['steps']==expected and s['rhs_calls']==4*expected and s['records']==round(cfg['horizon']/cfg['observable_interval'])+1 and len(s['snapshots'])==round(cfg['baseline_window']/cfg['diagnostic_interval'])+2
        checks.append(dict(name='counts_'+cid,passed=count_ok,steps=s['steps'],snapshots=len(s['snapshots'])))
        balance=np.max(abs(v[:,names.index('dn2_dt')]-v[:,names.index('I_hop_sink')]-v[:,names.index('I_form_sink')]-v[:,names.index('I_idle_sink')]+v[:,names.index('sink_flux')]))
        checks.append(dict(name='balance_'+cid,actual=float(balance),limit=1e-10,passed=bool(balance<=1e-10)))
        checks.append(dict(name='stationarity_'+cid,**s['stationarity']))
    for name in cfg['models']:
        a,b=name+'_coarse',name+'_fine'
        if a not in arrays or b not in arrays:continue
        x,n=arrays[a];y,ny=arrays[b]
        if n!=ny or x.shape!=y.shape or not np.allclose(x[:,0],y[:,0],atol=1e-10,rtol=0):
            raise ValueError('Refinement sampling differs')
        difference=float(np.max(abs(x[:,1:]-y[:,1:])))
        passed=difference<=cfg['acceptance']['refinement_observables']
        comparisons[name]=dict(max_observable_delta=difference,passed=passed)
        checks.append(dict(name='refinement_'+name,**comparisons[name]))
    complete=set(cases)=={c['id'] for c in cfg['cases']}
    checks.append(dict(name='all_cases',passed=complete,actual=len(cases),expected=len(cfg['cases'])))
    # Reproduction of frozen targets is checked, never repaired by retuning.
    for candidate in cfg['candidates']:
        cid=candidate+'_fine'
        if cid not in cases:continue
        a=cases[cid]['reference'];h=targets['candidates'][candidate];errors={}
        for e in EDGES:
            for key,value in [('pL',a['pL'+e]),('loss',loss(a,e))]:
                target=h['edges'][e][key];errors[key+e]=abs(value-target)/max(abs(target),1e-12)
        errors['hop']=abs(a['I_hop_sink']-h['baseline_hop'])/h['baseline_hop']
        limit=cfg['matching']['historical_reproduction_relative']
        checks.append(dict(name='historical_'+candidate,relative_errors=errors,limit=limit,passed=max(errors.values())<=limit))
    inventory=[dict(vm_path=f'results/{meta["run_id"]}/full/{p.relative_to(root/"full")}',bytes=p.stat().st_size,sha256=sha(p))
        for p in sorted((root/'full').rglob('*')) if p.is_file()]
    manifest=dict(run_id=meta['run_id'],source_commit=meta['source_commit'],full_files=inventory,
        full_file_count=len(inventory),full_bytes=sum(f['bytes'] for f in inventory),
        coverage='All observables every .2 in full JSONL; all pre-window observables in GitHub pre CSV. Selected 43 quantities (46 for RR) every .2 in GitHub series; all-observable extrema/means/std in metrics. Matrices t0 and last 10 every2; none between snapshots.')
    save_json(report/'data_manifest.json',manifest)
    checks.append(dict(name='inventory_budget',actual=len(inventory),limit=cfg['full_file_limit'],passed=len(inventory)<=cfg['full_file_limit']))
    valid=complete and not outcome['failure'] and all(c['passed'] for c in checks)
    decisions={}
    for candidate in cfg['candidates']:
        left,right=candidate+'_fine','RR_'+candidate+'_fine'
        if left in cases and right in cases:
            decisions[candidate]=match(cases[left]['reference'],cases[right]['reference'],cfg['matching'],valid)
        else:
            decisions[candidate]=dict(state='matching_numerical_failure',grade='ineligible',damage_eligible=False,reason='Missing cases')
    result=dict(**meta,protocol=cfg,targets=targets,cases=cases,refinements=comparisons,
        provisional_pair_decisions=decisions,failure=outcome['failure'],
        actual_steps=sum(c['steps'] for c in cases.values()),full_file_count=len(inventory),full_bytes=manifest['full_bytes'])
    return result,checks


def finalize(root,result,checks,seconds):
    cfg=result['protocol'];f=cfg['runtime_forecast'];report=root/'report'
    work=result['actual_steps']==f['main_steps'];production=cfg['mode']=='production'
    gate=dict(expected_seconds=f['expected_seconds'],actual_seconds=seconds,lower_seconds=f['lower_seconds'],upper_seconds=f['upper_seconds'],
        deviation_percent=100*(seconds/f['expected_seconds']-1),passed=bool(work and f['lower_seconds']<=seconds<=f['upper_seconds']),
        measurement='entry to before final report writes; verify whole-process time in run.json')
    result['runtime_gate']=gate
    checks.append({**gate,'name':'runtime_gate','passed':gate['passed'] if production else True,'test_only':not production})
    blockers=[c['name'] for c in checks if not c['passed']]
    if result['failure']:blockers.append('task_failure')
    if not production:blockers.append('test_mode_not_scientific')
    def apply_blockers():
        result['acceptance_blockers']=sorted(set(blockers))
        result['acceptance_status']='BLOCKED' if blockers else 'AWAITING_GITHUB_VERIFICATION'
        result['pair_decisions']={k:{**v,'damage_eligible':v['damage_eligible'] and not blockers,
            'state':v['state'] if not blockers else 'matching_numerical_failure'} for k,v in result['provisional_pair_decisions'].items()}
        # Always false: even passing feasibility does not submit a damage job.
        result['automatic_damage_launch']=False
    apply_blockers()
    lines=['# E002b — feasibility без повреждений','',
        f'Время: прогноз {gate["expected_seconds"]:.3f} с; внутренний факт {seconds:.3f} с; отклонение {gate["deviation_percent"]:+.3f}%; гейт {gate["passed"]}. Сначала сверить полное время run.json.',
        f'Запуск {result["run_id"]}; код {result["source_commit"]}; режим {cfg["mode"]}; шаги {result["actual_steps"]}/{f["main_steps"]}.',
        'Вопрос: допускает ли каждый QS/QQ независимый RR с теми же населённостями, потерями и достаточно близким исходным hop? Повреждений не было; успешность ремонта не измерялась.',
        'QS основной; QQ вторичный. Один аналитический RR для каждого, скорости закреплены по E002 до запуска. Переподгонки нет. 1% на каждом pL/loss/renew; hop≤5% предпочтителен, 5–10% ограниченное сопоставление, >10% не допускается к damage.',
        'Квантовый hop сохранён. Q-образование и диагональное растворение не переносят узловые населённости напрямую; отсутствие такого переноса проверено операторами.',
        '','| Кандидат | Исход | Качество hop | hop кандидата | hop RR | Несовпадение hop |','|---|---|---|---:|---:|---:|']
    for k,v in result['pair_decisions'].items():
        fmt=lambda key:format(v[key],'.8g') if key in v else '—'
        lines.append(f'| {k} | {v["state"]} | {v["grade"]} | {fmt("candidate_hop")} | {fmt("control_hop")} | {fmt("hop_relative_error")} |')
    lines += ['', 'Ниже средние [T−10,T]. loss=break+background+idle; renew — события R→L у RR. Все три относительные ошибки проверяются отдельно на ≤1%.',
        '| Пара | Ребро | pL кандидата | pL RR | loss кандидата | loss RR | renew RR |',
        '|---|---|---:|---:|---:|---:|---:|']
    for candidate in cfg['candidates']:
        left,right=candidate+'_fine','RR_'+candidate+'_fine'
        if left not in result['cases'] or right not in result['cases']:continue
        a,b=result['cases'][left]['reference'],result['cases'][right]['reference']
        for e in EDGES:
            lines.append(f'| {candidate} | {e} | {a["pL"+e]:.12g} | {b["pL"+e]:.12g} | {loss(a,e):.12g} | {loss(b,e):.12g} | {b["event_rate__renew_"+e]:.12g} |')
    lines += ['', '| Ветка | rel_rhs | Изменение rho | Норма: ошибка | Эрмитичность | min eigen | Стационарность |',
        '|---|---:|---:|---:|---:|---:|---|']
    for cid,s in result['cases'].items():
        q=s['state_quality'];st=s['stationarity']
        lines.append(f'| {cid} | {st["max_relative_rhs"]:.5g} | {st["relative_rho_change"]:.5g} | {q["trace"]:.4g} | {q["hermiticity"]:.4g} | {q["min_eigen"]:.4g} | {st["passed"]} |')
    lines += ['Численные пределы: rel_rhs≤1e−6, относительное изменение rho≤1e−5, trace/hermiticity≤1e−8, min eigen≥−1e−7.']
    for name,r in result['refinements'].items():
        lines.append(f'Уменьшение шага {name}: max Δ наблюдаемых {r["max_observable_delta"]:.6g}, предел {cfg["acceptance"]["refinement_observables"]:.6g}.')
    lines+=['','Пороговые ошибки и все исходные величины — metrics.json и pre/*.csv; для независимой арифметики infra/verify_e002b_report.py.',
        f'Проверки до финальной проверки размера отчёта {sum(c["passed"] for c in checks)}/{len(checks)}. Блокировки: '+(', '.join(result['acceptance_blockers']) or 'нет внутренних; GitHub ещё обязателен')+'.',
        'Все провалы: '+(', '.join(c['name'] for c in checks if not c['passed']) or 'нет')+'.',
        f'Полные данные: {result["full_file_count"]} файлов, {result["full_bytes"]} байт; опись data_manifest.json. Числа на сетке .2; матрицы только t0 и последнее окно каждые2.',
        'Нет найденного контроля означает отсутствие подходящего контроля в этом фиксированном аналитическом семействе; это не доказательство невозможности любого контроля.',
        'Окончательная приёмка через GitHub. Для damage нужна отдельная заявка с проверенной feasibility. Автоматического запуска нет.']
    result_text='\n'.join(lines)+'\n'
    (report/'RESULT.md').write_text(result_text)
    (report/'README.md').write_text('Главный самодостаточный отчёт: [RESULT.md](RESULT.md).\n')
    save_json(report/'metrics.json',result);save_json(report/'checks.json',checks)
    files=[p for p in report.rglob('*') if p.is_file()]
    # Reserve 1 KiB for this check's own record and possible blocker metadata.
    ok=len(files)<=cfg['report_file_limit'] and sum(p.stat().st_size for p in files)+1024<=cfg['report_bytes_limit'] and all(p.stat().st_size+1024<=cfg['report_single_file_limit'] for p in files) and len(result_text.encode())<=cfg['result_bytes_limit']
    checks.append(dict(name='report_budget',passed=ok,files=len(files),bytes_before_budget_record=sum(p.stat().st_size for p in files)))
    save_json(report/'checks.json',checks)
    if not ok:
        blockers.append('report_budget');apply_blockers()
        save_json(report/'metrics.json',result)
        (report/'RESULT.md').write_text('Время: см. runtime_gate в metrics.json. BLOCKED: превышен бюджет отчёта; выводы не принимаются.\n')
    return 1 if (result['failure'] or any(not c['passed'] for c in checks) or not ok) else 0
