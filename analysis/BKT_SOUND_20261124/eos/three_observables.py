"""Conditional three-observable inversion of the Cambridge BKT data.

No measured temperature enters the free sound inversion. The bulk superfluid
curve is an external comparator and is never used to fit the modes.
"""
import json
import sys
from pathlib import Path
from statistics import NormalDist

import numpy as np
from scipy.integrate import quad
from scipy.interpolate import PchipInterpolator
from scipy.optimize import brentq, minimize_scalar

from three_calibrations import fit_all
from inversion import D0, EquationOfState, HERE

sys.path.insert(0, str(HERE.parent))
from thermodynamics import rows

# Same stable X range and upper bound on c20/cB as the previous six-row fit.
X_LO, X_HI = -.7, 1.4
ZMESH = np.linspace(0., 4., 161)
METHODS = ('nominal', 'critical_axis', 'pressure_stress', 'thinned',
           'speed_weight_positive', 'speed_weight_negative', 'free_gain', 'shared_scales')


def forward(state, z):
    fast, slow = state.speeds(z)
    weight = (z**2 - slow**2) / (fast**2 - slow**2)
    return fast, slow, weight


def local_minima(values):
    return np.flatnonzero((values[1:-1] <= values[:-2]) & (values[1:-1] < values[2:])) + 1


def minimum(grid, scores, fn):
    candidates = [(scores[0], grid[0]), (scores[-1], grid[-1])]
    for i in local_minima(scores):
        opt = minimize_scalar(fn, bounds=(grid[i-1], grid[i+1]), method='bounded',
                              options={'xatol': 1e-10})
        candidates.extend([(opt.fun, opt.x), (scores[i], grid[i])])
    return min(candidates)


class Fit:
    def __init__(self, row, method, shared, speed_only=False):
        self.row = row
        self.method = method
        n, temp, q, gs = shared if method == 'shared_scales' else np.ones(4)
        self.eos = EquationOfState(.64*gs, anchor=-.5 if method == 'pressure_stress' else 0.,
                                   omit_inner=method == 'thinned')
        self.dref = self.eos.dc if method == 'critical_axis' else D0*n/temp
        self.speed_factor = q*np.sqrt(n*gs)
        self.speed_only = speed_only
        self.rho = {'speed_weight_positive': .8, 'speed_weight_negative': -.8}.get(method, 0.)

    def loss(self, state, z, maximum=False):
        fast, slow, weight = forward(state, z)
        r = self.row
        a = (self.speed_factor*fast-r['c1']) / r['err_c1']
        b = (self.speed_factor*slow-r['c2']) / r['err_c2']
        if self.speed_only:
            return a*a + b*b
        scale = 1.
        if self.method == 'free_gain':
            # Jointly fit the measured raw f2 and fsum with a row-wise gain.
            sw, st = r['err_f2'], r['err_fsum']
            scale = (weight*r['author_f2']/sw**2+r['author_fsum']/st**2)/(weight**2/sw**2+1/st**2)
        c = (scale*weight-r['author_f2'])/r['err_f2']
        if maximum:
            return np.maximum(np.maximum(abs(a), abs(b)), abs(c))
        loss = a*a + b*b + (c-self.rho*b)**2/(1-self.rho**2)
        if self.method == 'free_gain':
            loss += ((scale-r['author_fsum'])/r['err_fsum'])**2
        return loss

    def profile_z(self, x, maximum=False):
        state = self.eos.at_X(x)
        fn = lambda z: self.loss(state, z, maximum)
        return minimum(ZMESH, fn(ZMESH), fn)

    def result(self, x, z, loss):
        state = self.eos.at_X(x)
        return dict(t=self.dref/state.D, X=x, z=z, Ds=state.Ds(z), loss=loss,
                    predicted=list(forward(state, z)))

    def fixed(self):
        x = self.eos.state(self.dref/self.row['T_over_Tc']).X
        loss, z = self.profile_z(x)
        return self.result(x, z, loss)

    def free(self, grid):
        # Screen the two-dimensional surface and refine every competing X minimum
        # in the z-profile, including all knots of the density interpolant.
        state = self.eos.at_X(grid[:, None])
        surface = self.loss(state, ZMESH)
        iz = surface.argmin(axis=1)
        # Vectorized golden search near the best grid z for every X. Competing
        # local basins are rechecked explicitly if more than one is present.
        left = ZMESH[np.maximum(iz-1, 0)]
        right = ZMESH[np.minimum(iz+1, len(ZMESH)-1)]
        points = self.eos.at_X(grid)
        for _ in range(32):
            a = left + (right-left)/3
            b = right - (right-left)/3
            keep_left = self.loss(points, a) < self.loss(points, b)
            left, right = np.where(keep_left,left,a), np.where(keep_left,b,right)
        scores = np.minimum(surface.min(axis=1), self.loss(points, (left+right)/2))
        multimodal = ((surface[:,1:-1] <= surface[:,:-2]) &
                      (surface[:,1:-1] < surface[:,2:])).sum(axis=1) > 1
        for i in np.flatnonzero(multimodal):
            scores[i] = self.profile_z(grid[i])[0]
        fn = lambda x: self.profile_z(x)[0]
        _, best_x = minimum(grid, scores, fn)
        chi, z = self.profile_z(best_x)
        out = self.result(best_x, z, chi)
        # All connected pieces, conditional delta-chi²=3.84 profile for one coordinate.
        cut = chi + 3.841458820694124
        inside = scores <= cut
        ends = [grid[0]] if inside[0] else []
        for i in np.flatnonzero(inside[:-1] != inside[1:]):
            ends.append(brentq(lambda x:fn(x)-cut,grid[i],grid[i+1]))
        if inside[-1]:
            ends.append(grid[-1])
        out['profile_t'] = sorted([sorted(self.dref/self.eos.density(np.array(pair)))
                                   for pair in np.reshape(ends,(-1,2))])
        out['at_X_bound'] = bool(min(best_x-X_LO,X_HI-best_x) < 1e-6)
        return out, scores


