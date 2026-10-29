"""Declared comparisons; independent scientific statuses, never a quantum PASS."""
import numpy as np
from .diagnostics import conditional_fraction

STRUCTURE=['pL01','pL12','pL02','ell01','ell12','ell02','inventory','pump','break']

def summarize(results,pairs,mode):
    errors={}
    for p in pairs.values():
        for section,values in p.get('errors',{}).items():
            for k,v in values.items():errors[k]=max(errors.get(k,0.),v)
    numerical_valid=bool(pairs) and all(p['pass_gate'] for p in pairs.values())
    en=errors.get('h',0.);threshold=max(1e-5,10*en)
    werror=max([v for k,v in errors.items() if k.startswith('W_s')]+[0.])
    wthreshold=max(1e-8,10*werror)
    cases=[];lookup={};joint=[]
    for r in results:
        s=r['summary'];a=r['series'];d=r['diagnostics'];ref=s['reference'];case=s['case']
        ng=[];fractions=[]
        for state in range(9):
            w=d[:,1+r['dnames'].index(f'W_s{state}')];finite=np.isfinite(w)
            minimum=float(min(w[finite])) if any(finite) else None
            ng.append(dict(state=state,minimum=minimum,threshold=wthreshold,
                status=('GME_CERTIFIED' if numerical_valid and minimum is not None and minimum < -wthreshold
                        else 'GME_NOT_CERTIFIED_BY_THIS_FAMILY'),
                numerical_context='paired_global_error_screen' if numerical_valid else 'not_numerically_certified'))
        last=dict(zip(r['names'],a[-1,1:]))
        for m in range(8):fractions.append(dict(mask=m,
            fK=conditional_fraction(last[f'k_m{m}'],last[f'w1_m{m}']),
            fD=conditional_fraction(last[f'd_m{m}'],last[f'w1_m{m}'])))
        joint.append(dict(id=case['id'],GME=ng,endpoint_fractions=fractions,
                          pair_negativity_max={k:float(np.nanmax(d[:,1+i])) for i,k in enumerate(r['dnames']) if k.startswith('pair_N_')}))
        if ref is not None and case['dt']==.01:
            lookup[(case['model'],case['phi_over_pi'],case['detuning'],case['dephasing'])]=s
        cases.append(s)
    gaps=[]
    for key,s in lookup.items():
        model,phi,eps,gamma=key
        if model!='QS':continue
        for control in ('RR_QS','IC1_QS'):
            other=lookup.get((control,phi,eps,gamma))
            if other is None:continue
            q=s['reference'];c=other['reference'];gap=q['h']-c['h']
            denom=max(abs(q['h']),1e-8)
            gaps.append(dict(control=control,phi_over_pi=phi,detuning=eps,dephasing=gamma,
                delta_h=gap,QS_h=q['h'],control_h=c['h'],denominator_QS=denom,
                relative_gap=gap/denom,I12_gap=q['I12']-c['I12'],I02_gap=q['I02']-c['I02'],
                scope='SCREENING_SIGNAL' if abs(gap)>threshold else 'no_resolved_gap',
                stationary=s['stationarity']['pass_gate'] and other['stationarity']['pass_gate']))
    phase=[]
    for key,s in lookup.items():
        model,phi,eps,gamma=key
        if phi==0:continue
        base=lookup.get((model,0,eps,gamma))
        if base is None:continue
        q=s['reference'];b=base['reference']
        shift=max(abs(q[k]-b[k])/max(abs(b[k]),1e-8) for k in STRUCTURE)
        phase.append(dict(model=model,phi_over_pi=phi,detuning=eps,dephasing=gamma,
            delta_h=q['h']-b['h'],threshold=threshold,
            status='flux_response' if abs(q['h']-b['h'])>threshold else 'no_resolved_response',
            structural_relative_max=shift,population_status='population_near_matched' if shift<=.01 else 'population_coupled_response'))
    interaction=[]
    gmap={(g['control'],g['phi_over_pi'],g['detuning'],g['dephasing']):g['delta_h'] for g in gaps}
    for control in ('RR_QS','IC1_QS'):
        for eps in (-.5,0.,.5):
            for gamma in (0.,.25):
                keys=[(control,.5,eps,gamma),(control,0,eps,gamma),(control,.5,eps,.05),(control,0,eps,.05)]
                if all(k in gmap for k in keys):
                    v=gmap[keys[0]]-gmap[keys[1]]-gmap[keys[2]]+gmap[keys[3]]
                    interaction.append(dict(control=control,detuning=eps,dephasing=gamma,gamma0=.05,value=v,
                        status='gap_flux_response' if abs(v)>threshold else 'no_resolved_gap_response'))
    gap_phase=[]
    for key,value in gmap.items():
        control,phi,eps,gamma=key
        base=(control,0.,eps,gamma)
        if phi!=0 and base in gmap:
            delta=value-gmap[base]
            gap_phase.append(dict(control=control,phi_over_pi=phi,detuning=eps,dephasing=gamma,value=delta,threshold=threshold,status='gap_flux_response' if abs(delta)>threshold else 'no_resolved_gap_response'))
    spans=[]
    for model in ('QS','RR_QS','IC1_QS'):
        values={phi:lookup[(model,phi,0.,.05)]['reference']['h'] for phi in (0.,.5,-.5,1.) if (model,phi,0.,.05) in lookup}
        if len(values)==4:spans.append(dict(model=model,span=max(values.values())-min(values.values()),
            h_by_phi_over_pi=values,plus_minus_difference=values[.5]-values[-.5]))
    return dict(cases=cases,joint=joint,gaps=gaps,phase=phase,interactions=interaction,gap_phase=gap_phase,flux_spans=spans,
                numerical_errors=errors,screening_threshold=threshold,GME_threshold=wthreshold,
                numerical_valid=numerical_valid,Fano_status='NOT_ESTABLISHED',mode=mode)
