"""Deterministic predeclared design; runtime main forecast is filled from calibration."""
import json
from pathlib import Path


def make(mode):
    base=dict(J=1.,g=.5,eta=.25,delta=.1,kappa_in=.5,kappa_out=.5,phi_e=.05,gamma_r=.05,gamma_bg=.01)
    variants=['PP','PQ','PS','QP','QQ','QS']
    models={}
    for level,phi in [('base',.05),('n0',0.),('n05',.5)]:
        for v in variants:
            models[level+'_'+v]=dict(base,phi_n=phi,gate_form='Pi' if v[0]=='P' else 'Q',gate_idle='Pi' if v[1]=='P' else v[1])
    cases=[]
    for mid in models:
        level=mid.split('_')[0]
        if mode=='main' and level=='base':
            for i in range(4):cases.append(dict(id=f'{mid}_p{i}',model=mid,state='phase',phase_index=i,dt=.01,horizon=200.))
        cases.append(dict(id=mid+'_mix',model=mid,state='mix',dt=.01,horizon=10. if mode=='calibration' else 200.))
        if level=='base':cases.append(dict(id=mid+'_fine',model=mid,state='mix',dt=.005,horizon=5. if mode=='calibration' else 200.))
    return {'experiment_id':'E001X_SQRT','version':'v001','mode':mode,'models':models,'cases':cases,
        'integration':{'dt':.01,'observable_interval':.2,'rho_interval':1.,'positivity_interval':5.,'heartbeat_seconds':5},
        'stationarity':{'relative_rhs':1e-6,'relative_flux_range':1e-4,'relative_rho_change':1e-5},
        'acceptance':{'algebra':1e-10,'trace':1e-8,'hermiticity':1e-8,'positivity':1e-7,
                      'expm_reference_relative':2e-6,'refinement_observables':2e-5,'mixture_error':2e-7,'disk_floor_bytes':1500000000},
        'practical_relative_effect':.001,
        'runtime_forecast':{'expected_seconds':100.,'lower_seconds':40.,'upper_seconds':160.,
            'reference':'Uncalibrated short SQRT benchmark: 24x1000 steps plus 18 preflight x300 steps. CONT measured ~0.00246 s/step including I/O. Extra model construction, preflight/expm, report provisionally budgeted ~28 s. Not a main-run forecast.',
            'uncalibrated':True} if mode=='calibration' else None,
        'retention':{'full':'all states every 1 and all 164 observables every .2','report':'RESULT.md <=24KiB; all cases; 31 specified series observables .2 through 20 then 2; global all-observable extrema/mean/std over every sample; counts and failures; snapshots not published'},
        'no_early_stopping':True,'conditional_extensions':False,'automatic_reboot_resume':False,
        'parent_model_commit':'f0c182527a9d1fd9208a56cbb1894d82510e4c79',
        'primary_question':'Compare PS-PP and QS-QP flow at T200 at fixed formation; rate/action control PS-PQ and QS-QQ; no damage/recovery in this run.',
        'predictions_not_acceptance':{'time':100,'QS_F':[.1102,.1111],'PS_F':[.1121,.1126]},
        'interpretation_limits':['Own-channel protection is not a full dark subspace or BIC.','P and S do not match all-state event rates.','Currents are signed and sink storage term must be retained.','Only base has full-horizon step-halving and four-phase ensemble checks.','No E002, J0, self-repair or quantum-advantage claim.']}


if __name__=='__main__':
    root=Path(__file__).resolve().parent.parent
    for mode in ['calibration','main']:
        (root/f'sqrt_config_{mode}.json').write_text(json.dumps(make(mode),ensure_ascii=False,indent=2)+'\n')
