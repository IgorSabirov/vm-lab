"""Nonlinear controlled BBN replay on a prescribed common thermal history."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np
from scipy.integrate import solve_ivp
from scipy.interpolate import PchipInterpolator


def run(corpus,primat,history,output,cv2):
    from replay import archive_baseline, compare_saved, MAP
    from response import trajectory_grid

    raw=subprocess.check_output([sys.executable,str(corpus/'bbn/signal_check.py'),
                                 '--primat',str(primat),'--vm_lab',str(history)])
    (output/'bbn_replay.json').write_bytes(raw)
    previous=json.loads(raw)
    compare_saved(previous,json.loads((corpus/'bbn/SIGNAL_CHECKS.json').read_text()))
    with tempfile.TemporaryDirectory() as tmp:
        folder=Path(tmp)
        archive_baseline(history,folder)
        t9,ys,rho,rates,dt,final,kernel,selected,_=trajectory_grid(primat,folder,4,2.)
        with np.load(folder/'primat.npz') as file:
            times=file['time_s']
            t0=times[-1]-dt.sum()
            y0=PchipInterpolator(np.log(times),file['Y'],axis=0)(np.log(t0))
        x=np.r_[0,np.cumsum(dt)]
        mids=(x[1:]+x[:-1])/2
        fields=np.column_stack((rho,t9,rates))
        def solve(clock,change,rtol):
            def evaluate(t,y,jac):
                k=np.clip(np.searchsorted(mids,t),1,len(mids)-1)
                weight=np.clip((t-mids[k-1])/(mids[k]-mids[k-1]),0.,1.)
                density,temp,*speed=fields[k-1]*(1-weight)+fields[k]*weight
                f=1. if clock=='standard' else (3. if clock=='triple' else 1.+2.*temp/(1.+temp))
                speed=np.asarray(speed)/f
                i=2+2*selected[0]
                speed[i:i+2]*=change
                # Coordinate is reference history time. Physical dt_new/dt_ref=f.
                return f*(kernel.jacobian(y,density,speed) if jac else kernel.rhs(y,density,speed))
            sol=solve_ivp(lambda t,y:evaluate(t,y,False),(0,x[-1]),y0,method='BDF',
                          rtol=rtol,atol=rtol*1e-10,jac=lambda t,y:evaluate(t,y,True))
            assert sol.success
            y=sol.y[:,-1]
            baryons=np.array([1,1,2,3,3,4,7,7])@sol.y
            assert np.ptp(baryons)<1e-8
            return np.array([y[2]/y[1],4*y[5]])
        solutions={name:solve(clock,factor,1e-8) for name,clock,factor in [
            ('standard','standard',1.),('common_3','triple',1.),('common_T','variable',1.),
            ('dp_plus_1pct','standard',1.01),('dp_minus_1pct','standard',.99)]}
        fine=solve('standard',1.,2e-9)
        relative={key:value/solutions['standard']-1 for key,value in solutions.items()}
        error=np.abs(fine/solutions['standard']-1)
        null=max(np.max(abs(relative[k])) for k in ('common_3','common_T'))
        assert null < 1e-5 and relative['dp_plus_1pct'][0]<0<relative['dp_minus_1pct'][0]
        archive_values=np.array([final[2]/final[1],4*final[5]])
    marks=previous['spectrum_tests']['marks']
    conditional={}
    for law in ['GOE','GUE']:
        pos=np.square(marks[law]['equal']['obs_sd'])
        white=np.square(marks[law]['common_chi2_2']['obs_sd'])-pos
        conditional[law]=np.sqrt(pos+cv2*white).tolist()
    return dict(primat_commit=MAP['sources']['primat']['commit'],output_order=['D/H','Yp'],
        common_clock_max_relative_difference=null,tolerance_refinement_relative=error.tolist(),
        observables={k:v.tolist() for k,v in solutions.items()},
        fractional_change={k:v.tolist() for k,v in relative.items()},
        baseline_vs_archived_relative=(solutions['standard']/archive_values-1).tolist(),
        common_cv2_conditional_BBN_sd_in_obs_sigma=conditional,
        assumption='Independent marks, 10% fictional line fraction and 10 keV spacing, same Fe train CV2 for both ensembles. No Fe channel in BBN.')
