"""Fixed-coordinate EOS, covariance and finite-size checks for Cambridge sound data."""
import csv
from itertools import permutations, product
import json

import numpy as np
from scipy.constants import hbar
from scipy.integrate import quad, trapezoid
from scipy.optimize import brentq
from scipy.stats import chi2, rankdata

from inversion import CUT, D0, HERE, MASS, EquationOfState
from three_observables import Fit, ZMESH, bulk_reference, forward, minimum, rows


def channels(u, v, f):
    return 1/((1-f)/u**2+f/v**2), (1-f)*u**2+f*v**2


def isothermal_gradient(u, v, f):
    iso, _ = channels(u,v,f)
    return iso**2*np.array([2*(1-f)/u**3,2*f/v**3,1/u**2-1/v**2])


def association(xs,ys):
    x = rankdata(xs)
    y = rankdata(ys)
    corr = np.corrcoef(x,y)[0,1]
    hits = sum(abs(np.corrcoef(x,p)[0,1])+1e-12 >= abs(corr) for p in permutations(y))
    return dict(spearman=corr, two_sided_permutation_fraction=hits/720)


def audit_row(r, point, vector):
    t,u,v,f,s = (r[key] for key in ['T_over_Tc','c1','c2','author_f2','author_fsum'])
    iso, ad = channels(u,v,f)
    frac_iso, _ = channels(u,v,f/s)
    sd = np.array([r['err_c1'],r['err_c2'],r['err_f2']])
    gradient = isothermal_gradient(u,v,f)
    contributions = abs(gradient)*sd
    sigma = np.linalg.norm(contributions)
    upper = contributions.sum()
    lower = max(0.,2*max(contributions)-upper)
    fstar = v**2*(u**2-1)/(u**2-v**2)
    if abs(point['t_graph']-t) > .0015:
        raise ValueError('Graphical marker not matched to tabulated temperature')
    diff = vector['D_over_hbar_m']
    if abs(vector['t_graph']-t)>.001 or abs(diff-point['D2_over_hbar_m'])>.04:
        raise ValueError('Thesis plots disagree about the row or central diffusivity')
    out = dict(t=t,I=iso,adiabatic=ad,I_fraction=frac_iso,I_absolute_inverse_moment=frac_iso/s,
               f_at_I_one=fstar,f_minus_fstar_in_SE=(f-fstar)/sd[-1],
               I_linear_gradient=gradient.tolist(),I_sigma_diag=sigma,
               I_sigma_PSD=[lower,upper],D2_graph=diff,D2_plotted_halfbar=vector['D_halfbar'],scenarios={})
    for name, thin, critical in [('nominal',False,False),('critical',False,True),
                                 ('thin_nominal',True,False),('thin_critical',True,True)]:
        eos = EquationOfState(omit_inner=thin)
        scale = eos.dc if critical else D0
        st = eos.state(scale/t)
        if not np.isclose(st.B,2/eos.slope(st.X)):
            raise AssertionError('EOS derivative invariant failed')
        # Bound B on the full t +/- 1 marginal SE interval, retaining spline knots
        # and turning points of its derivative, which are extrema of B=2/slope.
        ends = sorted(eos.state(scale/k).X for k in [t-r['err_T'],t+r['err_T']])
        knots = np.r_[ends, eos.X, eos.curve.derivative(2).roots(extrapolate=False)]
        domain = knots[(ends[0]<=knots)&(knots<=ends[1])]
        B_range = 2/eos.slope(domain)
        delta = iso-st.B
        out['scenarios'][name] = dict(X=st.X,B=st.B,A=st.A,I_minus_B=delta,
            ad_minus_A=ad-st.A,Z_diag=delta/sigma,abs_Z_min_PSD=abs(delta)/upper,
            B_t_marginal_range=[min(B_range),max(B_range)])
    out['trial_Gamma2_over_omega2_at_cB_2p3_mm_s'] = {
        str(length):diff*hbar/MASS*(np.pi*1e6/length)/(v*.0023) for length in [33,23]}
    return out


