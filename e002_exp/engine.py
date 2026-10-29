"""Fixed full trajectories with a trace-preserving intervention at t_damage."""
import json,os,time,shutil
from collections import deque
from pathlib import Path
import numpy as np
from j0_exp.engine import initial,Progress,preflight
from .model import save_json,sha,validate,rk4,maxabs
from .damage import apply


def save_state(v,path,t,step):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp')
    with tmp.open('wb') as stream:
        np.savez_compressed(stream,rho=v.reshape(216,216,order='F'),time=t,step=step)
        stream.flush();os.fsync(stream.fileno())
    os.replace(tmp,path)
    return dict(path=str(path),time=t,step=step,bytes=path.stat().st_size,sha256=sha(path))


def stationary(window,limit):
    first,last=window[0],window[-1];v=last['v'];f=np.array([r['F'] for r in window])
    r=dict(window_start=first['time'],window_end=last['time'],max_relative_rhs=max(r['rhs'] for r in window),
      relative_rho_change=float(np.linalg.norm(v-first['v'])/np.linalg.norm(v)),flux_range=float(np.ptp(f)),
      flux_bound=limit['absolute_flux_range']+limit['relative_flux_range']*abs(float(f[-1])))
    r['passed']=bool(last['time']-first['time']>=10-1e-9 and r['max_relative_rhs']<=limit['relative_rhs'] and r['relative_rho_change']<=limit['relative_rho_change'] and r['flux_range']<=r['flux_bound'])
    return r


def run_case(case,model,cfg,progress,completed):
    start=time.monotonic();dt=case['dt'];steps=round(case['horizon']/dt);hit=round(case['damage_time']/dt)
    obs=round(cfg['observable_interval']/dt);snap=round(cfg['rho_interval']/dt)
    v=initial({'state':'mix'});names=model['names'];ix=model['index'];L=model['L']
    folder=Path('cases');folder.mkdir(exist_ok=True);cid=case['id']
    window=deque(maxlen=round(10/cfg['rho_interval'])+1)
    pre_rows=[];diagnostics=[];events=[];pre=None;damage=None
    timings=dict(integration=0.,observations=0.,diagnostics=0.,checkpoint_io=0.)
    save_json(folder/(cid+'_schema.json'),{'case':case,'observable_names':names})
    with (folder/(cid+'.jsonl')).open('w') as stream:
        for step in range(steps+1):
            t=step*dt
            if step:
                tick=time.monotonic();v=rk4(L.dot,v,dt);timings['integration']+=time.monotonic()-tick
            before=None
            if step%obs==0:
                tick=time.monotonic();before=np.asarray(model['rows']@v)
                if not np.isfinite(before).all() or maxabs(before.imag)>1e-8:raise ValueError('Invalid observables')
                if case['damage_time']-cfg['pre_window']-1e-9<=t<=case['damage_time']+1e-9:
                    pre_rows.append({'time':t,'values':before.real.tolist()})
                timings['observations']+=time.monotonic()-tick
            if step%snap==0:
                if before is None:before=np.asarray(model['rows']@v)
                tick=time.monotonic();q=validate(v,cfg['acceptance'],abs(t/cfg['positivity_interval']-round(t/cfg['positivity_interval']))<1e-9)
                node=np.einsum('abcb->ac',v.reshape((216,216),order='F').reshape(8,27,8,27))
                q.update(time=t,rhs=float(np.linalg.norm(L@v)/np.linalg.norm(v)),node_coherence_fro=float(np.linalg.norm(node-np.diag(np.diag(node)))))
                window.append(dict(time=t,v=v.copy(),rhs=q['rhs'],F=float(before[ix['sink_flux']].real)))
                diagnostics.append(q);timings['diagnostics']+=time.monotonic()-tick
            if step==hit:
                pre=stationary(window,cfg['stationarity']);before_v=v.copy()
                events.append(save_state(v,Path('states')/cid/'pre_damage.npz',t,step))
                v=apply(v,case['damage']);validate(v,cfg['acceptance'],True)
                after=np.asarray(model['rows']@v).real
                damage=dict(kind=case['damage'],time=t,before=dict(zip(names,before.real.tolist())),after=dict(zip(names,after.tolist())),
                            trace_before=float(np.trace(before_v.reshape(216,216,order='F')).real),trace_after=float(np.trace(v.reshape(216,216,order='F')).real))
                before=after.astype(complex)
                window.clear();window.append(dict(time=t,v=v.copy(),rhs=float(np.linalg.norm(L@v)/np.linalg.norm(v)),F=float(after[ix['sink_flux']])))
            if step%obs==0:
                stream.write(json.dumps({'time':t,'values':before.real.tolist()},allow_nan=False)+'\n')
            if step%snap==0:
                progress.update(experiment='E002',status='running',current_case=cid,current_step=step,target_steps=steps,model_time=t,completed_cases=completed)
            if step%snap==0 and (t==0 or t>=cfg['rho_start']-1e-9):
                tick=time.monotonic();stream.flush();os.fsync(stream.fileno())
                ev=save_state(v,Path('states')/cid/f'rho_step{step:06d}.npz',t,step);events.append(ev)
                save_json('checkpoint_latest.json',dict(case_id=cid,**ev))
                progress.update(experiment='E002',status='running',current_case=cid,current_step=step,target_steps=steps,model_time=t,completed_cases=completed)
                if shutil.disk_usage('.').free<cfg['acceptance']['disk_floor_bytes']:raise ValueError('Disk reserve reached')
                timings['checkpoint_io']+=time.monotonic()-tick
    for ev in events:
        if sha(ev['path'])!=ev['sha256']:raise ValueError('Snapshot integrity failure')
    save_json(folder/(cid+'_pre.json'),pre_rows);save_json(folder/(cid+'_diagnostics.json'),diagnostics);save_json(folder/(cid+'_damage.json'),damage)
    summary=dict(case=case,steps=steps,rhs_calls=4*steps,records=steps//obs+1,snapshots=events,
      pre_stationarity=pre,final_stationarity=stationary(window,cfg['stationarity']),
      state_quality=dict(trace=max(q['trace_error'] for q in diagnostics),hermiticity=max(q['hermiticity_error'] for q in diagnostics),
                         min_eigen=min(q['min_eigenvalue'] for q in diagnostics if 'min_eigenvalue' in q)),
      elapsed_seconds=time.monotonic()-start,timing_seconds=timings)
    save_json(folder/(cid+'.json'),summary)
    return summary