def order_cost(grid, fits, scores):
    # Temperature falls as X increases. Prefix/suffix minima allow disjoint
    # branches. For constrained optima refine the equality boundary and all
    # individual local minima; smooth interior optima must minimize each row.
    candidates = []
    for fit, sc in zip(fits,scores):
        xs = [grid[0],grid[-1]]
        for i in local_minima(sc):
            opt = minimize_scalar(lambda x:fit.profile_z(x)[0],bounds=(grid[i-1],grid[i+1]),
                                  method='bounded', options={'xatol':1e-9})
            xs.extend([opt.x,grid[i]])
        candidates.append([(x,fit.profile_z(x)[0]) for x in xs])
    equal, _ = minimum(grid, scores[0]+scores[1],
                       lambda x:sum(fit.profile_z(x)[0] for fit in fits))
    values = [equal,equal]
    for xa,ca in candidates[0]:
        for xb,cb in candidates[1]:
            index = 0 if xb <= xa else 1
            values[index] = min(values[index], ca+cb)
    return dict(delta_loss_B_at_least_A=values[0]-min(values),
                delta_loss_B_at_most_A=values[1]-min(values))


def bulk_reference(t):
    # PS Table I, positive-X superfluid column, Eq. 42. Square-root coordinate
    # respects the one-sided cusp. The jump is part of this comparator.
    eos = EquationOfState()
    x = eos.state(eos.dc/t).X
    if x < 0:
        return 0.
    xs = np.array([0,.0044,.0444,.0944,.2444,.4944,.9944,1.9944,2.9944,3.9944])
    f = [1,1.077,1.274,1.433,1.823,2.37,3.348,5.135,6.87,8.58]
    return float(4*PchipInterpolator(np.sqrt(xs),f,extrapolate=False)(np.sqrt(x)))


