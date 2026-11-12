#!/usr/bin/env python3
"""A source-specific reduced-potential adapter, not a three-loop physics engine.

Equations: Claude (Anthropic), hexagon:2611.00175v1, sections 3, 5, 7, 8;
bootstrap expression: hexagon:2611.00174v1 abstract. Source works: CC BY 4.0.
Implementation written independently for vm-lab; published coefficients imported.
"""
import argparse
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import platform
import time

ROOT = Path(__file__).resolve().parent


def potential(u, a, b):
    """S/N^2 in the declared truncated large-N potential; a=m1^2.

    u is |tr(U)/N|, not time, memory, probability or a NOW node count.
    """
    if not (math.isfinite(u) and 0 <= u < 1):
        raise ValueError('u must belong to [0,1)')
    if not (math.isfinite(a) and math.isfinite(b)):
        raise ValueError('finite coefficients required')
    wall = 0.0 if u <= 0.5 else 0.25 - 0.5*math.log(2*(1-u)) - u*u
    return wall + a*u*u + b*u**4


def eliminate_massive_mode(b_tilde, kappa, m2_squared):
    if m2_squared <= 0:
        raise ValueError('stable massive mode requires m2_squared > 0')
    return b_tilde - kappa*kappa/m2_squared


def quartic(beta, Q4, c3, A2, q4):
    if beta <= 0 or A2 <= 0:
        raise ValueError('positive beta and A2 required')
    I = Q4/2 + 2*c3*c3/A2
    bg4 = -4*beta*beta*I + beta*q4
    return {'I': I, 'b_over_g4': bg4, 'b_over_lambda2': bg4/(256*math.pi**4),
            'q4_sign_threshold': 4*beta*I}


def bisect(fn, lo, hi):
    flo, fhi = fn(lo), fn(hi)
    if flo*fhi >= 0:
        raise ValueError('root not bracketed')
    for _ in range(100):
        mid = (lo+hi)/2
        fm = fn(mid)
        if fm == 0 or mid in (lo, hi):
            return mid
        if flo*fm < 0:
            hi = mid
        else:
            lo, flo = mid, fm
    return (lo+hi)/2


def phase_landmarks(b):
    if not -0.1 <= b < 0:
        raise ValueError('adapter limited to declared small negative b in [-0.1,0)')
    # Stationarity solves for a; birth additionally has S''=0.
    a_at = lambda u: 1 - 1/(4*u*(1-u)) - 2*b*u*u
    ub = bisect(lambda u: 2*u-1+16*b*u**3*(1-u)**2, 0.5, 0.99)
    uc = bisect(lambda u: potential(u, a_at(u), b), ub, 0.99)
    return {'b': b, 'u_birth': ub, 'a_birth': a_at(ub),
            'u_coexist': uc, 'a_coexist': a_at(uc),
            'a_hagedorn': 0.0,
            'coexistence_residual': potential(uc, a_at(uc), b)}


def compute():
    started = time.perf_counter()
    checks = []
    def check(name, okay):
        checks.append({'id': name, 'passed': bool(okay)})
    # Exact completion of the square for complex u1=x+iy and u2=p+iq.
    for x,y,p,q,k,m,bt in [(F(1,3),F(1,5),F(2,7),F(-1,4),F(3,5),F(2),F(1,8)),
                          (F(-1,2),F(1,7),F(1,2),F(2,3),F(-4,3),F(1,2),F(-2)),
                          (F(1),F(0),F(0),F(0),F(0),F(1),F(2))]:
        xr, xi = x*x-y*y, 2*x*y
        norm4 = (x*x+y*y)**2
        before = m*(p*p+q*q)+2*k*(xr*p+xi*q)+bt*norm4
        after = m*((p+k*xr/m)**2+(q+k*xi/m)**2)+eliminate_massive_mode(bt,k,m)*norm4
        check('complete_square_'+str(len(checks)), before == after)
    check('disabled_exchange', eliminate_massive_mode(F(2),F(0),F(1)) == 2)
    for m in (0,-1):
        try:
            eliminate_massive_mode(1,1,m)
        except ValueError:
            check('reject_mass_'+str(m), True)
        else:
            check('reject_mass_'+str(m), False)
    x=F(1,2); Q4=4*x**3+8*x**4; c3=2*x**3; A2=F(1,2)
    su2=Q4/2+2*c3*c3/A2
    check('su2', su2 == F(3,4))
    values=quartic(2.6339158,2.1222,0.16821,0.9742786,-2.234)
    check('coefficient',abs(values['b_over_g4']+36.94)<=0.02)
    # Conditional rectangular envelope of printed I/q4 errors, not a confidence interval.
    beta=2.6339158
    envelope=sorted(-4*beta**2*I+beta*q for I in (1.11918-0.00015,1.11918+0.00015)
                    for q in (-2.234-0.003,-2.234+0.003))
    landmarks=phase_landmarks(-0.1)
    check('phase_birth',abs(landmarks['a_birth']-0.053)<=0.001)
    check('phase_coexist',abs(landmarks['a_coexist']-0.032)<=0.001)
    check('phase_order',0<landmarks['a_coexist']<landmarks['a_birth'])
    pos=[{'a':a,'b':0.1,'u_min':math.sqrt(-a/0.2)} for a in (-0.01,-0.0001,-0.000001)]
    check('positive_control',0<pos[2]['u_min']<pos[1]['u_min']<pos[0]['u_min']<=0.5)
    lam=12*math.pi**2/(math.pi**2+4*math.asinh(1)**2)
    check('bootstrap_constant',abs(lam-9.1266)<=0.00005)
    return {'schema':'vm-lab-anthropic-bh-formula-check-v1',
            'status':'SCOPED_CHECKS_PASS' if all(c['passed'] for c in checks) else 'CHECK_FAILED',
            'not_full_paper_replication':True,'upstream_code_executed':False,
            'new_physical_claim':False,'checks':checks,'su2_I_exact':str(su2),
            'imported_literal_scheme_combination':values,
            'b_over_g4_printed_input_envelope':[envelope[0],envelope[-1]],
            'envelope_scope':'Conditional on printed error magnitudes; not a statistical confidence interval or bound on unexamined systematic error.',
            'illustrative_phase_landmarks':landmarks,'positive_b_control':pos,
            'bootstrap_constant_only':lam,
            'plan_sha256':hashlib.sha256((ROOT/'PLAN.json').read_bytes()).hexdigest(),
            'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'python':platform.python_version(),'platform':platform.platform(),
            'wall_seconds':time.perf_counter()-started}


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=ROOT/'CHECKS.json');args=ap.parse_args()
    result=compute();args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'checks':len(result['checks']),'wall_seconds':result['wall_seconds']}))
    raise SystemExit(0 if result['status']=='SCOPED_CHECKS_PASS' else 1)
