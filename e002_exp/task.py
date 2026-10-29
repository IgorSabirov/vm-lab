"""Offline job. Sync service owns publication; no direct network use."""
import os,json,re,time,traceback,shutil,sys
from pathlib import Path
import numpy as np
import scipy
from .model import measurement_model,save_json,sha,maxabs
from .engine import Progress,preflight,run_case
from .report import prepare,finalize


def execute(cfg,source,entry):
    root=Path.cwd();run=os.environ.get('VM_JOB_ID','');commit=os.environ.get('VM_SOURCE_COMMIT','')
    if not re.fullmatch('[A-Za-z0-9_-]{12,64}',run) or not re.fullmatch('[a-f0-9]{40}',commit):raise ValueError('Missing pinned identity')
    if shutil.disk_usage(root).free<cfg['required_free_disk_bytes']:raise ValueError('Insufficient declared disk reserve')
    ids=[c['id'] for c in cfg['cases']]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate cases')
    full=root/'full';full.mkdir(exist_ok=False)
    meta=dict(run_id=run,source_commit=commit,config_sha256=sha(source/'config.json'),python=sys.version,numpy=np.__version__,scipy=scipy.__version__,
      source_files={str(p.relative_to(source)):sha(p) for folder in ['e002_exp','sqrt_exp','j0_exp'] for p in sorted((source/folder).glob('*.py'))})
    save_json(full/'execution.json',meta);save_json(full/'config_snapshot.json',cfg)
    outcome=dict(cases=[],checks=[],failure=None);progress=None;code=0
    timings=dict(models=0.,preflight=0.,cases=0.)
    try:
        os.chdir(full);progress=Progress(len(ids));progress.update(experiment='E002',status='building')
        models={}
        for name,p in cfg['models'].items():
            tick=time.monotonic();m=measurement_model(p,cfg['acceptance']);models[name]=m;timings['models']+=time.monotonic()-tick
            outcome['checks'].append(dict(name='operators_'+name,actual=max(m['checks'].values()),limit=1e-10,passed=max(m['checks'].values())<=1e-10))
            tick=time.monotonic();pf=preflight(m,dict(integration={'dt':.01},acceptance=cfg['acceptance']));timings['preflight']+=time.monotonic()-tick
            outcome['checks'].append(dict(name='preflight_'+name,**pf))
        for case in cfg['cases']:
            tick=time.monotonic();s=run_case(case,models[case['model']],cfg,progress,len(outcome['cases']));timings['cases']+=time.monotonic()-tick
            outcome['cases'].append(s);save_json('outcome.json',outcome)
            print(json.dumps(dict(case=case['id'],completed=len(outcome['cases']),total=len(ids),steps=s['steps'],seconds=s['elapsed_seconds'])),flush=True)
    except Exception as exc:
        code=1;outcome['failure']=dict(type=type(exc).__name__,message=str(exc));traceback.print_exc()
    finally:
        if progress:progress.update(status='failed' if code else 'reporting',completed_cases=len(outcome['cases']));progress.close()
        save_json(full/'outcome.json',outcome);os.chdir(root)
    try:
        tick=time.monotonic();result,checks=prepare(root,cfg,meta,outcome);timings['report']=time.monotonic()-tick
        if not all(x['passed'] for x in checks):code=1
        result['task_exit_code']=code;result['timings']=timings
        export=finalize(root,result,checks,time.monotonic()-entry)
        print(json.dumps(dict(run_id=run,task_exit_code=code,export=export,runtime_gate=result['runtime_gate'],status='awaiting_GitHub_publication')),flush=True)
        return code
    except Exception:
        traceback.print_exc();return 2
