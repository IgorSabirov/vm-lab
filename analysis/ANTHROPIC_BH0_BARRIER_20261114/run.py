"""Independent scalar saddle/barrier computation for Anthropic eq. (21).

No upstream code, loop engine, finite-N measure or kinetic law is imported.
"""
import argparse
from decimal import Decimal as D, localcontext
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import signal
import subprocess
import time
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write(p, x):
    p.write_text(json.dumps(x, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


def wall(u):
    return D(0) if u <= D('.5') else D('.25') - (2*(1-u)).ln()/2-u*u


def phi(u, a, q):
    return wall(u)+a*u*u-q*u**4


def a_stationary(u, q):
    return 1-1/(4*u*(1-u))+2*q*u*u


def bisect(fn, lo, hi, digits):
    fl, fh = fn(lo), fn(hi)
    if fl*fh >= 0:
        raise ValueError('No bracket')
    for _ in range(4*digits):
        mid = (lo+hi)/2
        fm = fn(mid)
        if fm == 0 or mid == lo or mid == hi:
            return mid
        if fl*fm < 0:
            hi = mid
        else:
            lo, fl = mid, fm
    return (lo+hi)/2


def solve(q_text, digits):
    with localcontext() as ctx:
        ctx.prec = digits
        q = D(q_text)
        ub = bisect(lambda u: 2*u-1-16*q*u**3*(1-u)**2, D('.5'), D('.99'), digits)
        uc = bisect(lambda u: phi(u,a_stationary(u,q),q), ub, D('.99'), digits)
        ac = a_stationary(uc,q)
        us = (ac/(2*q)).sqrt()
        barrier = ac*ac/(4*q)
        out = {'q':q,'u_birth':ub,'a_birth':a_stationary(ub,q),
               'u_coexist':uc,'a_coexist':ac,'u_barrier':us,'delta_phi':barrier,
               'coexistence_residual_over_q':abs(phi(uc,ac,q))/q,
               'barrier_identity_residual_over_q':abs(phi(us,ac,q)-barrier)/q,
               'curvature_deconfined':1/(2*(1-uc)**2)-2+2*ac-12*q*uc*uc,
               'curvature_barrier':2*ac-12*q*us*us,
               'barrier_over_leading':barrier/(q/64),
               'a_coexist_over_leading':ac/(q/4),
               'u_shift_over_leading':(uc-D('.5'))/(q.sqrt()/4),
               'N_at_action_height_1':1/barrier.sqrt(),
               'N_at_action_height_10':(10/barrier).sqrt(),
               'relative_temperature_gap_linear_map':ac/(D('1.5')*D('2.6339158'))}
        return {k:str(v) for k,v in out.items()}


def independent(row):
    import mpmath as mp
    with mp.workdps(70):
        q = mp.mpf(row['q'])
        def potential(u,a):
            return mp.mpf('0.25')-mp.log(2*(1-u))/2-u*u+a*u*u-q*u**4
        def derivative(u,a):
            return 1/(2*(1-u))-2*u+2*a*u-4*q*u**3
        # Analytic leading estimate, not a root imported from the Decimal solve.
        u,a = mp.findroot((potential,derivative),
                         (mp.mpf('.5')+mp.sqrt(q)/4,q/4),tol=mp.mpf('1e-60'),maxsteps=100)
        error = max(abs(u/mp.mpf(row['u_coexist'])-1),abs(a/mp.mpf(row['a_coexist'])-1))
        return str(error)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=HERE/'results');args=ap.parse_args()
    plan=json.loads((HERE/'PLAN.json').read_text())
    signal.signal(signal.SIGALRM,lambda *args: (_ for _ in ()).throw(TimeoutError('BH0 wall cap')))
    signal.alarm(plan['budget']['hard_wall_seconds'])
    resource.setrlimit(resource.RLIMIT_AS,(plan['budget']['memory_mib']*1024**2,)*2)
    out=args.output;out.mkdir(parents=True,exist_ok=False)
    started=time.perf_counter()
    write(out/'ADMISSION.json',{'utc':datetime.now(timezone.utc).isoformat(),
        'plan_sha256':sha(HERE/'PLAN.json'),'budget':plan['budget'],
        'source_commit':subprocess.check_output(['git','-C',str(REPO),'rev-parse','HEAD'],text=True).strip(),
        'source_sha256':{p.name:sha(p) for p in [HERE/'PLAN.json',HERE/'run.py']},
        'python':platform.python_version(),'platform':platform.platform(),
        'cpu':platform.processor() or None,'affinity':sorted(os.sched_getaffinity(0)),
        'load_average':os.getloadavg(),'algorithm':'single-thread scalar decimal arithmetic; no BLAS',
        'cpu_quota':Path('/sys/fs/cgroup/cpu.max').read_text().strip() if Path('/sys/fs/cgroup/cpu.max').exists() else None,
        'memory_cgroup':Path('/sys/fs/cgroup/memory.max').read_text().strip() if Path('/sys/fs/cgroup/memory.max').exists() else None})
    cases=[('lambda_'+l,str(-D(plan['imported_b_over_lambda_squared'])*D(l)**2),l) for l in plan['lambda_grid']]
    cases += [('q_'+q,q,None) for q in plan['additional_q']]
    rows=[];checks=[]
    def check(name,passed,detail=None):
        checks.append({'id':name,'passed':bool(passed),'detail':detail})
    for label,q,lam in cases:
        low=solve(q,plan['decimal_precisions'][0]);high=solve(q,plan['decimal_precisions'][1])
        with localcontext() as ctx:
            ctx.prec=95
            error=max(abs(D(low[k])/D(high[k])-1) for k in ('a_birth','a_coexist','u_coexist','delta_phi'))
        err2=independent(high)
        check(label+'_precision',error<D(plan['criteria']['precision_relative']),str(error))
        check(label+'_independent',D(err2)<D(plan['criteria']['independent_relative']),err2)
        check(label+'_residual',max(D(high[k]) for k in ('coexistence_residual_over_q','barrier_identity_residual_over_q'))<D(plan['criteria']['normalized_equation_residual']))
        check(label+'_saddles',D(high['a_birth'])>D(high['a_coexist'])>0 and D(high['u_barrier'])<D('.5')<D(high['u_coexist'])<1 and D(high['curvature_barrier'])<0<D(high['curvature_deconfined']))
        high.update(id=label,lambda_value=lam,precision_relative_error=str(error),independent_relative_error=err2)
        rows.append(high)
    last=rows[-1]
    check('asymptotic_limit',max(abs(D(last[k])-1) for k in ('barrier_over_leading','a_coexist_over_leading','u_shift_over_leading'))<D(plan['criteria']['leading_limit_relative_at_q_1e_16']))
    # For b>0 and a>=0 every contribution to phi is nonnegative.
    # d phi/du = 2au+4bu^3+wall'; wall'=2(u-.5)^2/(1-u)>=0 on gapped side.
    check('positive_b_control',all(2*a*u+4*b*u**3+(2*(u-D('.5'))**2/(1-u) if u>D('.5') else 0)>0
          for a in (D(0),D('.001')) for b in (D('.001'),D('.1')) for u in (D('.1'),D('.5'),D('.75'))))
    write(out/'ATLAS.json',{'rows':rows,'parameter_scope':'q=|b|; lambda grid uses imported leading coefficient; exact only within truncated potential'})
    write(out/'CHECKS.json',checks)
    coefficient=-D(plan['imported_b_over_lambda_squared'])
    summary={'status':'ENGINEERING_PASS' if all(c['passed'] for c in checks) else 'ENGINEERING_FAIL',
        'numerical_status':'REDUCED_BARRIER_DIAGNOSTIC_PASS' if all(c['passed'] for c in checks) else 'REVIEW_REQUIRED',
        'checks':len(checks),'failed_checks':[c['id'] for c in checks if not c['passed']],
        'case_count':len(rows),'leading_barrier_coefficient':str(coefficient/64),
        'leading_N_lambda_at_height_1':str(8/coefficient.sqrt()),
        'scientific_acceptance':False,'upstream_code_executed':False,'three_loop_replication':False,
        'finite_N_measure_computed':False,'kinetics_computed':False,
        'wall_seconds':time.perf_counter()-started,'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'budget':plan['budget'],'source_sha256':{'PLAN.json':sha(HERE/'PLAN.json'),'run.py':sha(HERE/'run.py')}}
    write(out/'SUMMARY.json',summary)
    signal.alarm(0)
    print(json.dumps(summary))
    return 0 if summary['status']=='ENGINEERING_PASS' else 1


if __name__=='__main__':raise SystemExit(main())
