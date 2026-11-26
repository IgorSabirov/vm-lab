"""Postprocess archived integrations and propagate Leonard's measured interval to partial rates."""
from pathlib import Path
import json
from hashlib import sha256
import numpy as np
from numpy.polynomial.legendre import leggauss
from scipy.optimize import brentq

ROOT=Path(__file__).resolve().parent
PHASE=ROOT.parent
BENCH=PHASE/'network_bench'
OBS=('Yp','D_H','He3_H_late','Li7_H_late')
read=lambda path: json.loads(path.read_text())


def window_fit(cases,engine,contact,eta):
    def response(name):
        return np.log([cases[name][engine][k]/cases['baseline'][engine][k] for k in OBS])
    early,late=response('early'),response('late')
    half=np.stack([response('early_half'),response('late_half')],axis=1)
    full=np.stack([early,late],axis=1)
    # y(s)=a*s+b*s*s through zero, half and full; s=1 equals the original amplitude.
    a=4*half-full;b=2*full-4*half
    matched=brentq(lambda s:a[0,1]*s+b[0,1]*s*s-early[0],.5,1)
    matched_linear=.5+.5*(early[0]-half[0,1])/(late[0]-half[0,1])
    ymatch=a[:,1]*matched+b[:,1]*matched**2
    interpolation_check=half[:,1]+(2*matched_linear-1)*(late-half[:,1])
    j=a/np.array([.003,.0055])
    def gradient(channel,prefix=''):
        return np.log([cases[prefix+channel+'_+0.125'][engine][k]/
                       cases[prefix+channel+'_-0.125'][engine][k] for k in OBS])/.25
    dd=np.array([gradient('ddHe3n'),gradient('ddtp','tight_')]).T
    # Local contrast insensitive to an early H perturbation. Logs keep dimensions explicit.
    ratio=j[1,0]/j[0,0]
    timing_diagnostic=np.array([-ratio,1,0,0])
    # Linear four-yield combinations constrained to cancel both archived q templates.
    # Residual tests on other solver below are independent of the defining templates there.
    cancel=np.linalg.solve(dd[[2,3]].T,-dd[1])
    control=np.r_[0.,1.,cancel]
    nuisance=np.column_stack((j[:,0],dd))
    control_joint=np.ones(4)
    rows=[0,2,3]
    control_joint[rows]=np.linalg.solve(nuisance[rows].T,-nuisance[1])
    np.testing.assert_allclose(control_joint@nuisance,0,atol=2e-15)
    two=np.linalg.solve(j[:2],contact[:2])
    predicted=j@two
    ranks={}
    for name,t in [('H',j),('H_and_DD',np.c_[j,dd]),('H_DD_eta',np.c_[j,dd,eta])]:
        normalized=t/np.linalg.norm(t,axis=0)
        sv=np.linalg.svd(normalized,compute_uv=False)
        ranks[name]=dict(rank=int(np.linalg.matrix_rank(normalized)),singular=sv,condition=sv[0]/sv[-1])
    linear_rd=timing_diagnostic@j
    return dict(early_percent=np.expm1(early)*100,late_percent=np.expm1(late)*100,
                early_late_difference_pp=(np.expm1(late)-np.expm1(early))*100,
                equal_helium_late_deltaH=matched*.0055,eqY_gap_D_pp=100*(np.expm1(ymatch[1])-np.expm1(early[1])),
                eqY_relative_D=100*np.expm1(ymatch[1]-early[1]),
                eqY_gap_ln=ymatch-early,
                eqY_linear_interpolation_pp=100*(np.expm1(interpolation_check[1])-np.expm1(early[1])),
                JH=j,JH_full_secant=full/np.array([.003,.0055]),JH_two_det=np.linalg.det(j[:2]),
                JDD=dd,eta_equivalent_eqY_D=(ymatch[1]-early[1])/eta[1],
                early_null_D_weight=timing_diagnostic,early_null_H=linear_rd,
                early_null_DD=timing_diagnostic@dd,early_null_eta=timing_diagnostic@eta,
                DD_null_D_weight=control,DD_null_checks=control@dd,DD_null_H=control@j,
                DD_null_contact=control@contact,DD_null_eta=control@eta,
                joint_weight=control_joint,joint_H=control_joint@j,joint_DD=control_joint@dd,
                joint_eta=control_joint@eta,joint_contact=control_joint@contact,
                joint_equal_helium_gap=control_joint@(ymatch-early),
                eqY_gap_after_DD_null=control@(ymatch-early),rank=ranks,
                H_only_mimic_of_contact_from_Yp_D=two,He3_Li_residual=contact[2:]-predicted[2:],
                matched_contact_scale_check=np.max(abs(contact[:2]-predicted[:2])))


