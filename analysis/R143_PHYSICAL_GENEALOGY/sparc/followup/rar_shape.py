"""Diagnostic transfer of the two published nu_p shapes with fixed nominal M/L."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

out=Path(__file__).resolve().parent
rad=pd.read_csv(out.parent/'radial_join.csv.gz')
curves={}
for gal,d in rad.groupby('Galaxy'):
    gas,star,bul,v,r=d[['Vgas','Vdisk','Vbul','Vobs','R']].to_numpy().T
    bar=(gas*abs(gas)+.5*star*abs(star)+.7*bul*abs(bul))*1e6/(r*3.0856775814913673e19)
    obs=v**2*1e6/(r*3.0856775814913673e19)
    ok=(bar>0)&(obs>0)
    curves[gal]=(d.split.iloc[0],bar[ok],np.log10(obs[ok]))
def loss(x,exponent,log_a):
    _,bar,y=x
    pred=np.log10(bar)+np.logaddexp(0,exponent*(log_a*np.log(10)-np.log(bar)))/((1+exponent)*np.log(10))
    return np.mean((pred-y)**2)
training=[v for v in curves.values() if v[0]=='train']
rows={}
for exponent in [.75,1.]:
    opt=minimize_scalar(lambda a:np.mean([loss(x,exponent,a) for x in training]),bounds=(-12,-8),method='bounded')
    rows[str(exponent)]={'a0':10**opt.x,'train_mse':opt.fun,'by_galaxy':{g:loss(x,exponent,opt.x) for g,x in curves.items() if x[0]=='test'}}
diff=np.array(list(rows['0.75']['by_galaxy'].values()))-np.array(list(rows['1.0']['by_galaxy'].values()))
rows['paired']={'mean_dex2':diff.mean(),'ci':np.percentile(np.random.default_rng(143).choice(diff,(10000,len(diff))).mean(1),[2.5,97.5]).tolist(),
                'wins_p075':int((diff<0).sum()),'n':len(diff)}
(out/'rar_shape.json').write_text(json.dumps(rows,indent=2)+'\n')