def order_statistics(data, archive):
    stats = {}
    logdet = 0.
    for r in data:
        ell = [.5*r[k]*r['err_T']/(r['T_over_Tc']*r['err_'+k]) for k in ['c1','c2']]
        logdet += sum(np.log1p(-np.square(ell)))
    for name, fits in archive['coherent_calibration'].items():
        best = fits['unconstrained']
        loss = best['loss']
        delta = max(fits[key]['loss'] for key in ['B_warmer','B_colder'])-loss
        stats[name] = dict(loss=loss,goF_reference=chi2.sf(loss,best['nominal_dof']),
            delta_order=delta, two_sided_reference=chi2.sf(delta,1),
            boundary_mixture_reference=.5*chi2.sf(delta,1), t_AB=best['fitted_t'][-2:])
    return dict(scenarios=stats, density_minus_diag_logdet=logdet,
                density_minus_diag_minus2logL=(stats['density_correlated']['loss']
                                               -stats['diagonal']['loss']+logdet))


def geometry(data, modes):
    # The two Fig 5.5 labels are printed to 0.01. Numbers in the other seven
    # rows have no published link to the driving geometry.
    identified = {.91:'S2',1.17:'S1'}
    blind = json.loads((HERE.parent/'results/BLIND.json').read_text())
    reveal = json.loads((HERE.parent/'preregistration/reveal.json').read_text())['map']
    def match(t, mode):
        hits = [p for p in modes[mode] if abs(p['t_graph']-t)<.001]
        if len(hits)>1:
            raise ValueError('Ambiguous plot-to-row match')
        return (hits[0]['D_over_hbar_m'],hits[0]['D_halfbar']) if hits else (None,None)
    table = []
    for r in data:
        t = r['T_over_Tc']
        spec = identified.get(round(t,2))
        first, first_err = match(t,'D1')
        second, second_err = match(t,'D2')
        heat, heat_err = match(t,'DT')
        table.append(dict(t=t,err_t=r['err_T'],u1=r['c1'],u2=r['c2'],f2=r['author_f2'],
            mode_assignment=r['spectral_status'],D1_graph_hbar_over_m=first,D1_halfbar=first_err,
            D2_graph_hbar_over_m=second,D2_halfbar=second_err,DT_graph_hbar_over_m=heat,DT_halfbar=heat_err,
            L_drive_nom_um=33 if spec else None,L_perp_nom_um=21 if spec else None,
            q_nom_per_um=np.pi/33 if spec else None,full_spectrum=reveal[spec]['member'] if spec else None,
            n_drive_freq=blind[spec]['n'] if spec else None,
            geometry_source='PC Fig 5.5 rounded label + Sec 5.2 box list' if spec else None))
    return table


def profile_superfluid_branch(row):
    """Compare the PS stiffness curve and a free stiffness at identical settings.
    Both fits allow the temperature readback to fluctuate on the subcritical branch.
    """
    fit = Fit(row,'critical_axis',np.ones(4))
    eos = fit.eos
    t, u, v, f = [row[k] for k in ['T_over_Tc','c1','c2','author_f2']]
    errors = np.array([row[k] for k in ['err_T','err_c1','err_c2','err_f2']])
    load = np.array([1., .5*u*errors[0]/(t*errors[1]), .5*v*errors[0]/(t*errors[2]), 0.])
    grid = np.unique(np.r_[np.linspace(0,1.4,281),eos.X[(eos.X>=0)&(eos.X<=1.4)]])
    out = {}
    for name, cov in [('diagonal',np.eye(4)),('density_correlated',np.diag(1-load**2)+np.outer(load,load))]:
        whitening = np.linalg.inv(np.linalg.cholesky(cov))
        def prof(x, use_ps):
            state = eos.at_X(x)
            theory_t = eos.dc/state.D
            def cost(z):
                a,b,c = forward(state,z)
                res = np.stack(np.broadcast_arrays(theory_t-t,a-u,b-v,c-f))
                res = np.einsum('ij,j...->i...',whitening/errors, res)
                return (res**2).sum(axis=0)
            if use_ps:
                ds = bulk_reference(theory_t) if x>1e-10 else 4.
                if ds >= state.D:
                    return np.inf
                return cost(np.sqrt(state.H*ds/(state.D-ds)))
            return minimum(ZMESH,cost(ZMESH),cost)[0]
        values = {}
        for label, use_ps in [('free',False),('PS',True)]:
            def score(x):
                return prof(x,use_ps)
            val, x = minimum(grid,np.array([score(x) for x in grid]),score)
            values[label] = dict(loss=val,t=eos.dc/eos.density(x))
        values['delta_loss'] = values['PS']['loss']-values['free']['loss']
        out[name] = values
    return out


