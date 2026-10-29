"""Fixed RK4 grids and one stationarity-driven extension, without state repairs."""
import json
import shutil
import time
from collections import deque
from pathlib import Path
import numpy as np
from scipy.integrate import simpson
from e002_exp.model import rk4, save_json
from .model import build, initial
from .diagnostics import expanded, quality, negativity

SNAPSHOTS=(0,.2,1,2,5,10,20,50,100,190,200,300,390,400)

def integral_mean(series, names, horizon):
    # Fixed even-time grid in last 10 units, present losslessly in report export.
    take=(series[:,0]>=horizon-10-1e-8)&np.isclose(series[:,0]/2,np.round(series[:,0]/2),atol=1e-8)
    a=series[take]
    if len(a)<6:return None
    return dict(zip(names,(simpson(a[:,1:],x=a[:,0],axis=0)/10).tolist()))

def stationarity(window, horizon):
    if len(window)<6 or abs(window[0]['t']-(horizon-10))>1e-8:
        return dict(pass_gate=False,reason='window_short',rhs=None,drift=None,flux_range=None)
    rhs=max(x['rhs'] for x in window)
    drift=float(np.linalg.norm(window[-1]['v']-window[0]['v'])/np.linalg.norm(window[-1]['v']))
    flux=np.array([x['F'] for x in window]);frange=float(np.ptp(flux))
    limit=1e-8+1e-5*abs(flux[-1])
    return dict(pass_gate=bool(rhs<=1e-7 and drift<=1e-6 and frange<=limit),rhs=rhs,
                drift=drift,flux_range=frange,flux_limit=float(limit),reason=None)

class Trajectory:
    def __init__(self,case,root,alpha=None,disk_floor=1.5*1024**3):
        self.case=dict(case);self.root=Path(root)/case['id'];self.root.mkdir(parents=True,exist_ok=False)
        self.started=time.monotonic();self.model=build(case,alpha);self.v=initial();self.step=0
        self.series=[];self.diags=[];self.certs=[];self.window=deque(maxlen=6)
        self.snapshots=[];self.node_edge=[];self.dnames=None;self.disk_floor=disk_floor
        self.integrator_seconds=0.;self.diagnostic_seconds=0.;self.failure=None;self.completed_horizon=0.
        save_json(self.root/'model.json',dict(case=case,alpha=None if alpha is None else list(alpha),
                    checks=self.model['checks'],dark=[d['info'] for d in self.model['dark']]))
        self.sample(0)

    def sample(self,step):
        dt=self.case['dt'];t=round(step*dt,10);r=self.v.reshape(216,216,order='F')
        scalar_stride=round(.2/dt);diag_stride=round(2/dt)
        if step%scalar_stride==0:
            raw=np.asarray(self.model['rows']@self.v)
            if not np.isfinite(raw).all() or max(abs(raw.imag))>1e-8:raise ValueError('Invalid observables')
            self.series.append(np.r_[t,raw.real])
        if step%diag_stride==0:
            start=time.monotonic();q=quality(r,self.model['L'])
            n,values,cert=expanded(r,self.model)
            self.dnames=n+['trace','hermiticity','min_eigen','rhs']
            self.diags.append(np.r_[t,values,[q[k] for k in ('trace','hermiticity','min_eigen','rhs')]])
            self.certs.append(cert)
            self.window.append(dict(t=t,v=self.v.copy(),rhs=q['rhs'],F=float(self.series[-1][5])))
            self.diagnostic_seconds+=time.monotonic()-start
            if shutil.disk_usage(self.root).free<self.disk_floor:raise RuntimeError('Disk reserve reached')
            save_json(self.root.parent/'progress.json',dict(case=self.case['id'],step=step,time=t,
                     elapsed_seconds=time.monotonic()-self.started))
        if any(abs(t-s)<1e-9 for s in SNAPSHOTS):
            path=self.root/f'rho_{t:g}.npz'
            np.savez(path,rho=r,time=np.array(t),step=np.array(step,dtype=np.int64))
            neg,mineig=negativity(r,[8,27],[0])
            self.node_edge.append(dict(time=t,negativity=neg,min_eigen=mineig,
                status='NODE_EDGE_NPT_DETECTED' if mineig < -1e-8 else 'NODE_EDGE_NPT_NOT_DETECTED',
                independent_reconstruction_from_node_export=False))
            self.snapshots.append(path.name)
            save_json(self.root/'checkpoint.json',dict(step=step,time=t,path=path.name,dt=dt))

    def advance(self,horizon):
        dt=self.case['dt'];target=round(horizon/dt)
        if abs(target*dt-horizon)>1e-9:raise ValueError('Non-integral step count')
        if target<=self.step:raise ValueError('Extension must advance time')
        for step in range(self.step+1,target+1):
            start=time.monotonic();self.v=rk4(self.model['L'].dot,self.v,dt)
            self.integrator_seconds+=time.monotonic()-start;self.step=step
            self.sample(step)
        self.completed_horizon=horizon
        return stationarity(self.window,horizon)

    def finish(self):
        series=np.asarray(self.series,dtype=np.float64);diag=np.asarray(self.diags,dtype=np.float64)
        np.savez(self.root/'series.npz',values=series)
        np.savez(self.root/'diagnostics.npz',values=diag)
        certs={k:np.array([c[k] for c in self.certs]) for k in ('blocks','vectors','alpha','overlap','valid')}
        np.savez(self.root/'certificates.npz',time=diag[:,0],**certs)
        np.savez(self.root/'final.npz',rho=self.v.reshape(216,216,order='F'))
        end=float(series[-1,0]);st=stationarity(self.window,end)
        ref=integral_mean(series,self.model['names'],end)
        h=series[:,1+self.model['names'].index('h')]
        tau=None;reason='not_stationary_or_short_window'
        if st['pass_gate'] and ref is not None:
            outside=np.flatnonzero(abs(h-ref['h'])>max(.1*abs(ref['h']),1e-6))
            i=int(outside[-1]+1) if len(outside) else 0
            if i<len(series) and end-series[i,0]>=10:
                tau=float(series[i,0]);reason=None
            else:reason='final_in_band_window_shorter_than_10'
        summary=dict(case=self.case,alpha=None if self.model['alpha'] is None else list(self.model['alpha']),
            horizon=end,requested_horizon=self.case['horizon'],extended=bool(end>self.case['horizon']+1e-9),
            transition_reference=integral_mean(series,self.model['names'],200.) if end>=200 else None,
            refinement_status='not_refined',steps=self.step,rhs_calls=4*self.step,scalar_records=len(series),diagnostic_records=len(diag),
            snapshots=len(self.snapshots),stationarity=st,reference=ref,failed=self.failure,
            state_status='finite_time_only' if not st['pass_gate'] else 'stationary',tau90=tau,tau90_reason=reason,
            operator_checks=self.model['checks'],dark_geometry=[x['info'] for x in self.model['dark']],node_edge=self.node_edge,
            elapsed_seconds=time.monotonic()-self.started,integrator_seconds=self.integrator_seconds,
            diagnostic_seconds=self.diagnostic_seconds)
        save_json(self.root/'summary.json',summary)
        return dict(summary=summary,series=series,diagnostics=diag,certs=certs,
                    names=self.model['names'],dnames=self.dnames,root=self.root)

