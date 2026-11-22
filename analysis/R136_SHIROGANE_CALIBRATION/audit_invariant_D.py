import numpy as np
from scipy.stats import norm, chi2
from scipy.optimize import brentq

# Archived R136 central values and graph-derived errors.
V = {
    '48': dict(beta0=6.0636007, ebc=0.00018, slope=68.96, resid=0.024438471, eh=0.021046414, ec=0.0092617872, e3=0.022559457),
    '64': dict(beta0=6.0629778, ebc=0.00014, slope=106.78, resid=-0.029300048, eh=0.016605519, ec=0.0071178013, e3=0.014992044),
}
D = V['48']['beta0'] - V['64']['beta0']

def contrast_errors(rho_hc, rho_153, rho_x=0.0):
    # Illustrative covariance model; rho values are assumptions, not measurements.
    phase = {}
    for key, v in V.items():
        var15 = v['eh']**2 + v['ec']**2 - 2*rho_hc*v['eh']*v['ec']
        varJ = var15 + v['e3']**2 - 2*rho_153*np.sqrt(var15)*v['e3']
        phase[key] = np.sqrt(varJ) / v['slope']
    a, b = phase['48'], phase['64']
    varD = a*a + b*b - 2*rho_x*a*b + V['48']['ebc']**2 + V['64']['ebc']**2
    return phase, np.sqrt(varD)

print('D_beta =', D)
for rhc, r153, rx in [(0,0,0),(.5,.5,0),(.7,.7,0),(.9,.9,0),(.9,.9,.3),(.5,.9,0),(.9,.5,0)]:
    _, sd = contrast_errors(rhc, r153, rx)
    z = D/sd
    print(f'rho_hc={rhc:.1f}, rho_153={r153:.1f}, rho_x={rx:.1f}: sigma_D={sd:.6f}, z={z:.3f}, p={2*norm.sf(abs(z)):.3f}')

rho_crit = brentq(lambda r: D/contrast_errors(r,r,0)[1]-1.96, 0, .999)
sd0 = contrast_errors(0,0,0)[1]
print('rho_crit common-rho slice =', rho_crit)
print('sigma_D rho=0 =', sd0, 'required sigma_D =', D/1.96, 'compression % =', 100*(1-(D/1.96)/sd0))

# GLS common-shift fit; compare with D using the same unrounded covariance.
for rho in (0,.9):
    phase,_ = contrast_errors(rho,rho,0)
    slopes = np.array([V['48']['slope'],V['64']['slope']])
    residuals = np.array([V['48']['resid'],V['64']['resid']])
    vJ = np.array([phase['48']**2,phase['64']**2])*slopes**2
    vbc = np.array([V['48']['ebc'],V['64']['ebc']])**2*slopes**2
    C = np.diag(vJ+vbc)+0.00028**2*np.outer(slopes,slopes)
    Ci = np.linalg.inv(C)
    db = (slopes@Ci@residuals)/(slopes@Ci@slopes)
    cmin = residuals@Ci@residuals-(slopes@Ci@residuals)**2/(slopes@Ci@slopes)
    c0 = residuals@Ci@residuals
    print(f'GLS rho={rho}: delta_beta={db:+.6f}, chi2_min={cmin:.3f}, p={chi2.sf(cmin,1):.3f}, chi2_zero={c0:.3f}, p0={chi2.sf(c0,2):.3f}')

# Anchor-cancellation identity, with x_match obtained from J15(x)=J3, not the temperature axis.
x48,x64 = 0.99678487,0.99918332
slope8 = 0.62168433
D_lin = (6.06160-6.06247)+slope8*(x64-x48)
print('D linearized =',D_lin,'archived D =',D,'difference =',D-D_lin)
print('D curve-anchor =',0.036564317/68.96+0.01009902/106.78)
print('D table-anchor =',0.024438471/68.96+0.029300048/106.78)
print('slope error contribution =',0.0008*(x64-x48))

# Flow-time and finite-volume controls.
J0_48,e0_48,J14_48,e14_48 = 1.20218387,.025700647,1.145928009,.022559457
J0_64,e0_64,J14_64,e14_64 = 1.131935434,.019561048,1.098524592,.014992044
d48,d64 = J14_48-J0_48,J14_64-J0_64
ed48,ed64 = np.hypot(e0_48,e14_48),np.hypot(e0_64,e14_64)
print('flow drifts:',d48,ed48,abs(d48)/ed48,d64,ed64,abs(d64)/ed64)
print('difference of drifts:',d48-d64,np.hypot(ed48,ed64),(d48-d64)/np.hypot(ed48,ed64))
print('J3 finite-volume difference:',J14_48-J14_64,np.hypot(e14_48,e14_64),(J14_48-J14_64)/np.hypot(e14_48,e14_64))
print('method-systematic order in D:',.02/68.96,.05/68.96)
