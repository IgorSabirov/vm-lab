"""Apply the published LOCK; all new fitted quantities depend on training galaxies only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy import stats
from scipy.optimize import minimize

p=argparse.ArgumentParser()
p.add_argument('donor',type=Path)
p.add_argument('data',type=Path)
args=p.parse_args()
sys.path.insert(0,str(args.donor.resolve()))
os.environ['SPARC_DATA']=str(args.data.resolve())
import sparc_io as io
import compare_models as cm
import ccc_core as cc

out=Path(__file__).resolve().parent
prior=out.parent
freeze=json.loads((prior/'freeze.json').read_text())
assert hashlib.sha256(Path(io.T1).read_bytes()).hexdigest()==freeze['source']['table1']
t=io.load_table1().join(pd.read_csv(prior/'samples.csv').set_index('Galaxy')[['split','in_CCC','R_max']])
t['Mbar']=(0.5*t.L36+1.33*t.MHI)*1e9
t['Sigma']=t.Mbar/(2*np.pi*(1000*t.Reff)**2)
t=t.join(pd.read_csv(out/'environment.csv').set_index('Galaxy'))
t['e21']=0.5*(10**(t.log_eN_max/2)+10**(t.log_eN_no/2))
points=pd.read_csv(prior/'radial_join.csv.gz').query('in_CCC')
modes=pd.read_csv(prior/'galaxy_scores.csv')
raw={}
for g,d in points.groupby('Galaxy'):
    r=d.R.to_numpy()
    vb=cc.sparc_vbar(d.Vgas.to_numpy(),d.Vdisk.to_numpy(),d.Vbul.to_numpy())
    grid,rho,_=cm.rho_from_v(r,vb,s=.5*len(r))
    raw[g]=(r,grid,rho,vb,d.Vobs.to_numpy(),np.maximum(1,d.e_Vobs.to_numpy()),np.log10(t.at[g,'Sigma']/100))
def curve(x,b):
    r,rg,rho,vb,v,e,feature=x
    threshold=10**np.clip(b[0]+b[1]*feature,3,12)
    return cm.ccc_forward(rg,rho,r,threshold)[0],threshold
def loss(x,b):
    pred,_=curve(x,b)
    return np.mean(((pred-x[4])/x[5])**2)
train=[raw[g] for g in freeze['train_common']]
constant=np.log10(freeze['params']['forward_sharp'])
def objective(b):
    return np.mean([loss(x,b) for x in train])
candidates=[(objective((a,b)),a,b) for a in np.linspace(3,12,19) for b in np.linspace(-3,3,13)]
fits=[(objective((constant,0)),constant,0)]+candidates
for _,a,b in sorted(candidates)[:3]:
    opt=minimize(objective,[a,b],method='Powell',bounds=[(3,12),(-3,3)],options={'xtol':1e-6,'ftol':1e-8})
    fits.append((float(opt.fun),*opt.x))
train_loss,b0,b1=min(fits)
params=dict(b0=b0,b1=b1,train_loss=train_loss,n_train=len(train))
(out/'predictor_parameters.json').write_text(json.dumps(params,indent=2)+'\n')
def paired(diff):
    z=np.array(diff); n=len(z); ids=np.random.default_rng(143).integers(n,size=(10000,n))
    return dict(N=n,mean=z.mean(),median=np.median(z),ci=np.percentile(z[ids].mean(axis=1),[2.5,97.5]).tolist(),
                wins=int((z<0).sum()),ties=int((z==0).sum()))
pred=[]
for g,x in raw.items():
    r,rg,rho,vb,v,e,feature=x
    y,rt=curve(x,(b0,b1))
    record=dict(Galaxy=g,split=t.at[g,'split'],Sigma=t.at[g,'Sigma'],rho_t=rt,loss=np.mean(((y-v)/e)**2))
    baseline=modes[(modes.Galaxy==g)&(modes['mode']=='forward_sharp')].iloc[0]
    record.update(constant=baseline.mean_chi2_CCC,mond=baseline.mean_chi2_MOND)
    if pd.notna(t.at[g,'e20']):
        # Chae et al. 2020 Eq. 6, using their 1.2e-10 acceleration convention in both arms.
        z=vb**2/r*cm.KMS2_KPC_TO_MS2/1.2e-10
        for fld,key in [(0,'simple0'),(t.at[g,'e20'],'simple_env')]:
            a=fld*(1+fld/2)/(1+fld); k=z/2-a
            gtot=1.2e-10*(k+np.sqrt(k*k+(1+fld)*z))
            vv=np.sqrt(np.maximum(0,gtot*r/cm.KMS2_KPC_TO_MS2))
            record[key]=np.mean(((vv-v)/e)**2)
    pred.append(record)
f=pd.DataFrame(pred).set_index('Galaxy')
f.to_csv(out/'threshold_by_galaxy.csv')
shared=t[t.in_CCC].copy()
tr=shared[shared.split=='train'];test=shared[shared.split=='test']
def sign_table(mode):
    z=modes[modes['mode']==mode]
    counts=[[sum((z.split==k)&(z.winner==m)) for m in ('CCC','MOND')] for k in ('train','test')]
    return dict(train=counts[0],test=counts[1],fisher=stats.fisher_exact(counts).pvalue)
cut=tr.SBeff.quantile(.25)
lsb=[[int((z.SBeff<=cut).sum()),int((z.SBeff>cut).sum())] for z in [tr,test]]
selection={}
for k in ['SBeff','Sigma','Reff','Rdisk','R_max','T']:
    selection[k]=dict(median_train=tr[k].median(),median_test=test[k].median(),
                  p=stats.mannwhitneyu(tr[k],test[k],alternative='two-sided').pvalue)
def holm(ps):
    order=np.argsort(ps); vals=np.minimum(1,np.maximum.accumulate(np.array(ps)[order]*np.arange(len(ps),0,-1)))
    return vals[np.argsort(order)]
for v,adj in zip(selection.values(),holm([o['p'] for o in selection.values()])):v['holm']=adj
cor=[]
for k,z in [('all',shared),('test',test)]:
    for name in ['SBeff','Sigma','e20','e21']:
        d=z[[name]].join((f.constant-f.mond).rename('delta')).dropna()
        r,pv=stats.spearmanr(d[name],d.delta)
        cor.append(dict(split=k,feature=name,n=len(d),rho=r,p=pv))
for row,adj in zip(cor,holm([x['p'] for x in cor])):row['holm']=adj
sub=f[f.split=='test']; e=sub.dropna(subset=['simple_env'])
bt=t[t.Vflat>0].copy()
bt['logv']=np.log10(bt.Vflat);bt['logm']=np.log10(bt.Mbar)
bttr=bt[bt.split=='train']
for slope,tag in [(3.5,'35'),(4,'4')]:
    intercept=(bttr.logm-slope*bttr.logv).mean()
    bt['r'+tag]=bt.logm-(intercept+slope*bt.logv)
    bt['intercept'+tag]=intercept
bt[['split','logm','logv','r35','r4','intercept35','intercept4']].to_csv(out/'btfr.csv')
btest=bt[bt.split=='test']
liter=pd.read_csv(out/'S11_scores.csv').set_index('Galaxy').join(t.split)
by_split={k:dict(n=len(z),p075=int((z.chi_p075<z.chi_p1).sum()),p1=int((z.chi_p1<z.chi_p075).sum()),
                       ties=int((z.chi_p075==z.chi_p1).sum())) for k,z in liter.groupby('split')}
models=dict(reference=1.2e-10,R142=freeze['params']['r142_a0'],forward=freeze['params']['forward_mond'],inverse=freeze['params']['inverse_mond'])
response=dict(scale={k:{str(h):v/(299792458*h/3.0856775814913673e19/(2*np.pi)) for h in [67.4,73.,73.04]} for k,v in models.items()},
      inverse={k:sign_table(k) for k in ['paper_inverse','inverse_common','inverse_model_sigma']},
      selection=selection,LSB=dict(cut=cut,counts=lsb,p=stats.fisher_exact(lsb).pvalue),environment=cor,
      predictor=dict(params=params,vs_constant=paired(sub.loss-sub.constant),vs_mond=paired(sub.loss-sub.mond)),
      winners=shared.loc[['IC2574','NGC6674','UGC04305'],['T','SBeff','Sigma','Reff','e20','e21']].join(
          f[['constant','mond','simple0','simple_env']]).replace({np.nan:None}).to_dict('index'),
      simple_EFE_test=paired(e.simple_env-e.simple0),btfr=dict(ntrain=len(bttr),comparison=paired(btest.r35**2-btest.r4**2),
             rms35=np.mean(btest.r35**2)**.5,rms4=np.mean(btest.r4**2)**.5,S11=by_split))
(out/'sparc_results.json').write_text(json.dumps(response,indent=2,allow_nan=False,default=lambda x:x.item())+'\n')
shared[['split','SBeff','Reff','Rdisk','R_max','T','Sigma','e20','e21']].to_csv(out/'covariates.csv')
