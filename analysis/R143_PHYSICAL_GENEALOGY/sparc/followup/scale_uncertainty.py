"""Whole-galaxy uncertainty of the original R142 training estimator, keeping the catalog fixed."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
out=Path(__file__).resolve().parent
d=pd.read_csv(out.parent/'radial_join.csv.gz').query('split=="train"')
grid=np.linspace(-12,-8,801)
loss=[]
for _,z in d.groupby('Galaxy'):
    gas,st,bul,r,v=z[['Vgas','Vdisk','Vbul','R','Vobs']].to_numpy().T
    b=(gas*abs(gas)+.5*st*abs(st)+.7*bul*abs(bul))*1e6/(3.0856775814913673e19*r)
    obs=v**2*1e6/(3.0856775814913673e19*r)
    ok=(b>0)&(obs>0); b=b[ok,None]
    pred=b/(-np.expm1(-np.sqrt(b/(10**grid))))
    loss.append(np.mean(np.square(np.log10(pred)-np.log10(obs[ok,None])),axis=0))
loss=np.array(loss);n=len(loss)
assert n==140
def estimate(curves):
    idx=curves.argmin(axis=1)
    assert (idx>0).all() and (idx<len(grid)-1).all()
    left,mid,right=(curves[np.arange(len(idx)),idx+k] for k in (-1,0,1))
    return 10**(grid[idx]+.5*(grid[1]-grid[0])*(left-right)/(left-2*mid+right))
rng=np.random.default_rng(143)
samples=[]
for _ in range(20):
    counts=rng.multinomial(n,np.repeat(1/n,n),size=500)
    samples.extend(estimate(counts@loss))
samples=np.array(samples)
point=float(estimate(loss.mean(axis=0)[None,:])[0])
original=json.loads((out.parent/'freeze.json').read_text())['params']['r142_a0']
assert abs(point/original-1)<1e-4
q=lambda x:np.percentile(x,[2.5,50,97.5]).tolist()
result=dict(n=n,draws=len(samples),a0=original,bootstrap_a0=q(samples),conditional_Q={})
for h,sigma in [(67.4,.5),(73.04,1.04)]:
    hs=rng.normal(h,sigma,len(samples))
    result['conditional_Q'][str(h)]=q(samples/(299792458*hs/3.0856775814913673e19/(2*np.pi)))
(out/'scale_uncertainty.json').write_text(json.dumps(result,indent=2)+'\n')
