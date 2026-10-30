"""Audited IC retry and its representative VM calibration/release probe."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import traceback
import numpy as np
import scipy
from e002_exp.model import save_json
from .engine import run_group, compare_pair
from .export import export_case, schema, manifest, digest
from .fitting import FIELDS, structural_target
from .retry_search import search
from .retry_verify import verify_report
from .ic_status import decide_ic_status
from .comparability import comparison_gate
from .task import ROOT, kernel_hash


def preflight(config):
    if config['mode'] not in ('ic_retry_calibration','ic_retry'):raise ValueError('Wrong mode')
    if os.environ.get('VM_SOURCE_DIR') and Path(os.environ['VM_SOURCE_DIR']).name!=config['run_id']:
        raise ValueError('Run identity differs from source directory')
    if not os.environ.get('VM_SOURCE_COMMIT',config.get('local_source_commit')):raise ValueError('Missing source SHA')
    if shutil.disk_usage('.').free<4.5*1024**3:raise ValueError('Need 4.5 GiB free')
    prov=json.loads((ROOT/'e002c_exp/provenance.json').read_text())
    for path,expected in prov['files'].items():
        if digest(ROOT/path)!=expected:raise ValueError('Pinned original source changed: '+path)
    if config['mode']=='ic_retry':
        cal=config['calibration']
        if cal['kernel_sha256']!=kernel_hash():raise ValueError('Code changed after retry calibration')
        if cal['numpy']!=np.__version__ or cal['scipy']!=scipy.__version__:raise ValueError('Library version changed')
        if cal['runtime_status']!='PASS' or cal['volume_pass'] is not True:raise ValueError('Unverified calibration')
        if len(cal['report_commit'])!=40:raise ValueError('Unpinned calibration')


def run(config,workdir=None):
    started=time.monotonic();workdir=Path.cwd() if workdir is None else Path(workdir)
    report=workdir/'report';full=workdir/'full'
    report.mkdir(parents=True,exist_ok=False);full.mkdir(parents=True,exist_ok=False)
    identity=dict(run_id=config['run_id'],source_commit=os.environ.get('VM_SOURCE_COMMIT',config.get('local_source_commit')))
    mode=config['mode'];summaries=[];exported=[];fit=validation=transport=release=None;fatal=None
    targets=json.loads((ROOT/'data/e002b_targets.json').read_text());target=structural_target(targets)
    t=targets['candidates']['QS']['edges'];seed=np.array([t[e]['loss']/(.5*t[e]['pR']) for e in ('01','12','02')])
    export_schema=None;pair=None
    def consume(cases,alpha,extend=False,publish=True):
        nonlocal export_schema
        begin=time.monotonic();rs=run_group(cases,full,alpha,extend=extend)
        group_seconds=time.monotonic()-begin
        for r in rs:
            summaries.append(r['summary'])
            if publish:
                export_case(report,r);exported.append(r['summary']['case']['id'])
                export_schema=schema(r['names'],r['dnames'])
        save_json(full/'retry_progress.json',dict(completed_trajectories=len(summaries),steps=sum(s['steps'] for s in summaries),
            elapsed_seconds=time.monotonic()-started,last_case=cases[-1]['id']))
        return rs,group_seconds
    try:
        preflight(config)
        if mode=='ic_retry_calibration':
            for index,(horizon,alpha) in enumerate([(20.,config['previous_alpha']),(20.,seed*4),(200.,config['previous_alpha'])]):
                case=dict(id=f'RETRY_CAL_{index+1}',model='IC1_QS',phi_over_pi=0.,detuning=0.,dephasing=.05,
                    dt=.02,horizon=horizon,family='retry_calibration')
                rs,elapsed=consume([case],alpha)
                rs[0]['summary']['measured_group_seconds']=elapsed
            from .lifetimes import measure
            release=measure(workdir.parent/'E002c_PROD_v001_r001'/'full',config['release_source_files'],report)
            save_json(report/'release.json',release)
        else:
            def evaluate(alpha,index):
                case=dict(id=f'RETRY_FIT_{index:03d}',model='IC1_QS',phi_over_pi=0.,detuning=0.,
                    dephasing=.05,dt=.02,horizon=200.,family='retry_fit')
                rs,elapsed=consume([case],alpha,publish=False);s=rs[0]['summary'];s['measured_group_seconds']=elapsed
                valid=s['failed'] is None and s['stationarity']['pass_gate'] and s['reference'] is not None
                return ([s['reference'][k] for k in FIELDS] if s['reference'] else [np.nan]*6,valid,
                    s['failed'] or (None if valid else 'not_stationary'))
            fit=search(evaluate,target,seed)
            if fit['selected']:
                selected=dict(alpha=fit['selected']['alpha'],selection=fit['selected'],source='IC-1 retry structural search; no hop objective')
                # Freeze exact bytes before validation and held-out transport.
                save_json(full/'selected_alpha.json',selected)
                shutil.copyfile(full/'selected_alpha.json',report/'selected_alpha.json')
                fit['selected_alpha_sha256']=digest(full/'selected_alpha.json')
                cases=[dict(id=f'RETRY_VALIDATE_{dt}',model='IC1_QS',phi_over_pi=0.,detuning=0.,
                    dephasing=.05,dt=dt,horizon=200.,family='retry_validation') for dt in (.01,.005)]
                vr,elapsed=consume(cases,selected['alpha'],extend=True);pair=compare_pair(*vr)
                for r in vr:r['summary']['refinement_status']='passed' if pair['pass_gate'] else 'failed'
                errors=[(abs(np.array([r['summary']['reference'][k] for k in FIELDS])-target)/target).tolist() for r in vr]
                passed=bool(max(np.max(x) for x in errors)<=.01 and pair['pass_gate'] and all(r['summary']['stationarity']['pass_gate'] and r['summary']['failed'] is None for r in vr))
                validation=dict(structural_pass=passed,relative_errors=errors,pair=pair,group_seconds=elapsed,
                    selected_alpha_sha256=fit['selected_alpha_sha256'])
                if passed:
                    src=config['baseline_source'];p=workdir.parent/src['run_id']/'report'/'metrics.json'
                    if digest(p)!=src['metrics_sha256']:raise ValueError('Pinned QS baseline changed')
                    bm=json.loads(p.read_text());qs=next(s for s in bm['cases'] if s['case']['id']=='QS_P05_dt005')
                    ic=vr[1]['summary'];comp=comparison_gate([qs,ic],pair['pass_gate'] and bm['numerical_valid'])
                    transport=dict(evaluable=comp['comparable'],comparison=comp,QS_case_id='QS_P05_dt005',IC_case_id=ic['case']['id'],baseline_source=src)
                    if transport['evaluable']:
                        q=qs['reference']['h'];h=ic['reference']['h']
                        transport.update(QS_h=q,IC_h=h,relative_error=abs(h-q)/max(abs(q),1e-8),denominator_QS=max(abs(q),1e-8))
            save_json(report/'fit_search.json',fit)
    except Exception as exc:
        fatal=dict(type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc());save_json(full/'failure.json',fatal)
    steps=sum(s['steps'] for s in summaries);expected_steps=sum(round(s['horizon']/s['case']['dt']) for s in summaries)
    volume=steps==expected_steps and all(s['failed'] is None and s['rhs_calls']==4*s['steps'] and
        s['scalar_records']==round(s['horizon']/.2)+1 and s['diagnostic_records']==round(s['horizon']/2)+1 for s in summaries)
    if mode=='ic_retry_calibration':volume &= steps==12000 and len(summaries)==3 and release is not None
    elif fit:volume &= len(summaries)==fit['computations']+(2 if fit['selected'] else 0)
    f=config['forecast']
    validation_steps=sum(s['steps'] for s in summaries if s['case']['family']=='retry_validation')
    if mode=='ic_retry':
        expected=f['fixed_seconds']+f['seconds_per_fit']*(fit['computations'] if fit else 0)+f['seconds_per_validation_step']*validation_steps
        delta=max(.4*expected,60.);lo=max(0.,expected-delta);hi=expected+delta
    else:expected=f['expected_seconds'];lo=f['lower_seconds'];hi=f['upper_seconds']
    failures=[] if fatal is None else [fatal['message']]
    if not volume:failures.append('work_volume_mismatch')
    checks=dict(failures=failures,volume_pass=bool(volume),runtime_gate=dict(expected_seconds=expected,lower_seconds=lo,upper_seconds=hi,
        actual_seconds=None,status='NOT_EVALUABLE',source=f,executed_branch=dict(fit_computations=fit['computations'] if fit else 0,validation_steps=validation_steps),
        measured_interval='Entry to report finalization; externally verify job.finished-job.started'))
    metrics=dict(identity=identity,mode=mode,kernel_sha256=kernel_hash(),environment=dict(numpy=np.__version__,scipy=scipy.__version__),
        target=target.tolist(),target_fields=list(FIELDS),seed=seed.tolist(),fit=fit,validation=validation,transport=transport,
        ic_status=decide_ic_status(fit,validation,transport),trajectory_summaries=summaries,exported_cases=exported,
        work=dict(trajectories=len(summaries),steps=steps,expected_steps=expected_steps,rhs_calls=sum(s['rhs_calls'] for s in summaries),
            scalar_records=sum(s['scalar_records'] for s in summaries),diagnostic_records=sum(s['diagnostic_records'] for s in summaries),
            snapshots=sum(s['snapshots'] for s in summaries)),release=release,fatal=fatal)
    save_json(report/'metrics.json',metrics)
    if export_schema:save_json(report/'schema.json',export_schema)
    (report/'README.md').write_text('IC-1 repeat search/calibration. Read RESULT.md, checks.json, metrics.json; full states remain on VM.\n')
    def write_result():
        rt=checks['runtime_gate']
        lines=[f"Время: прогноз {expected:.6f} с; диапазон {lo:.6f}–{hi:.6f} с; внутренний факт {rt['actual_seconds']}; статус {rt['status']}.",
            'Полный факт проверяется отдельно по run.json: job.finished − job.started; очередь и публикация отдельно.',
            f"Запуск {identity['run_id']}; код {identity['source_commit']}; kernel {metrics['kernel_sha256']}.",
            f"Объём: {len(summaries)} траекторий, {steps} шагов, {metrics['work']['rhs_calls']} RHS, {metrics['work']['scalar_records']} scalar, {metrics['work']['diagnostic_records']} diagnostic, {metrics['work']['snapshots']} snapshots.",
            f"Проверки: volume={volume}; failures={failures}.",
            f"IC-статусы: {metrics['ic_status']}. Шесть целей pL/ell, три alpha, никаких новых каналов; hop не входит в поиск."]
        if mode=='ic_retry_calibration':
            lines+=['Калибровка: две пробы T20 и одна T200, dt=.02. Стационарность коротких проб не является гейтом production.',
                '|Проба|Шаги|Полное время траектории, с|Стационарность|','|---|---:|---:|---|']
            lines += [f"|{s['case']['id']}|{s['steps']}|{s.get('measured_group_seconds')}|{s['stationarity']['pass_gate']}|" for s in summaries]
        if fit:
            lines += [f"Поиск: {fit['calls']} вызовов, {fit['computations']} вычислений, {fit['cache_hits']} попаданий кэша; максимум 141 вызов. Не доказательство глобальной невозможности IC-1.",
                '|Старт|Вызовы|Различных alpha01/12/02|Оптимизатор status/success|','|---|---:|---|---|']
            lines += [f"|{s['factor']}|{s['calls']}|{[c['distinct'] for c in s['coverage']]}|{s['optimizer']['status']}/{s['optimizer']['success']}|" for s in fit['starts']]
            if fit['selected']:lines += [f"Выбрано alpha={fit['selected']['alpha']}; max error={fit['selected']['maximum_error']}; SHA256={fit['selected_alpha_sha256']}."]
            if validation:lines += [f"Валидация: structural_pass={validation['structural_pass']}; шесть ошибок dt.01/.005={validation['relative_errors']}; dt pass={pair['pass_gate']}."]
            if transport:lines += [f"Held-out transport: {transport}."]
        if release:
            lines += ['', 'Время освобождения из изоляции: отдельная source-off проба, насос 0 вместо 0.5; остальные каналы без изменений.',
                'Это НЕ время пребывания при непрерывной накачке и НЕ первое время выхода из маски. Начальное условие — нормированный изолированный одночастичный блок сохранённого NESS t=200.',
                'tau_abs=интеграл вероятности выживания до бесконечности; tau_iso=накопленное время в любых изолированных компонентах с повторными входами.',
                '|Модель|Маска|Начальный вес|tau_abs|tau_iso|P(не вышло к 200)|P(не вышло к 400)|','|---|---:|---:|---:|---:|---:|---:|']
            for model in release['models']:
                lines += [f"|{model['model']}|{r['mask']}|{r['initial_weight']:.9g}|{r['mean_absorption_time']:.9g}|{r['accumulated_isolated_time']:.9g}|{r['survival_200']:.9g}|{r['survival_400']:.9g}|" for r in model['rows']]
                lines += [f"{model['model']}: сертификат {model['certificate']}; grid=0:2:400, 201 точка × 4 маски; min eig final={model['final_min_eigenvalue']}; max increase S={model['maximum_survival_increase']}; время={model['elapsed_seconds']:.6f} с."]
            lines += ['Изменение источника необходимо для однозначного отслеживания единственного возбуждения. Для исходного NESS утверждение о времени отдельного возбуждения этим контролем не доказано.',
                'Источник: results/E002c_PROD_v001_r001/full/{QS,RR_QS}_P05_dt005/final.npz; размеры и SHA256 сверены с data_manifest.json отчёта 7fd36d60044b436484e81a5e92a80163c4688b45. Полные состояния не экспортируются.',
                'Все 8 условных состояний и обе модели опубликованы. Ряды S(t) и изоляционного веса сохранены без прореживания в *_release.npz; сертификаты и хвосты в release.json.']
        lines += ['Подробности: metrics.json, checks.json, data_manifest.json. Исходные прогоны и их статусы не изменены.']
        formatted=[]
        for line in lines:
            if formatted and (line.startswith('|') != formatted[-1].startswith('|')):
                formatted.append('')
            formatted.append(line)
        body='\n'.join(formatted)+'\n'
        if len(body.encode())>24*1024:raise ValueError('Compact result too large')
        (report/'RESULT.md').write_text(body)
    save_json(report/'checks.json',checks);write_result();manifest(report,full)
    if not failures:checks['independent_report_checks']=verify_report(report)
    elapsed=time.monotonic()-started
    checks['runtime_gate'].update(actual_seconds=elapsed,actual_over_expected=elapsed/expected,
        status='PASS' if volume and lo<=elapsed<=hi else 'REVIEW_REQUIRED')
    save_json(report/'checks.json',checks);write_result();manifest(report,full)
    if failures:raise RuntimeError('; '.join(failures))
    verify_report(report)
    print(json.dumps(dict(identity=identity,checks=checks,work=metrics['work']),ensure_ascii=False))
