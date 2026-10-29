"""VM entry point. Calibration and production are separate pinned jobs."""
import csv
import hashlib
import json
import os
import platform
import shutil
import sys
import time
import traceback
from pathlib import Path
import numpy as np
import scipy
from e002_exp.model import save_json
from . import fitting
from .engine import run_group,compare_pair
from .export import export_case,schema,manifest,compact_result
from .analysis import summarize
from .ic_status import decide_ic_status
from .comparability import comparison_gate

ROOT=Path(__file__).resolve().parents[1]

def kernel_hash():
    paths=[ROOT/'e002_exp/model.py', ROOT/'data/e002b_targets.json', ROOT/'experiments/e002c/plan.json', ROOT/'experiments/e002c/calibration_v002.json', ROOT/'e002c_exp/provenance.json', *sorted((ROOT/'e002c_exp').glob('*.py'))]
    h=hashlib.sha256()
    for p in paths:h.update(p.relative_to(ROOT).as_posix().encode()+b'\0'+p.read_bytes())
    return h.hexdigest()

def calibration_cases():
    return json.loads((ROOT/'experiments/e002c/calibration_v002.json').read_text())['cases']

def preflight(config,identity,free_bytes=None):
    mode=config.get('mode')
    prov=json.loads((ROOT/'e002c_exp/provenance.json').read_text())
    for path,expected in prov['files'].items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest()!=expected:raise ValueError('Pinned source changed: '+path)
    if os.environ.get('VM_SOURCE_DIR') and Path(os.environ['VM_SOURCE_DIR']).name!=config.get('run_id'):
        raise ValueError('Config run_id differs from VM source directory')
    if mode not in ('calibration','production','smoke'):raise ValueError('Unknown mode')
    if not config.get('run_id') or not identity.get('source_commit'):raise ValueError('Missing run identity')
    forecast=config.get('forecast',{})
    if mode=='calibration':
        calibration_plan=json.loads((ROOT/'experiments/e002c/calibration_v002.json').read_text())
        if len(calibration_plan['cases'])!=12 or sum(round(c['horizon']/c['dt']) for c in calibration_plan['cases'])!=25000:
            raise ValueError('Invalid calibration workload')
        if forecast!=calibration_plan['forecast']:
            raise ValueError('Calibration forecast must match protocol')
    elif mode=='production':
        cal=config.get('calibration',{})
        required=('report_commit','source_commit','kernel_sha256','scipy_version','numpy_version','accepted_by_user')
        if any(k not in cal for k in required) or cal['accepted_by_user'] is not True:
            raise ValueError('Missing accepted VM calibration')
        if cal['kernel_sha256']!=kernel_hash():raise ValueError('Kernel changed after calibration')
        if cal['scipy_version']!=scipy.__version__ or cal['numpy_version']!=np.__version__:
            raise ValueError('Numerical library version changed after calibration')
        if any(len(cal[k])!=40 for k in ('report_commit','source_commit')):raise ValueError('Unpinned calibration')
        if not all(k in forecast for k in ('seconds_per_step','fixed_seconds','relative_band','source')):
            raise ValueError('Missing calibrated runtime formula')
        if forecast['seconds_per_step']<=0 or forecast['fixed_seconds']<0 or forecast['relative_band']!=.4:
            raise ValueError('Invalid frozen runtime formula')
    if mode!='smoke':
        free=shutil.disk_usage('.').free if free_bytes is None else free_bytes
        if free<4.5*1024**3:raise ValueError('Need at least 4.5 GiB free before job')
    return True

def grouped(cases):
    groups={}
    for c in cases:
        key=(c['model'],c['phi_over_pi'],c['detuning'],c['dephasing'])
        groups.setdefault(key,[]).append(c)
    return list(groups.values())

