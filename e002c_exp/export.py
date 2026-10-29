"""Lossless report export with explicit sampling limits and byte budgets."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
from e002_exp.model import save_json
from .diagnostics import FLOOR

MAX_BYTES=30*1024**2

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def scalar_keep(t):return (t<=10+1e-8)|np.isclose(t/2,np.round(t/2),atol=1e-9)
def diag_keep(t):return (t<=20+1e-8)|np.isclose(t/4,np.round(t/4),atol=1e-9)

def extrema(a):
    data=[]
    for j in range(1,a.shape[1]):
        valid=np.isfinite(a[:,j]);rows=np.flatnonzero(valid)
        if len(rows):
            lo=rows[np.argmin(a[valid,j])];hi=rows[np.argmax(a[valid,j])]
            data.append([float(a[lo,j]),float(a[lo,0]),float(a[hi,j]),float(a[hi,0]),len(rows)])
        else:data.append([None,None,None,None,0])
    return data

def evidence(result):
    c=result['certs'];t=result['diagnostics'][:,0];end=t[-1]
    fixed=np.array([i for i,x in enumerate(t) if x in {2.,20.,end}],dtype=int)
    out={'time':t[fixed]}
    for k in ('blocks','vectors','alpha','overlap','valid'):
        out[k]=c[k][fixed].astype(complex if k in ('blocks','vectors') else np.float64)
    ext=[]
    for s in range(9):
        valid=np.flatnonzero(c['valid'][:,s])
        if len(valid):
            w=np.min(c['alpha'][valid,s]-c['overlap'][valid,s],axis=1)
            ext.append(int(valid[np.argmin(w)]))
        else:ext.append(-1)
    out['extreme_time']=np.array([t[i] if i>=0 else np.nan for i in ext],dtype=float)
    for k in ('blocks','vectors','alpha','overlap','valid'):
        shape=c[k].shape[2:]
        out['extreme_'+k]=np.array([c[k][i,s] if i>=0 else np.zeros(shape,dtype=c[k].dtype)
                                  for s,i in enumerate(ext)],dtype=complex if k in ('blocks','vectors') else float)
    return out

def export_case(report,result):
    cid=result['summary']['case']['id']
    for d in ('series','diagnostics','evidence'):(report/d).mkdir(parents=True,exist_ok=True)
    a=result['series'];b=result['diagnostics']
    np.savez(report/'series'/f'{cid}.npz',values=a[scalar_keep(a[:,0])])
    np.savez(report/'diagnostics'/f'{cid}.npz',values=b[diag_keep(b[:,0])])
    np.savez(report/'evidence'/f'{cid}.npz',**evidence(result))
    if (report/'evidence'/f'{cid}.npz').stat().st_size>80*1024:raise ValueError('Evidence budget exceeded')
    return dict(scalar=extrema(a),diagnostic=extrema(b),
                h_t_positive=extrema(a[a[:,0]>0][:,[0,1+result['names'].index('h')]])[0] if len(a)>1 else None,
                h_start=float(a[0,1+result['names'].index('h')]),
                scalar_records=len(a),diagnostic_records=len(b))

def array_spec(path):
    with np.load(path,allow_pickle=False) as z:
        return {k:dict(dtype=str(z[k].dtype),shape=list(z[k].shape)) for k in z.files}

def manifest(report,full):
    exported=[];original=[]
    for root,out in ((report,exported),(full,original)):
        for p in sorted(root.rglob('*')):
            if not p.is_file() or p.name=='data_manifest.json':continue
            rec=dict(path=p.relative_to(root).as_posix(),bytes=p.stat().st_size,sha256=digest(p))
            if root==report and p.suffix=='.npz':rec['arrays']=array_spec(p)
            out.append(rec)
    fullbytes=sum(x['bytes'] for x in original)
    if fullbytes>3*1024**3:raise ValueError('Full data budget exceeded')
    save_json(report/'data_manifest.json',dict(version=1,exported=exported,full=original,
        full_bytes=fullbytes,selection='series 0:.2:10 then 12:2:T; diagnostics 0:2:20 then 24:4:T',
        limitations=['Full-state positivity and nodes|edges PT require full VM states.',
          'Extrema on omitted samples are reported, not independently recoverable from sparse grids.',
          'No full density matrix reconstruction from node reductions.']))
    files=[p for p in report.rglob('*') if p.is_file()]
    total=sum(p.stat().st_size for p in files)
    if total>MAX_BYTES or len(files)>500 or any(p.stat().st_size>8*1024**2 for p in files):
        raise ValueError(f'Export budget failed: {len(files)} files, {total} bytes')
    return dict(bytes=total,files=len(files),full_bytes=fullbytes)

def schema(names,dnames):
    return dict(version='e002c-1',series=['time']+names,diagnostics=['time']+dnames,
        mask_bits=['01','12','02'],node_basis='000,001,010,011,100,101,110,111',
        states=['unconditional']+[f'mask_{m}' for m in range(8)],
        evidence='unnormalized node blocks; vectors indexed state,template,node basis',
        null_policy='NaN only for conditional diagnostics with weight <=1e-6; valid_sN=0. JSON uses null.',
        fraction_rule='k_m/w1_m and d_m/w1_m only if w1_m>1e-6, otherwise null: weight_le_1e-6',
        reference_mean='Simpson integration on even times in last 10 units (six points); no sector renormalization.',
        extrema_columns=['minimum','time_of_minimum','maximum','time_of_maximum','finite_record_count'],
        full_scalar_dt=.2,full_diagnostic_dt=2.,probability_floor=FLOOR,
        scientific_limits=['FANO_CANDIDATE at most; no Fano proof from a dip.',
            'NPT on all cuts does not prove GME. Zero negativity does not prove separability.',
            'No damage operation. No automatic follow-on experiment.'])

def compact_result(metrics,checks):
    rt=checks['runtime_gate'];ident=metrics['identity']
    lines=[f"Время: прогноз {rt.get('expected_seconds')}; диапазон {rt.get('lower_seconds')}–{rt.get('upper_seconds')} с; "
           f"факт внутри задачи {rt.get('actual_seconds')} с; статус {rt['status']}.",
           'Полное время процесса и публикация проверяются отдельно по run.json. Научная приёмка при REVIEW_REQUIRED/NOT_EVALUABLE отложена.',
           '',f"E002c v001 | {ident['run_id']} | {ident['source_commit']} | режим {metrics['mode']}",
           '', 'Вопрос: достаточно ли IC-1 для структурного согласования и воспроизведения транспорта QS?',
           'Базис: 3 кубита × 3 qutrit, размер 216. J=1, g=.5, eta=.25, delta=.1, gamma_bg=.01, gamma_r=.05, source=sink=.5, edge dephasing=.05.',
           'Phi=theta01+theta12-theta02; theta02=-Phi. epsilon*n1; независимые sqrt(gamma)Z_i. Начало: равная смесь |100;RRR> и |010;RRR>.',
           'QS: Q=C/2, S=sqrt(I-Q). RR сохраняет когерентный hop. IC: только sqrt(alpha)Bplus*C, без H_form и обратного IC-скачка.',
           '',f"IC: {metrics.get('ic_status','not_run')}. Выбор по pL/ell; hop в цель подбора не входит.",
           f"Объём: {metrics['work']}. Операторный допуск 1e-10; физичность trace/hermiticity 1e-10, eigen >=-1e-8; dt: 1e-6+1e-4*scale.",
           f"Проверки: {checks.get('summary')}. Все провалы: {checks.get('failures',[])}.",
           '', '|Случай (Phi/pi;epsilon;gamma;dt)|T|h|F|min/max h (t>0)|tau90|стационарность|',
           '|---|---:|---:|---:|---|---:|---|']
    for s in metrics['cases']:
        ref=s['reference'] or {};x=s.get('h_extrema');hr='null' if x is None else f'{x[0]:.6g}@{x[1]:g} / {x[2]:.6g}@{x[3]:g}'
        lines.append(f"|{s['case']['id']} ({s['case']['phi_over_pi']:g};{s['case']['detuning']:g};{s['case']['dephasing']:g};{s['case']['dt']:g})|{s['horizon']:g}|{ref.get('h',float('nan')):.7g}|{ref.get('F',float('nan')):.7g}|{hr}|{s['tau90']}|{s['state_status']}|")
    joint=metrics.get('joint',[])
    certs=[(j['id'],g) for j in joint for g in j['GME'] if g['minimum'] is not None]
    if certs:
        cid,g=min(certs,key=lambda x:x[1]['minimum'])
        count=sum(g['status']=='GME_CERTIFIED' for _,g in certs)
        lines += ['',f"GME: сертифицировано {count} состояний/случаев; минимум witness {g['minimum']:.9g} ({cid}, состояние {g['state']}); численный порог {g['threshold']:.9g}."]
        pairmax=max((v for j in joint for v in j['pair_negativity_max'].values()),default=0.)
        lines.append(f'Максимальная парная negativity на полной диагностической сетке: {pairmax:.9g}.')
    for g in metrics.get('gaps',[]):
        if g['phi_over_pi']==0 and g['detuning']==0 and g['dephasing']==.05:
            lines.append(f"Базовая QS/{g['control']}: Delta h={g['delta_h']:.9g}; I12={g['I12_gap']:.9g}, I02={g['I02_gap']:.9g}; знаменатель QS={g['denominator_QS']:.9g}; относительный зазор={g['relative_gap']:.7g}.")
    if metrics.get('phase'):
        p=max(metrics['phase'],key=lambda x:abs(x['delta_h']))
        lines.append(f"Максимальный фазовый сдвиг h: {p['delta_h']:.9g} ({p['model']}; Phi/pi={p['phi_over_pi']}, epsilon={p['detuning']}, gamma={p['dephasing']}); {p['population_status']}, структурный сдвиг {p['structural_relative_max']:.7g}.")
    if metrics.get('interactions'):
        v=max(metrics['interactions'],key=lambda x:abs(x['value']))
        lines.append(f"Максимальное взаимодействие фаза×дефазировка в зазоре: {v['value']:.9g}; {v['control']}, epsilon={v['detuning']}, gamma={v['dephasing']}. Это не доказательство роли GME.")
    for s in metrics['cases']:
        c=s['case'];ref=s['reference']
        if ref and c['dt']==.005 and c['phi_over_pi']==0 and c['detuning']==0 and c['dephasing']==.05 and all(f'p_m{m}' in ref for m in range(8)):
            probs=', '.join(f"{ref[f'p_m{m}']:.6g}" for m in range(8))
            dark=sum(ref[f'd_m{m}'] for m in range(8));weight=sum(ref[f'w1_m{m}'] for m in range(8))
            lines.append(f"{c['model']}, базовая fine: веса масок 0…7=[{probs}]; суммарный тёмный вес={dark:.8g}, вес сектора одного возбуждения={weight:.8g}.")
    lines += ['', 'Идентификаторы P01…P32 соответствуют полной сетке в cases.csv; там даны Phi/pi, epsilon, gamma, dt и модель для каждой строки.',
              'Все сравнения QS/RR/IC, знаковые зазоры и знаменатели, фазовые разности и взаимодействия — в metrics.json.',
              'Публикуются GME-сертификаты и negativity тех же состояний. Нулевые свидетели не означают отсутствия GME; Bell×|0> не является GME.',
              'Тёмные веса относятся к секторному гамильтониану; они не доказывают устойчивости полной динамики. 59/41 не является разделением классики/кванта.',
              'Вне заранее уточнённых точек положительные выводы имеют статус SCREENING_SIGNAL. Корреляция тока и запутанности не доказывает необходимость запутанности.',
              'Скаляры full: шаг .2, диагностика full: шаг 2. Экспорт разрежен по schema.json; extrema.json рассчитан до разрежения. Значения в тексте округлены, NPZ lossless.',
              'Полные матрицы, остальные сертификаты и fit-ряды остаются full/. Опись, размеры, SHA256 и ограничения: data_manifest.json. Научная приёмка остаётся за пользователем.']
    result='\n'.join(lines)+'\n'
    if len(result.encode())>24*1024:raise ValueError('RESULT exceeds 24 KiB; no truncation allowed')
    return result
