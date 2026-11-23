"""Historical per-galaxy replay in an isolated process after the frozen comparison."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

import numpy as np
import pandas as pd

parser=argparse.ArgumentParser()
for a in ('donor','data','out'):
    parser.add_argument('--'+a,type=Path,required=True)
args=parser.parse_args()
out=args.out.resolve()
freeze=json.loads((out/'freeze.json').read_text())
assert (out/'r142_test.csv').exists() and len(freeze['test'])==35
sys.path.insert(0,str(args.donor.resolve()))
os.environ['SPARC_DATA']=str(args.data.resolve())
source=(args.donor/'regen_all.py').read_text()
assert hashlib.sha256(source.encode()).hexdigest() == 'd4ff0e0e5f6d2acd851d1527e6feb65b28b63e293e89050e6bc7a0241c76477b'
# Attach observers to two local variables. The predictor, optimizer, all 6 original
# model fits and order of Monte Carlo draws are retained. Fail loudly on any skip.
def replace_once(old,new):
    global source
    assert source.count(old)==1
    source=source.replace(old,new)
replace_once('return dict(param=10 ** best, chi2r=',
             'return dict(saved_prediction=pred(R,V,eV,10**best), saved_sigma=sig.copy(), param=10 ** best, chi2r=')
replace_once('except Exception:\n        continue','except Exception:\n        raise')
replace_once('    T = int(t1.loc[g, "T"])','    record(g, R, Vb, r_std, r_mond)\n    T = int(t1.loc[g, "T"])')
records=[]
def record(g,r,vb,c,m):
    records.append(pd.DataFrame(dict(Galaxy=g, R=r, target=vb, CCC=c['saved_prediction'],
             MOND=m['saved_prediction'], sigma_CCC=c['saved_sigma'], sigma_MOND=m['saved_sigma'])))

with tempfile.TemporaryDirectory() as td:
    source=source.replace('/mnt/user-data/outputs/',str(Path(td))+'/')
    exec(compile(source, 'regen_all.py', 'exec'),{'record':record})
    ic=pd.read_csv(Path(td)/'ic_smooth_ccc.csv')
    par=pd.read_csv(Path(td)/'fit_parameters.csv')
    ic=ic[['Galaxy','N','T','CCC_standard_param','MOND_smooth_param','CCC_standard_chi2r','MOND_smooth_chi2r']]
    ic=ic.merge(par[['Galaxy','inner_slope','CCC_rhot']],on='Galaxy',validate='one_to_one')
    assert len(ic)==165
    ic.to_csv(out/'native_replay.csv',index=False,float_format='%.15g')
df=pd.concat(records,ignore_index=True)
for model in ['CCC','MOND']:
    df['resid_'+model]=df[model]-df.target
df['delta_chi2']=(df.resid_CCC/df.sigma_CCC)**2-(df.resid_MOND/df.sigma_MOND)**2
df.to_csv(out/'native_radial.csv.gz',index=False,float_format='%.15g',compression={'method':'gzip','mtime':0})
