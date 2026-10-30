"""Bounded, immutable-source report repair. Does not import or execute dynamics."""
import copy
import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path

import numpy as np
import scipy

from .analysis import comparison_tables
from .export import array_spec, compact_result, MAX_BYTES
from .verify import verify
from .windows import integral_mean

ROOT = Path(__file__).resolve().parents[1]
FAILURE = 'independent_export_verification: Transition mean mismatch'
EXPECTED_CHANGED = {'RR_QS_P21_dt010','RR_QS_P22_dt010','RR_QS_P25_dt010','RR_QS_P26_dt010',
                    'RR_QS_P27_dt010','RR_QS_P28_dt010','RR_QS_P31_dt010','RR_QS_P32_dt010'}


def load(path):
    return json.loads(path.read_text())


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def refresh_manifest(report, original_manifest, source):
    """Retain the original full-data inventory with an explicit source location."""
    man = copy.deepcopy(original_manifest)
    exported = []
    for p in sorted(report.rglob('*')):
        if not p.is_file() or p.name == 'data_manifest.json':
            continue
        entry = dict(path=p.relative_to(report).as_posix(),bytes=p.stat().st_size,sha256=digest(p))
        if p.suffix == '.npz':
            entry['arrays'] = array_spec(p)
        exported.append(entry)
    man['exported'] = exported
    man['full_data_source'] = dict(run_id=source['run_id'],report_commit=source['report_commit'],
        directory='results/'+source['run_id']+'/full',accessed_for_repair=False,
        note='The inherited full inventory refers to the original run, not this repair job.')
    dump(report/'data_manifest.json',man)
    files = [p for p in report.rglob('*') if p.is_file()]
    if len(files)>500 or sum(p.stat().st_size for p in files)>MAX_BYTES or any(p.stat().st_size>8*1024**2 for p in files):
        raise ValueError('Repaired report exceeds original publication budgets')


def verify_original_volume(metrics, checks):
    cases=metrics['cases'];work=metrics['work'];fit=metrics['fit']
    assert len(cases)==74 and sum(s['case']['model'] in ('QS','RR_QS') for s in cases)==72
    assert fit['computations']==48 and fit['executed_steps']==480000
    assert work['steps']==work['expected_steps']==2300000
    assert sum(s['steps'] for s in cases)+fit['executed_steps']==work['steps']
    assert checks['work_volume_pass'] and not metrics['fatal']
    for s in cases:
        assert s['failed'] is None and s['steps']==round(s['horizon']/s['case']['dt'])
        assert s['rhs_calls']==4*s['steps'] and s['scalar_records']==round(s['horizon']/.2)+1
        assert s['diagnostic_records']==round(s['horizon']/2)+1
    for key in ('scalar_records','diagnostic_records','snapshots'):
        assert work[key]==sum(s[key] for s in cases)
    assert work['rhs_calls']==4*work['steps']


