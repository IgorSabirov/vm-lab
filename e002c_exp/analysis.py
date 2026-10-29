"""Separate stationary screening from comparisons on the fixed [190,200] window."""
import numpy as np
from .diagnostics import conditional_fraction,coherence_quality
from .comparability import comparison_gate,response_status

STRUCTURE=['pL01','pL12','pL02','ell01','ell12','ell02','inventory','pump','break']

def comparison_tables(summaries,numerical_screen_pass,threshold,kind='stationary'):
    refkey='reference' if kind=='stationary' else 'transition_reference'
    lookup={}
    for s in summaries:
        c=s['case']
        if c['dt']!=.01 or c.get('family') in ('fit','validation','calibration'):continue
        key=(c['model'],c['phi_over_pi'],c['detuning'],c['dephasing'])
        if key in lookup:raise ValueError('Duplicate physics point in comparison table')
        lookup[key]=s
    def gate(records):return comparison_gate(records,numerical_screen_pass,kind)
    def value(s,field):return s[refkey][field] if s.get(refkey) is not None else None
    def difference(a,b):return None if a is None or b is None else a-b
    def status(c,v,label='flux_response',negative='no_resolved_response'):
        return response_status(c,v is not None and abs(v)>threshold,label,negative)
    gaps=[];gap_records={}
    for key,q in lookup.items():
        model,phi,eps,gamma=key
        if model!='QS':continue
        for control in ('RR_QS','IC1_QS'):
            r=lookup.get((control,phi,eps,gamma))
            if r is None:continue
            comp=gate([q,r]);qh=value(q,'h');rh=value(r,'h');delta=difference(qh,rh)
            denom=max(abs(qh),1e-8) if qh is not None else None
            row=dict(control=control,phi_over_pi=phi,detuning=eps,dephasing=gamma,
                     delta_h=delta,QS_h=qh,control_h=rh,denominator_QS=denom,
                     relative_gap=delta/denom if delta is not None else None,
                     I12_gap=difference(value(q,'I12'),value(r,'I12')),
                     I02_gap=difference(value(q,'I02'),value(r,'I02')),
                     comparison=comp,status=status(comp,delta,'transport_gap','no_resolved_gap'))
            gaps.append(row);gap_records[(control,phi,eps,gamma)]=(row,[q,r])
    phase=[]
    for key,s in lookup.items():
        model,phi,eps,gamma=key
        if phi==0:continue
        base=lookup.get((model,0,eps,gamma))
        if base is None:continue
        comp=gate([s,base]);delta=difference(value(s,'h'),value(base,'h'))
        shift=max(abs(s[refkey][k]-base[refkey][k])/max(abs(base[refkey][k]),1e-8) for k in STRUCTURE) if s.get(refkey) is not None and base.get(refkey) is not None else None
        phase.append(dict(model=model,phi_over_pi=phi,detuning=eps,dephasing=gamma,
            delta_h=delta,threshold=threshold,comparison=comp,status=status(comp,delta),
            structural_relative_max=shift,population_status=('not_comparable' if not comp['comparable'] else
            ('population_near_matched' if shift<=.01 else 'population_coupled_response'))))
    interactions=[]
    for control in ('RR_QS','IC1_QS'):
        for eps in (-.5,0.,.5):
            for gamma in (0.,.25):
                keys=[(control,.5,eps,gamma),(control,0,eps,gamma),(control,.5,eps,.05),(control,0,eps,.05)]
                if not all(k in gap_records for k in keys):continue
                rows=[gap_records[k][0] for k in keys];records=[s for k in keys for s in gap_records[k][1]]
                comp=gate(records);v=[r['delta_h'] for r in rows];delta=v[0]-v[1]-v[2]+v[3] if all(x is not None for x in v) else None
                interactions.append(dict(control=control,detuning=eps,dephasing=gamma,gamma0=.05,value=delta,
                    comparison=comp,status=status(comp,delta,'gap_flux_response','no_resolved_gap_response')))
    gap_phase=[]
    for key,(row,records) in gap_records.items():
        control,phi,eps,gamma=key;base=(control,0.,eps,gamma)
        if phi==0 or base not in gap_records:continue
        brow,brecords=gap_records[base];comp=gate(records+brecords);delta=difference(row['delta_h'],brow['delta_h'])
        gap_phase.append(dict(control=control,phi_over_pi=phi,detuning=eps,dephasing=gamma,value=delta,
            threshold=threshold,comparison=comp,status=status(comp,delta,'gap_flux_response','no_resolved_gap_response')))
    spans=[]
    for model in ('QS','RR_QS','IC1_QS'):
        keys=[(model,phi,0.,.05) for phi in (0.,.5,-.5,1.)]
        if not all(k in lookup for k in keys):continue
        records=[lookup[k] for k in keys];comp=gate(records);values={str(k[1]):value(s,'h') for k,s in zip(keys,records)}
        ok=all(v is not None for v in values.values());span=max(values.values())-min(values.values()) if ok else None
        spans.append(dict(model=model,span=span,h_by_phi_over_pi=values,
            plus_minus_difference=difference(values['0.5'],values['-0.5']),comparison=comp,status=status(comp,span)))
    return dict(gaps=gaps,phase=phase,interactions=interactions,gap_phase=gap_phase,flux_spans=spans)