def measured_integral(temp,energies,method,points):
    # E and T in MeV, y ordered on descending laboratory energies as in Table V.
    # N_A <sigma v> in cm^3 mol^-1 s^-1 when the input total cross section is in mb.
    mu=1875.61294/2
    eg=2*mu*(np.pi/137.035999)**2
    factor=6.02214076e23*2.99792458e10*1e-27*np.sqrt(8/(np.pi*mu))*temp**(-1.5)
    x,w=leggauss(points)
    nodes=energies[::-1]
    weights=np.zeros(len(nodes))
    for i,(lo,hi) in enumerate(zip(nodes,nodes[1:])):
        e=lo+(hi-lo)*(x+1)/2
        weight=(hi-lo)/2*w*np.exp(-e/temp)
        frac=(e-lo)/(hi-lo)
        for j,hat in [(i,1-frac),(i+1,frac)]:
            kernel=e if method=='sigma' else nodes[j]*np.exp(np.sqrt(eg/nodes[j])-np.sqrt(eg/e))
            weights[j]+=weight@(hat*kernel)
    return factor*weights[::-1]


def laboratory():
    path=ROOT/'leonard_input.json'
    assert sha256(path.read_bytes()).hexdigest()=='806b63b8369294a2a1eafbb6d4b19b15ad076fb07e532d1c73971d89569a65ad'
    lab=read(path);energy=np.array(lab['lab_energy_keV'])/2000
    mu=np.array(lab['cross_section_mb'])
    cov=(4*np.pi)**2*np.array(lab['covariance_a0'])
    np.linalg.cholesky(cov)
    corr_input=cov/np.sqrt(np.outer(np.diag(cov),np.diag(cov)))
    uncorr=cov.copy();uncorr[:8,8:]=0;uncorr[8:,:8]=0
    tables={r['id']:r for r in read(BENCH/'data/common/canonical.json')['rates']['reactions']}
    T=np.array([.04,.06,.07,.08,.10,.13,.20])
    answers={}
    for method in ['S','sigma']:
        ws=np.array([measured_integral(t,energy,method,32) for t in T])
        np.testing.assert_allclose(ws,[measured_integral(t,energy,method,64) for t in T],rtol=3e-13)
        W=np.kron(np.eye(2),ws)
        mean=W@mu
        c=W@cov@W.T
        ci=W@uncorr@W.T
        s=np.sqrt(np.diag(c));rho=c/np.outer(s,s)
        np.testing.assert_allclose(np.diag(c),np.diag(ci),rtol=2e-14)
        np.testing.assert_allclose(c,c.T,rtol=2e-14)
        rates=[]
        for j,t in enumerate(T):
            ii=[j,len(T)+j]
            sub=c[np.ix_(ii,ii)]/np.outer(mean[ii],mean[ii])
            sub0=ci[np.ix_(ii,ii)]/np.outer(mean[ii],mean[ii])
            ratios=[]
            for b in [np.array([.5,.5]),np.array([1.,-1.])]:
                ratios.append(np.sqrt((b@sub@b)/(b@sub0@b)))
            baseline=np.array([np.interp(t/.08617333262,tables[k]['T9'],tables[k]['values']) for k in ('ddtp','ddHe3n')])
            rates.append(dict(T_MeV=t,in_band=mean[ii],ratio_to_tabulated_total=mean[ii]/baseline,
                 relative_sd=s[ii]/mean[ii],correlation=rho[ii[0],ii[1]],joint_over_independent_sigma=ratios))
        answers[method]=dict(rows=rates,covariance=c,weights=W)
    return dict(T_MeV=T,order='p temperatures then n temperatures',input_rank=int(np.linalg.matrix_rank(cov)),
                lab_cross_correlation_range=[corr_input[:8,8:].min(),corr_input[:8,8:].max()],models=answers)


