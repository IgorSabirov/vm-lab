"""Stage A only. Stage B cannot be triggered by this executable."""
import json
import os
import re
import shutil
import time
import traceback
from pathlib import Path
import numpy as np
import scipy
from e002_exp.model import measurement_model,save_json,sha,maxabs
from j0_exp.engine import Progress,preflight
from .engine import prepare
from .matching import derive_rates
from .report import prepare_report,finalize


def validate_config(cfg,targets):
    if cfg['stage']!='feasibility_only' or cfg['damage_plan']['allow_automatic_launch']:
        raise ValueError('This entrypoint cannot launch damage')
    if cfg['candidates']!=['QS','QQ'] or set(cfg['models'])!={'QS','QQ','RR_QS','RR_QQ'}:
        raise ValueError('Changed fixed model set')
    ids=[c['id'] for c in cfg['cases']]
    expected={m+'_'+q for m in cfg['models'] for q in ['coarse','fine']}
    if len(ids)!=len(set(ids)) or set(ids)!=expected:raise ValueError('Missing/duplicate cases')
    for c in cfg['cases']:
        if c['id']!=c['model']+('_coarse' if c['dt']==.01 else '_fine' if c['dt']==.005 else ''):
            raise ValueError('Wrong step/refinement label')
    if cfg['mode'] not in {'production','test'}:raise ValueError('Invalid mode')
    if cfg['mode']=='production' and cfg['horizon']!=200:raise ValueError('Production horizon changed')
    if cfg['baseline_window']!=10 or cfg['horizon']<12:raise ValueError('Invalid stationary window')
    for value in [cfg['horizon'],cfg['baseline_window'],cfg['diagnostic_interval'],cfg['positivity_interval']]:
        for dt in [.01,.005,cfg['observable_interval']]:
            if abs(value/dt-round(value/dt))>1e-8:raise ValueError('Incompatible grid')
    count=sum(round(cfg['horizon']/c['dt']) for c in cfg['cases'])
    if count!=cfg['runtime_forecast']['main_steps']:raise ValueError('Wrong step forecast')
    for name in cfg['candidates']:
        p=cfg['models'][name];rr=cfg['models']['RR_'+name]
        if p!=targets['candidates'][name]['parameters']:raise ValueError('Candidate changed')
        expected_rates=derive_rates(targets['candidates'][name],p)
        if any(not np.allclose(rr['rr_rates'][e],r,rtol=1e-13,atol=1e-15) for e,r in expected_rates.items()):
            raise ValueError('RR calibration changed')
        if rr!={**p,'g':0.,'gamma_r':0.,'gate_idle':'Q','rr_rates':rr['rr_rates']}:
            raise ValueError('RR must preserve all external coefficients')


def execute(cfg,source,entry):
    root=Path.cwd();run=os.environ.get('VM_JOB_ID','');commit=os.environ.get('VM_SOURCE_COMMIT','')
    if not re.fullmatch('[A-Za-z0-9_-]{12,64}',run) or not re.fullmatch('[a-f0-9]{40}',commit):
        raise ValueError('Missing pinned run identity')
    if shutil.disk_usage(root).free<cfg['required_free_disk_bytes']:raise ValueError('Insufficient disk reserve')
    full=root/'full';full.mkdir(exist_ok=False)
    meta=dict(run_id=run,source_commit=commit,config_sha256=sha(source/'config.json'),
        target_sha256=sha(source/cfg['target_file']),python=__import__('sys').version,
        numpy=np.__version__,scipy=scipy.__version__)
    save_json(full/'execution.json',meta);save_json(full/'config_snapshot.json',cfg)
    outcome=dict(cases=[],checks=[],failure=None);arrays={};progress=None
    targets=json.loads((source/cfg['target_file']).read_text())
    try:
        validate_config(cfg,targets);os.chdir(full)
        progress=Progress(len(cfg['cases']));progress.update(experiment='E002b_FEAS',status='building')
        models={}
        for name,p in cfg['models'].items():
            m=measurement_model(p,cfg['acceptance']);models[name]=m
            machine=max(maxabs(m['rows'][m['index']['I_'+k+e]]) for k in ['form','idle'] for e in ['01','12','02'])
            outcome['checks'].append(dict(name='operators_'+name,actual=max(m['checks'].values()),machine_operator_max=machine,passed=max(m['checks'].values())<=1e-10 and machine<=1e-12))
            outcome['checks'].append(dict(name='preflight_'+name,**preflight(m,dict(integration={'dt':.01},acceptance=cfg['acceptance']))))
        if not all(c['passed'] for c in outcome['checks']):raise ValueError('Operator/preflight failure')
        for case in cfg['cases']:
            s,a,n=prepare(case,models[case['model']],cfg,progress,len(outcome['cases']))
            outcome['cases'].append(s);arrays[case['id']]=(a,n);save_json('outcome.json',outcome)
            print(json.dumps(dict(case=case['id'],completed=len(outcome['cases']),total=len(cfg['cases']),steps=s['steps'],seconds=s['elapsed_seconds'])),flush=True)
    except Exception as exc:
        outcome['failure']=dict(type=type(exc).__name__,message=str(exc));traceback.print_exc()
    finally:
        if progress:progress.update(status='failed' if outcome['failure'] else 'reporting',completed_cases=len(outcome['cases']));progress.close()
        save_json(full/'outcome.json',outcome);os.chdir(root)
    try:
        result,checks=prepare_report(root,cfg,targets,meta,outcome,arrays)
        return finalize(root,result,checks,time.monotonic()-entry)
    except Exception as exc:
        traceback.print_exc();report=root/'report';report.mkdir(exist_ok=True)
        save_json(report/'metrics.json',dict(**meta,failure=str(exc),acceptance_status='BLOCKED',automatic_damage_launch=False))
        (report/'README.md').write_text('Calculation/report failed; inspect metrics.json and output.log.\n')
        save_json(report/'data_manifest.json',dict(full_file_count=0,full_files=[],inventory_incomplete=True))
        return 2
