"""Bounded scientific export; checkpoints and raw 0.2-step series stay on VM."""
import csv
import json
import math
from pathlib import Path
import numpy as np
from .model import sha, save_json


def load_optional(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def statistics(times, values):
    lo,hi=int(np.argmin(values)),int(np.argmax(values))
    return {'count':len(values),'mean':float(values.mean()),'stddev':float(values.std()),
            'min':float(values[lo]),'min_time':float(times[lo]),'max':float(values[hi]),
            'max_time':float(times[hi]),'first':float(values[0]),'last':float(values[-1]),
            'quantiles':{str(q):float(np.quantile(values,q)) for q in [.01,.25,.5,.75,.99]}}


def export_series(full, report, case_id, policy):
    schema=json.loads((full/'cases'/(case_id+'_schema.json')).read_text())
    names=schema['observable_names']
    samples=[json.loads(line) for line in (full/'cases'/(case_id+'.jsonl')).read_text().splitlines()]
    if not samples:raise ValueError('Empty recorded series: '+case_id)
    times=np.array([x['time'] for x in samples],dtype=float)
    values=np.array([x['values'] for x in samples],dtype=float)
    if values.shape!=(len(samples),len(names)) or not np.isfinite(values).all() or not np.isfinite(times).all() or np.any(np.diff(times)<=0):
        raise ValueError('Invalid recorded series: '+case_id)
    fmt=lambda value:format(float(value),policy['csv_float_format'])
    interval=policy['series_interval']
    selected=np.flatnonzero(abs(times/interval-np.rint(times/interval))<1e-8)
    selected=np.unique(np.r_[0,selected,len(times)-1])
    series_path=report/'series'/(case_id+'.csv');series_path.parent.mkdir(exist_ok=True)
    with series_path.open('w',newline='') as handle:
        writer=csv.writer(handle);writer.writerow(['time',*names])
        for i in selected:writer.writerow([fmt(times[i]),*(fmt(v) for v in values[i])])
    width=policy['extrema_bin_width']
    bins=max(1,int(math.ceil((times[-1]-times[0])/width)))
    ids=np.minimum(np.floor((times-times[0]+1e-8)/width).astype(int),bins-1)
    extrema_path=report/'extrema'/(case_id+'.csv');extrema_path.parent.mkdir(exist_ok=True)
    counts=[]
    with extrema_path.open('w',newline='') as handle:
        writer=csv.writer(handle)
        writer.writerow(['bin','time_first','time_last','count','observable','first','last','min','min_time','max','max_time','mean','stddev'])
        for group in range(bins):
            chosen=np.flatnonzero(ids==group)
            if not len(chosen):continue
            counts.append(len(chosen));ts,block=times[chosen],values[chosen]
            for column,name in enumerate(names):
                x=block[:,column]
                vals=[x[0],x[-1],x.min(),ts[int(np.argmin(x))],x.max(),ts[int(np.argmax(x))],x.mean(),x.std()]
                writer.writerow([group,fmt(ts[0]),fmt(ts[-1]),len(chosen),name,*(fmt(v) for v in vals)])
    stats={name:statistics(times,values[:,i]) for i,name in enumerate(names)}
    diagnostics=load_optional(full/'cases'/(case_id+'_diagnostics.json'),[])
    if diagnostics:
        folder=report/'diagnostics';folder.mkdir(exist_ok=True)
        keys=sorted(set().union(*(d.keys() for d in diagnostics)))
        with (folder/(case_id+'.csv')).open('w',newline='') as handle:
            writer=csv.DictWriter(handle,fieldnames=keys);writer.writeheader();writer.writerows(diagnostics)
    coverage={'case_id':case_id,'source_records':len(times),'published_series_records':len(selected),
              'observable_count':len(names),'time_first':float(times[0]),'time_last':float(times[-1]),
              'source_interval':0.2,'published_interval':interval,'extrema_bin_width':width,
              'extrema_bins':len(counts),'records_covered_by_extrema':sum(counts),
              'extrema_rows':len(counts)*len(names),'series_file':str(series_path.relative_to(report)),
              'extrema_file':str(extrema_path.relative_to(report)),
              'loss_of_detail':'Series omits intermediate 0.2-time samples; every original sample contributes to bin counts, extrema with times, mean and stddev. Ordering and correlations inside bins require full JSONL. Nothing is claimed between original records.'}
    if coverage['records_covered_by_extrema']!=len(times):raise RuntimeError('Extrema coverage mismatch')
    return stats,coverage,diagnostics


def write_report(job_root, config, metadata, *, failure=None):
    full,report=job_root/'full',job_root/'report';report.mkdir(exist_ok=True)
    raw=load_optional(full/'report.json',{})
    preflight=load_optional(full/'preflight_report.json',{})
    retention=load_optional(full/'retention_check.json',{})
    inputs=load_optional(full/'input_checks.json',[])
    checks=[{'name':'task_execution','category':'execution','expected_exit_code':0,
             'actual_exit_code':metadata['task_exit_code'],'passed':metadata['task_exit_code']==0},
            {'name':'preflight','category':'numerical','expected':True,'actual':preflight.get('passed',False),'passed':preflight.get('passed',False)}]
    if preflight:
        for group,rows in preflight['operator_checks'].items():
            checks.append({'name':'operators_'+group,'category':'numerical','actual_max_residual':max(rows.values()),
                           'tolerance':config['acceptance']['algebra'],'passed':max(rows.values())<=config['acceptance']['algebra'],'individual_residuals':rows})
        for name,row in preflight['cases'].items():
            checks.append({'name':'integration_'+name,'category':'numerical','actual':row,
                           'limits':{'rhs_relative_error':1e-6,**{k:config['acceptance'][k] for k in ['expm_reference_relative','refinement_observables']}},
                           'passed':row['rhs_relative_error']<=1e-6 and row['expm_relative_error']<=config['acceptance']['expm_reference_relative'] and row['dt_halving_max_observable_difference']<=config['acceptance']['refinement_observables']})
    summaries={case['case']['id']:case for case in raw.get('cases',[])}
    metrics,coverage={},[]
    for case in config['cases']:
        cid=case['id'];data={'status':'not_started','summary':summaries.get(cid)}
        if (full/'cases'/(cid+'.jsonl')).exists():
            stats,cov,diagnostics=export_series(full,report,cid,config['report_policy'])
            coverage.append(cov);data.update(status='completed' if cid in summaries else 'partial',statistics=stats,coverage=cov)
            checks.append({'name':'coverage_'+cid,'category':'report','actual':cov['records_covered_by_extrema'],
                           'expected':cov['source_records'],'passed':cov['records_covered_by_extrema']==cov['source_records']})
            if diagnostics:
                limits=config['acceptance']
                observed={'trace_max':max(x['trace_error'] for x in diagnostics),'hermiticity_max':max(x['hermiticity_error'] for x in diagnostics),
                          'minimum_eigenvalue':min(x['min_eigenvalue'] for x in diagnostics if 'min_eigenvalue' in x),'all_finite':all(x['finite'] for x in diagnostics)}
                checks.append({'name':'state_quality_'+cid,'category':'numerical','actual':observed,
                               'limits':{k:limits[k] for k in ['trace','hermiticity','positivity']},
                               'passed':observed['all_finite'] and observed['trace_max']<=limits['trace'] and observed['hermiticity_max']<=limits['hermiticity'] and observed['minimum_eigenvalue']>=-limits['positivity']})
        if cid in summaries:
            checks.append({'name':'stationarity_'+cid,'category':'scientific','actual':summaries[cid]['stationarity'],
                           'limits':config['stationarity'],'passed':summaries[cid]['stationarity']['passed']})
        metrics[cid]=data
    if metadata['mode']=='continuation':checks.append({'name':'snapshot_retention','category':'retention','actual':retention,'passed':retention.get('passed',False)})
    numerical_ok=bool(preflight.get('passed',False)) and all(c['passed'] for c in checks if c['category']=='numerical')
    save_json(report/'metrics.json',{'run_id':metadata['run_id'],'source_commit':metadata['source_commit'],
        'experiment':config['experiment_id'],'mode':metadata['mode'],'task_exit_code':metadata['task_exit_code'],'failure':failure,
        'numerical_checks_passed':numerical_ok,'all_stationarity_passed':raw.get('all_stationarity_passed'),'cases':metrics,
        'preflight':preflight,'retention':retention,'forecasts_not_acceptance_criteria':config['forecasts_not_acceptance_criteria'],
        'interpretation_limits':config['interpretation_limits']})
    save_json(report/'checks.json',checks)
    inventory=[]
    for path in sorted(full.rglob('*')):
        if path.is_symlink():raise RuntimeError('Full-data symlink is unsupported')
        if path.is_file():
            name=path.relative_to(full).as_posix()
            item={'vm_path':f'results/{metadata["run_id"]}/full/{name}','bytes':path.stat().st_size,'sha256':sha(path),'format':path.suffix.lstrip('.')}
            if path.suffix=='.npz':item['arrays']={'rho':{'shape':[216,216],'dtype':'complex128'},'time':'float64','step':'integer','case_json':'JSON string'}
            inventory.append(item)
    save_json(report/'data_manifest.json',{'run_id':metadata['run_id'],'source_commit':metadata['source_commit'],
        'input_files':inputs,'expected_input_files':config['cases'],'full_files':inventory,'full_file_count':len(inventory),
        'full_bytes':sum(x['bytes'] for x in inventory),'coverage':coverage,
        'selection':{'method':'All observables every model time unit; all recorded 0.2 samples contribute to 10-unit extrema/statistics bins and whole-series statistics.',
                     'float_encoding':config['report_policy']['csv_float_format'],'density_matrices_published':False,
                     'full_data_access':'Separate explicit user instruction required.',
                     'dense_step_history':'Integration dt=0.01; scalar records each 0.2 and full rho each 1. Values between stored records are not retained.'},
        'report_partial':failure is not None,'report_policy':config['report_policy']})
    rows=['| Траектория | Последнее t | Стационарность | Поток F | ΔF/F смеси T100 | Прогноз «пройти к T500» |','|---|---:|---|---:|---:|---|']
    for cid,data in metrics.items():
        summary=data['summary']
        if summary:
            flow=format(summary['final_observables']['sink_flux'],'.12g')
            delta=format(summary['mixture_T100_flux_relative_difference'],'.6g')
            prediction=next(("подтверждён" if x['passed'] else "не подтверждён" for x in summary['endpoint_tests'] if abs(x['window_end']-500)<1e-8),'не проверен')
        else:flow=delta=prediction='—'
        rows.append(f'| {cid} | {summary["final_time"] if summary else "—"} | {("PASS" if summary["stationarity"]["passed"] else "FAIL") if summary else data["status"]} | {flow} | {delta} | {prediction} |')
    if failure:answer='Расчёт завершился ошибкой. Успешный расчёт не подтверждён. '+failure['type']+': '+failure['message']
    elif metadata['mode']=='preflight':answer='Техническая проверка пройдена. Продолжение до T=500/1000 не выполнялось.'
    else:answer='Продолжение выполнено. '+('Все траектории прошли заданные численные критерии.' if raw.get('all_stationarity_passed') else 'Есть непройденные критерии; результаты сохранены как конечновременные.')
    reference='https://github.com/IgorSabirov/vm-lab/tree/'+metadata['source_commit']
    text=(f'# E001X CONT: отчёт\n\nЗапуск: `{metadata["run_id"]}`. [Исходный коммит]({reference}).\n\n'
          'Вопрос: проходят ли четыре ранее непройденные фазовые траектории прежний критерий стационарности при T=500, либо после продления до T=1000?\n\n'
          f'**Фактический ответ:** {answer}\n\n'+'\n'.join(rows)+'\n\n'
          'Ожидание до запуска: пройти к T=500; это прогноз, а не критерий правильности интегратора. Конечные времена и все провалы указаны в metrics.json и checks.json.\n\n'
          'series/ содержит все 164 наблюдаемые с шагом 1; extrema/ сохраняет число записей, экстремумы с временами, средние и разброс по всем исходным отсчётам с шагом 0.2. Полные ряды и матрицы остаются на ВМ; размеры, форматы, хеши и потери детализации указаны в data_manifest.json.\n\n'
          'Сравнение со смесью использует сохранённый ориентир T=100. PP и PQ здесь не продолжаются: общий стационарный ранжир четырёх вариантов этим прогоном не доказывается. Конечное окно не доказывает единственность стационара.\n\n'
          'B_L + M_L + E_L = pL проверяется как тождество. Токи hop/form/idle относятся к переносу возбуждений; formation_current — отдельный ток конверсии R↔L. Интегральные вклады имеют знак.\n\n'
          'Код завершения и полнота экспорта проверяются по родительскому run.json. Окончательную приёмку выполняет пользователь.\n')
    (report/'README.md').write_text(text)
    sizes=[p.stat().st_size for p in report.rglob('*') if p.is_file()];policy=config['report_policy']
    if len(sizes)>policy['max_files'] or max(sizes,default=0)>policy['max_file_bytes'] or sum(sizes)>policy['max_total_bytes']:
        raise RuntimeError('Declared report budget exceeded; files retained, export must not be accepted as complete')
    return {'files':len(sizes),'bytes':sum(sizes),'max_file_bytes':max(sizes,default=0),'task_succeeded':metadata['task_exit_code']==0}
