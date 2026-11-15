"""One bounded local engineering suite. Does not integrate BBN or sample a GP."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import resource
import sys
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'upstream'))
os.environ.setdefault('JAX_ENABLE_X64','true')
os.environ.setdefault('JAX_PLATFORMS','cpu')
os.environ.setdefault('OMP_NUM_THREADS','1')
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
if hasattr(os,'sched_setaffinity'):
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
out=HERE/'results';out.mkdir(exist_ok=True)
pre=json.loads((HERE/'ENGINEERING_PLAN.json').read_text())
source_digest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.iterdir()
               if p.is_file() and p.suffix in ('.py','.json','.txt','.patch','.lock')}
receipt={'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
         'kind':'ENGINEERING_UNIT_AND_RHS_ONLY','source_sha256':source_digest,'plan':pre,
         'python':sys.version,'platform':platform.platform(),
         'cpu_affinity':sorted(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else None,
         'versions':{n:importlib.metadata.version(n) for n in ('jax','jaxlib','equinox','diffrax','interpax','numpy','scipy','pytest')},
         'bbn_integrations':0,'gp_draws':0,'scientific_acceptance':False}
(out/'ADMISSION.json').write_text(json.dumps(receipt,indent=2)+'\n')
t=time.perf_counter();cpu=time.process_time()
import pytest
code=pytest.main([str(HERE/'test_adapter.py'),'-q','--junitxml='+str(out/'junit.xml')])
import test_adapter
receipt.update({'exit_code':int(code),'engineering_status':'PASS' if code==0 else 'FAIL',
                'wall_seconds':time.perf_counter()-t,'cpu_seconds':time.process_time()-cpu,
                'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                'rhs_metrics':test_adapter.METRICS,
                'full_bbn_identity':'NOT_EXECUTED_BUDGET_WAIT',
                'scope':'Reaction tables, detailed balance, host validation, real LINX RHS and JAX trace reuse only'})
lo,hi=pre['forecast_seconds']['range']
receipt['runtime_status']='WITHIN_ESTIMATE' if lo <= receipt['wall_seconds'] <= hi else 'REVIEW_REQUIRED'
(out/'RESULT.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({k:receipt[k] for k in ('engineering_status','wall_seconds','cpu_seconds','max_rss_kib','rhs_metrics','full_bbn_identity','runtime_status')},indent=2))
sys.exit(code)
