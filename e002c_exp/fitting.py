"""IC-1 structural search: callback API has exactly six observables, no hop."""
import hashlib
import json
import numpy as np
import scipy
from scipy.optimize import minimize
from e002_exp.model import save_json
from .engine import run_group
from .model import EDGES

FIELDS=tuple('pL'+e for e in EDGES)+tuple('ell'+e for e in EDGES)

def structural_target(targets):
    t=targets['candidates']['QS']['edges']
    return np.array([t[e]['pL'] for e in EDGES]+[t[e]['loss'] for e in EDGES])

def search(evaluate,target,seed):
    records=[];cache={};total_calls=0;computations=0;cache_hits=0
    target=np.asarray(target);den=np.maximum(abs(target),1e-8)
    for start_factor in (.25,1.,4.):
        calls=0
        def objective(logalpha):
            nonlocal calls,total_calls,computations,cache_hits
            if calls>=16:raise RuntimeError('Hard objective call budget exceeded')
            calls+=1;total_calls+=1
            alpha=np.exp(logalpha);key=tuple(alpha)
            if key in cache:
                cache_hits+=1;rec=dict(cache[key]);cached=True
            else:
                computations+=1;cached=False
                values,valid,reason=evaluate(alpha,computations)
                values=np.asarray(values,dtype=float)
                if values.shape!=(6,):raise ValueError('Objective only accepts six structural fields')
                errors=abs(values-target)/den
                valid=bool(valid and np.isfinite(errors).all())
                rec=dict(alpha=alpha.tolist(),values=values.tolist() if np.isfinite(values).all() else None,
                         valid=valid,reason=reason,maximum_error=float(max(errors)) if valid else None,
                         objective=float(errors@errors) if valid else 1e6,computation=computations)
                cache[key]=rec
            records.append(dict(rec,call=total_calls,start_factor=start_factor,cache_hit=cached))
            return rec['objective']
        minimize(objective,np.log(np.clip(seed*start_factor,1e-4,2.)),method='Powell',
                 bounds=[(np.log(1e-4),np.log(2.))]*3,
                 options=dict(maxfev=16,xtol=1e-3,ftol=1e-4))
    feasible=[r for r in cache.values() if r['valid']]
    selected=min(feasible,key=lambda r:(r['maximum_error'],r['objective'],tuple(r['alpha']))) if feasible else None
    return dict(calls=total_calls,computations=computations,cache_hits=cache_hits,
                scipy_version=scipy.__version__,records=records,selected=selected,
                selection_fields=['maximum_error','objective','alpha_lexicographic'],hop_in_objective=False)

def perform(full,targets):
    target=structural_target(targets);t=targets['candidates']['QS']['edges']
    seed=np.clip([t[e]['loss']/(.5*t[e]['pR']) for e in EDGES],1e-4,2.)
    summaries=[]
    def evaluate(alpha,index):
        case=dict(id=f'fit_{index:02d}',model='IC1_QS',phi_over_pi=0.,detuning=0.,
                  dephasing=.05,dt=.02,horizon=200.,family='fit')
        r=run_group([case],full,alpha,extend=False)[0];s=r['summary'];summaries.append(s)
        valid=s['failed'] is None and s['stationarity']['pass_gate'] and s['reference'] is not None
        return ([s['reference'][k] for k in FIELDS] if s['reference'] is not None else [np.nan]*6,
                valid,s['failed'] or (None if valid else 'not_stationary'))
    result=search(evaluate,target,seed)
    if result['selected'] is not None:
        # Written and hashed before any validation or held-out transport decision.
        payload=json.dumps(dict(alpha=result['selected']['alpha'],selection=result['selected'],
            source='E002c declared structural search'),sort_keys=True,allow_nan=False).encode()
        (full/'selected_alpha.json').write_bytes(payload)
        result['selected_alpha_sha256']=hashlib.sha256(payload).hexdigest()
    result['executed_steps']=sum(s['steps'] for s in summaries)
    result['trajectory_count']=len(summaries)
    save_json(full/'fit_search.json',result)
    return result
