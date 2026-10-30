"""Read-only extraction of pre-existing E002c states; no dynamics imports."""
import hashlib
import io
import json
import os
from pathlib import Path
import resource
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def npz(data):
    with np.load(io.BytesIO(data), allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def complex_pairs(a):
    return np.stack([a.real, a.imag], axis=-1).tolist()


def reconstruct(blocks):
    b = blocks[:, 1:]
    p = np.trace(b, axis1=-2, axis2=-1).real
    require(np.all(p > 1e-6), 'Conditional weight floor reached')
    e12 = np.array([bool(m & 2) for m in range(8)])
    e02 = np.array([bool(m & 4) for m in range(8)])
    currents = -2 * np.stack([b[:, :, 1, 2].imag * e12,
                             b[:, :, 5, 6].imag * e12,
                             b[:, :, 1, 4].imag * e02,
                             b[:, :, 3, 6].imag * e02], axis=-1)
    h1 = currents[:, :, 0] + currents[:, :, 2]
    h2 = currents[:, :, 1] + currents[:, :, 3]
    diag = np.diagonal(b, axis1=-2, axis2=-1).real
    iso = np.zeros_like(p)
    iso[:, 0] = diag[:, 0, 2] + diag[:, 0, 4]
    iso[:, 1] = diag[:, 1, 2] + diag[:, 1, 4]
    iso[:, 2] = diag[:, 2, 4]
    iso[:, 4] = diag[:, 4, 2]
    inter = np.zeros_like(p)
    for m in (6, 7):
        inter[:, m] = .5 * (diag[:, m, 2] + diag[:, m, 4]) - b[:, m, 2, 4].real
    c = b[:, :, 2, 4]
    return dict(p=p, h=h1+h2, j=(h1+h2)/p, h_N1=h1, h_N2=h2,
                isolated_N1=iso, interference_N1=inter, C01=c, c01=c/p,
                current_components=currents)


def summarize(values, times):
    low, high = int(np.argmin(values)), int(np.argmax(values))
    return dict(minimum=float(values[low]), time_of_minimum=float(times[low]),
                maximum=float(values[high]), time_of_maximum=float(times[high]),
                range=float(np.ptp(values)), count=len(values))


def extract(config, results_root, destination, identity):
    schema = json.loads((ROOT/'window_schema.json').read_text())
    si = {n: i for i, n in enumerate(schema['series'])}
    di = {n: i for i, n in enumerate(schema['diagnostics'])}
    times = np.array(config['window'], float)
    weights = np.array(config['simpson_normalized_weights'], float)
    require(np.array_equal(times, np.arange(190., 201., 2.)), 'Unexpected window')
    require(abs(weights.sum()-1) < 1e-14, 'Invalid mean weights')
    destination.mkdir(parents=True, exist_ok=False)
    (destination/'windows').mkdir()
    source_files, checked_errors, models = [], {}, {}
    for source in config['sources']:
        label = source['label']
        base = results_root/source['run_id']/'full'/source['case_id']
        raw = {}
        for name in ('certificates.npz', 'series.npz', 'diagnostics.npz', 'model.json', 'summary.json'):
            path = base/name
            require(not path.is_symlink() and path.is_file(), f'Unsafe or absent input: {path}')
            require(path.resolve().is_relative_to(results_root.resolve()), 'Input escapes results')
            raw[name] = path.read_bytes()
            source_files.append(dict(path=str(path.relative_to(results_root.parent)),
                                     bytes=len(raw[name]), sha256=digest(raw[name])))
        require(digest(raw['certificates.npz']) == source['certificates_sha256'], 'Certificate hash mismatch')
        require(digest(raw['model.json']) == source['model_sha256'], 'Model hash mismatch')
        model = json.loads(raw['model.json']); case = model['case']; summary = json.loads(raw['summary.json'])
        require(case['id'] == source['case_id'] and float(case['dt']) == .005, 'Case identity/dt mismatch')
        require(float(case['phi_over_pi']) == 0 and float(case['detuning']) == 0 and
                float(case['dephasing']) == .05 and float(case['horizon']) == 200, 'Physics mismatch')
        require(summary['case']['id'] == case['id'] and summary['failed'] is None and
                summary['stationarity']['pass_gate'] is True, 'Original stationarity/failure gate')
        cert = npz(raw['certificates.npz'])
        scalar = npz(raw['series.npz'])['values']
        diagnostic = npz(raw['diagnostics.npz'])['values']
        require(np.array_equal(cert['time'], np.arange(0.,201.,2.)) and
                cert['blocks'].shape == (101,9,8,8), 'Certificate coverage mismatch')
        require(scalar.shape == (1001,len(si)) and diagnostic.shape == (101,len(di)), 'Full row counts mismatch')
        require(np.array_equal(diagnostic[:,0],cert['time']), 'Diagnostic time mismatch')
        require(np.allclose(scalar[:,0],np.arange(1001)*.2,atol=1e-10,rtol=0), 'Scalar time mismatch')
        take = np.flatnonzero(np.isin(cert['time'],times))
        st = np.flatnonzero(np.isin(scalar[:,0],times))
        require(len(take)==6 and len(st)==6, 'Missing required sample')
        blocks, series, diag = cert['blocks'][take], scalar[st], diagnostic[take]
        for name, array in [('blocks',blocks),('series',series),('diagnostics',diag)]:
            require(np.isfinite(array).all(), 'Nonfinite '+name)
            anchor = digest(np.ascontiguousarray(array[-1]).tobytes())
            require(anchor == source['github_T200_anchors'][name+'_T200'], 'Published T200 mismatch: '+name)
        frame = reconstruct(blocks)
        errors = {
            'mask_sum':float(np.max(abs(blocks[:,0]-blocks[:,1:].sum(axis=1)))),
            'trace':float(np.max(abs(np.trace(blocks[:,0],axis1=-2,axis2=-1)-1))),
            'hermiticity':float(np.max(abs(blocks-blocks.conj().swapaxes(-1,-2)))),
            'p_m':float(np.max(abs(frame['p']-series[:,[si[f'p_m{m}'] for m in range(8)]]))),
            'h_m':float(np.max(abs(frame['h']-(diag[:,[di[f'I12_m{m}'] for m in range(8)]]+
                                                     diag[:,[di[f'I02_m{m}'] for m in range(8)]])))),
            'h':float(np.max(abs(frame['h'].sum(axis=1)-series[:,si['h']]))),
            'isolated':float(np.max(abs(frame['isolated_N1']-diag[:,[di[f'd_isolated_m{m}'] for m in range(8)]]))),
            'interference':float(np.max(abs(frame['interference_N1']-diag[:,[di[f'd_interference_m{m}'] for m in range(8)]]))),
        }
        for m in (6,7):
            for tag in ('C01','c01'):
                original=diag[:,di[f'{tag}_m{m}_re']]+1j*diag[:,di[f'{tag}_m{m}_im']]
                errors[f'{tag}_m{m}']=float(np.max(abs(frame[tag][:,m]-original)))
        require(max(errors.values()) < 1e-10, 'Reconstruction disagreement')
        eig = float(np.linalg.eigvalsh(blocks).min())
        require(eig >= -1e-8, 'Nonpositive node block')
        checked_errors[label]=dict(errors=errors,minimum_eigenvalue=eig,original_stationarity=summary['stationarity'])
        means={key:np.tensordot(weights,value,axes=(0,0)) for key,value in frame.items()}
        pbar,hbar=means['p'],means['h']; jeff=hbar/pbar; ceff=means['C01']/pbar
        avg=dict(h=float(hbar.sum()),h_N1=float(means['h_N1'].sum()),h_N2=float(means['h_N2'].sum()),
                 isolated_N1=float(means['isolated_N1'].sum()),interference_N1=float(means['interference_N1'].sum()),
                 abs_c01_eff_m6=float(abs(ceff[6])),abs_c01_eff_m7=float(abs(ceff[7])))
        extrema={k:summarize(frame[k].sum(axis=1),times) for k in ('h','h_N1','h_N2','isolated_N1','interference_N1')}
        extrema.update({f'abs_c01_m{m}':summarize(abs(frame['c01'][:,m]),times) for m in (6,7)})
        masks=[]
        for m in range(8):
            masks.append(dict(mask=m,p=float(pbar[m]),h=float(hbar[m]),j_effective=float(jeff[m]),
                    mean_j=float(means['j'][m]),h_N1=float(means['h_N1'][m]),h_N2=float(means['h_N2'][m]),
                    isolated_N1=float(means['isolated_N1'][m]),interference_N1=float(means['interference_N1'][m]),
                    C01=complex_pairs(means['C01'][m]),c01_effective=complex_pairs(ceff[m]),
                    mean_c01=complex_pairs(means['c01'][m])))
        models[label]=dict(case=case,alpha=model['alpha'],means=avg,masks=masks,extrema=extrema,
                           max_abs_mean_j_minus_effective=float(np.max(abs(means['j']-jeff))))
        np.savez(destination/'windows'/f'{label}.npz',time=times,blocks=blocks,series=series,diagnostics=diag,**frame)
    comparisons={}
    for other in ('IC','RR'):
        a,b=models['QS'],models[other]
        gap=a['means']['h']-b['means']['h']; pop=cond=0.;rows=[]
        for x,y in zip(a['masks'],b['masks']):
            dp=(x['p']-y['p'])*(x['j_effective']+y['j_effective'])/2
            dj=(x['p']+y['p'])*(x['j_effective']-y['j_effective'])/2
            pop+=dp;cond+=dj;rows.append(dict(mask=x['mask'],population=dp,conditional_current=dj,gap=x['h']-y['h']))
        require(abs(gap-pop-cond)<1e-12,'Decomposition does not close')
        comparisons['QS-'+other]=dict(gap=gap,relative_gap=gap/a['means']['h'],population_share=pop/gap,
             conditional_current_share=cond/gap,N2_share=(a['means']['h_N2']-b['means']['h_N2'])/gap,
             mask_total_variation=sum(abs(x['p']-y['p']) for x,y in zip(a['masks'],b['masks']))/2,by_mask=rows)
    for item in source_files:
        require(digest((results_root.parent/item['path']).read_bytes())==item['sha256'],'Original input changed')
    budget=config['work_budget']
    work=dict(models=len(models),source_time_points_per_model=101,window_time_points_per_model=len(times),
              matrix_blocks=len(models)*len(times)*9,new_trajectories=0,integration_steps=0,rhs_calls=0)
    require(all(work[k]==budget[k] for k in work),'Work volume mismatch')
    return dict(identity=identity,mode='window_export',sources=config['sources'],source_files=source_files,
                source_schema=schema,window=times.tolist(),weights=weights.tolist(),models=models,
                comparisons=comparisons,verification=checked_errors,work=work,
                mean_definition='Simpson [190,200] on six even times; j_effective=<h_m>/<p_m>, separately export <j_m>; c01_effective=<C01>/<p_m>.',
                limits=['No new time evolution, intervention or causal identification.',
                        'Six-point window quadrature, not storage at every RK4 step.',
                        'N=1 dark weights; no N=2 dark-projector claim.',
                        'QS/RR full files come from original PROD; published repaired T200 anchors must match exactly.'])


def write_outputs(destination, metrics, checks):
    dump(destination/'metrics.json',metrics);dump(destination/'checks.json',checks)
    dump(destination/'schema.json',metrics['source_schema'])
    (destination/'README.md').write_text('Read RESULT.md. Existing archive window export; no new dynamics. Raw six-point blocks in windows/.\n')
    rt=checks['runtime_gate']
    lines=[f"Время: прогноз {rt['expected_seconds']:.3f} с; диапазон {rt['lower_seconds']:.3f}–{rt['upper_seconds']:.3f} с; внутренний факт {rt['actual_seconds']:.6f} с; статус внутреннего участка {rt['status']}.",
      'Полный факт и окончательный временной гейт проверяются отдельно по run.json: job.finished − job.started; очередь и публикация отдельно.',
      '',f"# E002c: дополнение окна [190,200] — {metrics['identity']['run_id']}",
      '',f"Исходный код: {metrics['identity']['source_commit']}. Дополнительный экспорт разрешён пользователем; обычный канал работы — GitHub, архив только по прямому указанию.",
      '', 'Повторной эволюции нет. Проверены три ранее сохранённых случая dt=0.005, phi=0, detuning=0, dephasing=0.05. Из certificates.npz выбраны 190,192,194,196,198,200: 18 временных записей и 162 узловые матрицы 8×8 (безусловная и восемь масок).',
      '', 'Ожидание до запуска: полное покрытие шести точек, точное совпадение T=200 с опубликованными GitHub-массивами и согласование токов/когерентностей между блоками, series и diagnostics. Сама операция не является причинным экспериментом.',
      '', '## Средние по окну', '', '| Величина | QS | IC retry | RR |','|---|---:|---:|---:|']
    for key,title in [('h','Hop-ток'),('h_N1','Ток N=1'),('h_N2','Ток N=2'),('isolated_N1','Изолированный тёмный вес N=1'),('interference_N1','Интерференционный тёмный вес N=1'),('abs_c01_eff_m6','Модуль эффективной c01, m6'),('abs_c01_eff_m7','Модуль эффективной c01, m7')]:
        lines.append('| '+title+' | '+' | '.join(f"{metrics['models'][m]['means'][key]:.10f}" for m in ('QS','IC','RR'))+' |')
    lines+=['','Simpson на шести точках. j_eff=<h_m>/<p_m>, c_eff=<C01>/<p_m>; средние самих условных j и c сохранены отдельно. Тёмные веса относятся к сектору N=1 и не перенормированы. Комплексные C01/c01 и четыре токовые когерентности доступны из всех сырых масочных блоков.',
            '', '## Зазоры', '', '| Пара | Δh/h_QS | Доля Δp | Доля Δj_eff | Доля N=2 |','|---|---:|---:|---:|---:|']
    for name,row in metrics['comparisons'].items():
        lines.append(f"| {name} | {100*row['relative_gap']:.6f}% | {100*row['population_share']:.6f}% | {100*row['conditional_current_share']:.6f}% | {100*row['N2_share']:.6f}% |")
    lines+=['','Отрицательная доля Δp означает компенсацию части зазора. Это алгебраическое разложение, не доказательство причинности или невозможности всего IC-1.',
            '', '## Динамика внутри окна', '', '| Модель | Наблюдаемая | Минимум (время) | Максимум (время) | Размах |','|---|---|---:|---:|---:|']
    for name,model in metrics['models'].items():
        for key,row in model['extrema'].items():
            lines.append(f"| {name} | {key} | {row['minimum']:.10g} ({row['time_of_minimum']:g}) | {row['maximum']:.10g} ({row['time_of_maximum']:g}) | {row['range']:.3e} |")
    maximum=max(max(v['errors'].values()) for v in metrics['verification'].values())
    minimum=min(v['minimum_eigenvalue'] for v in metrics['verification'].values())
    lines+=['','## Проверки и объём', '',f"План/факт: {metrics['work']}. Все 15 исходных файлов проверены на неизменность после чтения; certificates и model имеют заранее закреплённые хеши; T=200 совпал с закреплённым GitHub-экспортом побайтно.",
       f"Максимальная ошибка реконструкции {maximum:.3e} при допуске 1e-10; минимальное собственное значение узловых блоков {minimum:.3e} при границе -1e-8. Проверены след, эрмитовость, сумма масок, p_m, секторная сумма токов, тёмные веса и C01/c01. Исходные stationarity-гейты пройдены. failures={checks['failures']}.",
       f"Прочитано {sum(x['bytes'] for x in metrics['source_files'])} байт исходников; исходные файлы не менялись. Пиковая память процесса {metrics['peak_memory_mib']:.2f} MiB. Самостоятельные исходные выводы и статусы старых запусков не переписывались.",
       '', '## Границы вывода', '', 'Теперь секторные токи и когерентности можно сравнивать на общей шеститочечной сетке всего окна. Это закрывает ограничение прежнего сокращённого GitHub-экспорта. Матрицы на каждом шаге dt=0.005 не экспортируются; dt остаётся шагом интегратора. Полные 216×216 состояния здесь не требуются.',
       'Различие совместных состояний не отделено причинно от различий динамики каналов. Новый поиск IC-2 и причинная проба этим заданием не запускались.',
       '', '## Источники и файлы', '', 'QS/RR: сохранённые full-файлы E002c_PROD_v001_r001; якорь опубликованного исправленного отчёта E002c_REPAIR_v001_r001, 7fd36d60044b436484e81a5e92a80163c4688b45. IC: E002c_IC_RETRY_v001_r001, 3839e9229ef97c230479f024d055a8507ae86fa5. Все конкретные пути, хеши и параметры — metrics.json.',
       'Сырые данные: windows/QS.npz, windows/IC.npz, windows/RR.npz. Полные средние по маскам, экстремумы, проверки и источники: metrics.json, checks.json, schema.json. Числа в тексте округлены, NPZ/JSON сохраняют исходную точность.']
    text='\n'.join(lines)+'\n';require(len(text.encode())<=24*1024,'RESULT exceeds budget')
    (destination/'RESULT.md').write_text(text)
    files=[]
    for path in sorted(destination.rglob('*')):
        if path.is_file() and path.name!='data_manifest.json':
            data=path.read_bytes();files.append(dict(path=str(path.relative_to(destination)),bytes=len(data),sha256=digest(data)))
    dump(destination/'data_manifest.json',dict(version=1,exported=files,selection='All six window points and all nine node blocks for three models; omitted earlier times and unused certificate witnesses.'))


def run(config,workdir=None):
    started=time.monotonic()
    workdir=Path.cwd() if workdir is None else Path(workdir)
    require(config['mode']=='window_export','Wrong mode')
    require(workdir.name==config['run_id'],'Run/output identity mismatch')
    identity=dict(run_id=config['run_id'],source_commit=os.environ['VM_SOURCE_COMMIT'])
    destination=workdir/'report'
    try:
        metrics=extract(config,workdir.parent,destination,identity)
        metrics['peak_memory_mib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
        require(metrics['peak_memory_mib']<=config['work_budget']['peak_memory_budget_mib'],'Memory budget exceeded')
        rt=dict(config['forecast'],actual_seconds=0.,status='NOT_EVALUABLE',measured_interval='run() entry to checkpoint before final serialization; external process and final write checked separately')
        checks=dict(failures=[],volume_pass=True,inputs_unchanged=True,anchors_pass=True,runtime_gate=rt)
        write_outputs(destination,metrics,checks)
        elapsed=time.monotonic()-started
        rt.update(actual_seconds=elapsed,actual_over_expected=elapsed/rt['expected_seconds'],
                  status='PASS' if rt['lower_seconds']<=elapsed<=rt['upper_seconds'] else 'REVIEW_REQUIRED')
        write_outputs(destination,metrics,checks)
        require(sum(p.stat().st_size for p in destination.rglob('*') if p.is_file())<=config['work_budget']['report_max_bytes'],'Report byte budget exceeded')
        print(json.dumps(dict(status='WINDOW_EXPORT_COMPLETE',work=metrics['work'],internal_seconds=elapsed)),flush=True)
    except Exception as exc:
        destination.mkdir(parents=True,exist_ok=True)
        dump(destination/'failure.json',dict(identity=identity,error=repr(exc),new_trajectories=0))
        dump(destination/'checks.json',dict(failures=[repr(exc)],runtime_gate=dict(config['forecast'],status='NOT_EVALUABLE')))
        raise
