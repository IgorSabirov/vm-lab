"""Finite-frequency tests for E55 and explicit observable maps for R141–R148."""
import csv
import json
from pathlib import Path

import numpy as np
from scipy.constants import hbar
from scipy.stats import chi2, norm

from inversion import MASS

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CB = hbar/MASS*np.sqrt(3e12*.64)  # reference n in m^-2, not per-series thermometry
CUTOFFS = {'peak': np.sqrt(2), 'pole': 2.}


def pooled(values, errors):
    weights = 1/errors**2
    weights /= weights.sum()
    centre = weights@values
    se = np.linalg.norm(weights*errors)
    loss = np.sum(((values-centre)/errors)**2)
    return weights, centre, se, loss


def contrast(values, errors, coeff):
    terms = abs(coeff)*errors
    delta = coeff@values
    max_sd = terms.sum()
    sd = np.linalg.norm(terms)
    return dict(delta=delta,SE_diag=sd,Z_diag=delta/sd,SE_max_PSD=max_sd,
                Z_min_abs_PSD=abs(delta)/max_sd,coefficients=coeff.tolist())


def plateau(rows):
    t = np.array([r['t'] for r in rows])
    d = np.array([r['D2_graph_hbar_over_m'] for r in rows])
    se = np.array([r['D2_halfbar'] for r in rows])
    w, centre, sm, loss = pooled(d[:-1],se[:-1])
    ab = contrast(d,se,np.array([0.,0.,0.,0.,1.,-1.]))
    ab['Z_max_abs_PSD'] = ab['delta']/abs(se[-2]-se[-1])
    against = contrast(d,se,np.r_[w,-1.])
    # Compare one target chosen from six rows with its complementary pool.
    loo = []
    for i in range(len(d)):
        keep = np.arange(len(d))!=i
        co = np.full(len(d),-1.)
        co[keep] = pooled(d[keep],se[keep])[0]
        loo.append(contrast(d,se,co)['Z_diag'])
    first4 = pooled(d[:4],se[:4])[0]
    all_loss = pooled(d,se)[3]
    design = np.column_stack((np.ones(len(t)),t))
    line = np.linalg.lstsq(design/se[:,None],d/se,rcond=None)[0]
    return dict(mean=centre,SE_diag=sm,Q_first5=loss,lower_tail=chi2.cdf(loss,4),
        upper_tail=chi2.sf(loss,4),AB=ab,B_vs_first5=against,
        B_vs_first4=contrast(d,se,np.r_[first4,0.,-1.]),
        six_common=dict(Q=all_loss,dof=5,p_reference=chi2.sf(all_loss,5)),
        six_linear=dict(coefficients=line.tolist(),Q=np.sum(((d-design@line)/se)**2),dof=4),
        leave_one_out_Z=loo,
        six_choices_two_sided_Bonferroni=min(1.,6*2*norm.sf(abs(loo[-1]))))


def threshold(row, speed_error, length, cb):
    q = np.pi*1e6/length
    k = (hbar/MASS)*q/cb
    d, ds, u = row['D2_graph_hbar_over_m'],row['D2_halfbar'],row['u2']
    r = k*d/u
    sr = r*np.hypot(ds/d,speed_error/u)
    out = dict(r=r,ratio_SE_delta=sr)
    for label,h in CUTOFFS.items():
        # Test the boundary as a linear contrast of the reported marginals.
        # This avoids replacing the random denominator by a constant in a tail.
        gap = h*u-k*d
        errors = [h*speed_error,k*ds]
        out[label] = dict(Z_ratio_delta=(h-r)/sr,Z_gap_diag=gap/np.linalg.norm(errors),
                          Z_gap_min=gap/sum(errors),Z_gap_max=gap/abs(errors[0]-errors[1]))
    return out


def oscillator(y,u,gamma):
    return gamma*y/(np.pi*((y*y-u*u)**2+gamma**2*y*y))


def generator(u,gamma):
    a = np.zeros((4,4))
    for i,(speed,width) in enumerate(zip(u,gamma)):
        i *= 2
        a[i:i+2,i:i+2] = [[0.,1.],[-speed**2,-width]]
    return a


def spectrum(row):
    y,obs,err = np.loadtxt(ROOT/'data/S2.txt',skiprows=1).T
    order = np.argsort(y)
    y,obs,err = y[order],obs[order],err[order]
    speeds = np.array([row['u1'],row['u2']])
    diffusion = np.array([row['D1_graph_hbar_over_m'],row['D2_graph_hbar_over_m']])
    widths = (hbar/MASS)*row['q_nom_per_um']*1e6/CB*diffusion
    f2 = row['f2']
    weights = np.array([row['fsum']-f2,f2])
    basis = np.array([oscillator(y,u,g) for u,g in zip(speeds,widths)])
    predictions = dict(two_modes=weights@basis,unit_total=np.array([1.-f2,f2])@basis,
        no_second_weight=weights.sum()*basis[0],swapped_weights=weights[::-1]@basis)
    a = generator(speeds,widths)
    b = np.array([0.,1.,0.,1.])
    c = np.array([weights[0],0.,weights[1],0.])
    def readout(mat,bvec,cvec):
        return np.array([(cvec@np.linalg.solve(-1j*v*np.eye(4)-mat,bvec)).imag/np.pi for v in y])
    perm = np.eye(4)[[2,3,0,1]]
    direct = readout(a,b,c)
    permuted = readout(perm@a@perm.T,perm@b,c@perm.T)
    return dict(t=row['t'], n_bins=len(y), widths_over_omega_B=widths.tolist(),fitted_parameters_here=0,
                error_to_analytic=max(abs(direct-predictions['two_modes'])),
                error_after_relabel=max(abs(direct-permuted)),
                chi2_descriptive={k:float(np.sum(((v-obs)/err)**2)) for k,v in predictions.items()},
                frequency_obs_se_reconstruction=np.column_stack((y,obs,err,direct)).tolist())