def run(config,workdir=None):
    started=time.monotonic();workdir=Path.cwd() if workdir is None else Path(workdir)
    report=workdir/'report';full=workdir/'full'
    # Never overwrite an old run or silently mix partial results.
    report.mkdir(parents=True,exist_ok=False);full.mkdir(parents=True,exist_ok=False)
    identity=dict(run_id=config.get('run_id'),source_commit=os.environ.get('VM_SOURCE_COMMIT',config.get('local_source_commit')))
    results=[];pair_checks={};fit=None;validation=None;transport=None;fatal=None
    mode=config.get('mode');export_extrema={};all_summaries=[]
    try:
        preflight(config,identity)
        plan=json.loads((ROOT/'experiments/e002c/plan.json').read_text())
        if len(plan['cases'])!=72 or sum(c['main_steps'] for c in plan['cases'])!=1600000:
            raise ValueError('Machine plan changed unexpectedly')
        def consume(cases,alpha=None,extend=True):
            group=run_group(cases,full,alpha,extend,disk_floor=0 if mode=='smoke' else 1.5*1024**3)
            if len(group)==2:
                pair_checks[cases[0]['id']]=compare_pair(*group)
                for r in group:r['summary']['refinement_status']='passed' if pair_checks[cases[0]['id']]['pass_gate'] else 'failed'
            for r in group:
                export_extrema[r['summary']['case']['id']]=export_case(report,r)
                r['summary']['h_extrema']=export_extrema[r['summary']['case']['id']]['h_t_positive']
                all_summaries.append(r['summary'])
            results.extend(group)
            return group
        if mode=='calibration':
            for c in calibration_cases():consume([c],c.get('alpha'),extend=False)
        elif mode=='smoke':
            for model in ('QS','RR_QS','IC1_QS'):
                cases=[dict(id=f'SMOKE_{model}_{dt}',model=model,phi_over_pi=.5,detuning=.5,
                            dephasing=.25,dt=dt,horizon=2.,family='smoke') for dt in (.01,.005)]
                consume(cases,[.1]*3 if model=='IC1_QS' else None,extend=False)
        else:
            targets=json.loads((ROOT/'data/e002b_targets.json').read_text())
            fit=fitting.perform(full,targets)
            if fit['selected'] is not None:
                alpha=fit['selected']['alpha']
                cases=[dict(id=f'IC_VALIDATE_{dt}',model='IC1_QS',phi_over_pi=0.,detuning=0.,
                    dephasing=.05,dt=dt,horizon=200.,family='validation') for dt in (.01,.005)]
                vr=consume(cases,alpha)
                errors=[]
                for r in vr:
                    ref=r['summary']['reference']
                    if ref is not None:
                        errors.append(np.abs(np.array([ref[k] for k in fitting.FIELDS])-fitting.structural_target(targets))/fitting.structural_target(targets))
                good=len(errors)==2 and max(np.max(x) for x in errors)<=.01 and pair_checks[cases[0]['id']]['pass_gate'] and all(r['summary']['stationarity']['pass_gate'] and r['summary']['failed'] is None for r in vr)
                validation=dict(structural_pass=bool(good),relative_errors=[x.tolist() for x in errors],
                    selected_alpha_sha256=fit['selected_alpha_sha256'])
            for group in grouped(plan['cases']):consume(group)
            if validation and validation['structural_pass']:
                for group in grouped(plan['conditional_ic_cases']):consume(group,fit['selected']['alpha'])
                qs=next(r for r in results if r['summary']['case']['model']=='QS' and r['summary']['case']['phi_over_pi']==0 and r['summary']['case']['detuning']==0 and r['summary']['case']['dephasing']==.05 and r['summary']['case']['dt']==.005)
                ic=vr[1]
                qs_coarse=next(r for r in results if r['summary']['case']['model']=='QS' and r['summary']['case']['phi_over_pi']==0 and r['summary']['case']['detuning']==0 and r['summary']['case']['dephasing']==.05 and r['summary']['case']['dt']==.01)
                qs_numerical=pair_checks[qs_coarse['summary']['case']['id']]['pass_gate']
                comparison=comparison_gate([qs['summary'],ic['summary']],qs_numerical)
                transport=dict(evaluable=comparison['comparable'],comparison=comparison,
                               QS_case_id=qs['summary']['case']['id'],IC_case_id=ic['summary']['case']['id'])
                if transport['evaluable']:
                    q=qs['summary']['reference']['h'];h=ic['summary']['reference']['h'];err=abs(h-q)/max(abs(q),1e-8)
                    transport.update(QS_h=q,IC_h=h,relative_error=err,denominator_QS=max(abs(q),1e-8))
    except Exception as e:
        fatal=dict(type=type(e).__name__,message=str(e),traceback=traceback.format_exc())
        save_json(full/'failure.json',fatal)
    ic_statuses=decide_ic_status(fit,validation,transport)
    metrics=summarize(results,pair_checks,mode) if results else dict(cases=[],joint=[],gaps=[],phase=[],interactions=[])
    steps=sum(s['steps'] for s in all_summaries)+(fit['executed_steps'] if fit else 0)
    expected_steps=sum(round(s['horizon']/s['case']['dt']) for s in all_summaries)+(10000*fit['computations'] if fit else 0)
    if mode=='calibration':expected_steps=sum(round(c['horizon']/c['dt']) for c in calibration_cases())
    failures=[]
    if fatal:failures.append(fatal['message'])
    failures.extend(k+':dt_pair_failed' for k,p in pair_checks.items() if not p['pass_gate'])
    failures.extend(s['case']['id']+':'+s['failed'] for s in all_summaries if s['failed'])
    volume=(steps==expected_steps and all(s['rhs_calls']==4*s['steps'] and s['scalar_records']==round(s['horizon']/.2)+1 and s['diagnostic_records']==int(np.floor(s['horizon']/2+1e-9))+1 for s in all_summaries))
    if mode=='production':volume &= sum(s['case']['model'] in ('QS','RR_QS') for s in all_summaries)==72
    if not volume:failures.append('work_volume_mismatch')
    f=config.get('forecast',{});actual=time.monotonic()-started
    if mode=='production' and 'seconds_per_step' in f:
        expected=f['fixed_seconds']+f['seconds_per_step']*expected_steps;lo=.6*expected;hi=1.4*expected
    else:expected=f.get('expected_seconds');lo=f.get('lower_seconds');hi=f.get('upper_seconds')
    status='NOT_EVALUABLE' if expected is None or mode=='smoke' or not os.environ.get('VM_SOURCE_COMMIT') else ('PASS' if lo<=actual<=hi and volume and not fatal else 'REVIEW_REQUIRED')
    runtime=dict(forecast_scope='VM',execution_scope='VM' if os.environ.get('VM_SOURCE_COMMIT') else 'local_test',expected_seconds=expected,lower_seconds=lo,upper_seconds=hi,actual_seconds=actual,
        actual_over_expected=actual/expected if expected else None,status=status,
        calibration_reference=config.get('calibration',{'status':'provisional_calibration'}),
        executed_branch=dict(mode=mode,**ic_statuses,steps=expected_steps),
        measured_interval='task entry to before final report assembly; external process time must be checked in run.json')
    metrics.update(identity=identity,mode=mode,**ic_statuses,fit=fit,ic_validation=validation,ic_transport=transport,
        work=dict(trajectories=len(all_summaries),fit_trajectories=fit['computations'] if fit else 0,
                  steps=steps,expected_steps=expected_steps,rhs_calls=4*steps,
                  scalar_records=sum(s['scalar_records'] for s in all_summaries),
                  diagnostic_records=sum(s['diagnostic_records'] for s in all_summaries),
                  snapshots=sum(s['snapshots'] for s in all_summaries)),
        environment=dict(python=sys.version,numpy=np.__version__,scipy=scipy.__version__,platform=platform.platform(),
                         threads={k:os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')},
                         kernel_sha256=kernel_hash()),fatal=fatal)
    checks=dict(runtime_gate=runtime,work_volume_pass=bool(volume),pairs=pair_checks,failures=failures,
                summary='FAILED' if failures else 'COMPLETED_CHECKS_NO_TECHNICAL_FAILURE',
                scientific_acceptance='USER_REVIEW_REQUIRED',export_complete=False)
    if results:save_json(report/'schema.json',schema(results[0]['names'],results[0]['dnames']))
    if (full/'selected_alpha.json').exists():
        (report/'selected_alpha.json').write_bytes((full/'selected_alpha.json').read_bytes())
    save_json(report/'extrema.json',export_extrema)
    save_json(report/'metrics.json',metrics)
    with (report/'cases.csv').open('w',newline='') as out:
        fields=['id','model','phi_over_pi','detuning','dephasing','dt','horizon','family'];w=csv.DictWriter(out,fields,extrasaction='ignore');w.writeheader()
        for s in all_summaries:w.writerow(dict(s['case'],horizon=s['horizon']))
    checks['export_complete']=fatal is None
    save_json(report/'checks.json',checks)
    (report/'RESULT.md').write_text(compact_result(metrics,checks),encoding='utf-8')
    (report/'README.md').write_text('E002c: see RESULT.md for time-first review, schema.json for arrays and data_manifest.json for hashes.\n',encoding='utf-8')
    budget=manifest(report,full)
    # Independent exporter verification is a prerequisite to successful completion.
    if not fatal:
        from .verify import verify
        try:verify(report)
        except Exception as e:
            checks['export_complete']=False
            checks['failures'].append('independent_export_verification: '+str(e))
            checks['summary']='FAILED'
            save_json(report/'checks.json',checks)
            (report/'RESULT.md').write_text(compact_result(metrics,checks),encoding='utf-8')
            manifest(report,full)
            raise
    print(json.dumps(dict(status=status,work=metrics['work'],report=budget,fatal=fatal is not None),ensure_ascii=False),flush=True)
    if fatal:raise RuntimeError(fatal['message'])
    return metrics,checks

if __name__=='__main__':
    run(json.loads((ROOT/'config.json').read_text()))