def run_group(cases,full,alpha=None,extend=True,disk_floor=1.5*1024**3):
    # The members of one group have the same physics and distinct dt.
    runs=[];gates=[]
    for case in cases:
        run=Trajectory(case,full,alpha,disk_floor);runs.append(run)
        try:gates.append(run.advance(case['horizon'])['pass_gate'])
        except ValueError as e:run.failure=str(e);gates.append(False)
    if extend and not all(gates):
        for run in runs:
            if run.failure is None:
                try:run.advance(400.)
                except ValueError as e:run.failure=str(e)
    return [r.finish() for r in runs]

def compare_pair(a,b):
    # Full common scalar/diagnostic grids, not just the reduced report grid.
    result={};passed=True
    for key in ('series','diagnostics'):
        x,y=a[key],b[key]
        if x.shape!=y.shape or not np.array_equal(x[:,0],y[:,0]):
            return dict(pass_gate=False,reason='grid_mismatch',errors={})
        if not np.array_equal(np.isnan(x),np.isnan(y)):
            return dict(pass_gate=False,reason='conditional_validity_mismatch',errors={})
        finite=np.isfinite(x)&np.isfinite(y)
        error=np.where(finite,abs(x-y),0.)
        scale=1e-6+1e-4*np.maximum(np.nan_to_num(abs(x)),np.nan_to_num(abs(y)))
        # Quality RHS/eigenvalues are still compared, as are all measured diagnostics.
        passed &= bool(np.all(error<=scale))
        names=['time']+(a['names'] if key=='series' else a['dnames'])
        result[key]=dict(zip(names,error.max(axis=0).tolist()))
    return dict(pass_gate=passed,reason=None,errors=result)