def diagnostics(data, previous):
    central = []
    for r, rec in zip(data, previous['records']):
        u,v,f,total = (r[k] for k in ('c1','c2','author_f2','author_fsum'))
        state = EquationOfState().state(D0/r['T_over_Tc'])
        zz = [v*v+fraction*(u*u-v*v) for fraction in [f,f/total]]
        low, high = rec['nominal']['interval95'][0]
        central.append(dict(t=r['T_over_Tc'], z_raw=np.sqrt(zz[0]), z_normalized=np.sqrt(zz[1]),
                            Ds_raw=state.Ds(np.sqrt(zz[0])),Ds_normalized=state.Ds(np.sqrt(zz[1])),
                            adiabatic_squared=u*u+v*v-zz[0], isothermal_squared=(u*v)**2/zz[0],
                            in_two_speed_profile=bool(low<=state.Ds(np.sqrt(zz[0]))<=high),
                            total_pull=(total-1)/r['err_fsum'],Ds_bulk_PS=bulk_reference(r['T_over_Tc'])))
    a,b=data[-2:]
    delta=b['T_over_Tc']-a['T_over_Tc']
    sa,sb=a['err_T'],b['err_T']
    corr={str(r):delta/np.sqrt(sa*sa+sb*sb-2*r*sa*sb) for r in [-1,0,.5,.9,1]}
    w_ratio=(b['c2']/a['c2'])*np.sqrt(a['T_over_Tc']/b['T_over_Tc'])
    # Check the measured damped-oscillator first moment at several widths.
    damped=[]
    for key,rec in json.loads((HERE.parent/'results/BLIND.json').read_text()).items():
        _,omega,_,gamma,_,amplitude=rec['physical']
        for mult in [.5,1.,2.]:
            width=gamma*mult
            def moment(y):
                return amplitude*omega**2*width*y*y/((y*y-omega**2)**2+(width*y)**2)
            integral=2*quad(moment,0,np.inf,epsabs=1e-11)[0]
            damped.append(dict(spectrum=key,width_over_omega=width/omega,
                               moment_ratio=integral/(np.pi*amplitude*omega**2)))
    return dict(central=central,thermal_significance=corr,w_ratio=w_ratio,
                TB_over_TA_at_equal_dimensional_c2=1/w_ratio**2,
                cB_ratio_at_equal_T=np.sqrt(a['T_over_Tc']/b['T_over_Tc']),
                damped_moment=damped)


def calculate(steps=440):
    data=[r for r in rows() if r['spectral_status']=='two_sound_speeds']
    prev=json.loads((HERE/'results.json').read_text())
    shared=prev['joint_fits']['baseline']['relative_scales']
    grid=np.unique(np.r_[np.linspace(X_LO,X_HI,steps+1),
                         [x for x in EquationOfState().X if X_LO<x<X_HI]])
    output=diagnostics(data,prev)
    modes={}
    for name in (*METHODS,'speeds_only'):
        records=[]; pair_fits=[]; pair_scores=[]
        for r in data:
            fit=Fit(r,name,shared,speed_only=name=='speeds_only')
            fixed=fit.fixed()
            free,scores=fit.free(grid)
            record=dict(fixed=fixed,free=free)
            if name=='nominal':
                record['min_max_marginal_pull_fixed_t']=fit.profile_z(fixed['X'],maximum=True)[0]
            records.append(record)
            if len(records)>4:
                pair_fits.append(fit);pair_scores.append(scores)
        modes[name]=dict(rows=records,pair_order=order_cost(grid,pair_fits,pair_scores))
    output['fits']=modes
    output['coherent_calibration']={}
    for flag in [False,True]:
        name = 'density_correlated' if flag else 'diagonal'
        output['coherent_calibration'][name] = fit_all(
            data, modes['nominal']['rows'], prev['joint_fits']['baseline'], flag)
    output['gaussian_three_marginal_95_bonferroni']=NormalDist().inv_cdf(1-.05/6)
    # Descriptive fits in a single finite-system temperature coordinate; neither
    # the intercept nor its agreement with 4 determines the bulk limit.
    check={}
    for name in ['nominal','critical_axis','pressure_stress','thinned','shared_scales','author']:
        lower=[(r['T_over_Tc'],r['author_Ds'] if name=='author' else rec['fixed']['Ds'])
               for r,rec in zip(data,modes['nominal' if name=='author' else name]['rows'])
               if r['T_over_Tc']<1]
        x,ds=np.array(lower).T
        trials={}
        for label,sl,curved in [('five_sqrt',slice(None),False),('last_three_sqrt',slice(-3,None),False),
                                ('five_sqrt_plus_linear',slice(None),True)]:
            delta=1-x[sl]
            cols=[np.ones_like(delta),np.sqrt(delta)]
            if curved:cols.append(delta)
            trials[label]=float(np.linalg.lstsq(np.column_stack(cols),ds[sl],rcond=None)[0][0])
        check[name]=trials
    output['finite_coordinate_intercepts']=check
    return output


if __name__=='__main__':
    print(json.dumps(calculate(),indent=2,allow_nan=False))
