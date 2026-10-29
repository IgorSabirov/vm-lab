"""Self-contained E002 report with all-case ledgers and predeclared decisions."""
import csv,json
from pathlib import Path
import numpy as np
from scipy.integrate import simpson
from sqrt_exp.report import stats,KEYS
from .model import save_json,sha
from .metrics import recovery,classify


def load_series(full,case):
    cid=case['id'];names=json.loads((full/'cases'/f'{cid}_schema.json').read_text())['observable_names']
    rows=[json.loads(s) for s in (full/'cases'/f'{cid}.jsonl').read_text().splitlines()]
    t=np.array([r['time'] for r in rows]);a=np.array([r['values'] for r in rows])
    return t,a,names


def prepare(root,cfg,meta,outcome):
    full=root/'full';report=root/'report';report.mkdir(exist_ok=True)
    allarrays={};cases={};checks=list(outcome['checks'])
    for summary in outcome['cases']:
        case=summary['case'];cid=case['id'];t,a,names=load_series(full,case)
        pre=json.loads((full/'cases'/f'{cid}_pre.json').read_text());pt=np.array([r['time'] for r in pre]);pa=np.array([r['values'] for r in pre])
        ref=dict(zip(names,(simpson(pa,x=pt,axis=0)/(pt[-1]-pt[0])).tolist()))
        take=t>=case['damage_time']-1e-9;rt=t[take];ra=a[take];series={n:ra[:,i] for i,n in enumerate(names)}
        allarrays[cid]=(t,a,names,rt,series)
        damage=json.loads((full/'cases'/f'{cid}_damage.json').read_text())
        cases[cid]=dict(summary=summary,reference=ref,damage=damage,statistics={n:stats(t,a[:,i]) for i,n in enumerate(names)},
                        recovery_statistics={n:stats(rt,ra[:,i]) for i,n in enumerate(names)})
        expected_snapshots=int(1+sum(tm==0 or tm>=cfg['rho_start']-1e-9 for tm in np.arange(round(case['horizon']/cfg['rho_interval'])+1)*cfg['rho_interval']))
        checks.append(dict(name='counts_'+cid,actual_snapshots=len(summary['snapshots']),expected_snapshots=expected_snapshots,
            passed=len(t)==summary['records']==round(case['horizon']/cfg['observable_interval'])+1
            and summary['steps']==round(case['horizon']/case['dt']) and summary['rhs_calls']==4*summary['steps']
            and len(summary['snapshots'])==expected_snapshots))
        balance=np.max(abs(series['dn2_dt']-series['I_hop_sink']-series['I_form_sink']-series['I_idle_sink']+series['sink_flux']))
        checks.append(dict(name='balance_'+cid,actual=float(balance),limit=1e-10,passed=bool(balance<=1e-10)))
        # Exact post-damage population map including all untouched marginals.
        bef,aft=damage['before'],damage['after'];errors=[]
        for e in ['01','12','02']:
            old=np.array([bef['p'+label+e] for label in ['0','R','L']]);want=old.copy()
            if case['damage']=='link':want=np.array([old[0]+old[2],old[1],0.])
            if case['damage']=='feed':want=np.array([old[0],old[1]+old[2],0.])
            if case['damage']=='resource':want=np.array([old[0]+old[1],0.,old[2]])
            if case['damage']=='hard':want=np.array([1.,0.,0.])
            errors.extend(abs(want-np.array([aft['p'+label+e] for label in ['0','R','L']])))
        errors.extend(abs(aft['n'+str(i)]-bef['n'+str(i)]) for i in range(3))
        checks.append(dict(name='damage_'+cid,actual=float(max(errors)),limit=1e-10,passed=bool(max(errors)<=1e-10)))
        pre_folder=report/'pre';pre_folder.mkdir(exist_ok=True)
        with (pre_folder/(cid+'.csv')).open('w',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['time',*KEYS])
            for j,tm in enumerate(pt):writer.writerow([format(tm,'.17g'),*[format(pa[j,names.index(k)],'.17g') for k in KEYS]])
        # Publish every recovery sample for ALL primary/ledger/structure keys, no decimation.
        folder=report/'series';folder.mkdir(exist_ok=True)
        with (folder/(cid+'.csv')).open('w',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['time',*KEYS])
            for j,tm in enumerate(rt):writer.writerow([format(tm,'.17g'),*[format(ra[j,names.index(k)],'.17g') for k in KEYS]])
    planned={c['id']:c for c in cfg['cases']}
    checks.append(dict(name='all_cases',passed=set(cases)==set(planned),actual=len(cases),expected=len(planned)))
    pp=cases.get('PP_none_fine');ppref=pp['reference'] if pp else {'I_hop_sink':0.,'sink_flux':0.}
    for cid,r in cases.items():
        case=r['summary']['case'];base=cases.get(case['model']+'_none_fine')
        if base is None:continue
        baseid=base['summary']['case']['id'];bt,ba,bn,brt,bs=allarrays[baseid]
        bq=float(simpson(bs['sink_flux'],x=brt));_,_,_,rt,series=allarrays[cid]
        rec=recovery(rt,series,base['reference'],ppref,bq);r['recovery']=rec
        q=rec['integrals'];limit=1e-4+1e-5*abs(q['sink_flux'])
        checks.append(dict(name='ledger_'+cid,actual=max(abs(q['residual']),abs(q['inventory_residual'])),limit=limit,passed=max(abs(q['residual']),abs(q['inventory_residual']))<=limit))
    for cid,r in cases.items():
        if 'recovery' not in r:continue
        rec=r['recovery'];base=cases[r['summary']['case']['model']+'_none_fine'].get('recovery')
        base_share=base['machine_share'] if base else None
        rec['guard_limit']=base_share+.20 if base_share is not None else None
        rec['guard_passed']=bool(rec['machine_share']<=rec['guard_limit']) if rec['machine_share'] is not None and rec['guard_limit'] is not None else None
    refinements={}
    for cid,r in cases.items():
        if not cid.endswith('_coarse'):continue
        fid=cid.removesuffix('_coarse')+'_fine'
        if fid not in cases or 'recovery' not in cases[fid] or 'recovery' not in r:continue
        x,y=r['recovery'],cases[fid]['recovery'];t,a,n,_,_=allarrays[cid];tf,af,nf,_,_=allarrays[fid]
        if n!=nf or not np.allclose(t,tf,rtol=0,atol=1e-10):raise ValueError('Refinement grids differ')
        row=dict(max_observable_delta=float(np.max(abs(a-af))),metric_differences={},passed=True)
        row['passed']=row['max_observable_delta']<=cfg['acceptance']['refinement_observables']
        for key in ['Lambda_hop','Lambda_total']:
            if x[key] is None or y[key] is None:row['passed'] &= x[key] is None and y[key] is None;continue
            delta=abs(x[key]-y[key]);limit=max(.05,.01*abs(y[key]));row['metric_differences'][key]=dict(delta=delta,limit=limit);row['passed'] &= delta<=limit
        if x['shares'] is not None and y['shares'] is not None:
            row['max_share_delta']=max(abs(x['shares'][k]-y['shares'][k]) for k in x['shares']);row['passed'] &= row['max_share_delta']<=.01
        else:row['passed'] &= x['shares'] is None and y['shares'] is None
        refinements[cid]=row;checks.append(dict(name='refinement_'+cid,**row))
    matches={}
    if pp:
        for v in ['RR','RR2']:
            rr=cases.get(v+'_none_fine')
            if not rr:continue
            a,b=rr['reference'],pp['reference'];errors={}
            for k in ['pL01','pL12','pL02','inventory','pump_flux','break_flux']:
                errors[k]=abs(a[k]-b[k])/max(abs(b[k]),1e-12)
            for e in ['01','12','02']:
                loss=lambda x:cfg['models']['PP']['delta']*x['pL'+e]+x['event_rate__background_'+e]+x['event_rate__idle_'+e]
                expected=loss(b)*(2 if v=='RR2' else 1)
                errors['loss_'+e]=abs(loss(a)-expected)/max(abs(expected),1e-12)
            matches[v]=dict(relative_errors=errors,passed=max(errors.values())<=cfg['matching_tolerance'],
                F_mismatch=a['sink_flux']-b['sink_flux'],hop_mismatch=a['I_hop_sink']-b['I_hop_sink'])
    def eligible(cid):
        r=cases.get(cid,{});model=r.get('summary',{}).get('case',{}).get('model','')
        return bool(r.get('summary',{}).get('pre_stationarity',{}).get('passed') and cases.get(model+'_none_fine',{}).get('summary',{}).get('pre_stationarity',{}).get('passed') and refinements.get(cid,{}).get('passed'))
    primary='metric_undefined';sensitivity='metric_undefined'
    if 'PP_link_coarse' in cases and 'RR_link_coarse' in cases:
        ppd=cases['PP_link_coarse']['recovery'];rrd=cases['RR_link_coarse']['recovery']
        primary=classify(ppd,rrd,matches.get('RR',{}).get('passed',False),eligible('PP_link_coarse') and eligible('RR_link_coarse') and all(c['passed'] for c in checks))
        if 'RR2_link_coarse' in cases:
            sensitivity=classify(ppd,cases['RR2_link_coarse']['recovery'],matches.get('RR2',{}).get('passed',False),eligible('PP_link_coarse') and eligible('RR2_link_coarse') and all(c['passed'] for c in checks))
    qualifiers=[]
    for left,right in [('PP','QP'),('PQ','QQ'),('PS','QS'),('PP','PQ'),('PP','PS')]:
        lc,rc=left+'_link_coarse',right+'_link_coarse'
        if lc not in cases or rc not in cases:continue
        l,r=cases[lc].get('recovery',{}),cases[rc].get('recovery',{});den=r.get('Lambda_hop');num=l.get('Lambda_hop')
        ratio=num/den if num is not None and den is not None and den>1e-8 else None
        qualifiers.append(dict(left=left,right=right,ratio=ratio,candidate=bool(ratio is not None and ratio<=.8 and eligible(lc) and eligible(rc) and l.get('guard_passed'))))
    inventory=[dict(vm_path=f'results/{meta["run_id"]}/full/{p.relative_to(full)}',bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(full.rglob('*')) if p.is_file()]
    checks.append(dict(name='inventory_budget',actual=len(inventory),limit=cfg['full_file_limit'],passed=len(inventory)<=cfg['full_file_limit']))
    manifest=dict(run_id=meta['run_id'],source_commit=meta['source_commit'],full_files=inventory,full_file_count=len(inventory),full_bytes=sum(x['bytes'] for x in inventory),
      coverage='All raw observables at .2, post-damage t200 replaces pre in ordinary row; pre data and pre state separate. GitHub CSV retains all recovery and pre-window samples for 31 named quantities; ALL-observable global and recovery extrema/means/std in metrics. No claims between samples. Matrices only t0, t>=196 every2, plus pre-damage. No full-matrix archive for early preparation.')
    save_json(report/'data_manifest.json',manifest)
    return dict(**meta,protocol=cfg,cases=cases,refinements=refinements,matches=matches,primary_outcome=primary,RR2_outcome=sensitivity,qualifiers=qualifiers,
      failure=outcome.get('failure'),actual_steps=sum(r['summary']['steps'] for r in cases.values()),planned_steps=cfg['runtime_forecast']['main_steps'],full_file_count=len(inventory),full_bytes=manifest['full_bytes']),checks


def finalize(root,result,checks,actual):
    report=root/'report';cfg=result['protocol'];g=cfg['runtime_forecast'];work=result['actual_steps']==result['planned_steps']
    gate=dict(expected=g['expected_seconds'],actual=actual,lower=g['lower_seconds'],upper=g['upper_seconds'],passed=bool(work and g['lower_seconds']<=actual<=g['upper_seconds']))
    gate.update(expected_seconds=gate['expected'],actual_seconds=actual,lower_seconds=gate['lower'],upper_seconds=gate['upper'],
        actual_over_expected=actual/gate['expected'],calibration_reference=g['reference'],executed_branch='fixed_50_cases',
        status='PASS' if gate['passed'] else 'REVIEW_REQUIRED',measurement='entry timer to before final metrics/RESULT writes; verify whole-process run.json separately')
    result['runtime_gate']=gate;checks.append(dict(name='runtime_gate',**gate))
    save_json(report/'metrics.json',result);save_json(report/'checks.json',checks)
    lines=['# E002 — повреждение и восстановление','',f'Время: прогноз {gate["expected"]:.1f} с; внутренний факт {actual:.1f} с; отклонение {100*(actual/gate["expected"]-1):+.2f}%; диапазон {gate["lower"]:.1f}–{gate["upper"]:.1f}; PASS={gate["passed"]}.',
      'Сначала сверить полное время по run.json. Внутренний замер исключает финальную запись. При выходе за границы сначала разбор объёма и времени; исходы ниже до этого не принимаются.',
      f'Запуск {result["run_id"]}; код {result["source_commit"]}. Шаги {result["actual_steps"]}/{result["planned_steps"]}; полные данные {result["full_file_count"]} файлов, {result["full_bytes"]} байт.',
      'Вопрос: PP восстанавливает перенос hop лучше RR с согласованными населённостями рёбер и диссипативными потерями? Размерность 216; базовые коэффициенты как J0; t_damage=200, конец300; источник и ресурсная помпа не выключаются. link=L→0, feed=L→R, resource=R→0, hard=всё→0; none — контроль.',
      'PP/PQ/PS/QP/QQ/QS: первая буква образование, вторая idle-фактор P:I−Π, Q:I−diagΠ, S:sqrt(I−diagΠ). RR удаляет form и условный idle, вводит независимые R→L/L→R. RR2 удваивает суммарную скорость потерь и согласованную скорость образования при той же стационарной населённости. J0 выключает только hop.',
      'Подпитка η=.25, поломка δ=.1, g=.5, J=1 (кроме J0), κin=κout=.5, φn=φe=.05, γr=.05, γbg=.01. RRR и равная смесь узлов |100>,|010>. Все параметры/скорости заранее в config.',
      f'Предварительная классификация: **{result["primary_outcome"]}**. Проверка RR×2: **{result["RR2_outcome"]}**.',
      'Порог ремонта Λhop≤50; преимущество PP: Λhop_PP≤0.7Λhop_RR; guard для каждого варианта Mmachine≤Mmachine_none,same_window+0.20. Неопределённые метрики не равны нулю. Сравнение RR меняет также прямой транспорт form/idle: преимущество не доказывает уникальный механизм или необходимость обратной связи вообще.','',
      '| Случай | Λhop | Λtotal | Mmachine | guard | Qpump | pre steady |', '|---|---:|---:|---:|---|---:|---|']
    fmt=lambda x:'—' if x is None else format(x,'.7g')
    for cid,r in result['cases'].items():
        rec=r.get('recovery',{});lines.append('| '+cid+' | '+' | '.join(fmt(rec.get(k)) for k in ['Lambda_hop','Lambda_total','machine_share'])+' | '+str(rec.get('guard_passed'))+' | '+fmt(rec.get('integrals',{}).get('pump_flux'))+' | '+str(r['summary']['pre_stationarity']['passed'])+' |')
    lines+=['','## Независимо пересчитываемый баланс (coarse)','',
      'QF=Qhop+Qform+Qidle+stored; stored=n2(200+)−n2(300). Интеграл на post-damage окне, без скачка. Знаковые доли не клиппируются.','',
      '| Случай | QF | Qhop | Qform | Qidle | stored | остаток |','|---|---:|---:|---:|---:|---:|---:|']
    for cid,r in result['cases'].items():
        if not cid.endswith('coarse') or 'recovery' not in r:continue
        q=r['recovery']['integrals'];lines.append('| '+cid+' | '+' | '.join(format(q[k],'.12g') for k in ['sink_flux','I_hop_sink','I_form_sink','I_idle_sink','stored','residual'])+' |')
    lines+=['','## Проверки и предел вывода','']
    for v,m in result['matches'].items():lines.append(f'{v}: max относительная ошибка matching={max(m["relative_errors"].values()):.6g}, PASS={m["passed"]}; ΔF={m["F_mismatch"]:.6g}, Δhop={m["hop_mismatch"]:.6g} не подгонялись.')
    failures=[x['name'] for x in checks if not x['passed']];lines.append(f'Проверки: {len(checks)-len(failures)}/{len(checks)}. Все провалы: '+(', '.join(failures) or 'нет')+'.')
    lines += ['dt/2: Λ допуск max(.05,.01Λfine), доли .01, все наблюдаемые 2e−5. Для resource/hard полного уточнения нет: только диагностика.',
      'Baseline: среднее fine [190,200]. Hop-floor=max(1e−8,.05 PP_hop); F-floor=max(1e−8,.01 PP_F); QF-floor=max(1e−8,.01 QF_none). J0 имеет hop_undefined. Нулевой baseline RR_J0 не используется как нормированная эффективность.',
      'Стационарность baseline: ||Lρ||/||ρ||≤1e−6, Δρ/||ρ||≤1e−5, ΔF≤1e−10+1e−4|F| за10. Ledger residual≤1e−4+1e−5|QF|. trace/hermiticity≤1e−8, eigen≥−1e−7 на сетке10. Невосстановление, слабый baseline и отсутствие преимущества — разные исходы.',
      'metrics.json: все случаи, экстремумы, статистики, дискретные повреждения и pre/post-состояния наблюдаемых, численные сравнения, расходы и квалификаторы. CSV содержит все .2 recovery-отсчёты 31 величины; можно пересчитать Λ, ledger и ресурс. Pre/*.csv содержит все pre-window отсчёты тех же 31 величин для пересчёта baseline.',
      'Снимки rho: t0, 196…300 каждые2, плюс отдельно 200−. Ранние матрицы не сохранялись по плану; scalar-ряды полные. SHA и размеры: run.json и data_manifest.json. Ошибки обеих описей блокируют приёмку.',
      'Никаких выводов о квантовой необходимости, автопоэзисе, BIC. Гейтовые квалификаторы — кандидаты, не доказательство. Источник подпитки внешний. Порог 0.7 практический, не статистическая значимость. RR2 — чувствительность, не доказанная граница всех возможных RR.']
    if result['failure']:lines.append('Ошибка: '+str(result['failure']))
    text='\n'.join(lines)+'\n'
    if len(text.encode())>24576:raise ValueError('RESULT exceeds 24KiB')
    (report/'RESULT.md').write_text(text);(report/'README.md').write_text('# E002\n\n[Главный результат](RESULT.md).\n')
    sizes=[p.stat().st_size for p in report.rglob('*') if p.is_file()]
    if len(sizes)>500 or max(sizes,default=0)>8*1024**2 or sum(sizes)>30*1024**2:raise ValueError('Export budget exceeded')
    return dict(files=len(sizes),bytes=sum(sizes),result_bytes=len(text.encode()))
