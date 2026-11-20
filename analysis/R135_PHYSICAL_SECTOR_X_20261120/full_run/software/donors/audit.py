"""Run the donor-based thermodynamic and sudden freeze-out controls."""
import argparse
import json
import math
from pathlib import Path
import sys

import numpy as np
from scipy.integrate import quad
from scipy.optimize import brentq
from scipy.special import kv

from extract import physics, observations, baseline_observations, article, measurement, one, WITH_ERROR
from fetch import acquire, HERE, sources
sys.path.insert(0, str(HERE.parent / 'xb_reference'))
import compute as xb  # published cold-boundary calculation


class SM:
    def __init__(self, path):
        t, rho, _, s, err = np.loadtxt(path, unpack=True)
        if len(t) != 10000 or not np.all(np.diff(t) > 0) or not np.all(np.diff(s*t**3) > 0):
            raise ValueError('Invalid SM entropy table')
        self.t = np.log(t)
        self.rho = rho
        self.s = s
        self.table = (self.t, s, err)

    def degrees(self, temp):
        y = math.log(temp)
        if not self.t[0] <= y <= self.t[-1]:
            raise ValueError('Outside the SM table')
        return float(np.interp(y, self.t, self.s)), float(np.interp(y, self.t, self.rho))

    def temp(self, entropy):
        return xb.photon_temperature(self.table, entropy, 0)


def gas_entropy(states, x, relativistic):
    total = 0.
    for state in states:
        z = x * state['m_over_m0']
        g = 2 * state['spin'] + 1
        if relativistic:
            # Bose gas at mu=0. At z>=5, terms above k=12 are exponentially suppressed.
            total += g*z*z/(2*math.pi**2)*sum(4*kv(2,k*z)/k**2 + z*kv(1,k*z)/k for k in range(1,13))
        else:
            total += g*(z/(2*math.pi))**1.5 * math.exp(-z)*(z+2.5)
    return float(total)


def boundary(sm, m, R, x, entropy):
    tx = m/x
    tg = sm.temp(entropy * tx**3 / R)
    return dict(s_over_T3=entropy,T_X_GeV=tx,T_gamma_GeV=tg,xi=tx/tg)


def freeze_out(sm, m, R, xc):
    # FMS equations 8, 10-15, single nonrelativistic species, N=3, NDA B=1.
    reduced_mpl = 2.435e18  # GeV
    sigma = (4*math.pi/3)**6 / ((4*math.pi)**3 * m**5)

    def at(x):
        n = (m*m/(2*math.pi*x))**1.5 * math.exp(-x)
        tg = sm.temp(x*n/R)
        gs,grho = sm.degrees(tg)
        rho_sm = math.pi**2/30 * grho * tg**4
        h = math.sqrt(rho_sm/3)/reduced_mpl
        return tg,gs,grho,n,rho_sm,math.log(x*sigma*n*n/(3*h))
    x = brentq(lambda y: at(y)[-1],xc,40)
    tg,gs,grho,n,rho_sm,residual = at(x)
    rhs = gs*R/(180*math.pi)*(m**4*reduced_mpl*sigma/math.sqrt(grho*math.pi**2/10))**1.5
    if abs(2.5*math.log(x)+2*x-math.log(rhs)) > 1e-8 or abs(residual)>1e-8:
        raise ValueError('Equations 12 and 14 disagree')
    yield_fo = R/x
    return dict(x_fo=x,T_gamma_fo_GeV=tg,g_s_fo=gs,g_rho_fo=grho,Y_LO=yield_fo,
                Omega_h2_LO=0.1186*m*yield_fo/4.322e-10,
                rho_X_over_visible_at_fo=n*m*(1+1.5/x)/rho_sm)


def equilibrium_eos(inputs):
    """One pressure anchor and integration constant on both stable branches."""
    fit = inputs['entropy_fit']

    def entropy(t):  # s/Tc^3
        if not 0.8 <= t <= 3.433:
            raise ValueError('Outside fitted stable branches')
        if t < 1:
            y = (1-t)**(1/3)
            a,b,c,d = fit['s_cold']
            reduced = a+y*(b+y*(c+y*d))
        else:
            w = math.log(t)
            a,b,c,d,e = fit['s_hot'][int(t>1.1)]
            reduced = (a+w*(b+c*w))/(1+w*(d+e*w))
        return reduced*t**3

    def pressure(t):
        return fit['p_anchor_hot'] + quad(entropy,1,t,points=[1.1] if t>1.1 else [])[0]

    rows = []
    for row in inputs['continuum_s_over_T3']:
        t = row['T_over_Tc']
        p = pressure(t)
        s = entropy(t)
        # At a change of fit or a domain endpoint a central derivative has no single branch.
        cs2 = None
        h = 1e-5
        if all(abs(t-edge)>h for edge in (0.8,1,1.1,3.433)):
            ds = (entropy(t+h)-entropy(t-h))/(2*h)
            cs2 = s/(t*ds)
            if not 0 < cs2 < 1 or not math.isclose(
                    (pressure(t+h)-pressure(t-h))/(2*h),s,rel_tol=2e-5):
                raise ValueError('Stable EOS consistency failure')
        rows.append(dict(T_over_Tc=t, s_over_T3=s/t**3,p_over_T4=p/t**4,
                         rho_over_T4=(t*s-p)/t**4,cs2_fit=cs2))
    return rows


