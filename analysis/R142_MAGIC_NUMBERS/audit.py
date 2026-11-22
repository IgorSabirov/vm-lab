"""Retrospective numerical controls. Masses in MeV, wavelengths in vacuum."""
import json
from math import pi, factorial, sqrt
from pathlib import Path


def superstable(parameter, period):
    x = 0.5
    for _ in range(period):
        x = parameter * x * (1 - x)
    return x - 0.5


def period_root(period, lo, hi):
    sign = superstable(lo, period)
    assert sign * superstable(hi, period) < 0
    for _ in range(48):
        mid = (lo + hi) / 2
        if sign * superstable(mid, period) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


roots = [2.] + [period_root(2**i, lo, hi) for i, (lo, hi) in enumerate(
    [(3.2, 3.3), (3.49, 3.51), (3.55, 3.558), (3.565, 3.567),
     (3.5691, 3.5694), (3.5697, 3.56985)], 1)]
e, mu, tau = 0.51099895, 105.6583755, 1776.86
a = sqrt(e) + sqrt(mu)
b = 3 * (e + mu) - 2 * a*a
tau_roots = [(2*a + s*sqrt(4*a*a-b))**2 for s in (-1, 1)]
wyler = 9/(8*pi**4)*(pi**5/(16*factorial(5)))**0.25
rinfty = 10973731.568
ratio = 1836.152673
results = {
    "Balmer_H_vacuum_nm_reduced_mass": [1e9*(1+1/ratio)/(rinfty*(1/4-1/n**2)) for n in range(3,7)],
    "Koide_Q_reference_masses": (e+mu+tau)/(a+sqrt(tau))**2,
    "Koide_tau_branches_MeV": tau_roots,
    "Wyler_inverse_alpha": 1/wyler,
    "Wyler_residual_in_CODATA2022_u": (1/wyler-137.035999177)/0.000000021,
    "Feigenbaum_parameters": roots,
    "Feigenbaum_ratios": [(y-x)/(z-y) for x,y,z in zip(roots,roots[1:],roots[2:])],
    "Mackay_closed_sizes": [(10*k**3+15*k**2+11*k+3)//3 for k in range(1,5)],
    "Dirac_inverse_age_per_year_for_13_8_Gyr": -1/13.8e9,
    "Omega_linear_last_interval_MeV_rounded_inputs": 1530+(1530-1385),
    "Bode_Uranus_Neptune_AU": [0.4+0.3*2**k for k in (6,7)]
}
assert all(abs((e+mu+t)/(a+sqrt(t))**2-2/3)<1e-12 for t in tau_roots)
assert 4.66 < results["Feigenbaum_ratios"][-1] < 4.68
Path(__file__).with_name("AUDIT.json").write_text(json.dumps(results, indent=2)+"\n")
