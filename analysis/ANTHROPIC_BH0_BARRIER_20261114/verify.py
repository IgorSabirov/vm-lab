"""Check the frozen evidence; optional bounded replay in a fresh directory."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--recompute',action='store_true');args=ap.parse_args()
    root=HERE/'results';manifest=read(root/'ARTIFACTS.json')
    if sha(root/'ARTIFACTS.json')!=read(root/'ARTIFACTS_SHA256.json')['sha256']:raise ValueError('Manifest changed')
    for rel,entry in manifest['files'].items():
        p=(root/rel).resolve()
        if not p.is_relative_to(root) or sha(p)!=entry['sha256']:raise ValueError('Artifact changed: '+rel)
    summary=read(root/'SUMMARY.json')
    for rel,h in summary['source_sha256'].items():
        if sha(HERE/rel)!=h:raise ValueError('Frozen source changed: '+rel)
    checks=read(root/'CHECKS.json')
    if len(checks)!=38 or not all(c['passed'] for c in checks):raise ValueError('Checks fail')
    if summary['case_count']!=9 or summary['numerical_status']!='REDUCED_BARRIER_DIAGNOSTIC_PASS':raise ValueError('Wrong outcome')
    if args.recompute:
        with tempfile.TemporaryDirectory() as td:
            fresh=Path(td)/'replay'
            subprocess.run([sys.executable,str(HERE/'run.py'),'--output',str(fresh)],check=True,timeout=95)
            if read(fresh/'ATLAS.json')!=read(root/'ATLAS.json'):raise ValueError('Atlas replay differs')
            if read(fresh/'CHECKS.json')!=checks:raise ValueError('Check replay differs')
    print('BH0 evidence verified; 9 cases / 38 checks. Scientific acceptance remains separate.')

if __name__=='__main__':main()
