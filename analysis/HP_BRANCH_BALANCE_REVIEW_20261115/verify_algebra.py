#!/usr/bin/env python3
"""Exact review checks and counterexamples; no HP, BBN or kinetic simulation.

Scope and budget declared in issue #66: forecast <10 s, hard limit 60 s.
Examples are mathematical counterexamples, never candidate physical inputs.
"""
import hashlib
import json
import platform
import time
from pathlib import Path
import sympy as s


def main():
    started = time.perf_counter()
    checks = []

    def zero(key, expression, scope):
        residual = s.simplify(expression)
        checks.append(dict(id=key, passed=residual == 0, residual=str(residual), scope=scope))

    t = s.symbols('t', real=True)
    R, chi, f = [s.Function(n)(t) for n in ('R', 'chi', 'f')]
    A, D = s.Function('C_A')(chi), s.Function('DeltaC')(chi)
    H = s.diff(R,t)/R
    G = A+f*D
    rho = G/R**4
    Q = s.diff(rho,t)+4*H*rho
    zero('two_phase_balance', Q-s.diff(G,t)/R**4, 'R>0, H=Rdot/R, p=rho/3')
    zero('background_derivative', s.diff(A/R**4,t)+4*H*A/R**4-s.diff(A,chi)*s.diff(chi,t)/R**4,
         'Baseline branch derivative is not a separately identified exchange channel')
    pa, dp = s.Function('p_A')(t), s.Function('Delta_p')(t)
    q0 = s.diff(A/R**4,t)+3*H*(A/R**4+pa)
    qfull = s.diff(rho,t)+3*H*(rho+pa+f*dp)
    zero('nonconformal_remainder', qfull-q0-(D*s.diff(f,t)+f*s.diff(D,chi)*s.diff(chi,t))/R**4-3*H*f*(dp-D/(3*R**4)), 'General additive pressure ansatz')
    Ha, theta = s.symbols('H_a Theta')
    p = (rho+theta)/3
    zero('radius_and_trace_correction', s.diff(rho,t)+3*Ha*(rho+p)-(s.diff(G,t)/R**4+4*(Ha-H)*rho+Ha*theta), 'R need not equal cosmic scale; Theta=-rho+3p')
    T, r, x = s.symbols('T r x', positive=True)
    Phi = s.Function('Phi')
    F = Phi(T*r)/r
    V = 2*s.pi**2*r**3
    E = F-T*s.diff(F,T)
    pressure = -s.diff(F,r)/s.diff(V,r)
    zero('pressure_from_free_energy', pressure-E/(3*V), 'Fixed dimensionless couplings; no omitted geometric terms')
    I = s.Function('I')(x)
    C = (x*I-x*s.diff(x*I,x))/(2*s.pi**2)
    zero('action_to_density', C+x**2*s.diff(I,x)/(2*s.pi**2), 'I=-ln Z, not entropy')
    c = (Phi(x)-x*s.diff(Phi(x),x))/(2*s.pi**2)
    zero('heat_capacity', s.diff(c,x)+x*s.diff(Phi(x),x,2)/(2*s.pi**2), 'dE/dT at fixed R = 2*pi^2*Cprime')
    k = s.symbols('k')
    zero('common_vacuum_offset', ((Phi(x)+k)-x*s.diff(Phi(x)+k,x))/(2*s.pi**2)-c-k/(2*s.pi**2), 'F shifts by k/R; common C offset, no Cprime shift')
    xdot = -D*s.diff(f,t)/(s.diff(A,chi)+f*s.diff(D,chi))
    zero('isolated_constraint', (s.diff(A,chi)+f*s.diff(D,chi))*xdot+D*s.diff(f,t), 'Nonzero denominator; necessary balance, not a kinetic solution')
    # G=chi+f, R=1. At chi=1, f=1/2, opposite velocities give opposite Q.
    values = {'same_state_Q_plus': 1, 'same_state_Q_minus': -1,
              'crossing_level_G_1_5_at_t_0_Q': 1,
              'Q_change_without_crossing_G_1_5': {'G':'3/2+t^2','Q':'2*t'}}
    zero('cross_level_without_sign_change', s.diff(1+t+s.Rational(1,2),t)-1, 'Crossing G=3/2 at t=0 does not flip Q')
    zero('reverse_velocity_reverses_Q', s.diff(1+t+s.Rational(1,2),t)+s.diff(1-t+s.Rational(1,2),t), 'Same state; different tangent directions')
    # Leading N^2 compensation remains without C_Aprime.
    N = s.symbols('N', positive=True)
    zero('leading_N_compensation', s.diff(s.exp(-4*t)*N**2*s.exp(t)**4,t), 'C_A=0, DeltaC=N^2*chi^4, f=e^-4t, chi=e^t, t>=0; algebra only')
    a, b = s.symbols('a b', positive=True)
    eps = (a/(a+f*b*N**2)).subs(f,a/(b*N**2))
    zero('boundary_layer', eps-s.Rational(1,2), 'f=a/(b*N^2), omitted background contributes half the denominator')
    # A Taylor value at one point does not determine a derivative.
    D0, xc, slope = s.symbols('D0 xc slope')
    zero('one_anchor_many_slopes', (D0+slope*(x-xc)).subs(x,xc)-D0, 'Latent heat at coexistence does not determine DeltaCprime')
    d = s.symbols('d', positive=True)
    singular_I = s.log(d-x)
    singular_C = -x**2*s.diff(singular_I,x)/(2*s.pi**2)
    zero('simple_pole_density', singular_C-x**2/(2*s.pi**2*(d-x)), 'Free pole approached from below only')
    zero('simple_pole_heat_capacity', s.diff(singular_C,x)-(2*x/(d-x)+x**2/(d-x)**2)/(2*s.pi**2), 'No substitution of interacting Tc into a free pole')
    # SU(N) adjoint character removes a common U(1) thermal factor.
    z = s.Function('z')(x)
    Iu = s.log(1-z)
    Isu = Iu+z  # n=1 contribution; general term z_n/n.
    zero('su_u_common_prefactor', -x**2*s.diff(Isu-Iu,x)/(2*s.pi**2)+x**2*s.diff(z,x)/(2*s.pi**2), 'Normalized Haar, zero-vacuum free thermal convention')
    result = dict(schema='vm-lab-hp-balance-review-checks-v1', status='PASS' if all(c['passed'] for c in checks) else 'FAIL',
                  checks=checks, counterexample_values=values, scientific_acceptance=False,
                  new_HP_BBN_or_kinetic_simulation=False, preregistered_confirmatory_experiment=False,
                  purpose='Post-review exact verification and falsification of overclaims; not new physical model',
                  python=platform.python_version(), sympy=s.__version__,
                  code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  wall_seconds=time.perf_counter()-started, forecast_seconds=10, hard_wall_seconds=60)
    Path(__file__).with_name('CHECKS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'checks':len(checks),'wall_seconds':result['wall_seconds']}))
    if result['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