def twist_control():
    # Full six-cycle: R144's base q=3 is a dimensionless diagonal entry.
    n = 6
    angles = 2*np.pi*np.arange(n)/n
    energy = 3.-2*np.cos(angles)
    first = 2*np.sin(angles)/n
    second = 2*np.cos(angles)/n**2
    curvature = {}
    for T in [.1,.5,1.]:
        p = np.exp(-(energy-energy.min())/T)
        p /= p.sum()
        curvature[str(T)] = p@second-(p@first**2-(p@first)**2)/T
    per, op = [], []
    for phase in [0.,np.pi/2,np.pi]:
        shift = np.diag(np.ones(n-1),1).astype(complex)
        mat = 3*np.eye(n)-np.exp(1j*phase/n)*shift-np.exp(-1j*phase/n)*shift.T
        op.append(np.linalg.det(mat).real)
        shift[-1,0] = 1.
        mat = 3*np.eye(n)-np.exp(1j*phase/n)*shift-np.exp(-1j*phase/n)*shift.T
        per.append(np.linalg.det(mat).real)
    return dict(phases=[0.,np.pi/2,np.pi],cycle_det=per,open_path_det=op,
                canonical_one_particle_F2_by_kBT=curvature)


def finite_q_counterexample(row, r):
    # Positive weights in a longitudinal retarded response. The first linewidth
    # scales as q^2; the slow oscillator has a constant relaxation rate. At
    # small q it supplies a thermal diffusion pole, perfectly admissible on
    # the normal side. This construction does not fit a vortex diffusivity.
    u = row['u2']
    gamma = r*u  # dimensions scaled by cB and the sampled q
    examples = []
    for q in [1.,.1,.01]:
        poles = np.roots([1.,gamma,(u*q)**2])
        examples.append(dict(q_over_q_sample=q,
            poles_s=[[v.real,v.imag] for v in poles],
            nonzero_S2_peak=bool(2*(u*q)**2>gamma**2)))
    return dict(fast_speed=row['u1'],slow_speed=u,slow_weight=row['f2'],fast_weight=1-row['f2'],
                gamma2=gamma,q_pole_threshold_over_sample=r/2,samples=examples)


def calculate():
    with (HERE/'geometry.csv').open() as stream:
        matrix = list(csv.DictReader(stream))
    with (ROOT/'results/THERMO_INPUTS.csv').open() as stream:
        thermo = {float(r['T_over_Tc']):r for r in csv.DictReader(stream)}
    measured = []
    for raw in matrix:
        if raw['mode_assignment']!='two_sound_speeds':
            continue
        keys = ['t','D2_graph_hbar_over_m','D2_halfbar','D1_graph_hbar_over_m','D1_halfbar','u1','u2','f2']
        row = {k:float(raw[k]) for k in keys}
        row['q_nom_per_um'] = float(raw['q_nom_per_um']) if raw['q_nom_per_um'] else None
        source = thermo[row['t']]
        row.update(su=float(source['err_c2']),fsum=float(source['author_fsum']))
        measured.append(row)
    mode = {label:{str(L):threshold(r,r['su'],L,CB) for L in [33,23]}
            for label,r in zip(['A','B'],measured[-2:])}
    relative = []
    for r in measured:
        rel = (r['D2_graph_hbar_over_m']/r['D1_graph_hbar_over_m'])*(r['u1']/r['u2'])
        relative.append(dict(t=r['t'],r2_over_r1=rel))
    across = {}
    for la,a in mode['A'].items():
        for lb,b in mode['B'].items():
            delta = a['r']-b['r']
            across[la+'_'+lb] = dict(delta=delta,Z_diag=delta/np.hypot(a['ratio_SE_delta'],b['ratio_SE_delta']))
    blind = json.loads((ROOT/'results/BLIND.json').read_text())
    references = {}
    for name,rec in blind.items():
        _,w,_,g,*_ = rec['physical']
        correlations = {}
        for key in ['physical_local_cov','physical_boot_cov']:
            c = np.array(rec[key])
            correlations[key] = c[1,3]/np.sqrt(c[1,1]*c[3,3])
        references[name] = dict(r=g/w,peak_discriminant_profile95=rec['profile95'],verdict=rec['verdict'],
                                corr_gamma2_omega2=correlations)
    qratio = 33/23
    return dict(plateau=plateau(measured),thresholds=mode,cb_reference_m_s=CB,reference_spectra=references,delta_r_AB=across,
        normal_response_example=finite_q_counterexample(measured[-1],mode['B']['33']['r']),
        calibration_invariant_ratio=relative,cold_spectrum=spectrum(next(r for r in measured if r['q_nom_per_um'])),
        twist=twist_control(),two_q_predictions=dict(q_high_over_low=qratio,
            linewidth_ratio_at_constant_D=qratio**2,Q_ratio_at_constant_D=1/qratio,
            D_ratio_at_Q_proportional_to_q=1/qratio**2,Q_ratio_at_Q_proportional_to_q=qratio,
            drive_to_smallest_q=[1.,56/23],log_rounding_ratio_Lmin_only=(np.log(21.)/np.log(23.))**2))


if __name__=='__main__':
    (HERE/'dynamic_bridge.json').write_text(json.dumps(calculate(),indent=2,allow_nan=False)+'\n')
