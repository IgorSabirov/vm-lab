"""Technical checks of formulas in the review; not a scientific model run.

Inputs D, CMB direction and H0 are the neighbor's illustrative parameters,
not a fresh fit of observations. Two distinct simultaneity questions are kept.
"""
from pathlib import Path
import json
import math
import time

started = time.perf_counter()
c = 299792458.0
D = 2.365e22
day = 86400.0
year = 365.25 * day
rows = []
for v in [1.0, 1.5, 2.6, 30000.0, 109000.0, 369820.0, .1*c, .9*c]:
    gamma = 1/math.sqrt(1-(v/c)**2)
    t_selected = v*D/c**2
    t_fixed_prime = -gamma*v*D/c**2
    x_selected_prime = gamma*(D-v*t_selected)
    invariant = x_selected_prime**2 - (gamma*(c*t_selected-v*D/c))**2
    assert math.isclose(invariant, D**2-(c*t_selected)**2, rel_tol=1e-12)
    assert abs(gamma*(t_selected-v*D/c**2)) < 1e-8
    rows.append(dict(v_m_s=v, beta=v/c, distant_clock_simultaneous_days=t_selected/day,
                     distant_clock_simultaneous_years=t_selected/year,
                     fixed_event_tprime_years=t_fixed_prime/year))

lc, bc, lm, bm = map(math.radians, [264.021, 48.253, 121.174329, -21.573309])
cos_angle = math.sin(bc)*math.sin(bm)+math.cos(bc)*math.cos(bm)*math.cos(lc-lm)
v_parallel = 369820*cos_angle
H0 = 67400/3.085677581491367e22
fermi_leading_years = -H0*D*D/(2*c*c)/year
# Milne is flat spacetime, but cosmic and Fermi simultaneity differ.
# Dimensionless rho/(c*tau)=0.01 avoids subtractive cancellation in the check.
x = .01
milne_exact = -x*x/(1+math.sqrt(1-x*x))
milne_leading = -.5*x*x
assert abs(milne_exact/milne_leading-1) < 3e-5

# Explicit ABL counterexample to unique intermediate outcome:
# pre=post=|+x>, intermediate Z projectors, no intervening Hamiltonian.
# Squared transition amplitudes are exactly (1/4, 1/4).
abl_weights = [.25, .25]
abl = [w/sum(abl_weights) for w in abl_weights]
assert abl == [.5, .5]

out = dict(scope="technical_validation; supplied scales and exact elementary examples",
           inputs=dict(c_m_s=c, distance_m=D, year_days=365.25),
           simultaneity=rows,
           cmb=dict(cos_angle=cos_angle, projected_velocity_m_s=v_parallel,
                    selected_distant_clock_years=v_parallel*D/c**2/year),
           flrw_leading_fermi_minus_cosmic_note="t_cosmic - tau_Fermi at equal Fermi time; idealized FLRW only",
           cosmic_minus_fermi_years=fermi_leading_years,
           milne=dict(rho_over_c_tau=x, exact_relative_difference=milne_exact,
                      quadratic_relative_difference=milne_leading, spacetime_curvature=0),
           abl_probabilities=abl, pass_checks=True,
           runtime_seconds=time.perf_counter()-started,
           scientific_simulations=0, vm_runs=0)
Path(__file__).with_name('EXAMPLE_CHECKS.json').write_text(json.dumps(out, indent=2)+'\n')
print(json.dumps(out, indent=2))
