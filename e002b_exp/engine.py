"""Stationary preparation only; this module has no damage operation."""
import json
import os
import shutil
import time
from collections import deque
from pathlib import Path

import numpy as np
from scipy.integrate import simpson

from e002_exp.engine import save_state, stationary
from e002_exp.model import maxabs, rk4, save_json, sha, validate
from j0_exp.engine import initial


def prepare(case, model, cfg, progress, completed):
    started=time.monotonic();dt=case['dt'];end=cfg['horizon']
    steps=round(end/dt);obs=round(cfg['observable_interval']/dt)
    diag=round(cfg['diagnostic_interval']/dt);start_window=end-cfg['baseline_window']
    v=initial({'state':'mix'});L=model['L'];names=model['names'];ix=model['index']
    folder=Path('cases');folder.mkdir(exist_ok=True);cid=case['id']
    save_json(folder/(cid+'_schema.json'),{'observable_names':names,'case':case})
    samples=[];diagnostics=[];snapshots=[]
    window=deque(maxlen=round(cfg['baseline_window']/cfg['diagnostic_interval'])+1)
    with (folder/(cid+'.jsonl')).open('w') as stream:
        for step in range(steps+1):
            t=step*dt
            if step:v=rk4(L.dot,v,dt)
            values=None
            if step%obs==0:
                raw=np.asarray(model['rows']@v)
                if not np.isfinite(raw).all() or maxabs(raw.imag)>1e-8:
                    raise ValueError('Invalid observable')
                values=raw.real
                samples.append([t,*values.tolist()])
                stream.write(json.dumps({'time':t,'values':values.tolist()},allow_nan=False)+'\n')
            if step%diag==0:
                if values is None:values=np.asarray(model['rows']@v).real
                q=validate(v,cfg['acceptance'],abs(t/cfg['positivity_interval']-round(t/cfg['positivity_interval']))<1e-9)
                q.update(time=t,rhs=float(np.linalg.norm(L@v)/np.linalg.norm(v)))
                diagnostics.append(q)
                window.append(dict(time=t,v=v.copy(),rhs=q['rhs'],F=float(values[ix['sink_flux']])))
                stream.flush();os.fsync(stream.fileno())
                if t==0 or t>=start_window-1e-9:
                    event=save_state(v,Path('states')/cid/f'rho_step{step:06d}.npz',t,step)
                    snapshots.append(event);save_json('checkpoint_latest.json',dict(case=cid,**event))
                if shutil.disk_usage('.').free<cfg['acceptance']['disk_floor_bytes']:
                    raise ValueError('Disk reserve reached')
                progress.update(experiment='E002b_FEAS',status='running',current_case=cid,
                    current_step=step,target_steps=steps,model_time=t,completed_cases=completed)
    for event in snapshots:
        if sha(event['path'])!=event['sha256']:raise ValueError('Snapshot changed')
    a=np.array(samples);t=a[:,0];values=a[:,1:];take=t>=start_window-1e-9
    ref=dict(zip(names,(simpson(values[take],x=t[take],axis=0)/cfg['baseline_window']).tolist()))
    summary=dict(case=case,steps=steps,rhs_calls=4*steps,records=len(t),snapshots=snapshots,
        stationarity=stationary(window,cfg['stationarity']),reference=ref,
        state_quality={'trace':max(q['trace_error'] for q in diagnostics),
            'hermiticity':max(q['hermiticity_error'] for q in diagnostics),
            'min_eigen':min(q['min_eigenvalue'] for q in diagnostics if 'min_eigenvalue' in q)},
        elapsed_seconds=time.monotonic()-started)
    save_json(folder/(cid+'_diagnostics.json'),diagnostics)
    save_json(folder/(cid+'.json'),summary)
    return summary,a,names
