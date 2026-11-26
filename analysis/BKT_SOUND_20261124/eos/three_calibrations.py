"""One calibration per instrument scale for all six Cambridge conditions."""
from functools import lru_cache
import numpy as np
from scipy.optimize import least_squares

from inversion import D0, DomainError, EquationOfState
from joint import CAL_SIGMA


def fit_all(rows, fixed_records, previous, density_component):
    # Readbacks in each condition: t, u1, u2, f2, fsum. The five calibration
    # pulls are common to all rows. Remaining unreported correlations are zero
    # in these scenarios. The gain represents a 5% uncertainty in response.
    fields=('T_over_Tc','c1','c2','author_f2','author_fsum')
    errors=('err_T','err_c1','err_c2','err_f2','err_fsum')
    obs=np.array([[r[k] for k in fields] for r in rows])
    sd=np.array([[r[k] for k in errors] for r in rows])
    width=np.r_[CAL_SIGMA,.05]
    count=len(rows)
    block=np.tile(np.eye(5), (count,1,1))
    if density_component:
        for i,(y,s) in enumerate(zip(obs,sd)):
            # Published bootstrap at fixed nominal T: t ~ 1/n, uj ~ 1/sqrt(n).
            loading=np.r_[1., .5*y[1:3]*s[0]/(y[0]*s[1:3]),0.,0.]
            if np.max(abs(loading))>1:
                raise ValueError('Marginal errors cannot accommodate a shared density term')
            block[i]=np.outer(loading,loading)+np.diag(1-loading**2)
    whitening=np.linalg.inv(np.linalg.cholesky(block))
    @lru_cache(maxsize=64)
    def equation(g):
        return EquationOfState(g)
    def model(p):
        n,T,q,g,gain=1+width*p[:5]
        x,z=np.split(p[5:],2)
        s=equation(.64*g).at_X(x)
        u,v=s.speeds(z)
        f=(z*z-v*v)/(u*u-v*v)
        c=q*np.sqrt(n*g)
        prediction=np.column_stack((D0*n/(T*s.D),c*u,c*v,gain*f,np.full(count,gain)))
        return prediction, s.D*z*z/(s.H+z*z)
    def residual(p):
        try:
            pred,_=model(p)
        except DomainError:
            return np.full(5+5*count,1e5)
        return np.r_[p[:5],np.einsum('ijk,ik->ij',whitening,(pred-obs)/sd).ravel()]
    low=np.r_[np.full(5,-3.),np.full(count,-.7),np.zeros(count)]
    high=np.r_[np.full(5,3.),np.full(count,1.4),np.full(count,4.)]
    old=np.r_[previous['pulls'],0.,previous['fitted_X'],previous['fit_z']]
    seeds=[old]
    for mode in ['fixed','free']:
        seeds.append(np.r_[np.zeros(5),[r[mode]['X'] for r in fixed_records],
                           [r[mode]['z'] for r in fixed_records]])
    for shift in [-.14,.14,-.30,.30]:
        p=old.copy()
        p[5:5+count]+=shift
        seeds.append(p)
    # Either ordering is fitted separately. Transform the last X to a
    # fraction of the interval on the allowed side of the preceding X.
    def solve(direction, starts):
        ia, ib = 5+count-2, 5+count-1
        lb, ub = low.copy(), high.copy()
        boundary = low[ib] if direction == 'B_warmer' else high[ib]
        if direction:
            lb[ib], ub[ib] = 0., 1.
        def unpack(v):
            p=v.copy()
            if direction:
                p[ib] = p[ia]+v[ib]*(boundary-p[ia])
            return p
        def fun(v):
            return residual(unpack(v))
        attempts=[]
        for seed in starts:
            v=np.clip(seed,low+1e-7,high-1e-7)
            if direction:
                v[ib]=(v[ib]-v[ia])/(boundary-v[ia])
            sol=least_squares(fun,np.clip(v,lb+1e-7,ub-1e-7),bounds=(lb,ub),
                              max_nfev=550,xtol=2e-8,ftol=2e-8,gtol=2e-8)
            attempts.append(sol)
        # An unfinished iterate is still a feasible witness. Report its
        # convergence explicitly, including when it beats a converged start.
        best=min(attempts,key=lambda s:s.cost)
        p=unpack(best.x)
        pred,ds=model(p)
        report=dict(loss=2*best.cost, nominal_dof=5*count-2*count,
                    scale_names=['n','T','q','g','response_gain'],scales=(1+width*p[:5]).tolist(),
                    pulls=p[:5].tolist(),fitted_t=pred[:,0].tolist(),Ds=ds.tolist(),
                    predicted=pred.tolist(),active_bounds=best.active_mask.tolist(),
                    best_converged=bool(best.success),converged_starts=sum(bool(s.success) for s in attempts),
                    total_starts=len(attempts),start_losses=[2*s.cost for s in attempts],
                    cond_J=float(np.linalg.cond(best.jac)))
        return p,report
    p,free=solve(None,seeds)
    output={'unconstrained':free}
    warm_seed=p.copy()
    warm_seed[5+count-2:5+count]=warm_seed[5+count-2:5+count][::-1]
    for direction in ['B_warmer','B_colder']:
        _,output[direction]=solve(direction,[p,warm_seed,old,seeds[1],seeds[2]])
    return output
