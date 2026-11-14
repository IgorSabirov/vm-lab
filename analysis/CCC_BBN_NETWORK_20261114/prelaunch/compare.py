"""Freeze discretization envelopes before S1; evaluate all active species."""
import argparse
import json
from pathlib import Path
import numpy as np
from run import dump, digest


def load(p): return json.loads(p.read_text())


def main():
    p=argparse.ArgumentParser(); p.add_argument('action',choices=['freeze','compare'])
    p.add_argument('--baseline',type=Path,required=True); p.add_argument('--other',type=Path,required=True)
    p.add_argument('--envelope',type=Path,required=True); p.add_argument('--out',type=Path)
    a=p.parse_args(); b=load(a.baseline/'TRACE.json'); x=load(a.other/'TRACE.json')
    env=load(a.envelope) if a.action=='compare' else {'formula':'5*max_refinement_difference + 1e-10*max_baseline_abundance + 1e-14','fixed_inputs':'same weak/plasma caches and background grid','eras':[]}
    rows=[]
    for k,(eb,ex) in enumerate(zip(b['eras'],x['eras'])):
        assert eb['era']==ex['era'] and eb['species']==ex['species']
        assert np.allclose(eb['T_MeV'],ex['T_MeV'],rtol=1e-12,atol=0)
        yb,yx=np.array(eb['Y']),np.array(ex['Y']); diff=np.max(np.abs(yx-yb),axis=0)
        if a.action=='freeze':
            tol=5*diff+1e-10*np.max(np.abs(yb),axis=0)+1e-14
            env['eras'].append({'era':eb['era'],'species':eb['species'],'max_refinement_difference':diff.tolist(),'absolute_tolerance':tol.tolist()})
        else:
            tol=np.array(env['eras'][k]['absolute_tolerance'])
            rows.append({'era':eb['era'],'species':eb['species'],'max_difference':diff.tolist(),'tolerance':tol.tolist(),'max_ratio':float(np.max(diff/tol)),'pass':bool(np.all(diff<=tol))})
    rb,rx=load(a.baseline/'RESULT.json'),load(a.other/'RESULT.json')
    final=[]
    for key in ('YPBBN','DoH','Neff'):
        db=rb['result'][key]; dx=rx['result'][key]; d=abs(dx-db)
        if a.action=='freeze': env.setdefault('observables',{})[key]=5*d+1e-10*abs(db)+1e-14
        else: final.append({'name':key,'difference':d,'tolerance':env['observables'][key],'pass':d<=env['observables'][key]})
    if a.action=='freeze':
        if a.envelope.exists(): raise RuntimeError('Never overwrite a frozen envelope')
        env['baseline']={str(q.name):digest(q) for q in (a.baseline/'TRACE.json',a.baseline/'RESULT.json')}
        env['refinement']={str(q.name):digest(q) for q in (a.other/'TRACE.json',a.other/'RESULT.json')}
        dump(a.envelope,env); print(json.dumps({'envelope':str(a.envelope),'sha256':digest(a.envelope)['sha256']}))
    else:
        result={'baseline':str(a.baseline),'other':str(a.other),'envelope_sha256':digest(a.envelope)['sha256'],
                'eras':rows,'observables':final,'invariance_pass':all(r['pass'] for r in rows+final),
                'max_trajectory_tolerance_ratio':max(r['max_ratio'] for r in rows)}
        dump(a.out,result); print(json.dumps({'invariance_pass':result['invariance_pass'],'max_ratio':result['max_trajectory_tolerance_ratio']}))


if __name__=='__main__': main()
