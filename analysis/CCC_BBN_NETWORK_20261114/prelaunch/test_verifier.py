"""Failure-oriented checks for the scientific comparison gate; no BBN runs."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from run import dump

root=Path(__file__).resolve().parent
checks=[]
for mutation in ('missing_LT','nonfinite_abundance','wrong_baseline_digest'):
    with tempfile.TemporaryDirectory() as tmp:
        tmp=Path(tmp); other=tmp/'other'; other.mkdir()
        for name in ('TRACE.json','RESULT.json'):
            shutil.copy2(root/'results/S1_exponential_repaired'/name,other/name)
        env=json.loads((root/'results/S1_ENVELOPE.json').read_text())
        trace=json.loads((other/'TRACE.json').read_text())
        if mutation=='missing_LT': trace['eras'].pop()
        elif mutation=='nonfinite_abundance': trace['eras'][0]['Y'][5][0]=float('nan')
        else: env['baseline']['TRACE.json']['sha256']='0'*64
        (other/'TRACE.json').write_text(json.dumps(trace))
        envelope=tmp/'envelope.json';envelope.write_text(json.dumps(env))
        result=subprocess.run([sys.executable,str(root/'compare.py'),'compare','--baseline',str(root/'results/P1_cold'),'--other',str(other),'--envelope',str(envelope),'--out',str(tmp/'result.json')],capture_output=True,text=True)
        checks.append({'case':mutation,'rejected':result.returncode!=0,'no_pass_file':not (tmp/'result.json').exists()})
assert all(x['rejected'] and x['no_pass_file'] for x in checks)
dump(root/'results/VERIFIER_TESTS.json',{'status':'PASS','checks':checks,'BBN_runs':0})
print(json.dumps({'status':'PASS','cases':len(checks)}))
