"""Paired scores and reproducibility checks from saved curves only."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

parser=argparse.ArgumentParser()
parser.add_argument('--out',type=Path,required=True)
out=parser.parse_args().out
samples=pd.read_csv(out/'samples.csv').set_index('Galaxy')
points=pd.read_csv(out/'predictions.csv.gz')
native=pd.read_csv(out/'native_radial.csv.gz')
native['split']=native.Galaxy.map(samples.split)
native['mode']='paper_inverse'
combined=pd.concat([points,native],ignore_index=True)
assert not combined.duplicated(['mode','Galaxy','R']).any()
counts=samples.query('in_CCC').n_shared.sort_index()
assert len(counts)==165 and counts.sum()==3345
for mode,d in combined.groupby('mode'):
    assert d.groupby('Galaxy').size().sort_index().equals(counts)
    if mode.startswith('forward') or mode=='inverse_common':
        np.testing.assert_array_equal(d.sigma_CCC,d.sigma_MOND)
    np.testing.assert_allclose(d.CCC-d.target,d.resid_CCC,atol=3e-11)
    np.testing.assert_allclose(d.MOND-d.target,d.resid_MOND,atol=3e-11)
    calculated=(d.resid_CCC/d.sigma_CCC)**2-(d.resid_MOND/d.sigma_MOND)**2
    np.testing.assert_allclose(calculated,d.delta_chi2,rtol=2e-9,atol=2e-9)
rows=[]
for (mode,split,gal),d in combined.groupby(['mode','split','Galaxy']):
    rec=dict(mode=mode,split=split,Galaxy=gal,n=len(d))
    for m in ['CCC','MOND']:
        resid=d['resid_'+m].to_numpy()
        chi=float(np.sum((resid/d['sigma_'+m])**2))
        rec['chi2_'+m]=chi
        rec['mean_chi2_'+m]=chi/len(d)
        rec['bias_'+m]=np.mean(resid)
        rec['MAE_'+m]=np.mean(np.abs(resid))
        rec['RMSE_'+m]=np.mean(resid**2)**0.5
    rec['delta_chi2']=rec['chi2_CCC']-rec['chi2_MOND']
    rec['delta_per_point']=rec['delta_chi2']/len(d)
    rec['winner']='CCC' if rec['delta_chi2']<0 else ('MOND' if rec['delta_chi2']>0 else 'tie')
    rows.append(rec)
by=pd.DataFrame(rows)
by.to_csv(out/'galaxy_scores.csv',index=False,float_format='%.15g')
orig=pd.read_csv(out/'native_replay.csv').set_index('Galaxy').sort_index()
replay=by.query('mode=="paper_inverse"').set_index('Galaxy').sort_index()
for m,c in [('CCC','CCC_standard_chi2r'),('MOND','MOND_smooth_chi2r')]:
    np.testing.assert_allclose(replay['chi2_'+m]/(orig.N-1),orig[c],rtol=1e-11,atol=1e-11)

def group_stats(d):
    delta=d.delta_per_point.to_numpy(); n=len(delta)
    rng=np.random.default_rng(143)
    idx=rng.integers(n,size=(10000,n))
    ci=lambda x:np.percentile(x,[2.5,97.5]).tolist()
    signs=rng.choice([-1,1],(10000,n))
    flip_mean=np.abs((signs*delta).mean(axis=1))
    total=d.delta_chi2.to_numpy()
    return dict(n_gal=n,n_radial=int(d.n.sum()),ccc_wins=int((delta<0).sum()),
            mond_wins=int((delta>0).sum()),ties=int((delta==0).sum()),
            delta_sum=float(total.sum()),delta_sum_cluster_ci=ci(total[idx].sum(axis=1)),
            equal_gal_mean=float(delta.mean()),equal_gal_mean_cluster_ci=ci(delta[idx].mean(axis=1)),
            median=float(np.median(delta)),quartiles=np.percentile(delta,[25,75]).tolist(),
            median_cluster_ci=ci(np.median(delta[idx],axis=1)),win_fraction_ci=ci((delta[idx]<0).mean(axis=1)),
            leave_one_out_mean_range=[float(x((delta.sum()-delta)/(n-1))) for x in (np.min,np.max)],
            sign_randomization_p=(1+int((flip_mean>=abs(delta.mean())).sum()))/10001,
            means={k:float(d[k].mean()) for k in ['mean_chi2_CCC','mean_chi2_MOND','MAE_CCC','MAE_MOND','RMSE_CCC','RMSE_MOND']})
summary={}
for mode,d in by.groupby('mode'):
    summary[mode]={s:group_stats(z) for s,z in list(d.groupby('split'))+[('all',d)]}
geometry=pd.read_csv(out/'forward_geometry.csv').set_index('Galaxy')
for mode in ['forward_sharp','forward_standard']:
    d=by.query('mode==@mode and split=="test"')
    summary[mode]['test_no_clipping']=group_stats(d[d.Galaxy.map(geometry.negative_grid)==0])
ctrl=pd.read_csv(out/'controls.csv')
null={}
for split,z in ctrl.groupby('split'):
    null[split]={}
    for m in ['mond','sharp','standard']:
        dif=(z['reversed_'+m]-z[m]).to_numpy()
        idx=np.random.default_rng(143).integers(len(z),size=(10000,len(z)))
        null[split][m]=dict(real_mean=float(z[m].mean()),reversed_mean=float(z['reversed_'+m].mean()),
                    degraded=int((dif>0).sum()),delta_ci=np.percentile(dif[idx].mean(axis=1),[2.5,97.5]).tolist())
    null[split]['newton_mean']=float(z.newton.mean())
paper=dict(mean=[orig.CCC_standard_chi2r.mean(),orig.MOND_smooth_chi2r.mean()],
           median=[orig.CCC_standard_chi2r.median(),orig.MOND_smooth_chi2r.median()],
           ccc_wins=int((orig.CCC_standard_chi2r<orig.MOND_smooth_chi2r).sum()),
           ccc_rhot_cgs_median=float(orig.CCC_rhot.median()),
           ccc_rhot_scatter_dex=float(np.log10(orig.CCC_rhot).std()))
report=dict(delta_convention='CCC minus MOND',replicates=10000,seed=143,
            freeze_sha256=hashlib.sha256((out/'freeze.json').read_bytes()).hexdigest(),
            historical=paper,paired=summary,controls=null)
(out/'statistics.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