def run():
    arc=read(BENCH/'data/common/archive_17_cases.json')['cases']
    contact=read(PHASE/'experiment_review/followup/results/conv_3.json')['intervention_on_graph_interaction_ln']
    contact=np.array(contact)
    eta=np.array([read(PHASE/'cosmology/data/eta.json')['observables'][k]['dlnY_dlneta_secant']
                  for k in ['YPBBN','DoH','He3oH','Li7oH']])
    engines={e:window_fit(arc,e,contact,eta) for e in ['linx','primat']}
    for first,second in [('linx','primat'),('primat','linx')]:
        e=engines[first]
        e['DD_null_on_other_engine']=e['DD_null_D_weight']@engines[second]['JDD']
        e['joint_other_H']=e['joint_weight']@engines[second]['JH']
        e['joint_other_DD']=e['joint_weight']@engines[second]['JDD']
        e['timing_on_other_engine']=e['early_null_D_weight']@engines[second]['JH']
    # Locally defined R150 inputs. One column per +1 keV at three B_D knots,
    # one per +1 keV early Q, plus the two H windows at their tested amplitudes.
    review=read(PHASE/'experiment_review/followup/results/summary.json')
    hot=np.array(review['hot']['0.5']['jacobian_per_MeV'])*.001
    weak=review['weak_derivative_per_keV']['fermi0_lifetime1']
    baseline=read(BENCH/'results/paired_runs.json')['off']['result']
    q=np.array([weak[k]/baseline[k] for k in OBS])
    responses=np.c_[engines['linx']['JH']*np.array([.003,.0055]),hot,q]
    s=np.linalg.svd(responses,compute_uv=False)
    multi_input=dict(columns=['H_early_0.30pct','H_late_0.55pct','BD_60keV_plus1keV',
                  'BD_70keV_plus1keV','BD_80keV_plus1keV','Q_early_plus1keV_fixed_tau'],
                  matrix=responses,rank=int(np.linalg.matrix_rank(responses)),singular_values=s,
                  null_dimension=responses.shape[1]-int(np.linalg.matrix_rank(responses)))
    for channel, e in engines.items():
        assert e['JH_two_det']>0 and e['rank']['H_and_DD']['rank']==4
        assert abs(e['eqY_gap_ln'][0])<1e-13
        assert abs(e['joint_other_H'][1]-e['joint_H'][1])<.003
        assert e['JDD'][2,0]>0>e['JDD'][2,1]
    gaps={name:r['primat']['D_H']/r['linx']['D_H']-1 for name,r in arc.items()}
    bench=read(BENCH/'results/paired_runs.json')
    bench_windows={k:np.array([np.log(bench[k]['result'][i]/bench['off']['result'][i]) for i in OBS]) for k in ['early_H','late_H']}
    dd=engines['linx']['JDD'][1]
    def sigma(rho):return np.sqrt(dd@np.array([[1,rho],[rho,1]])@dd)
    return dict(outputs=OBS,archive_cases=len(arc),agreement_baseline=gaps['baseline'],
                agreement_max_abs=max(abs(v) for v in gaps.values()),agreement_worst=max(gaps,key=lambda k:abs(gaps[k])),
                eta=eta,contact=contact,absolute_contact_DH=np.expm1(contact[1])*arc['baseline']['linx']['D_H'],
                engines=engines,combined_local_example=multi_input,R150_single_engine_H_control_percent={k:100*np.expm1(v) for k,v in bench_windows.items()},
                q_unit_marginal_hypotheses_sigma_lnD={str(r):sigma(r) for r in (-1,0,.5,1)},lab=laboratory())


def convert(z):
    return z.tolist() if isinstance(z,np.ndarray) else z.item()


if __name__=='__main__':
    print(json.dumps(run(),indent=2,allow_nan=False,default=convert))
