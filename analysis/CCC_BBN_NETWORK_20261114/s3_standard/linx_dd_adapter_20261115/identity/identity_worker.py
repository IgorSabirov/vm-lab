"""Prepared full BBN worker; --execute AND a fresh controller receipt required.

No LINX/JAX import or numerical computation occurs for --help. Each arm must
run in a separate process/root under the existing bounded executor.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
PARENT=HERE.parent
digest=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()

def admission_check(a,c):
    if not a.execute:raise ValueError('Prepared only; --execute is required')
    if a.admission is None:raise ValueError('Fresh budget/runtime admission is required')
    r=json.loads(a.admission.read_text());now=datetime.now(timezone.utc)
    if now < datetime.fromisoformat(c['not_before_utc'].replace('Z','+00:00')):raise ValueError('BUDGET_WAIT')
    if not re.fullmatch('[0-9a-f]{40}',a.source_sha):raise ValueError('Full source SHA required')
    if r.get('admitted') is not True or r.get('source_sha')!=a.source_sha:raise ValueError('Admission/source mismatch')
    if r.get('contract_sha256')!=digest(HERE/'BBN_IDENTITY_CONTRACT.json'):raise ValueError('Contract not frozen in admission')
    if r.get('ledger_and_actions_checked') is not True or not 0<=r.get('packages_last_24h',999)<2:
        raise ValueError('Combined budget count must be checked before reservation of this package')
    if not 0 <= (now-datetime.fromisoformat(r['observed_utc'].replace('Z','+00:00'))).total_seconds() <= 7200:
        raise ValueError('Stale admission')
    forecast=r.get('forecast_package_seconds');route=r.get('route')
    if not r.get('calibration_evidence') or not isinstance(forecast,(int,float)) or not 0<forecast<=5400:
        raise ValueError('Actual calibration and full-package forecast required')
    if route != ('local' if forecast<=600 else 'github_actions'):raise ValueError('Wrong runtime route')
    if r.get('bounded_executor') is not True:raise ValueError('Use the bounded executor; worker has no supervisor')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=HERE,text=True).strip()
    if head != a.source_sha:raise ValueError('Checkout HEAD differs from source SHA')
    subprocess.run(['git','diff','--exit-code',a.source_sha,'--',str(PARENT)],cwd=HERE,check=True,stdout=subprocess.DEVNULL)
    return r

def verify_root(root,role):
    manifest=json.loads((PARENT/'UPSTREAM.json').read_text())
    patch=json.loads((PARENT/'PATCH_RECEIPT.json').read_text())
    for e in manifest['files']:
        expected=e['sha256']
        if role=='identical_override' and e['path']=='linx/abundances.py':expected=patch['patched_sha256']
        if digest(root/e['path'])!=expected:raise ValueError('Upstream pin mismatch: '+e['path'])
    return 'PRISTINE' if role=='native_pristine' else 'ONLY_RECORDED_ABUNDANCES_PATCH'

def main():
    p=argparse.ArgumentParser()
    p.add_argument('role',choices=['native_pristine','identical_override'])
    p.add_argument('--upstream',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--native-dir',type=Path);p.add_argument('--admission',type=Path)
    p.add_argument('--source-sha',required=True);p.add_argument('--execute',action='store_true')
    a=p.parse_args();c=json.loads((HERE/'BBN_IDENTITY_CONTRACT.json').read_text())
    admission=admission_check(a,c);integrity=verify_root(a.upstream,a.role)
    a.out.mkdir(parents=True,exist_ok=False)
    (a.out/'ADMISSION.json').write_text(json.dumps(admission,indent=2)+'\n')
    start=time.perf_counter();cpu=time.process_time()
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    os.environ.update(JAX_ENABLE_X64='true',JAX_PLATFORMS='cpu',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
    sys.path.insert(0,str(a.upstream.resolve()));sys.path.insert(0,str(PARENT))
    import jax
    jax.config.update('jax_enable_x64',True)
    import jax.numpy as jnp
    import numpy as np
    from diffrax import Kvaerno3,Tsit5
    from linx.nuclear import NuclearRates
    from linx.abundances import AbundanceModel
    from linx import const
    versions={n:importlib.metadata.version(n) for n in ('jax','jaxlib','equinox','diffrax','interpax','numpy','scipy')}
    locked={line.split('==')[0]:line.split('==')[1] for line in (PARENT/'requirements.lock').read_text().splitlines() if '==' in line}
    if any(v!=locked[n] for n,v in versions.items()):raise ValueError('Dependency versions differ from pin')
    if not math.isclose(const.T_start/const.kB,c['bbn']['T_start_K'],rel_tol=2e-15) or not math.isclose(const.T_end/const.kB,c['bbn']['T_end_K'],rel_tol=2e-15):
        raise ValueError('Temperature defaults changed')
    net=NuclearRates(nuclear_net=c['network'],interp_type=c['interpolation'])
    if set(net.reactions_names)!=set(c['q_by_reaction']):raise ValueError('Reaction list mismatch')
    q=jnp.asarray([c['q_by_reaction'][n] for n in net.reactions_names],dtype=jnp.float64)
    model=AbundanceModel(net)
    if a.role=='native_pristine':
        from linx.background import BackgroundModel
        b=c['background'];opts={k:b[k] for k in ('n_out','max_steps','decoupled','use_FD','collision_me','LO','NLO')}
        bg=BackgroundModel(**opts)(jnp.asarray(b['Delta_Neff_init']),solver=Tsit5(),rtol=b['rtol'],atol=b['atol'])
        jax.block_until_ready(bg)
        background=a.out/'background.npz'
        np.savez(background,**{k:np.asarray(v) for k,v in zip(('t','a','rho_g','rho_nu','rho_extra','p_extra','Neff'),bg)})
    else:
        if a.native_dir is None:raise ValueError('Reuse the native arm directory')
        n=json.loads((a.native_dir/'RESULT.json').read_text())
        if n['source_sha']!=a.source_sha or n['contract_sha256']!=digest(HERE/'BBN_IDENTITY_CONTRACT.json'):
            raise ValueError('Native arm provenance differs')
        background=a.native_dir/'background.npz'
        if digest(background)!=n['background_sha256']:raise ValueError('Shared background changed')
    with np.load(background,allow_pickle=False) as z: bg={k:jnp.asarray(z[k]) for k in z.files}
    tables=tuple(net.precompute_rate_tables(q))
    table_hashes=[hashlib.sha256(np.asarray(x,dtype='<f8').tobytes()).hexdigest() for x in tables]
    b=c['bbn'];kw={k:b[k] for k in ('sampling_nTOp','rtol','atol','max_steps','save_history')}
    kw.update(a_vec=bg['a'],t_vec=bg['t'],solver=Kvaerno3(),eta_fac=jnp.asarray(b['eta_fac']),
              tau_n_fac=jnp.asarray(b['tau_n_fac']),xi_nu=jnp.asarray(b['xi_nu']),nuclear_rates_q=q)
    args=(bg['rho_g'],bg['rho_nu'],bg['rho_extra'],bg['p_extra'])
    all_tables_native=None
    if a.role=='native_pristine':
        sol=model(*args,**kw)
    else:
        from dd_adapter import DDTable,CHANNELS,UNITS,prepare_dd_tables,solve_with_dd
        replacements={r.name:DDTable(np.asarray(r.T9_vec,dtype=np.float64),np.asarray(tables[i]),'linear',UNITS)
                      for i,r in enumerate(net.reactions) if r.name in CHANNELS}
        prepared=prepare_dd_tables(net,replacements,q,temperature_bounds_K=(b['T_end_K'],b['T_start_K']),boundary_policy=c['boundary_policy'])
        all_tables_native=all(np.asarray(x).tobytes()==np.asarray(y).tobytes() for x,y in zip(tables,prepared.tables))
        if not all_tables_native:raise ValueError('Identity payload changed native tables')
        sol=solve_with_dd(model,*args,replacements=replacements,boundary_policy=c['boundary_policy'],**kw)
    jax.block_until_ready(sol)
    yf=np.asarray(sol.evaluate(sol.t1),dtype=np.float64);yi=np.asarray(sol.evaluate(sol.t0),dtype=np.float64)
    if yf.shape!=(len(c['species']),) or not np.all(np.isfinite(yf)):raise ValueError('Invalid final state')
    import resource
    result={'role':a.role,'source_sha':a.source_sha,'contract_sha256':digest(HERE/'BBN_IDENTITY_CONTRACT.json'),
            'background_sha256':digest(background),'versions':versions,'reaction_order':net.reactions_names,
            'effective_q':np.asarray(q).tolist(),'table_sha256':table_hashes,'upstream_integrity':integrity,
            'all_tables_bitwise_native':all_tables_native,'integration_interval':[float(sol.t0),float(sol.t1)],
            'Y_initial':yi.tolist(),'Y_final':yf.tolist(),'solver_stats':{k:int(v) for k,v in sol.stats.items()},
            'Yp_diagnostic':float(4*yf[5]),'D_H_diagnostic':float(yf[2]/yf[1]),
            'wall_seconds':time.perf_counter()-start,'cpu_seconds':time.process_time()-cpu,
            'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'scientific_acceptance':False}
    (a.out/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':main()
