"""Reproducible local validation; never submits a VM job or accepts its calibration."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='1'
os.chdir(ROOT)
for folder,pattern,logname in [('tests','test_*.py','e002c_regression_tests.log'),('infra','test_e002c.py','e002c_unit_tests.log')]:
    with (ROOT/'infra'/logname).open('w') as log:
        subprocess.run([sys.executable,'-m','unittest','discover','-s',folder,'-p',pattern,'-v'],stdout=log,stderr=subprocess.STDOUT,check=True)
from e002c_exp.task import run,kernel_hash
cfg=json.loads((ROOT/'config.json').read_text());cfg['local_source_commit']='LOCAL_TEST';cfg['run_id']='LOCAL_E002c_CALIBRATION_TEST'
with tempfile.TemporaryDirectory() as tmp:
    start=time.monotonic();metrics,checks=run(cfg,tmp)
    result=dict(local_only=True,elapsed_whole_seconds=time.monotonic()-start,work=metrics['work'],
                checks=checks['summary'],runtime_gate=checks['runtime_gate'],kernel_sha256=kernel_hash(),
                environment=metrics['environment'],fast_tests=16,integration_tests=24)
    if checks['failures']:raise RuntimeError('Local calibration-path check failed')
spec=importlib.util.spec_from_file_location('budget',ROOT/'infra/check_e002c_export_budget.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
result['synthetic_maximum_export']=module.check()
(ROOT/'infra/e002c_local_validation.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