def inverse_moment_cold():
    # Full S4 integrals are analytic. Report separately the actually sampled band.
    spec = json.loads((HERE.parent/'results/BLIND.json').read_text())['S2']
    u,v,g1,g2,x1,x2 = spec['physical']
    w,obs,_ = np.loadtxt(HERE.parent/'data/S2.txt',skiprows=1).T
    order = np.argsort(w)
    w,obs = w[order],obs[order]
    def inverse_integrand(k):
        return sum(2*x*om**2*g/((k*k-om**2)**2+(g*k)**2)
                   for x,om,g in [(x1,u,g1),(x2,v,g2)])
    full = np.pi*(x1+x2)
    band = quad(inverse_integrand,w[0],w[-1])[0]
    check = quad(inverse_integrand,0,np.inf)[0]
    if not np.isclose(check,full,rtol=1e-10):
        raise ValueError('S4 inverse moment mismatch')
    return dict(spectrum='S2',band=[w[0],w[-1]],full_S4=full,band_S4=band,
                band_observed_trapezoid=trapezoid(2*obs/w,w),outside_fraction_S4=1-band/full,
                I_from_full_S4=1/full)


def calculate():
    data = rows()
    sound = [r for r in data if r['spectral_status']=='two_sound_speeds']
    points = json.loads((HERE/'figure_5_10.json').read_text())['points']
    modes = json.loads((HERE/'figure_4_9.json').read_text())['modes']
    audit = [audit_row(r,p,v) for r,p,v in zip(sound,points,modes['D2'],strict=True)]
    archived = json.loads((HERE/'three_results.json').read_text())
    assoc = {}
    for scale in ['nominal','critical']:
        residual = [r['scenarios'][scale]['I_minus_B'] for r in audit]
        assoc[scale] = dict(f2=association(residual,[r['author_f2'] for r in sound]),
                            D2_graph=association(residual,[r['D2_graph'] for r in audit]))
        # Row 0.9058 is the only known geometry among the six. Assume a common
        # cB for this sensitivity only and enumerate both boxes for the other five.
        gamma_ranks = []
        for choices in product(['23','33'],repeat=len(audit)-1):
            lengths = list(choices)
            lengths.insert(3,'33')
            widths = [r['trial_Gamma2_over_omega2_at_cB_2p3_mm_s'][k] for r,k in zip(audit,lengths)]
            gamma_ranks.append(np.corrcoef(rankdata(residual),rankdata(widths))[0,1])
        assoc[scale]['Gamma_over_omega_rank_range_trial_boxes'] = [min(gamma_ranks),max(gamma_ranks)]
    a = sound[-2]
    fit = Fit(a,'critical_axis',np.ones(4))
    fixed = fit.fixed()
    state = fit.eos.at_X(fixed['X'])
    ps = bulk_reference(a['T_over_Tc'])
    def loss(ds):
        z = np.sqrt(state.H*ds/(state.D-ds))
        return fit.loss(state,z)
    def boundary(ds):
        return loss(ds)-fixed['loss']-CUT
    ds = fixed['Ds']
    comp = dict(t=a['T_over_Tc'],Ds_fit=ds,Ds_PS=ps,loss_fit=fixed['loss'],
                delta_loss_at_PS=loss(ps)-fixed['loss'],conditional_profile95=[
                    brentq(boundary,0,ds),brentq(boundary,ds,state.D*(1-1e-10))])
    da, db = audit[-2:]
    diff = da['D2_graph']-db['D2_graph']
    ea,eb = da['D2_plotted_halfbar'],db['D2_plotted_halfbar']
    width = dict(difference=diff,Z_if_halfbars_are_SE=[diff/(ea+eb),diff/abs(ea-eb)],
                 max_central_disagreement_between_plots=max(abs(r['D2_graph']-p['D2_over_hbar_m'])
                                                            for r,p in zip(audit,points)))
    return dict(rows=audit,D2_graph_AB=width,cold_inverse_moment=inverse_moment_cold(),conditional_rank_associations=assoc,order=order_statistics(sound,archived),
                A_at_fixed_critical_coordinate=comp,A_profiled_temperature=profile_superfluid_branch(a)),geometry(data,modes)


if __name__=='__main__':
    report, matrix = calculate()
    (HERE/'scale_audit.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    with (HERE/'geometry.csv').open('w',newline='') as dest:
        writer = csv.DictWriter(dest,matrix[0].keys(),lineterminator='\n')
        writer.writeheader()
        writer.writerows(matrix)
