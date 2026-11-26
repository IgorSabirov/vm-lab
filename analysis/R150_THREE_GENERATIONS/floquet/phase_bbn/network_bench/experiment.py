"""Run the frozen controls, parameter contrasts, matched-amplitude test and BBN kernels."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, replace
import json
import platform
import sys
import numpy as np
import scipy
from scipy.optimize import brentq
from bench import Config, History, solve, ROOT, OBS, KNOTS
from graph import TREF, target_x
from checks import audit, summarize


def dump(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,allow_nan=False,indent=2,default=lambda x:x.item())+'\n')


def run_case(task):
    name,c,out,save=task
    result=solve(History(),c,out/(name+'.csv') if save else None)
    return name,{'config':asdict(c),'result':result}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--jobs',type=int,default=1)
    p.add_argument('--output',type=__import__('pathlib').Path,default=ROOT/'results')
    args=p.parse_args(); out=args.output.resolve(); out.mkdir(parents=True,exist_ok=True)
    off=Config(J=target_x(3,.4)*TREF/2,lam=-.1*TREF)
    direct=replace(off,mode='direct')
    med=replace(direct,mode='mediator')
    full=replace(med,reverse=True)
    cases=dict(off=off,direct=direct,mediated=med,coupled=full,passive_A=replace(direct,layer='A'),
               fast=replace(med,tau=.02),slow=replace(med,tau=500.),
               no_forward=replace(full,forward=False),both_off=replace(med,forward=False),
               zero_contact=replace(med,lam=0.),
               self_only=replace(full,lam=0.),  # nuclear self-response, no graph coupling
               direct_positive=replace(direct,lam=-direct.lam),
               total_contact=replace(direct,full_contact=True),
               frozen=replace(direct,S=65.,p_initial=0.),thermal_barrier=replace(direct,thermal_c=24.),
               tight=replace(full,rtol=3e-9), tight_off=replace(off,rtol=3e-9),
               clock=replace(full,clock=3.),relative_clock=replace(full,graph_clock=.1),
               np_power_2p5=replace(full,forward_np_power=2.5),
               hot_relic=replace(off,relic_background=True),both_channels=replace(full,relic_background=True),
               early_H=replace(off,window_H='early'),late_H=replace(off,window_H='late'),
               L15_fixed_J=replace(direct,L=15,J=.15),
               L15_isocontrast=replace(direct,L=15,J=target_x(15,.4)*TREF/2),
               L5_isocontrast=replace(direct,L=5,J=target_x(5,.4)*TREF/2),
               L7_isocontrast=replace(direct,L=7,J=target_x(7,.4)*TREF/2),
               weak_feedback=replace(full,domains_per_baryon=100.),
               strong_feedback=replace(full,domains_per_baryon=.1),
               bias_table=replace(med,branch_file=str(ROOT/'data'/'illustrative_branch.csv')))
    pulse=.00030
    for i in range(len(KNOTS)):
        for sign in (-1,1):
            cases[f'kernel_{i}_{sign}']=replace(off,mode='imposed',pulse_MeV=sign*pulse,basis=i)
    for mag in (-pulse,pulse,pulse/2,-pulse/2):
        cases[f'uniform_{mag}']=replace(off,mode='imposed',pulse_MeV=mag)
    from branches import make_branch_table
    landmarks=make_branch_table(out/'BH_branches.csv')
    cases.update(algebraic_feedback=replace(full,mode='algebraic'),fast_feedback=replace(full,tau=.02),
                 comoving_domain=replace(direct,comoving_J=True),
                 bh_donor=replace(med,branch_file=str(out/'BH_branches.csv')))
    tasks=[(name,c,out,not name.startswith(('kernel','uniform'))) for name,c in cases.items()]
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        runs=dict(pool.map(run_case,tasks))
    h=History()
    # Remove the free contact amplitude as a discriminator: fit D/H and predict the other yields.
    target=runs['coupled']['result']['D_H']
    def residual(scale):
        return solve(h,replace(direct,lam=direct.lam*scale))['D_H']/target-1.
    scale=brentq(residual,.1,3.,xtol=.00005)
    name,fit=run_case(('refit_direct',replace(direct,lam=scale*direct.lam),out,True))
    runs[name]=fit
    table=np.genfromtxt(out/'coupled.csv',names=True,delimiter=',')
    np.savetxt(out/'imposed_history.csv',np.c_[table['Tgamma_MeV'][::-1],table['deltaBD_MeV'][::-1]],
               delimiter=',',header='T_MeV,deltaBD_MeV',comments='')
    name,fixed=run_case(('prescribed',replace(off,mode='imposed',profile_file=str(out/'imposed_history.csv')),out,True))
    fixed['config']['profile_file']='results/imposed_history.csv'
    runs[name]=fixed
    # Serialize the example table relative to the package for portability.
    runs['bias_table']['config']['branch_file']='data/illustrative_branch.csv'
    runs['bh_donor']['config']['branch_file']='results/BH_branches.csv'
    dump(out/'bh_landmarks.json',landmarks)
    dump(out/'paired_runs.json',runs)
    dump(out/'finite_model.json',audit(h))
    summary=summarize(h,runs,out,pulse,scale)
    from energy import energy_audit
    dump(out/'energy.json',energy_audit(h,out))
    summary['versions']={'python':platform.python_version(),'numpy':np.__version__,'scipy':scipy.__version__}
    dump(out/'analysis.json',summary)
    if not all(summary['checks'].values()): raise SystemExit('A validation failed; see analysis.json')
    print(f'{len(runs)} saved cases; all validation checks passed',flush=True)


if __name__=='__main__': main()
