"""Frozen galaxy calibration on the five X-COP clusters of Kelleher & Lelli (2024)."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from astropy.io import fits
p=argparse.ArgumentParser()
p.add_argument('donor',type=Path)
p.add_argument('fitsdir',type=Path)
args=p.parse_args()
sys.path.insert(0,str(args.donor.resolve()))
import ccc_core as cc
import compare_models as cm

out=Path(__file__).resolve().parent
f=json.loads((out.parent/'freeze.json').read_text())['params']
rows=[];records=[];sources={}
for g in ['A644','A1795','A2029','A2142','A2319']:
    files={k:args.fitsdir/f'{g}_{k}.fits' for k in ['fgas_profile','hydro_mass','mstar']}
    sources[g]={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files.values()}
    gas=fits.getdata(files['fgas_profile'],1)
    h=fits.getdata(files['hydro_mass'],1)
    sr,ss=(fits.getdata(files['mstar'],n) for n in (1,2))
    # These two HDUs tabulate the identical stellar grid in R/R500 and kpc.
    ratio=ss['RADIUS'].astype(float)/sr['RADIUS']
    r500=float(np.median(ratio))
    np.testing.assert_allclose(ratio,r500,rtol=1e-5)
    rr=r500*gas['RADIUS'].astype(float)
    lo=max(h['RADIUS'].min(),ss['RADIUS'].min());hi=min(h['RADIUS'].max(),ss['RADIUS'].max())
    ok=(rr>=lo)&(rr<=hi)
    r=rr[ok]
    mg=gas['MGAS'].astype(float)[ok]
    ms=np.interp(r,ss['RADIUS'],ss['MSTAR']);mb=mg+ms
    m_obs=np.interp(r,h['RADIUS'],h['M_FORW'])
    m_err=np.interp(r,h['RADIUS'],h['EM_FORW'])
    assert np.all(np.diff(mb)>0) and np.all(m_obs>0)
    vb=np.sqrt(cc.G*mb/r)
    rg,rho,_=cm.rho_from_v(r,vb,s=0.5*len(r))
    vc=cm.ccc_forward(rg,rho,r,f['forward_sharp'])[0]
    vm=cm.mond_v(vb,r,f['forward_mond'])
    mc=r*vc**2/cc.G;mm=r*vm**2/cc.G
    # Geometry sensitivity: constant-density shells, central enclosed mass anchored to zero.
    vol=(4*np.pi/3)*np.diff(np.r_[0,r**3])
    rhob=np.diff(np.r_[0,mb])/vol
    m_shell=np.cumsum(np.maximum(rhob,np.sqrt(f['forward_sharp']*rhob))*vol)
    for i,ri in enumerate(r):
        rows.append((g,ri,r500,ri/r500,mg[i],ms[i],m_obs[i],m_err[i],mc[i],mm[i],m_shell[i]))
    zone=(r>=.1*r500)&(r<=r500)
    item=dict(cluster=g,n=len(r),n_01_1=int(zone.sum()),R500=r500,negative_density=int((rho<0).sum()))
    for name,model in [('CCC',mc),('MOND',mm),('CCC_shell',m_shell)]:
        y=model/m_obs
        item[name+'_abslog']=np.mean(abs(np.log10(y[zone])))
        for x in (.3,.5,1.):
            if not r[0]<x*r500<r[-1]:
                item[name+'_ratio_'+str(x)]=np.nan
                continue
            item[name+'_ratio_'+str(x)]=np.interp(x*r500,r,y)
    records.append(item)
pd.DataFrame(rows,columns=['cluster','r_kpc','R500_kpc','r_R500','Mgas','Mstar','Mhydro','e_Mhydro','M_CCC','M_MOND','M_CCC_shell']).to_csv(out/'cluster_radial.csv',index=False)
pd.DataFrame(records).to_csv(out/'cluster_scores.csv',index=False)
(out/'cluster_inputs.json').write_text(json.dumps(sources,indent=2)+'\n')
print(pd.DataFrame(records)[['cluster','CCC_ratio_0.5','MOND_ratio_0.5','CCC_shell_ratio_0.5','CCC_abslog','MOND_abslog']].to_string(index=False))
