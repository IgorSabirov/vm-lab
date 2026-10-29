"""Design and deterministic RR rates; no optimizer or damage-result fitting."""
import json
from pathlib import Path
EDGES=['01','12','02']

def rates(target,delta=.1,bg=.01,factor=1):
    result={}
    for e in EDGES:
        l=target['pL'+e];r=target['pR'+e];idle=target['event_rate__idle_'+e]
        if min(l,r)<=1e-8:raise ValueError('Degenerate matching target')
        beta=idle/l;alpha=(delta+bg+beta)*l/r
        result[e]=[factor*alpha,factor*(beta+delta+bg)-delta-bg]
        if min(result[e])<=0:raise ValueError('Nonpositive rate')
    return result

def make(target):
    base=dict(J=1.,g=.5,eta=.25,delta=.1,kappa_in=.5,kappa_out=.5,phi_n=.05,phi_e=.05,gamma_r=.05,gamma_bg=.01)
    models={}
    for v in ['PP','PQ','PS','QP','QQ','QS']:
        models[v]={**base,'gate_form':'Pi' if v[0]=='P' else 'Q','gate_idle':{'P':'Pi','Q':'Q','S':'S'}[v[1]]}
    for v,factor in [('RR',1),('RR2',2)]:models[v]={**base,'g':0.,'gamma_r':0.,'gate_form':'Q','gate_idle':'Q','rr_rates':rates(target,factor=factor)}
    models['PP_J0']={**models['PP'],'J':0.};models['RR_J0']={**models['RR'],'J':0.}
    cases=[]
    for v in models:
        ds=['none','link']+(['feed'] if v in ['PP','QQ','RR'] else [])+(['resource','hard'] if v in ['PP','RR'] else [])
        for damage in ds:
            for label,dt in [('coarse',.01),('fine',.005)]:
                if label=='fine' and damage in ['resource','hard']:continue
                cases.append(dict(id=f'{v}_{damage}_{label}',model=v,damage=damage,dt=dt,horizon=300.,damage_time=200.))
    n=sum(round(c['horizon']/c['dt']) for c in cases)
    expected=n*(1567.6807916164398/720000)+90
    return dict(experiment_id='E002',version='v001',models=models,cases=cases,rr_target=target,
      rr_target_source={'run':'E001X_J0_GH_v001_r001','report_commit':'d4a20d665dca2e263917269699b53254620c12b5','case':'j1_PP_fine','selection':'T200 endpoint, stationary before any damage; rates frozen in config. New PP pre-damage window must reproduce matching targets.'},
      observable_interval=.2,rho_interval=2.,rho_start=196.,positivity_interval=10.,pre_window=10.,
      acceptance=dict(algebra=1e-10,trace=1e-8,hermiticity=1e-8,positivity=1e-7,expm_reference_relative=2e-6,refinement_observables=2e-5,disk_floor_bytes=1500000000),
      stationarity=dict(relative_rhs=1e-6,relative_rho_change=1e-5,absolute_flux_range=1e-10,relative_flux_range=1e-4),
      matching_tolerance=.10,full_file_limit=4500,required_free_disk_bytes=4000000000,
      runtime_forecast=dict(expected_seconds=expected,lower_seconds=.6*expected,upper_seconds=1.4*expected,main_steps=n,preflight_steps=300*len(models),
        formula='main_steps * (1567.6807916164398 / 720000) + 90 seconds',reference='J0 whole-process VM timing, report d4a20d665dca2e263917269699b53254620c12b5',
        assumptions=['Proxy from prior full job, not pure RK4 rate. +90 seconds setup/extra reporting allowance. No RR optimization.',
                     '+/-40% engineering convention, not a confidence interval. RR operator sparsity and I/O differ.',
                     'Each branch repeats T200 preparation; no hidden preparation reuse; no conditional extensions.']),
      no_early_stopping=True,automatic_resume=False)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='config.json');args=parser.parse_args()
    target=json.loads(Path('data/e002_rr_target.json').read_text())
    Path(args.output).write_text(json.dumps(make(target),indent=2)+'\n')
