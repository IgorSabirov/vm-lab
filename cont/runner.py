"""Serial continuation and checkpoints. Writes inside the caller-selected full directory."""
import json,os,time,threading,shutil
from pathlib import Path
from datetime import datetime,timezone
from collections import deque
import numpy as np
from scipy.integrate import simpson
from scipy.sparse.linalg import expm_multiply
from .model import sha,save_json,validate,maxabs,rk4,make_direct_rhs,measurement_model
class Progress:
    def __init__(self):
        self.start=time.monotonic()
        self.lock=threading.Lock()
        self.stop_event=threading.Event()
        self.data={'experiment':'E001X_CONT','status':'initializing','completed_cases':0,'total_cases':4}
        self.thread=threading.Thread(target=self.beat,daemon=True)
        self.thread.start()
    def update(self,**kwargs):
        with self.lock:
            self.data.update(kwargs)
            self.data['elapsed_seconds']=time.monotonic()-self.start
            self.data['heartbeat_utc']=datetime.now(timezone.utc).isoformat()
            save_json('progress.json',self.data)
    def beat(self):
        while not self.stop_event.wait(5): self.update()
    def close(self):
        self.stop_event.set()
        self.thread.join(timeout=2)

def append_jsonl(path, record):
    with Path(path).open('a',encoding='utf-8') as f:
        f.write(json.dumps(record,ensure_ascii=False,allow_nan=False)+'\n')
        f.flush();os.fsync(f.fileno())

def snapshot(v,case,step,dt):
    folder=Path('states')/case['id'];folder.mkdir(parents=True,exist_ok=True)
    path=folder/f'rho_step{step:06d}.npz';temp=path.with_suffix('.tmp')
    with temp.open('wb') as f:
        np.savez_compressed(f,rho=v.reshape((216,216),order='F'),time=step*dt,step=step,case_json=json.dumps(case))
        f.flush();os.fsync(f.fileno())
    os.replace(temp,path)
    record={'case_id':case['id'],'step':step,'time':step*dt,'path':str(path),'sha256':sha(path),'bytes':path.stat().st_size}
    append_jsonl('snapshot_events.jsonl',record)
    save_json('checkpoint_latest.json',record)
    return record

def input_state(case,root,local_input_dir):
    path=Path(local_input_dir)/(case['id']+'.npz') if local_input_dir else root/case['input_path']
    if not local_input_dir:
        relative=Path(case['input_path'])
        if relative.is_absolute() or '..' in relative.parts or not relative.parts or relative.parts[0]!='results':
            raise ValueError('Checkpoint must be under the VM results directory')
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('Checkpoint path escapes VM workspace')
    if path.stat().st_size>8*1024**2:
        raise ValueError('Checkpoint exceeds the declared input bound')
    if sha(path)!=case['input_sha256']:raise RuntimeError('Input checksum mismatch: '+str(path))
    with np.load(path,allow_pickle=False) as d:
        rho=d['rho'].copy();when=float(d['time']);old=json.loads(str(d['case_json']))
    if rho.shape!=(216,216) or when!=100 or old['phase_index']!=case['phase_index'] or old['mixed']:
        raise RuntimeError('Input identity mismatch: '+case['id'])
    if old['id']!=case['source_case_id'] or abs(old['phi']-case['phase_index']*np.pi/2)>1e-12:
        raise RuntimeError('Input phase mismatch: '+case['id'])
    return rho.reshape(-1,order='F')

def preflight(protocol,models,states):
    results={}
    for case in protocol['cases']:
        m=models[case['config']];v=states[case['id']].copy();L=m['L'];dt=protocol['integration']['dt']
        check=validate(v,protocol['acceptance'],True)
        direct=make_direct_rhs(m['H'],m['jumps'])(v)
        rhs_error=float(np.linalg.norm(direct-L@v)/max(np.linalg.norm(direct),1e-12))
        start=time.monotonic()
        coarse=v.copy()
        for _ in range(round(1/dt)):coarse=rk4(lambda x:L@x,coarse,dt)
        seconds=time.monotonic()-start
        fine=v.copy()
        for _ in range(round(2/dt)):fine=rk4(lambda x:L@x,fine,dt/2)
        exact=expm_multiply(L,v)
        err=float(np.linalg.norm(coarse-exact)/np.linalg.norm(exact))
        refinement=float(np.max(abs(m['rows']@(coarse-fine))))
        if rhs_error>1e-6 or err>protocol['acceptance']['expm_reference_relative'] or refinement>protocol['acceptance']['refinement_observables']:
            raise RuntimeError('Preflight numerical failure '+case['id']+': '+json.dumps({'rhs_relative_error':rhs_error,'expm_relative_error':err,'dt_halving_max_observable_difference':refinement}))
        validate(coarse,protocol['acceptance'],True)
        results[case['id']]={'initial_state_checks':check,'rhs_relative_error':rhs_error,'expm_relative_error':err,'dt_halving_max_observable_difference':refinement,'seconds_per_100_steps':seconds}
    return {'passed':True,'cases':results,'operator_checks':{k:m['checks'] for k,m in models.items()},'measurement_count':len(next(iter(models.values()))['names'])}

def stationary(window, samples, index, thresholds):
    a,b=window[0],window[-1]
    recent=[row[index['sink_flux']] for t,row in samples if t>=b['time']-10-1e-8]
    rhs=max(q['relative_rhs'] for q in window)
    flux=(max(recent)-min(recent))/max(abs(recent[-1]),1e-14)
    distance=float(np.linalg.norm(b['v']-a['v'])/max(np.linalg.norm(b['v']),1e-14))
    values={'window_start':a['time'],'window_end':b['time'],'max_relative_rhs':rhs,'relative_flux_range':flux,'relative_rho_change':distance}
    values['passed']=bool(b['time']-a['time']>=10-1e-8 and rhs<=thresholds['relative_rhs'] and flux<=thresholds['relative_flux_range'] and distance<=thresholds['relative_rho_change'])
    return values

