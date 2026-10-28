"""VM job lifecycle; the existing sync service performs all GitHub I/O."""
import json
import os
import re
import sys
import time
import traceback
from pathlib import Path

import numpy as np
import scipy

from .engine import Progress, preflight, run_case
from .checks import operator_checks
from sqrt_exp.model import measurement_model, save_json, sha
from .report import prepare_report, finalize_report


def runtime_gate(config, actual, workload_ok):
    estimate=config['runtime_forecast']
    expected=estimate['expected_seconds']
    status='PASS' if estimate['lower_seconds']<=actual<=estimate['upper_seconds'] and workload_ok else 'REVIEW_REQUIRED'
    return {'expected_seconds':expected,'lower_seconds':estimate['lower_seconds'],'upper_seconds':estimate['upper_seconds'],
            'actual_seconds':actual,'actual_over_expected':actual/expected,'status':status,
            'calibration_reference':estimate['reference'],'executed_branch':config['mode'],
            'workload_matches':workload_ok,
            'measurement_scope':'Entry-point monotonic clock through report preparation; final writes and interpreter shutdown excluded. Authoritative whole-process duration must be checked from published run.json.'}


def execute(config, source_dir, entry_monotonic):
    root=Path.cwd().resolve()
    run_id=os.environ.get('VM_JOB_ID','')
    commit=os.environ.get('VM_SOURCE_COMMIT','')
    if not re.fullmatch(r'[A-Za-z0-9_-]{12,64}',run_id) or not re.fullmatch(r'[0-9a-f]{40}',commit):
        raise ValueError('Missing pinned VM identity')
    if config['mode'] not in {'calibration','main','test'}:raise ValueError('Unknown task mode')
    if 'runtime_forecast' not in config:raise ValueError('Runtime forecast required before launch')
    ids=[c['id'] for c in config['cases']]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate case ids')
    full=root/'full';full.mkdir(exist_ok=False)
    metadata={'run_id':run_id,'source_commit':commit,'config_sha256':sha(source_dir/'config.json'),
              'python':sys.version,'numpy':np.__version__,'scipy':scipy.__version__,
              'pid':os.getpid(),'uid':os.getuid(),'started_record_unix':time.time(),
              'thread_environment':{k:os.environ.get(k) for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']},
              'source_files':{str(p.relative_to(source_dir)):sha(p) for folder in ['sqrt_exp','j0_exp'] for p in sorted((source_dir/folder).glob('*.py'))}}
    save_json(full/'execution.json',metadata)
    save_json(full/'config_snapshot.json',config)
    outcome={'operators':{},'preflight':[],'cases':[],'failure':None}
    phases={'imports_and_startup':time.monotonic()-entry_monotonic,'models':0.,'preflight':0.,'cases':0.,'retention':0.}
    progress=None
    exit_code=0
    try:
        os.chdir(full)
        progress=Progress(len(config['cases']))
        models={}
        for mid,p in config['models'].items():
            progress.update(status='building',current_model=mid)
            tick=time.monotonic();m=measurement_model(p,config['acceptance']);m['checks'].update(operator_checks(m,p,config['acceptance']['algebra']));phases['models']+=time.monotonic()-tick
            models[mid]=m;outcome['operators'][mid]=m['checks']
            tick=time.monotonic();row=preflight(m,config);duration=time.monotonic()-tick;phases['preflight']+=duration
            row.update(model=mid,elapsed_seconds=duration,generator_nnz=m['L'].nnz)
            outcome['preflight'].append(row)
            save_json('preflight.json',outcome['preflight'])
        for case in config['cases']:
            tick=time.monotonic()
            summary=run_case(case,models[case['model']],config,progress,len(outcome['cases']))
            phases['cases']+=time.monotonic()-tick
            outcome['cases'].append(summary)
            save_json('outcome.json',outcome)
            print(json.dumps({'case':case['id'],'completed':len(outcome['cases']),'total':len(config['cases']),
                              'steps':summary['steps'],'elapsed_seconds':summary['elapsed_seconds']}) ,flush=True)
        tick=time.monotonic()
        events=[json.loads(x) for x in Path('snapshot_events.jsonl').read_text().splitlines()]
        if len({x['path'] for x in events})!=len(events):raise RuntimeError('Duplicate snapshot')
        for event in events:
            p=Path(event['path'])
            if p.stat().st_size!=event['bytes'] or sha(p)!=event['sha256']:raise RuntimeError('Snapshot mismatch')
        for case in config['cases']:
            got=[x['step'] for x in events if x['case_id']==case['id']]
            wanted=list(range(0,round(case['horizon']/case['dt'])+1,round(config['integration']['rho_interval']/case['dt'])))
            if got!=wanted:raise RuntimeError('Snapshot grid gap: '+case['id'])
        outcome.update(retention_passed=True,verified_snapshots=len(events))
        phases['retention']+=time.monotonic()-tick
    except Exception as exc:
        exit_code=1
        outcome['failure']={'type':type(exc).__name__,'message':str(exc)}
        traceback.print_exc()
    finally:
        if progress:
            progress.update(status='failed' if exit_code else 'reporting',completed_cases=len(outcome['cases']))
            progress.close()
        save_json(full/'outcome.json',outcome)
        os.chdir(root)
    tick=time.monotonic()
    try:
        result,checks=prepare_report(root,config,metadata,outcome)
        phases['report_preparation']=time.monotonic()-tick
        work_ok=all(c['passed'] for c in checks if c['name'].startswith('workload_') or c['name']=='all_cases_completed')
        if not all(c['passed'] for c in checks):exit_code=1
        result['task_exit_code']=exit_code
        timing={'phases_seconds':phases,'gate':runtime_gate(config,time.monotonic()-entry_monotonic,work_ok)}
        export=finalize_report(root,result,checks,timing)
        print(json.dumps({'run_id':run_id,'task_exit_code':exit_code,'export':export,
                          'runtime_gate':timing['gate'],'status':'awaiting_GitHub_publication'}),flush=True)
    except Exception:
        traceback.print_exc()
        return 2
    return exit_code
