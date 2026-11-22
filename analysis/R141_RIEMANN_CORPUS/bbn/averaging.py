"""Finite circular spectra, independent marks, thermal filtering and cross-time coherence."""
import numpy as np
from scipy.special import betaln, digamma, ndtr

from replay import ensemble_covariance, thermal


def circular_variance(g, de, spacing, levels, ensemble, mark_variance=0, fixed_total=False):
    """Periodize the physical filter on a circle of length N*spacing. Exact finite form factors."""
    cells = round(levels * spacing / de)
    folded = np.bincount(np.arange(g.size) % cells, weights=g, minlength=cells)
    power = np.abs(de * np.fft.fft(folded))**2
    m = np.abs(np.rint(np.fft.fftfreq(cells)*cells)).astype(int)
    if ensemble == 'GUE':
        form = np.minimum(m / levels, 1.)
    else:
        lo = m <= levels
        mid = (levels + 1) / 2
        form = np.empty_like(m, dtype=float)
        form[lo] = (m[lo]/levels) * (2 - digamma(mid+m[lo]) + digamma(mid))
        form[~lo] = 2 - m[~lo]/levels * (digamma(m[~lo]+mid) - digamma(m[~lo]-levels+mid))
        assert abs(form[1] - 2/(levels+1)) < 1e-12
    pos = power @ form / levels
    white = spacing * de * (folded @ folded)
    assert np.isclose(power.sum()/levels, white)
    if fixed_total and mark_variance:
        # Conditional independent gamma marks divided by their sample mean (Dirichlet).
        return (levels*pos + mark_variance*(levels*white-power[0])) / (levels+mark_variance)
    return pos + mark_variance*white


def balanced_strength_variance(nu):
    # Isolated, narrow, two open channels with equal mean width, independent Gamma(nu/2).
    # Strength is proportional to W1 W2 / (W1+W2) = total * r(1-r).
    a = nu/2
    log_ratio = betaln(a+2,a+2) + betaln(a,a) - 2*betaln(a+1,a+1)
    return (1+1/(2*a))*np.exp(log_ratio)-1


def direct_cue_check():
    # Discrete projector kernel of the circular determinantal process, independent formula.
    n, cells, de = 8, 160, 0.5
    x = np.arange(cells)*de
    f = np.exp(-((x-16)/7)**2)
    kernel = np.exp(2j*np.pi*np.outer(np.arange(cells),np.arange(n))/cells)
    kernel = kernel @ kernel.conj().T / cells
    spacing = de*cells/n
    var = spacing**2*((f*f) @ kernel.diagonal().real - f @ (abs(kernel)**2) @ f)
    spectral = circular_variance(f,de,spacing,n,'GUE')
    assert np.isclose(spectral,var,atol=1e-10)
    return abs(spectral-var)


def windows(t9, sensitivity, de=0.5):
    energy = np.arange(2+de/2, 2000, de)
    _, w = thermal(t9,energy)
    _, fixed = thermal(np.array([0.5,0.8]),energy)
    return energy,w,np.vstack((fixed,sensitivity[:,:,0] @ w))


def width_controls(t9, sensitivity, ref):
    de, spacing, b = 0.5, 10., 0.1
    e,w,filters = windows(t9,sensitivity,de)
    variances = {ens: np.diag(ensemble_covariance(filters,de,spacing,ens,32768))
                 for ens in ('GOE','GUE','Poisson')}
    units = b*np.array([1.,1.,ref['baseline'][0]/ref['observational_sigma'][0],
                              ref['baseline'][1]/ref['observational_sigma'][1]])
    rows = {}
    finite = {}
    for ens,nu in [('GOE',1),('GUE',2)]:
        pos = variances[ens]
        white = variances['Poisson']
        np.testing.assert_allclose(np.sqrt(pos),ref['projected']['10'][ens]['sd_unit_fraction'])
        values = {'equal':0.,'common_chi2_2':1.,'one_width':2/nu,
                  'balanced_two_channels':balanced_strength_variance(nu)}
        rows[ens] = {}
        for name,v in values.items():
            sd = np.sqrt(pos+v*white)
            rows[ens][name] = dict(mark_var=v, rate_rel_sd=(b*sd[:2]).tolist(),
                                   obs_sd=(units[2:]*sd[2:]).tolist(),
                                   marking_fraction_of_DH_variance=float(v*white[2]/sd[2]**2))
        finite[ens] = {}
        for n in [4,8,16,32,64,128,256,512,1024]:
            g=filters[2]
            fixed=circular_variance(g,de,spacing,n,ens)
            marked=circular_variance(g,de,spacing,n,ens,2/nu)
            conditioned=circular_variance(g,de,spacing,n,ens,2/nu,True)
            finite[ens][str(n)]=(units[2]*np.sqrt([max(fixed,0),marked,conditioned])).tolist()
    gaussian_accuracy = {}
    for model in rows['GOE']:
        # Equal priors, one D/H, identical means, independent Gaussian observational noise.
        wide, narrow = sorted([np.hypot(1, rows[e][model]['obs_sd'][0])
                               for e in ('GOE', 'GUE')], reverse=True)
        cross = np.sqrt(2*np.log(wide/narrow)/(1/narrow**2-1/wide**2))
        gaussian_accuracy[model] = .5 + ndtr(cross/narrow) - ndtr(cross/wide)
    resolution={}
    for width in [1,5,20,50,100]:
        g=np.exp(-0.5*((e-150)/width)**2)
        g /= g.sum()*de
        sigma=[np.sqrt(ensemble_covariance(g[None,:],de,spacing,ens,32768)[0,0]) for ens in ('GOE','GUE')]
        resolution[str(width)]=dict(equal_strength_GOE_GUE_sd_ratio=sigma[0]/sigma[1])
    input_n_eff = (filters.sum(axis=1)*de)**2 / (spacing * de * (filters*filters).sum(axis=1))
    covariance=ensemble_covariance(filters,de,spacing,'GOE',32768)
    corr=covariance[0,1]/np.sqrt(covariance[0,0]*covariance[1,1])
    return dict(marks=rows, idealized_single_DH_gaussian_accuracy=gaussian_accuracy, finite_circle_DH_obs_sd=finite, filter_resolution_keV=resolution,
                effective_count=input_n_eff.tolist(),rate_cross_T_GOE_corr=corr,
                cue_direct_absolute_error=direct_cue_check())


def independent_temperature_control(t9,sensitivity):
    # Exact white-mark term in energy. Comparison intentionally discards all off-diagonal
    # temperature covariances in the second calculation, then changes the time subdivision.
    _,w,g=windows(t9,sensitivity)
    j=sensitivity[0,:,0]
    coherent=np.sum(g[2]**2)
    diagonal=(j*j) @ np.sum(w*w,axis=1)
    return np.sqrt(diagonal/coherent)
