"""Independent finite-model, thermal, inverse-rate, clock and replay controls."""
import json
import math
import sys
import numpy as np
from scipy.integrate import trapezoid
from scipy.optimize import brentq
from scipy.special import iv, expit
from bench import ROOT, OBS, KNOTS
from graph import contrast, contacts, detector_contact, target_x, spectral_audit, diagonal_caps, screen, relic, TREF,HBAR

sys.path.insert(0,str(ROOT/'upstream'/'phase_bbn'/'formation'))
import check as original


def audit(h):
    rerun=json.loads(json.dumps(original.main()))
    expected=json.loads((ROOT/'upstream/phase_bbn/formation/results.json').read_text())
    def same(x,y):
        if isinstance(x,dict): return x.keys()==y.keys() and all(same(x[k],y[k]) for k in x)
        if isinstance(x,list): return len(x)==len(y) and all(same(a,b) for a,b in zip(x,y))
        if isinstance(x,(float,int)): return bool(np.isclose(x,y,atol=1e-13,rtol=1e-12))
        return x==y
    assert same(rerun,expected)
    kernels=[]; scan=[]
    for L in (3,5,7,9,15):
        n=L-1
        _,V,_=original.graph(L,0.)
        G,_,_=original.graph(L,np.pi)
        observed=abs(V.conj().T@G@V[:,1])**2
        weights=np.r_[0.,(1-2/n)**2,np.full(n-1,4/n**2)]
        assert np.max(abs(observed-weights))<2e-13
        kernels.append(dict(L=L,port=observed[0],return_to_s=observed[1],to_a=observed[1+n//2],
                            other=4*(n-2)/n**2,total=sum(observed)))
        x=target_x(L,.4)
        J=x*TREF/2
        rate=J/HBAR*np.exp(-50)
        Hint=lambda T:np.interp(np.log(T),h.logT[::-1],h.H[::-1])
        scan.append(dict(L=L,x=x,J=J,Smax=np.log(J/HBAR/Hint(TREF)),rate_over_H=rate/Hint(TREF),
                         T_cross_MeV=brentq(lambda T:Hint(T)-rate,.012,3.),
                         fixed_x4_contact=detector_contact(L,4,.1)['g_eff'],
                         I_N_over_leading=iv(n,4)/(2**n/math.factorial(n))))
    # Thermodynamic controls: energy conservation for the decoupled gas.
    t=np.geomspace(.006,2,64); eps=1e-4
    rho,p=relic(t,.2,1)
    deriv=(relic(t*np.exp(eps),.2)[0]-relic(t*np.exp(-eps),.2)[0])/(2*eps)
    resid=float(np.max(abs(deriv-3*(rho+p))/(3*(rho+p))))
    assert resid<1e-6 and np.allclose(relic(t,0)[0],np.pi**2/30*t**4,rtol=1e-12)
    # KMS kernel, rescale R->kR, T->T/k, J=j/R.
    ev=np.array([-2.,-.5,.1,1.7])
    def scale(T,R):
        y=ev/(T*R)
        return sum(np.logaddexp(0,-y)+y*expit(-y)),2*(.3/R)/T
    assert np.allclose(scale(.12,2),scale(.12/5,10))
    dg=2e-4
    # Reversing delta Q modifies forward/reverse ratios by exp(nu_D deltaB/T).
    db=.001; T=.075; base=np.ones_like(h.sto[2],dtype=float)
    rev=base*np.exp(-h.sto[2]*db/T)
    assert np.allclose(np.log(base/rev),h.sto[2]*db/T)
    theta=contacts(7,.15,0.,[TREF])
    derivative=(contacts(7,.15,dg*TREF,[TREF])[2,0]-contacts(7,.15,-dg*TREF,[TREF])[2,0])/(2*dg*TREF)
    assert abs(derivative-(theta[3,0]-theta[4,0]))<1e-8
    return dict(upstream_full_replay=rerun,channels=kernels,barriers=scan,contact_scan=spectral_audit(),
                exact_diagonal_caps=diagonal_caps(),relic_continuity_relative=resid,
                screen=[screen(L,eps,gd,gx,bath) for L in (3,5,7,9,15)
                        for eps in (.01,.10,.4) for gd in (28,106.75,202) for gx in sorted({1,L,126})
                        for bath in ('photon','relic')])


def summarize(h,runs,out,pulse,scale):
    results={k:v['result'] for k,v in runs.items()}
    R=lambda key:np.array([results[key][s] for s in OBS])
    base=R('off')
    log=lambda key:np.log(R(key)/base)
    history=lambda k:np.genfromtxt(out/(k+'.csv'),names=True,delimiter=',')
    kernel=np.array([(log(f'kernel_{i}_1')-log(f'kernel_{i}_-1'))/(2*pulse) for i in range(len(KNOTS))])
    np.savetxt(out/'binding_response.csv',np.c_[KNOTS,kernel],delimiter=',',
               header='T_knot_MeV,'+','.join('dln_'+k+'_per_MeV' for k in OBS),comments='')
    convolutions={}
    for name in ('direct','mediated','coupled','total_contact'):
        tr=history(name)
        weights=np.interp(np.log(KNOTS),np.log(tr['Tgamma_MeV'][::-1]),tr['deltaBD_MeV'][::-1])
        estimate=weights@kernel
        convolutions[name]=dict(projected_ln=estimate.tolist(),integrated_ln=log(name).tolist(),
                                difference_ln=(estimate-log(name)).tolist())
    unif=(log(f'uniform_{pulse}')-log(f'uniform_{-pulse}'))/(2*pulse)
    half=(log(f'uniform_{pulse/2}')-log(f'uniform_{-pulse/2}'))/pulse
    tr=history('off')
    interp=lambda key,T:float(np.interp(T,tr['Tgamma_MeV'][::-1],tr[key][::-1]))
    micro=[]
    for T in (.1,.08,TREF,.07,.06):
        cap=h.forward_rates(T)[0]*np.exp(np.interp(np.log(T),h.logT[::-1],h.logrho[::-1]))*interp('p',T)
        T9=T/.08617333262145
        photo=h.forward_rates(T)[0]*h.alpha[0]*T9**h.beta[0]*np.exp(h.gamma[0]/T9)
        H=interp('H_s_inv',T)
        micro.append(dict(T_MeV=T,capture_per_n_s_inv=cap,photo_per_D_s_inv=photo,
                          nu_bath_pair_s_inv=cap+photo,relax_s=1/(cap+photo),nu_over_H=(cap+photo)/H))
    clock=max(abs(log('clock')-log('coupled')))
    precision=max(abs(log('tight')-log('coupled')))
    base_err={engine:[float(results['off'][k]/h.reference[engine][k]-1.) for k in OBS]
              for engine in ('linx','primat')}
    nulls=max(max(abs(log(k))) for k in ('no_forward','both_off','zero_contact','passive_A'))
    fast=max(abs(log('fast')-log('direct')))
    checks={'finite_results':all(np.all(np.isfinite(R(k))) for k in results),
            'archive_all_four_relative_below_1e-5':max(np.max(np.abs(a)) for a in base_err.values())<1e-5,
            'null_rel_below_1e-5':nulls<1e-5,'baryons':max(r['max_baryon_error'] for r in results.values())<1e-9,
            'clock_rel_below_1e-5':clock<1e-5,
            'history_replay':max(abs(log('prescribed')-log('coupled')))<2e-5,
            'early_late_H_archive':max(abs(100*(R('early_H')[:2]/base[:2]-1)-[.13672,.07557]))<.001
                                  and max(abs(100*(R('late_H')[:2]/base[:2]-1)-[.14155,.91183]))<.001,'refined_rel_below_1e-5':precision<1e-5,
            'fast_mediator_limit':fast<1e-5,
            'fast_feedback_limit':max(abs(log('fast_feedback')-log('algebraic_feedback')))<1e-5,
            'kernel_partition':max(abs((kernel.sum(axis=0)-unif)/unif))<.02,
            'uniform_step_halving':max(abs((half-unif)/unif))<.02,
            'refit_DH':abs(log('refit_direct')[1]-log('coupled')[1])<5e-6}
    return dict(observable_order=OBS,percent_from_off={k:(100*(R(k)/base-1)).tolist() for k in results},
                fitted_lambda_factor=scale,matched_residual_percent=(100*(R('coupled')/R('refit_direct')-1)).tolist(),
                archive_relative_error=base_err,clock_max_log=clock,refined_max_log=precision,
                fast_limit_max_log=fast,null_max_log=nulls,kernel_uniform_sums=kernel.sum(axis=0).tolist(),
                uniform_central_per_MeV=unif.tolist(),half_uniform_central_per_MeV=half.tolist(),
                convolution=convolutions,bath_pair_calibration=micro,
                feedback_interaction_ln=(log('coupled')-log('mediated')-log('self_only')+log('zero_contact')).tolist(),
                checks={k:bool(v) for k,v in checks.items()})
