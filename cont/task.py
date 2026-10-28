"""Task lifecycle; no network, no publication and no access to credentials."""
import json
import os
from pathlib import Path
import re
import sys
import time
import traceback
import numpy as np
import scipy
from .model import sha, save_json, measurement_model
from .runner import Progress, input_state, preflight, run_continuation
from .report import write_report


def execute(config, source_dir):
    job_root = Path.cwd().resolve()
    run_id = os.environ.get('VM_JOB_ID', '')
    source_commit = os.environ.get('VM_SOURCE_COMMIT', '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{12,64}', run_id):
        raise ValueError('Missing or invalid VM_JOB_ID')
    if not re.fullmatch(r'[0-9a-f]{40}', source_commit):
        raise ValueError('Missing or invalid VM_SOURCE_COMMIT')
    work = Path(os.environ['VM_WORK']).resolve()
    full = job_root / 'full'
    full.mkdir(exist_ok=False)
    metadata = {'run_id':run_id,'source_commit':source_commit,'experiment':config['experiment_id'],
                'mode':config['mode'],'config_sha256':sha(source_dir/'config.json'),
                'python':sys.version,'numpy':np.__version__,'scipy':scipy.__version__,
                'pid':os.getpid(),'uid':os.getuid(),'started_unix':time.time()}
    save_json(full/'execution.json',metadata)
    save_json(full/'config_snapshot.json',config)
    progress = None
    failure = None
    exit_code = 0
    try:
        os.chdir(full)
        if config['mode'] not in {'continuation','preflight'}:
            raise ValueError('mode must be continuation or preflight')
        progress = Progress()
        models = {k:measurement_model(p,config['acceptance']) for k,p in config['configs'].items()}
        states, inputs = {}, []
        for case in config['cases']:
            states[case['id']] = input_state(case,work,None)
            inputs.append({'case_id':case['id'],'vm_path':case['input_path'],
                           'expected_sha256':case['input_sha256'],'verified_sha256':case['input_sha256'],'passed':True})
            save_json('input_checks.json',inputs)
        progress.update(status='preflight')
        checked=preflight(config,models,states)
        save_json('preflight_report.json',checked)
        outcome={'experiment':config['experiment_id'],'mode':config['mode'],'status':'running',
                 'cases':[],'preflight_passed':True,'interpretation_limits':config['interpretation_limits']}
        save_json('report.json',outcome)
        if config['mode']=='continuation':
            for case in config['cases']:
                result=run_continuation(case,models[case['config']],states[case['id']],config,progress,len(outcome['cases']))
                outcome['cases'].append(result)
                save_json('report.json',outcome)
            events=[json.loads(line) for line in Path('snapshot_events.jsonl').read_text().splitlines()]
            for event in events:
                if sha(event['path'])!=event['sha256']:
                    raise RuntimeError('Snapshot checksum mismatch: '+event['path'])
            outcome['verified_snapshot_count']=len(events)
            outcome['all_stationarity_passed']=all(c['stationarity']['passed'] for c in outcome['cases'])
            save_json('retention_check.json',{'passed':True,'snapshots':len(events)})
        outcome.update(status='completed',numerically_valid=True,elapsed_seconds=time.time()-metadata['started_unix'])
        save_json('report.json',outcome)
        progress.update(status='completed',completed_cases=len(outcome['cases']))
    except Exception as exc:
        exit_code=1
        failure={'type':type(exc).__name__,'message':str(exc)}
        save_json(full/'failure.json',failure)
        if progress is not None:progress.update(status='failed',error=failure)
        traceback.print_exc()
    finally:
        if progress is not None:progress.close()
        os.chdir(job_root)
    metadata.update(finished_unix=time.time(),task_exit_code=exit_code)
    save_json(full/'execution.json',metadata)
    try:
        write_report(job_root,config,metadata,failure=failure)
    except Exception as exc:
        print('REPORT_GENERATION_FAILED: '+repr(exc),flush=True)
        traceback.print_exc()
        return 2
    print(json.dumps({'experiment':config['experiment_id'],'mode':config['mode'],'run_id':run_id,
                      'source_commit':source_commit,'task_exit_code':exit_code,'report_directory':'report',
                      'result_confirmation':'Only after publication and GitHub report verification.'}),flush=True)
    return exit_code
