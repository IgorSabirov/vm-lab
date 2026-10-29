"""Metrics operate only on the post-intervention recovery window."""
import numpy as np
from scipy.integrate import simpson

def integral(t,y):return float(simpson(y,x=t))

def deficit(t,y,reference,floor):
    if reference<=floor:return None
    return integral(t,np.maximum(0.,1-np.asarray(y)/reference))

def recovery(t,a,ref,ppref,baseline_qf):
    q={k:integral(t,a[k]) for k in ['sink_flux','I_hop_sink','I_form_sink','I_idle_sink','pump_flux','break_flux']}
    q['stored']=float(a['n2'][0]-a['n2'][-1])
    q['residual']=q['sink_flux']-sum(q[k] for k in ['I_hop_sink','I_form_sink','I_idle_sink','stored'])
    q['inventory_change']=float(a['inventory'][-1]-a['inventory'][0])
    q['inventory_residual']=q['inventory_change']-q['pump_flux']+q['break_flux']
    floor=max(1e-8,.01*baseline_qf)
    shares={k:q[k]/q['sink_flux'] for k in ['I_hop_sink','I_form_sink','I_idle_sink','stored']} if q['sink_flux']>floor else None
    return dict(Lambda_hop=deficit(t,a['I_hop_sink'],ref['I_hop_sink'],max(1e-8,.05*ppref['I_hop_sink'])),
      Lambda_total=deficit(t,a['sink_flux'],ref['sink_flux'],max(1e-8,.01*ppref['sink_flux'])),
      integrals=q,shares=shares,machine_share=(shares['I_form_sink']+shares['I_idle_sink']) if shares else None,
      QF_min=floor,flow_per_pump=q['sink_flux']/q['pump_flux'] if q['pump_flux']>1e-8 else None)

def classify(pp,rr,matched,valid):
    if not valid or pp['Lambda_hop'] is None or rr['Lambda_hop'] is None:return 'metric_undefined'
    if not matched:return 'RR_matched_poorly'
    if pp['Lambda_hop']>50:return 'no_repair_within_window'
    if rr['Lambda_hop']<=1e-8:return 'control_deficit_too_small'
    if pp['Lambda_hop']>.7*rr['Lambda_hop']:return 'repair_not_better_than_control'
    if pp.get('guard_passed') is None:return 'metric_undefined'
    if not pp['guard_passed']:return 'machine_heavy_recovery'
    return 'network_repair_controlled'
