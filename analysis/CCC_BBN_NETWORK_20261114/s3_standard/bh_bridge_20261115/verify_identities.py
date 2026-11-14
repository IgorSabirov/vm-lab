"""Manual algebra check only: no BBN, sampled parameters, or phase kinetics.

Run with Python 3 and sympy==1.14.0. Writes JSON to stdout.
The existing parent result is referenced in place and verified by SHA256.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import time
import sympy as s

started = time.perf_counter()
checks = {}

def identity(name, expression):
    residual = s.simplify(expression)
    assert residual == 0, (name, residual)
    checks[name] = str(residual)

T, R, chi = s.symbols('T R chi', positive=True)
f = s.Function('f')
V = 2*s.pi**2*R**3
F = f(T*R)/R
E = F-T*s.diff(F, T)
p = -s.diff(F, R)/s.diff(V, R)
identity('finite_volume_conformal_trace', 3*p*V-E)
identity('entropy_depends_on_TR_only', -s.diff(F,T)+s.diff(f(chi),chi).subs(chi,T*R))
# S=-f'(chi), C=dE/dT=-chi*f''(chi), so dS=C*dln(chi).
C = -chi*s.diff(f(chi),chi,2)
identity('adiabatic_control_variable', -s.diff(f(chi),chi,2)-C/chi)

Qem, Qnu, Qen = s.symbols('Qem Qnu Qen')
identity('sector_energy_exchange_cancels', (-Qem-Qnu)+(Qem-Qen)+(Qnu+Qen))

D, eps = s.symbols('D eps', positive=True)
eta_ratio = D**-1
nu_ratio = D**s.Rational(-4,3)
identity('photon_entropy_eta_neff_relation', nu_ratio-eta_ratio**s.Rational(4,3))
identity('late_photon_energy_to_entropy', ((1+eps)**s.Rational(3,4))**s.Rational(-4,3)-(1+eps)**-1)
identity('zero_injection_limit', nu_ratio.subs(D,1)-1)

parser = argparse.ArgumentParser()
parser.add_argument('--parent-result', type=Path,
    default=Path(__file__).resolve().parents[2]/'s3_input_audit/results/RESULT.json')
args = parser.parse_args()
parent_text = args.parent_result.read_text()
assert hashlib.sha256(parent_text.encode()).hexdigest() == '48a81ecf8734e04426d4b3463a0e68deb20c12e8865459272fcdbae4d9858f02'
parent = json.loads(parent_text)
Y0 = parent['rows']['YPBBN']['baseline']
D0 = parent['rows']['DoH']['baseline']
Jy = parent['rows']['YPBBN']['J_dY_dlneta_secant']
Jd = parent['rows']['DoH']['J_dY_dlneta_secant']
output = {
    'status': 'MANUAL_ALGEBRA_VERIFIED',
    'BBN_executed': False,
    'BH1_executed': False,
    'scientific_acceptance': False,
    'scope': 'Conditional equilibrium/entropy identities and reuse of an existing local eta response; no physical embedding selected',
    'sympy_version': s.__version__,
    'identities': checks,
    'parent_commit': '9e2f5cec303e1a58f354479ffd1fca0db9cbd9b2',
    'parent_result_sha256': hashlib.sha256(parent_text.encode()).hexdigest(),
    'eta_component_only_at_fixed_late_eta': {
        'order': ['Yp','log10_D_over_H','ln_Neff_nu'],
        'derivative_wrt_ln_Dgamma': [Jy, Jd/(D0*math.log(10)), -4/3],
        'dln_D_over_H_dln_Dgamma': Jd/D0,
        'dln_D_over_H_dln_Neff_nu': -3/4*Jd/D0,
        'dYp_dln_Neff_nu': -3/4*Jy,
        'warning': 'Not a full BH1 prediction: omitted extra expansion, weak-spectrum, nonthermal and direct nuclear effects must be separately computed.'
    },
    'wall_seconds': time.perf_counter()-started
}
print(json.dumps(output,ensure_ascii=False,indent=2))
