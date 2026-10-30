"""Frozen E002d grid: primary matched pairs and secondary dose ladder."""
MODELS=('QS','RR_QS')
DOSES=(.05,.1,.2)

def case(model,target,kind,gamma,dt,horizon):
    tag='base' if target=='base' else f'{target}_{kind}_g{round(gamma*1000):03d}'
    return dict(id=f'{model}_{tag}_dt{round(dt*1000):03d}',model=model,
        target=target,kind=kind,gamma=gamma,dt=dt,horizon=horizon,
        phi_over_pi=0.,detuning=0.,dephasing=.05,family='e002d')

def cases(mode):
    out=[]
    if mode=='production':
        for model in MODELS:
            for dt in (.005,.01):
                out.append(case(model,'base','base',0.,dt,200.))
                for target in ('A','B'):
                    for kind in ('T','C'):out.append(case(model,target,kind,.1,dt,200.))
                for gamma in (DOSES if dt==.005 else (.1,)):
                    for kind in ('T','C'):out.append(case(model,'AB',kind,gamma,dt,200.))
    elif mode=='calibration':
        for model in MODELS:
            for dt in (.005,.01):
                for target,kind,gamma in [('base','base',0.),('AB','T',.2),('AB','C',.2)]:
                    out.append(case(model,target,kind,gamma,dt,5.))
    elif mode=='smoke':
        for model in MODELS:
            for dt in (.005,.01):out.append(case(model,'AB','T',.1,dt,2.))
    else:raise ValueError('Unknown mode')
    return out

def counts(mode,horizon=None):
    cs=cases(mode)
    steps=sum(round((horizon or c['horizon'])/c['dt']) for c in cs)
    return dict(trajectories=len(cs),steps=steps,rhs_calls=4*steps)

CALIBRATION_FORECAST=dict(expected_seconds=45.,lower_seconds=10.,upper_seconds=150.,
    source='E002c calibrated full CSR/RK4 ~0.0017 s/step; 9000 steps plus 12 builds, diagnostics and export; provisional new-observable calibration')