def run_continuation(case,m,initial,protocol,progress,completed):
    started=time.monotonic();dt=protocol['integration']['dt'];startstep=round(100/dt)
    sample_every=round(protocol['integration']['observable_interval']/dt)
    snapshot_every=round(protocol['integration']['rho_interval']/dt)
    v=initial.copy();window=deque(maxlen=11);samples=[];diagnostics=[];saved=[];endpoint_tests=[]
    Path('cases').mkdir(exist_ok=True)
    stream=Path('cases')/(case['id']+'.jsonl')
    index=m['index'];L=m['L']
    save_json(Path('cases')/(case['id']+'_schema.json'),{'case':case,'observable_names':m['names'],'operator_checks':m['checks']})
    def observe(step,handle):
        values=np.asarray(m['rows']@v)
        if maxabs(values.imag)>1e-8:raise RuntimeError('Complex expectation')
        vals=values.real.tolist();samples.append((step*dt,vals))
        handle.write(json.dumps({'time':step*dt,'values':vals},allow_nan=False)+'\n')
    def record_state(step,handle):
        t=step*dt
        check=validate(v,protocol['acceptance'],round(t)%5==0)
        rhsnorm=float(np.linalg.norm(L@v));norm=float(np.linalg.norm(v))
        node=np.einsum('abcb->ac',v.reshape((216,216),order='F').reshape(8,27,8,27))
        check.update(time=t,rhs_fro=rhsnorm,rho_fro=norm,relative_rhs=rhsnorm/norm,node_coherence_fro=float(np.linalg.norm(node-np.diag(np.diag(node)))))
        diagnostics.append(check);window.append({'time':t,'relative_rhs':check['relative_rhs'],'v':v.copy()})
        handle.flush();os.fsync(handle.fileno());last=snapshot(v,case,step,dt);saved.append(last)
        progress.update(status='running',current_case=case['id'],model_time=t,completed_cases=completed,last_checkpoint=last,last_validation=check)
        if round(t)%10==0 and shutil.disk_usage('.').free<protocol['acceptance']['disk_floor_bytes']:
            raise RuntimeError('Disk reserve reached')
    with stream.open('w',encoding='utf-8') as f:
        observe(startstep,f);record_state(startstep,f)
        step=startstep
        for endpoint in protocol['horizons']:
            progress.update(target_time=endpoint)
            while step<round(endpoint/dt):
                candidate=rk4(lambda x:L@x,v,dt)
                if not np.isfinite(candidate).all():raise RuntimeError('Nonfinite state; last checkpoint retained')
                v=candidate;step+=1
                if step%sample_every==0:observe(step,f)
                if step%snapshot_every==0:record_state(step,f)
            decision=stationary(window,samples,index,protocol['stationarity'])
            endpoint_tests.append(decision)
            save_json(Path('cases')/(case['id']+'_endpoint.json'),{'case':case,'endpoint_tests':endpoint_tests,'last_checkpoint':saved[-1]})
            if decision['passed']:break
    times=np.array([t for t,_ in samples]);values=np.array([r for _,r in samples])
    selected=['sink_flux','source_flux','pump_flux','break_flux','I_hop_sink','I_form_sink','I_idle_sink']
    integrals={name:float(simpson(values[:,index[name]],x=times)) for name in selected}
    integrals['stored_sink']=float(values[0,index['n2']]-values[-1,index['n2']])
    integrals['sink_balance_residual']=integrals['sink_flux']-sum(integrals[k] for k in ['I_hop_sink','I_form_sink','I_idle_sink','stored_sink'])
    integrals['inventory_change']=float(values[-1,index['inventory']]-values[0,index['inventory']])
    integrals['inventory_balance_residual']=integrals['inventory_change']-(integrals['pump_flux']-integrals['break_flux'])
    temporal_residual=values[:,index['dn2_dt']]-(values[:,index['I_hop_sink']]+values[:,index['I_form_sink']]+values[:,index['I_idle_sink']]-values[:,index['sink_flux']])
    algebra_residual=float(np.max(abs(temporal_residual)))
    if algebra_residual>protocol['acceptance']['algebra']:raise RuntimeError('Recorded node balance failed')
    # The integral residual is quadrature diagnostics, not a stationarity criterion.
    summary={'case':case,'final_time':float(times[-1]),'numerically_valid':True,'stationarity':endpoint_tests[-1],'endpoint_tests':endpoint_tests,'final_observables':dict(zip(m['names'],values[-1].tolist())),'selected_times':[{'time':float(t),'observables':dict(zip(m['names'],row))} for t,row in samples if any(abs(t-x)<1e-8 for x in [100,200,300,400,500,750,1000])], 'integrals':integrals,'max_recorded_node_balance_residual':algebra_residual,'mixture_T100_flux_relative_difference':float((values[-1,index['sink_flux']]-case['mixture_T100_flux'])/case['mixture_T100_flux']),'mixture_comparison_scope':'Reference is a saved T100 mixture, not a newly evolved mixture or certified stationary solution.','snapshots':len(saved),'first_snapshot':saved[0],'last_snapshot':saved[-1],'series_path':str(stream),'series_sha256':sha(stream),'elapsed_seconds':time.monotonic()-started,'max_relative_rhs':max(d['relative_rhs'] for d in diagnostics)}
    save_json(Path('cases')/(case['id']+'_diagnostics.json'),diagnostics)
    save_json(Path('cases')/(case['id']+'.json'),summary)
    return summary
