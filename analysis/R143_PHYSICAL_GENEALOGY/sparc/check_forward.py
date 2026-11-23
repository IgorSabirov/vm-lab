"""Rebuild every forward curve with the observed velocity and its error omitted."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy.integrate import cumulative_trapezoid

parser=argparse.ArgumentParser()
for a in ['out','donor']:
    parser.add_argument('--'+a,type=Path,required=True)
args=parser.parse_args()
sys.path.insert(0,str(args.donor.resolve()))
import ccc_core as cc
import compare_models as cm
from smooth_ccc import _NU

p=args.out
raw=pd.read_csv(p/'radial_join.csv.gz',usecols=['Galaxy','R','Vgas','Vdisk','Vbul','in_CCC'])
curve=pd.read_csv(p/'predictions.csv.gz',usecols=['Galaxy','R','mode','CCC','MOND'])
f=json.loads((p/'freeze.json').read_text())['params']
worst=0.
n=0
for gal,d in raw[raw.in_CCC].groupby('Galaxy'):
    r=d.R.to_numpy()
    vb=cc.sparc_vbar(d.Vgas.to_numpy(),d.Vdisk.to_numpy(),d.Vbul.to_numpy())
    rg,rho,_=cm.rho_from_v(r,vb,s=0.5*len(r))
    sharp=cm.ccc_forward(rg,rho,r,f['forward_sharp'])[0]
    # Evaluate the smooth density law using upstream nu, independently of experiment.py.
    positive=rho>0
    total=np.zeros_like(rho)
    total[positive]=rho[positive]*_NU['standard'](rho[positive]/f['forward_standard'])
    mass=cumulative_trapezoid(4*np.pi*rg**2*total,rg,initial=0)
    smooth=np.sqrt(cc.G*np.interp(r,rg,mass)/r)
    for mode,c,a0 in [('forward_sharp',sharp,f['forward_mond']),
                      ('forward_standard',smooth,f['forward_mond']),
                      ('forward_sharp_R142',sharp,f['r142_a0'])]:
        saved=curve[(curve.Galaxy==gal)&(curve['mode']==mode)].sort_values('R')
        m=cm.mond_v(vb,r,a0)
        np.testing.assert_array_equal(r,saved.R)
        for got,want in [(c,saved.CCC),(m,saved.MOND)]:
            np.testing.assert_allclose(got,want,rtol=1e-10,atol=1e-9)
            worst=max(worst,float(np.max(np.abs(got-want))))
        n+=len(saved)
print(f'{n} paired forward rows verified without Vobs or e_Vobs; max |difference| {worst:.3g} km/s')
