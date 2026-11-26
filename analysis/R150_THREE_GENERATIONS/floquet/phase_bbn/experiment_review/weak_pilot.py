"""Conditional two-input replay on published R150 tables. Set R150_BENCH to network_bench."""
import json
import os
from pathlib import Path
import sys
import tempfile
import numpy as np
from scipy.optimize import brentq
from scipy.special import expit, roots_legendre

BENCH = Path(os.environ['R150_BENCH']).resolve()
sys.path.insert(0, str(BENCH))
from bench import Config, History, solve, OBS

Q0, ME = 1.293332, .51099895


def integrate(piece, left, right, nodes, weights):
    E = left + (right-left)*(nodes+1)/2
    return ((right-left)/2) * np.dot(weights, piece(E))


def born(q, T, Tnu, sign, n=80):
    nodes, weights = roots_legendre(n)
    def integrand(e):
        def chi(E):
            k = E-sign*q
            return k*k*expit(-k/Tnu)*expit(E/T)
        return e*np.sqrt((e-ME)*(e+ME))*(chi(e)+chi(-e))
    # Split at the neutrino endpoint. Change the first interval variable to
    # remove the electron square-root threshold.
    high = q + 50*max(T,Tnu)
    def threshold(u):
        return integrand(ME+u*u)*2*u
    return (integrate(threshold, 0, np.sqrt(q-ME), nodes, weights)
            + integrate(integrand, q, high, nodes, weights))


def vacuum(q):
    nodes,w = roots_legendre(80)
    def integrand(u):
        e = ME+u*u
        return 2*u*e*np.sqrt((e-ME)*(e+ME))*(q-e)**2
    return integrate(integrand, 0, np.sqrt(q-ME), nodes,w)


def early(T):
    """Continuous ramp in log T, plateau in [0.3,0.8] MeV."""
    return np.interp(np.log(T), np.log([.2,.3,.8,1.]), [0.,1.,1.,0.])


def changed_rates(h, delta, scheme):
    for i,t in enumerate(h.tw):
        if delta[i]==0:
            continue
        tn=np.interp(np.log(t),h.logT[::-1],h.Tnu[::-1])
        q=Q0+delta[i]
        norm=vacuum(Q0)/vacuum(q) if scheme=='fixed_tau' else 1.
        for sign, table in [(1,h.wp),(-1,h.wn)]:
            table[i] *= norm*born(q,t,tn,sign)/born(Q0,t,tn,sign)


def archived_profile(name, column, T):
    a = np.genfromtxt(BENCH/'results'/f'{name}.csv', delimiter=',', names=True)
    return np.interp(np.log(T), np.log(a['Tgamma_MeV'][::-1]), a[column][::-1])


def scenarios(rtol=3.e-9):
    histories = {k:np.genfromtxt(BENCH/'results'/f'{k}.csv', delimiter=',',names=True)
                 for k in ('direct','mediated')}
    out = {}
    def trial(key, q_shape, scheme='fixed_tau', case=None, amplitude=1., tight=True):
        h=History()
        changed_rates(h, amplitude*q_shape(h.tw),scheme)
        with tempfile.TemporaryDirectory() as tmp:
            options={'mode':'off'}
            if case:
                a=histories[case]
                p=Path(tmp)/'profile.csv'
                np.savetxt(p,np.c_[a['Tgamma_MeV'][::-1],amplitude*a['deltaBD_MeV'][::-1]],
                           delimiter=',',header='T,delta_BD',comments='')
                options={'mode':'imposed','profile_file':str(p)}
            if tight: options['rtol']=rtol
            v=solve(h, Config(**options))
        out[key]=dict(amplitude=amplitude, scheme=scheme, **v)
        return v
    zero=lambda T: np.zeros_like(T)
    trial('off',zero)
    for s in ('fixed_tau','fixed_weak'):
        for val in (-.0003,.0003):
            trial(f'{s}_{val}',lambda T:val*early(T),s)
    for val in (-.00015,.00015):
        trial(f'half_{val}', lambda T:val*early(T))
    # Two different physical questions: externally imposed identical early shape,
    # and an early response proportional to the archived fast energy drive.
    # All amplitudes below multiply both the fast and slow channels together.
    for name,rho in [('binding_only',0.),('unification',(1.293332/2.224566)*(0.1+.7*160-.6*36)/(-6.5*161+18*36)),('strong_control',1.)]:
        def fit_q(case):
            if not rho: return zero
            return lambda T:rho*early(T)*archived_profile(case,'drive_MeV',T)
        obs='D_H'
        target=trial(name+'_delayed',fit_q('mediated'),case='mediated')[obs]
        v1=trial(name+'_direct',fit_q('direct'),case='direct')[obs]
        base=out['off'][obs]
        amp=(target-base)/(v1-base)
        sampled = {}
        def residual(scale):
            if scale not in sampled:
                sampled[scale]=trial(name+'_match_'+str(len(sampled)),fit_q('direct'),case='direct',amplitude=scale)
            return sampled[scale][obs]/target-1
        if abs(residual(amp))>2.e-7:
            brentq(residual,amp-.012,amp+.012,xtol=8.e-6)
        amp=min(sampled,key=lambda a:abs(residual(a)))
        v=sampled[amp]
        if abs(v[obs]/target-1)>5e-7:
            raise ValueError(f'Unresolved D/H match: {name} {amp} {v[obs]/target-1}')
        out[name+'_comparison']={'amplitude':amp,'D_relative_mismatch':v[obs]/target-1,
                                'delayed_minus_matched':{k:out[name+'_delayed'][k]-v[k] for k in OBS}}
    return out


if __name__=='__main__':
    for t in [.2,.4,.7,1.]:
        np.testing.assert_allclose(born(Q0,t,t,-1)/born(Q0,t,t,1), np.exp(-Q0/t),rtol=2e-10)
        for s in [1,-1]:
            np.testing.assert_allclose(born(Q0+.0003,t,t,s,120),born(Q0+.0003,t,t,s),rtol=2e-8)
    print(json.dumps(scenarios(float(sys.argv[1]) if len(sys.argv)>1 else 3.e-9),indent=2))