def summarize(results,pairs,mode):
    errors={}
    for p in pairs.values():
        for section,values in p.get('errors',{}).items():
            for k,v in values.items():errors[k]=max(errors.get(k,0.),v)
    numerical_valid=bool(pairs) and all(p['pass_gate'] for p in pairs.values())
    threshold=max(1e-5,10*errors.get('h',0.))
    wthreshold=max(1e-8,10*max([v for k,v in errors.items() if k.startswith('W_s')]+[0.]))
    cases=[];joint=[]
    for r in results:
        s=r['summary'];a=r['series'];d=r['diagnostics'];case=s['case'];ng=[];fractions=[]
        for state in range(9):
            w=d[:,1+r['dnames'].index(f'W_s{state}')];finite=np.isfinite(w)
            minimum=float(min(w[finite])) if any(finite) else None
            ng.append(dict(state=state,minimum=minimum,threshold=wthreshold,
                status=('GME_CERTIFIED' if numerical_valid and minimum is not None and minimum < -wthreshold else 'GME_NOT_CERTIFIED_BY_THIS_FAMILY'),
                numerical_context='paired_global_error_screen' if numerical_valid else 'not_numerically_certified'))
        last=dict(zip(r['names'],a[-1,1:]))
        for m in range(8):fractions.append(dict(mask=m,
            fK=conditional_fraction(last[f'k_m{m}'],last[f'w1_m{m}']),fD=conditional_fraction(last[f'd_m{m}'],last[f'w1_m{m}'])))
        row=a[np.argmin(abs(a[:,0]-d[-1,0]))];coherences=[]
        for m in (7,6):
            weight=float(row[1+r['names'].index(f'p_m{m}')]);vals={}
            for prefix in ('C','c'):
                v=[d[-1,1+r['dnames'].index(f'{prefix}01_m{m}_{part}')] for part in ('re','im')]
                vals[prefix]=[float(x) for x in v] if np.isfinite(v).all() else None
            coherences.append(dict(mask=m,time=float(d[-1,0]),weight=weight,status=coherence_quality(weight),
                                   unnormalized=vals['C'],conditional=vals['c']))
        joint.append(dict(id=case['id'],GME=ng,endpoint_fractions=fractions,coherences=coherences,
            pair_negativity_max={k:float(np.nanmax(d[:,1+i])) for i,k in enumerate(r['dnames']) if k.startswith('pair_N_')}))
        cases.append(s)
    return dict(cases=cases,joint=joint,**comparison_tables(cases,numerical_valid,threshold),
        transition_comparisons=comparison_tables(cases,numerical_valid,threshold,'transition_200'),
        numerical_errors=errors,screening_threshold=threshold,GME_threshold=wthreshold,
        numerical_valid=numerical_valid,Fano_status='NOT_ESTABLISHED',mode=mode)
