"""Probe the pristine native LINX path. No adapter import, patch, or ODE."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import resource
import sys
import time

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--upstream',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a = p.parse_args()
    a.out.mkdir(exist_ok=False,parents=True)
    plan=json.loads((HERE/'PROBE_PLAN.json').read_text())
    manifest=json.loads((PARENT/'UPSTREAM.json').read_text())
    # The probe does not need background/weak transport tables; verify every
    # materialized file including abundances.py if it is present. No patch allowed.
    checked={}
    for e in manifest['files']:
        f=a.upstream/e['path']
        if f.exists():
            digest=hashlib.sha256(f.read_bytes()).hexdigest()
            if digest != e['sha256']: raise ValueError('Not pristine: '+e['path'])
            checked[e['path']]=digest
    for required in ('linx/reactions.py','linx/nuclear.py',
                     'linx/data/nuclear_rates/key_PRIMAT_2023/ddHe3n.txt',
                     'linx/data/nuclear_rates/key_PRIMAT_2023/ddtp.txt'):
        if required not in checked: raise ValueError('Missing native source: '+required)
    admission={'plan':plan,'upstream_sha256':checked,
               'probe_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
               'python':sys.version,'cpu_affinity':sorted(os.sched_getaffinity(0)),
               'versions':{n:importlib.metadata.version(n) for n in ('jax','jaxlib','equinox','numpy','interpax')}}
    (a.out/'ADMISSION.json').write_text(json.dumps(admission,indent=2)+'\n')
    t=time.perf_counter();cpu=time.process_time()
    sys.path.insert(0,str(a.upstream.resolve()))
    import jax
    jax.config.update('jax_enable_x64',True)
    import jax.numpy as jnp
    import numpy as np
    from linx.nuclear import NuclearRates
    rows=[]
    temperatures=jnp.asarray(plan['T9'],dtype=jnp.float64)*1e9
    for mode in plan['interpolation']:
        net=NuclearRates(nuclear_net=plan['network'],interp_type=mode)
        tables=net.precompute_rate_tables(jnp.zeros(len(net.reactions),dtype=jnp.float64))
        for name in plan['channels']:
            i=net.reactions_names.index(name); r=net.reactions[i]
            native=r.frwrd_rate_from_table(temperatures,tables[i])
            legacy=r.frwrd_rate_param(temperatures,jnp.asarray(0.))
            native.block_until_ready(); legacy.block_until_ready()
            rows.append({'mode':mode,'channel':name,'grid_bounds_T9':[float(r.T9_vec[0]),float(r.T9_vec[-1])],
                         'T9_actual':np.asarray(temperatures*1e-9).tolist(),
                         'native_rates':np.asarray(native).tolist(),
                         'legacy_rates':np.asarray(legacy).tolist(),
                         'paths_exactly_equal':bool(np.array_equal(native,legacy))})
    wall=time.perf_counter()-t
    result={'id':plan['id'],'status':'COMPLETE','rows':rows,'wall_seconds':wall,
            'cpu_seconds':time.process_time()-cpu,
            'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'runtime_status':'WITHIN_ESTIMATE' if 2<=wall<=30 else 'REVIEW_REQUIRED',
            'bbn_integrations':0,'scientific_acceptance':False}
    (a.out/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__': main()
