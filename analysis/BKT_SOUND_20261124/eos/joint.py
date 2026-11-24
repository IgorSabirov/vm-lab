"""Six speed pairs share four calibration parameters, with explicit Gaussian pulls."""
import numpy as np
from scipy.optimize import least_squares
from inversion import D0, EquationOfState
CAL_SIGMA=np.array([.15,.10,.05,.03/.64])
NAMES=['density','absolute_temperature','wavevector','coupling']

def gradient(func, params):
    steps=2e-5*np.maximum(1.,abs(params))
    return np.column_stack([(func(params+step)-func(params-step))/(2*size)
                            for step,size in zip(np.diag(steps),steps)])

def fit(rows, rho=0.,anchor=0., extra_starts=3):
    t,dt,u,du,v,dv=np.array([[r[k] for k in ('T_over_Tc','err_T','c1','err_c1','c2','err_c2')]
                             for r in rows]).T
    count=len(t)
    def model(p):
        n,T,q,gs=1+CAL_SIGMA*p[:4]
        X=p[4:4+count];z=p[4+count:]
        state=EquationOfState(.64*gs,anchor).at_X(X)
        tf=D0*n/(T*state.D)
        fast,slow=state.speeds(z)
        factor=q*np.sqrt(n*gs)
        ds=state.D*z**2/(state.H+z**2)
        return tf,fast*factor,slow*factor,ds
    def resid(p):
        tf,uf,vf,_=model(p)
        a=(uf-u)/du; b=(vf-v)/dv
        return np.r_[p[:4],(tf-t)/dt,a,(b-rho*a)/np.sqrt(1-rho*rho)]
    eos=EquationOfState()
    x0=[eos.state(D0/t0).X for t0 in t]
    initial=np.r_[[0.]*4,x0,np.ones(count)]
    lower=np.r_[np.full(4,-3.),np.full(count,-.7),np.zeros(count)]
    upper=np.r_[np.full(4,3.),np.full(count,1.4),np.full(count,4.)]
    # The narrow knots of the numerical EOS can create local minima in X.
    # Starts cross the critical region in both directions.
    shifts=[0,-.08,.08,-.18,.18,-.32,.32][:1+extra_starts]
    fits=[]
    for shift in shifts:
        start=initial.copy()
        start[4:4+count]+=shift
        sol=least_squares(resid,np.clip(start,lower+1e-7,upper-1e-7),bounds=(lower,upper),
                          max_nfev=300,ftol=1e-9,xtol=1e-9,gtol=1e-9)
        if sol.success: fits.append(sol)
    best=min(fits,key=lambda x:x.cost)
    tf,uf,vf,ds=model(best.x)
    J=gradient(resid,best.x)
    vcov=np.linalg.pinv(J.T@J,rcond=1e-12)
    dJ=gradient(lambda p:model(p)[3],best.x)
    ds_cov=dJ@vcov@dJ.T
    return dict(Ds=ds,sd_local=np.sqrt(np.diag(ds_cov)),cov_Ds_local=ds_cov,chi2=2*best.cost,
                dof=count,used_T_over_Tc=t,fitted_T_over_Tc=tf,fit_speeds=np.column_stack([uf,vf]),
                calibration_names=NAMES,pulls=best.x[:4],relative_scales=1+CAL_SIGMA*best.x[:4],
                chi2_calibration=float(best.x[:4]@best.x[:4]),rho=rho,pressure_anchor_X=anchor,
                start_chi2=[2*s.cost for s in fits],active_bounds=best.active_mask.tolist(),
                fitted_X=best.x[4:4+count],fit_z=best.x[4+count:],cond_J=np.linalg.cond(J))
