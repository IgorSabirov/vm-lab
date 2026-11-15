"""Analytic checks only; <=60 seconds local; no BBN, VM, network or kinetics."""
import json
import time
import platform
from pathlib import Path
import sympy as s

started = time.perf_counter()
checks = {}
def eq(name, expr):
    residual = s.simplify(expr)
    assert residual == 0, (name, residual)
    checks[name] = str(residual)

# The free N=4 single-letter partition function, x=exp(-beta/R).
q = s.symbols('q', positive=True)
z = (6*q**2+12*q**4-2*q**6+16*q**3)/(1-q**2)**3
qH = 2-s.sqrt(3)
eq('single_letter_at_Hagedorn', z.subs(q,qH)-1)
eq('x_dz_dx_at_Hagedorn', (q*s.diff(z,q)/2).subs(q,qH)-s.Rational(3,2))
weak = s.Rational(3,2)*s.Rational(1,4)/(2*s.pi**2)
planar = 3*s.pi**2/8*(3/(2*s.pi))**4
eq('planar_to_weak', planar/weak-s.Rational(81,8))
x,R,N = s.symbols('x R N', positive=True)
T = (2*x*x+1)/(2*s.pi*R*x)
F = N*N*x*x*(1-x*x)/(4*R)
S = -s.diff(F,x)/s.diff(T,x)
E = s.factor(F+T*S)
eq('sphere_entropy', S-s.pi*N*N*x**3)
eq('sphere_energy', E-3*N*N*x*x*(1+x*x)/(4*R))
eq('sphere_coexistence', F.subs(x,1))
strong = s.simplify((E/(2*s.pi**2*R**3)).subs(x,1)*R**4/N**2)
eq('sphere_to_weak', strong/weak-4)
eq('planar_to_sphere', planar/strong-s.Rational(81,32))
t = s.symbols('t', positive=True)
f = s.Function('f')
FF=f(t*R)/R
EE=FF-t*s.diff(FF,t)
pp=-s.diff(FF,R)/(6*s.pi**2*R**2)
eq('conformal_pressure',3*pp*2*s.pi**2*R**3-EE)
chi=s.symbols('chi', positive=True)
entropy=-s.diff(f(chi),chi)
C=-chi*s.diff(f(chi),chi,2)
eq('adiabatic_chi',s.diff(entropy,chi)-C/chi)
a,A,cV,B,R0,H0=s.symbols('a A cV B R0 H0',positive=True)
integrand=A*(R0*a)**-4*s.exp(-B)*cV*(R0*a)**3/(a*(H0*a**-2))
eq('RD_hazard_integrand',integrand-A*cV*s.exp(-B)/(R0*H0))
delta=s.symbols('delta',positive=True)
D=(1+delta)**s.Rational(3,4)
eq('Neff_photon_identity',D**s.Rational(-4,3)-(1+delta)**-1)
eq('DH_entropy_exponent',D**s.Rational(-8,5)-(1+delta)**s.Rational(-6,5))
needed=s.Rational(99,100)**s.Rational(-5,6)-1
eq('one_percent_DH',((1+needed)**s.Rational(-6,5))-s.Rational(99,100))
result={
 'status':'CONDITIONAL_ALGEBRA_PASS','scientific_acceptance':False,
 'BBN_executed':False,'BH1_executed':False,'VM_seconds':0,
 'planned_wall_limit_seconds':60,'python':platform.python_version(),'sympy':s.__version__,
 'identities':checks,
 'coefficients':{k:float(v) for k,v in {'weak':weak,'planar_extrapolation':planar,'strong_sphere':strong}.items()},
 'photon_energy_for_one_percent_eta_component_DH_decrease':float(needed),
 'FIRAS_energy_limits_Jbb_1':{'mu':9e-5/1.401,'y':4*1.5e-5},
 'energy_scale_ratios':{'mu':float(needed)/(9e-5/1.401),'y':float(needed)/(4*1.5e-5)},
 'wall_seconds':time.perf_counter()-started,
 'scope':'Algebra under stated premises; no physical embedding, transition rate or spectral transfer solved.'}
assert result['wall_seconds']<60
Path(__file__).with_name('CHECKS.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
