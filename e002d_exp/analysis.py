"""Signed matched-control responses; numerical resolution is not significance."""
import numpy as np
from e002c_exp.engine import compare_pair
from e002c_exp.windows import integral_mean
from .plan import MODELS

def key(c):return (c['model'],c['target'],c['kind'],c['gamma'],c['dt'])

def analyze(results,mode):
    by={key(r['summary']['case']):r for r in results};pairs={}
    for k,r in by.items():
        other=(*k[:-1],.01)
        if k[-1]==.005 and other in by:
            check=compare_pair(r,by[other]);pairs[r['summary']['case']['id']]=check
            for obj in (r,by[other]):obj['summary']['refinement_status']='passed' if check['pass_gate'] else 'failed'
    if mode!='production':return dict(pairs=pairs,comparisons=[],scope='calibration/smoke; no scientific inference')
    comparisons=[]
    for target,gamma in [('A',.1),('B',.1),('AB',.05),('AB',.1),('AB',.2)]:
        for horizon in sorted(set([200.]+[r['summary']['horizon'] for r in results])):
            row=dict(target=target,gamma=gamma,horizon=horizon,models={})
            ready=True;all_stationary=True;all_refined=True
            for model in MODELS:
                rr=[]
                for dt in (.005,.01):
                    ks=[(model,'base','base',0.,dt),(model,target,'T',gamma,dt),(model,target,'C',gamma,dt)]
                    if any(k not in by for k in ks):continue
                    rs=[by[k] for k in ks];refs=[integral_mean(r['series'],r['names'],horizon) for r in rs]
                    if any(ref is None for ref in refs):continue
                    h0,ht,hc=[ref['h'] for ref in refs]
                    if abs(h0)<=1e-8:continue
                    record=dict(dt=dt,h0=h0,hT=ht,hC=hc,delta=ht-hc,r=(ht-hc)/h0,
                        refs=dict(base=refs[0],T=refs[1],C=refs[2]))
                    rr.append(record)
                    all_stationary &= all(r['summary']['stationarity']['pass_gate'] and r['summary']['horizon']==horizon for r in rs)
                    all_refined &= all(r['summary']['refinement_status']=='passed' for r in rs)
                if not rr or rr[0]['dt']!=.005:ready=False;continue
                fine=rr[0];coarse=rr[1] if len(rr)>1 else None
                row['models'][model]=dict(h0=fine['h0'],hT=fine['hT'],hC=fine['hC'],
                    delta=fine['delta'],r=fine['r'],r_coarse=coarse['r'] if coarse else None,
                    r_dt_difference=abs(fine['r']-coarse['r']) if coarse else None,
                    structural_T_minus_C={name:fine['refs']['T'][name]-fine['refs']['C'][name]
                      for name in fine['refs']['T'] if name.startswith(('p_','pL','ell','h_m','C_'))})
            row.update(evaluable=ready,stationary=bool(all_stationary),refinement_pass=bool(all_refined and gamma==.1))
            if ready:
                qs,rr=row['models']['QS'],row['models']['RR_QS'];q=qs['r']-rr['r'];row['Q']=q
                basegap=qs['h0']-rr['h0'];row['baseline_gap']=basegap
                row['gap_change']=qs['delta']-rr['delta']
                row['gap_change_fraction']=row['gap_change']/basegap if abs(basegap)>1e-8 else None
                qc=(qs['r_coarse']-rr['r_coarse']) if qs['r_coarse'] is not None and rr['r_coarse'] is not None else None
                row['Q_coarse']=qc;row['resolution_threshold']=1e-4+10*abs(q-qc) if qc is not None else None
                row['status']=('NONSTATIONARY' if not all_stationary else
                    'SCREENING_ONLY' if gamma!=.1 else 'REFINEMENT_FAILED' if not all_refined else
                    'RESOLVED_NEGATIVE' if q < -row['resolution_threshold'] else
                    'RESOLVED_POSITIVE' if q > row['resolution_threshold'] else 'UNRESOLVED_AT_TOLERANCE')
            else:row['status']='NOT_EVALUABLE'
            comparisons.append(row)
    return dict(pairs=pairs,comparisons=comparisons,scope='finite-dose matched interventions, fixed original physical model')
