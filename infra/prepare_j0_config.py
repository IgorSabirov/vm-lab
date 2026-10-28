"""Generate fixed paired J0/J1 design using measured SQRT VM timings."""
import json
from pathlib import Path

VARIANTS = ['PP','PQ','PS','QP','QQ','QS']
# Verified GitHub SQRT report 2ad72395..., base mix/fine, seconds for T200.
VM_SECONDS = {
 'PP':[55.5814919960103,102.64511987101287],
 'PQ':[52.986584764003055,96.65532880599494],
 'PS':[52.09873516600055,97.76200510199124],
 'QP':[48.4487771490094,89.30044669201015],
 'QQ':[46.80319376400439,85.4411914049997],
 'QS':[46.277193104004255,82.54487899100059]}

def make():
    p = dict(J=1.,g=.5,eta=.25,delta=.1,kappa_in=.5,kappa_out=.5,
             phi_e=.05,gamma_r=.05,gamma_bg=.01,phi_n=.05)
    models={};cases=[];costs=[]
    for j in [0,1]:
        for variant in VARIANTS:
            mid=f'j{j}_{variant}'
            models[mid]={**p,'J':float(j),'gate_form':'Pi' if variant[0]=='P' else 'Q',
                         'gate_idle':{'P':'Pi','Q':'Q','S':'S'}[variant[1]]}
            for label,dt,seconds in zip(['mix','fine'],[.01,.005],VM_SECONDS[variant]):
                cases.append(dict(id=mid+'_'+label,model=mid,state='mix',dt=dt,horizon=200.))
                costs.append(dict(case_id=cases[-1]['id'],steps=round(200/dt),expected_seconds=seconds,
                                  timing_source='base_'+variant+'_'+label,proxy_for_J0=(j==0)))
    expected=sum(c['expected_seconds'] for c in costs)+30
    return dict(experiment_id='E001X_J0',version='v001',mode='main',models=models,cases=cases,
      integration=dict(dt=.01,observable_interval=.2,rho_interval=2.,positivity_interval=10.,heartbeat_seconds=5),
      stationarity=dict(relative_rhs=1e-6,relative_flux_range=1e-4,absolute_flux_range=1e-10,relative_rho_change=1e-5),
      acceptance=dict(algebra=1e-10,trace=1e-8,hermiticity=1e-8,positivity=1e-7,
                      expm_reference_relative=2e-6,refinement_observables=2e-5,mixture_error=2e-7,disk_floor_bytes=1500000000),
      practical_relative_effect=.001,
      runtime_forecast=dict(expected_seconds=expected,lower_seconds=.6*expected,upper_seconds=1.4*expected,
        reference='SQRT VM E001X_SQRT_GH_v001_r001; report commit 2ad72395cbd131ac10c46afdee75a860997f1a60; metrics SHA256 81551c1c86d3c91c0509ccd4976efee4c05775c0ece3cc76320e4436f394b936',
        cases=costs,setup_report_allowance_seconds=30,
        assumptions=['J0 uses same-variant measured J1 time as a proxy, NOT a measured J0 calibration.',
          'J0 may run faster with a sparser generator; checkpoints every 2 instead of 1 also reduce I/O.',
          'Range +/-40%; mismatch requires workload and timing breakdown review; no padding or sleeping.',
          '720000 main steps + 3600 preflight steps. No conditional extensions. Queue/publication excluded.']),
      primary_question='How much sink output survives switching off ready-link hopping? Paired J0/J1 for six gates; this is not additive attribution or damage recovery.',
      null_flux_tolerance=1e-10,ratio_denominator_floor=1e-8,
      ledger_absolute_tolerance=1e-4,ledger_relative_tolerance=1e-5,
      full_inventory_limit=4500,
      no_early_stopping=True,conditional_extensions=False,automatic_reboot_resume=False,
      retention={'full':'164 observables each .2; rho each 2; positivity each 10; no omission of cases',
                 'report':'RESULT <=24KiB, full regular ledger CSV each .2, 31-observable selected series and extrema, all-observable statistics'},
      interpretation_limits=['J0 disables hop, not link formation or existence.',
        'J0/J1 ratio is an intervention response, not the machine fraction in J1.',
        'Only base phi_n=.05; no phase ensemble, uniqueness proof, E002, BIC or quantum-advantage claim.'])

if __name__=='__main__':
    Path('j0_config.json').write_text(json.dumps(make(),ensure_ascii=False,indent=2)+'\n')
