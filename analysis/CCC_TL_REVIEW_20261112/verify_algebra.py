#!/usr/bin/env python3
"""Small symbolic audit, not cosmological fitting; expected <5 s, sandbox only."""
import json
from pathlib import Path
from time import perf_counter
import sympy as s
start=perf_counter()
t=s.symbols('t',real=True); alpha,K,k,c=s.symbols('alpha K k c',real=True)
a=s.Function('a')(t); e=s.Function('e')(t); p=s.Function('p')(t)
f=s.exp(alpha*t); A=a*f; E=e/f**2; P=p/f**2
prime=lambda x:s.diff(x,t)/f
H=s.diff(a,t)/a
HA=s.simplify(prime(A)/A)
old_acc=-K*(e+3*p)/2-alpha*H
old_edot=-3*H*(e+p)-alpha*(e+3*p)
res={
 'hubble':s.simplify(HA-(H+alpha)/f),
 'friedmann':s.simplify(HA**2-K*E+k*c**2/A**2-((H+alpha)**2-K*e+k*c**2/a**2)/f**2),
 'acceleration':s.simplify((prime(prime(A))/A+K*(E+3*P)/2).subs(s.diff(a,t,2),a*old_acc)),
 'continuity':s.simplify((prime(E)+3*HA*(E+P)).subs(s.diff(e,t),old_edot)),
}
assert all(x==0 for x in res.values()),res
# A common positive clock factor cancels in the whole vector field.
F,G,h=s.symbols('F G h',nonzero=True)
res['common_factor']=s.simplify((F/h)/(-G/h)+F/G)
assert res['common_factor']==0
# A small killed generator illustrates the general linear-system identity.
lam=s.symbols('lambda',positive=True); B=s.Matrix([[3,-1],[-2,4]]); one=s.ones(2,1)
assert (lam*B).inv()*one==B.inv()*one/lam
# Monotonicity along one worldline does not imply a temporal function.
clock_gradient_norm=-1+2**2;assert clock_gradient_norm>0
out={'status':'SYMBOLIC_IDENTITIES_VERIFIED_NOT_PHYSICAL_VALIDATION','residuals':{k:str(v) for k,v in res.items()},'mean_hitting_time_scale_identity':True,'clock_counterexample_gradient_norm_minus_plus_signature':clock_gradient_norm,'sympy_version':s.__version__,'elapsed_seconds':perf_counter()-start,'runtime_plan':{'expected_seconds_upper':5,'route':'sandbox','new_vm_jobs':0},'limitations':['constant alpha in background identity','common positive scaling of the entire vector field','common constant lambda for the CTMC ratio','no cosmological fit or production simulation']}
Path(__file__).with_name('ALGEBRA_CHECK.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out,ensure_ascii=False))