def thin_wall_controls(files, latent_heat):
    source = article(files['iwasaki'], 'interface.tex')
    rows = []
    for macro, nt in [('SigRotF', 4), ('SigRotS', 6)]:
        result = measurement(one(r'\\def\\'+macro+r'\{'+WITH_ERROR+r'\}', source))
        coefficient = 16 * math.pi * result['value']**3 / (3 * latent_heat**2)
        # Delta p = L * delta, delta = 1 - T/Tc. Finite-Nt sensitivity only.
        rows.append(dict(Nt=nt, sigma_over_Tc3=result, thin_wall_coefficient=coefficient))
    return rows


def scalar_portal_control(files):
    source = article(files['fms-portals'], 'draft-v3.tex')
    scalar = measurement(one(r'4\\pi\\alpha_xF_\{\\zpp\}\^S = '+WITH_ERROR+r'\\,m_x\^3', source))
    # FMS dimension-eight gluonic operator, eq. labelled sglue. The matrix
    # element uses 4 pi alpha_x F^S / m0^3; divide by 4 pi before squaring.
    a,b = one(r'\\frac\{\\alpha_3\^2\}\{16\\pi\}\\lrf\{(\d+)\}\{(\d+)\}\^2',source)
    prefactor = 8/(16*math.pi) * (int(a)/int(b)/(4*math.pi))**2
    return dict(scalar_4pi_alpha_F_over_m0_cubed=scalar,
                K_gg=prefactor*scalar['value']**2,
                K_gg_one_sigma_input_range=[prefactor*(scalar['value']+sign*scalar['sigma'])**2 for sign in (-1,1)],
                convention='Gamma(0++ -> gg) = K_gg alpha_3^2 chi_3^2 m0^9/M^8; partonic EFT',
                C_odd_matrix_element='NDA in donor; independent calibration open')


def run(files):
    p = physics(files)
    sm = SM(files['sm'])
    fixture = json.loads((HERE.parent/'xb_reference/inputs.json').read_text())
    lattice = dict(r0_Tc=dict(p['r0_Tc'],source='FRANCIS'),r0_m0=dict(p['r0_m0'],source='MP'),
                   s_cold_over_Tc3=dict(p['phase_entropy']['cold'],source='GIUSTI'))
    if lattice != fixture['lattice']:
        raise ValueError('Source extraction differs from existing scale/entropy lock')
    computed = xb.compute(dict(lattice=lattice,preparations=p['preparations']),sm.table)
    frozen = json.loads((HERE.parent/'xb_reference/coordinates.json').read_text())
    if len(computed['points']) != len(frozen['points']):
        raise ValueError('Missing boundary')
    for pt, ref in zip(computed['points'], frozen['points']):
        if pt['point_id']!=ref['point_id'] or any(not math.isclose(pt[k],ref[k],rel_tol=1e-12)
                         for k in ('m0_GeV','R_post','T_X_MeV','T_gamma_MeV','xi')):
            raise ValueError('Source-driven cold boundary differs from published coordinates')
    xc = p['r0_m0']['value']/p['r0_Tc']['value']
    four = [s for s in p['states'] if s['index'] in (1,2,4,5)]
    rows = []
    for pt in p['preparations']:
        m,R = pt['m0_GeV'],pt['R_post']
        cases = {}
        for name,x in [('FMS',5.0),('Sommer',xc)]:
            variants = {'lattice':p['phase_entropy']['cold']['value']}
            for label,states in [('4',four),('12',p['states'])]:
                for approximation in ('NR','Bose'):
                    variants[label+approximation] = gas_entropy(states,x,approximation=='Bose')
            cases[name] = {k:boundary(sm,m,R,x,s) for k,s in variants.items()}
        rows.append(dict(**pt,boundary=cases,single_species_FMS=freeze_out(sm,m,R,xc)))
    lock = sources()
    return dict(source_sha256={k:lock[k]['sha256'] for k in files},
                dim8_portal=scalar_portal_control(files),finite_Nt_interfaces=thin_wall_controls(files,p['latent_heat']['value']),
                source_physics=p, equilibrium_eos=equilibrium_eos(p), observations={**baseline_observations(files), **observations(files)}, rows=rows,
                Tc_over_m0_string_tension_check=p['Tc_over_sqrt_sigma']['value']/p['m0_over_sqrt_sigma']['value'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache',type=Path,required=True)
    parser.add_argument('--offline',action='store_true')
    args=parser.parse_args()
    files=acquire(args.cache,{'physics','observations','interface','portal','bbn_baseline'},args.offline)
    print(json.dumps(run(files),indent=2,allow_nan=False))


if __name__=='__main__':
    main()
