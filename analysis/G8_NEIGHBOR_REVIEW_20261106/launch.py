"""Measure the whole verification process, including imports and report writing."""
import json, subprocess, sys, time
from pathlib import Path
p=Path(__file__).resolve().parent
plan=json.loads((p/'RUNTIME_PLAN.json').read_text())
t=time.perf_counter()
with (p/'PROCESS_OUTPUT.log').open('w') as f:
    result=subprocess.run([sys.executable,str(p/'verify_run.py')],stdout=f,stderr=subprocess.STDOUT,timeout=plan['hard_timeout_seconds'])
elapsed=time.perf_counter()-t
record={'returncode':result.returncode,'actual_seconds':elapsed,
 'expected_seconds':plan['full_process_expected_seconds'],
 'lower_seconds':plan['full_process_lower_seconds'],'upper_seconds':plan['full_process_upper_seconds'],
 'scope':'child process including imports, calculation, checks, file output and shutdown',
 'status':'PASS' if result.returncode==0 and plan['full_process_lower_seconds']<=elapsed<=plan['full_process_upper_seconds'] else 'REVIEW_REQUIRED'}
(p/'PROCESS_RUNTIME.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
if result.returncode:print((p/'PROCESS_OUTPUT.log').read_text()[-4000:])
sys.exit(result.returncode)
