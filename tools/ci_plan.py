#!/usr/bin/env python3
"""Select explicit active suites; never discover archived scientific runs."""
import argparse,json,subprocess
SUITES=('integrity','infra','e002','now','x27_043','x27_051')
def select(paths):
    picked={'integrity'}
    for p in paths:
        if p.startswith(('.github/','tools/')) or p in {'requirements-ci.txt','pyproject.toml'}:picked.update(SUITES)
        if p.startswith('infra/') and p.endswith('.py') or p=='reporting.py':picked.add('infra')
        if p.startswith(('e002','tests/test_e002','experiments/e002','analysis/E002','results/E002e_BASELINE')) or p in {'run.py','config.json','reporting.py'}:picked.add('e002')
        if p.startswith('experiments/now_integrated_v1/'):picked.add('now')
        if p.startswith('experiments/X27_PACKAGES_20261110/v043/'):picked.add('x27_043')
        if p.startswith('experiments/X27_PACKAGES_20261110/v051/'):picked.add('x27_051')
    return [s for s in SUITES if s in picked]
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--base');ap.add_argument('--head',default='HEAD');ap.add_argument('--all',action='store_true');ap.add_argument('--output');a=ap.parse_args()
    paths=[] if a.all else subprocess.check_output(['git','diff','--name-only','-z',a.base,a.head]).decode().split('\0')
    selected=list(SUITES) if a.all else select(paths)
    matrix={'include':[{'suite':s,'numerical':s in {'e002','now'}} for s in selected]}
    value=json.dumps(matrix,separators=(',',':'));print(value)
    if a.output:
        with open(a.output,'a') as f:f.write('matrix='+value+'\n')
if __name__=='__main__':main()