def rebuild(source_report, destination, source, identity, forecast):
    started=time.monotonic();source_report=Path(source_report);destination=Path(destination)
    expected={name[len('files/'):]:meta for name,meta in source['files'].items() if name.startswith('files/')}
    actual={p.relative_to(source_report).as_posix() for p in source_report.rglob('*') if p.is_file()}
    if actual != set(expected):
        raise ValueError('Source report inventory differs from pinned GitHub report')
    for name,meta in expected.items():
        p=Path(name)
        if p.is_absolute() or '..' in p.parts or (source_report/p).is_symlink():
            raise ValueError('Unsafe source path')
        if (source_report/p).stat().st_size!=meta['bytes'] or digest(source_report/p)!=meta['sha256']:
            raise ValueError('Source report SHA/size mismatch: '+name)
    original_metrics=load(source_report/'metrics.json');original_checks=load(source_report/'checks.json')
    if original_metrics['identity'] != dict(run_id=source['run_id'],source_commit=source['source_commit']):
        raise ValueError('Wrong original trajectory identity')
    if original_checks['failures'] != [FAILURE] or original_checks['export_complete'] is not False:
        raise ValueError('This repair only resolves the declared transition-window failure')
    verify_original_volume(original_metrics,original_checks)
    original_rt=original_checks['runtime_gate'];job=source['original_job']
    external=job['finished']-job['started']
    assert original_rt['lower_seconds']<=external<=original_rt['upper_seconds']
    trajectory_rt=dict(original_rt,actual_seconds=external,actual_over_expected=external/original_rt['expected_seconds'],
        deviation_seconds=external-original_rt['expected_seconds'],deviation_percent=100*(external/original_rt['expected_seconds']-1),
        status='PASS',queue_seconds=job['started']-job['created'],publication_seconds=None,
        measured_interval='Original external process: run.json job.finished - job.started')
    shutil.copytree(source_report,destination)  # refuses overwriting any previous output
    metrics=copy.deepcopy(original_metrics);checks=copy.deepcopy(original_checks)
    original_manifest=load(source_report/'data_manifest.json');names=load(source_report/'schema.json')['series'][1:]
    changes=[]
    for summary in metrics['cases']:
        cid=summary['case']['id']
        with np.load(destination/'series'/f'{cid}.npz',allow_pickle=False) as z:
            series=z['values']
        new=integral_mean(series,names,200.)
        if new is None:
            raise ValueError('Incomplete source [190,200] window: '+cid)
        old=summary['transition_reference']
        if not np.allclose([old[k] for k in names],[new[k] for k in names],atol=1e-10,rtol=1e-10):
            changes.append(dict(case=cid,horizon=summary['horizon'],old_h=old['h'],new_h=new['h'],
                maximum_absolute_change=max(abs(old[k]-new[k]) for k in names)))
        summary['transition_reference']=new
    if {x['case'] for x in changes} != EXPECTED_CHANGED:
        raise ValueError('Correction scope differs from the eight audited extended cases')
    metrics['transition_comparisons']=comparison_tables(metrics['cases'],metrics['numerical_valid'],
                                                       metrics['screening_threshold'],'transition_200')
    # Assert that correction cannot silently rewrite primary stationary conclusions.
    for key in ('gaps','phase','interactions','gap_phase','flux_spans','joint','fit','ic_validation','ic_transport','work'):
        assert metrics[key]==original_metrics[key],key
    for new,old in zip(metrics['cases'],original_metrics['cases']):
        assert {k:v for k,v in new.items() if k!='transition_reference'}=={k:v for k,v in old.items() if k!='transition_reference'}
    metrics['trajectory_identity']=metrics['identity'];metrics['identity']=identity
    metrics['mode']='repair_report'
    metrics['postprocessing_work']=dict(integration_steps=0,rhs_calls=0,new_trajectories=0,
        source_cases=len(metrics['cases']),corrected_windows=len(changes),full_states_read=0)
    metrics['postprocessing_environment']=dict(numpy=np.__version__,scipy=scipy.__version__)
    audit=dict(source=source,repair_identity=identity,changes=changes,
        resolved_failure=FAILURE,original_failure_preserved=True,
        source_report_files_verified=len(expected),unchanged_npz_files=sum(n.endswith('.npz') for n in expected),
        trajectory_runtime_gate=trajectory_rt,postprocessing_work=metrics['postprocessing_work'],
        scope='Only transition_reference and derived transition_comparisons change; primary references and all NPZ bytes remain unchanged.',
        limitations=['Original full-state and omitted-grid limitations remain.',
            'The rejected selected IC candidate does not exclude every IC parameterization.',
            'The 22.58% gap describes the baseline point, not all parameter points.'])
    # Source manifest is embedded in the pinned config; avoid duplicating it in report.
    audit['source']={k:v for k,v in source.items() if k not in ('files','original_job')}
    checks['original_failures']=original_checks['failures']
    checks['original_export_complete']=False
    checks['original_runtime_gate']=original_rt
    checks['trajectory_runtime_gate']=trajectory_rt
    checks['failures']=[];checks['export_complete']=True
    checks['summary']='REPAIRED_REPORT_CHECKS_PASSED'
    checks['runtime_gate']=dict(forecast,actual_seconds=None,status='NOT_EVALUABLE',
        executed_branch=metrics['postprocessing_work'],forecast_scope='VM_report_repair',
        measured_interval='Repair entry to final report rewrite; external process must be checked separately')
    dump(destination/'metrics.json',metrics)

    def write_outputs():
        dump(destination/'checks.json',checks);dump(destination/'repair_audit.json',audit)
        body=compact_result(metrics,checks).splitlines()
        intro=[
            f"Время исходного расчёта: прогноз {trajectory_rt['expected_seconds']:.6f} с; факт {external:.6f} с; "
            f"отклонение {trajectory_rt['deviation_percent']:+.4f}%; диапазон {trajectory_rt['lower_seconds']:.6f}–{trajectory_rt['upper_seconds']:.6f} с; PASS.",
            body[0].replace('Время:','Время пересборки:'),
            'Полное время пересборки и публикация проверяются отдельно по новому run.json; научная приёмка остаётся за пользователем.',
            '', 'Исправление отчёта без интегрирования: 0 новых траекторий, 0 RK4-шагов, 0 RHS; полные состояния не читались.',
            f"Исходный расчёт {source['run_id']}, код {source['source_commit']}; исходный отчёт {source['report_commit']} сохранён со статусом FAILED.",
            'Исправлены восемь средних [190,200] для T400 и зависимые переходные таблицы. Все исходные NPZ, конечные средние, стационарные таблицы и dt-проверки сохранены.',
            'IC: выбранный кандидат не прошёл структурную валидацию; перенос IC не выполнялся. Это не доказательство невозможности всего класса IC.',
            '22,58% — относительный зазор в базовой точке, а не единая величина всей сетки.',
            '', '|Исправленная траектория|Было h [неверное окно]|Стало h [190,200]|',
            '|---|---:|---:|']
        intro += [f"|{x['case']}|{x['old_h']:.10g}|{x['new_h']:.10g}|" for x in changes]
        (destination/'RESULT.md').write_text('\n'.join(intro+['']+body[2:])+'\n')
        refresh_manifest(destination,original_manifest,source)
    try:
        write_outputs()
        verified=verify(destination)
        for name,meta in expected.items():
            if name.endswith('.npz'):
                assert digest(destination/name)==meta['sha256'],name
        audit['independent_verifier']=verified
        elapsed=time.monotonic()-started
        rt=checks['runtime_gate'];rt.update(actual_seconds=elapsed,actual_over_expected=elapsed/forecast['expected_seconds'],
            status='PASS' if forecast['lower_seconds']<=elapsed<=forecast['upper_seconds'] else 'REVIEW_REQUIRED')
        write_outputs()
        verify(destination)  # verify final bytes, including final runtime/audit rewrite
        for name,meta in expected.items():
            assert digest(source_report/name)==meta['sha256'],'Original source changed: '+name
    except Exception as exc:
        checks['export_complete']=False;checks['summary']='FAILED'
        checks['failures']=[f'repaired_export_verification: {exc}']
        write_outputs()
        raise
    return dict(status='VERIFIED_EXPORTED_ARRAYS',elapsed_seconds=time.monotonic()-started,
                corrections=len(changes),new_steps=0,npz_unchanged=audit['unchanged_npz_files'])


def run(config,workdir=None):
    if config.get('mode')!='repair_report':
        raise ValueError('Expected explicit report-repair mode')
    workdir=Path.cwd() if workdir is None else Path(workdir)
    source=load(ROOT/'experiments/e002c/repair_v001_source.json')
    if not re.fullmatch(r'[A-Za-z0-9_-]+',source['run_id']):
        raise ValueError('Invalid source run')
    identity=dict(run_id=config['run_id'],source_commit=os.environ['VM_SOURCE_COMMIT'])
    if workdir.name!=identity['run_id']:
        raise ValueError('Output directory must match new run identity')
    if shutil.disk_usage(workdir).free<256*1024**2:
        raise ValueError('Insufficient report-repair disk space')
    result=rebuild(workdir.parent/source['run_id']/'report',workdir/'report',source,identity,config['forecast'])
    print(json.dumps(result),flush=True)
