"""Local acceleration and historical residuals on the 91 resolved SPARC galaxies."""
import argparse
import hashlib
import io as stream
import json
import os
import sys
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.stats import pearsonr, spearmanr, t
from disk import HERE, SPARC, ACC

CENTER=.352
DRAWS=10000


def concentration(raw):
    # The survey marks additional rejected rows with an initial '#'.
    a=np.genfromtxt(stream.BytesIO(raw),skip_header=1,ndmin=2)
    a=a[np.isfinite(a).all(axis=1)&(a[:,2]==1)&(a[:,0]>0)]
    if len(a)<3:
        return np.nan,np.nan,np.nan,len(a)
    a=a[np.argsort(a[:,0])]
    r=np.r_[0.,a[:,0]]
    light=10**(-.4*(a[:,1]-min(a[:,1])))
    light=np.r_[light[0],light]
    h=np.diff(r)
    assert (h>0).all()
    slope=np.diff(light)/h
    def integral(i,u):
        return r[i]*light[i]*u+(light[i]+r[i]*slope[i])*u*u/2+slope[i]*u**3/3
    c=np.r_[0.,np.cumsum(integral(np.arange(len(h)),h))]
    radii=[]
    for frac in [.2,.8]:
        target=frac*c[-1]
        i=np.searchsorted(c,target)-1
        radii.append(r[i]+brentq(lambda u: c[i]+integral(i,u)-target,0,h[i]))
    return *radii,5*np.log10(radii[1]/radii[0]),len(a)


def stats_local(d):
    x=np.log10(d.a0_native.to_numpy())
    y=np.log10(d.at_flat.to_numpy())
    sd1,sd2=np.std(y,ddof=1),np.std(x,ddof=1)
    pear=pearsonr(x,y).statistic
    rank=spearmanr(x,y).statistic
    z=y-x
    out=dict(n=len(d),sd_flat=sd1,sd_native=sd2,pearson=pear,spearman=rank,
             sd_identity_pearson=np.sqrt(sd1**2+sd2**2-2*pear*sd1*sd2),
             plug_in_spearman=np.sqrt(sd1**2+sd2**2-2*rank*sd1*sd2),
             sd_measured=z.std(ddof=1),mean_log=z.mean(),mean_SE=z.std(ddof=1)/np.sqrt(len(z)),
             median_log=np.median(z),centered_median=float(np.median(z-CENTER)),factor_sd=10**z.std(ddof=1))
    rng=np.random.default_rng(143)
    idx=rng.integers(len(d),size=(DRAWS,len(d)))
    out['mean_log_ci']=np.quantile(z[idx].mean(axis=1),[.025,.975]).tolist()
    out['median_log_ci']=np.quantile(np.median(z[idx],axis=1),[.025,.975]).tolist()
    out['ols_residual_sd']=np.std(y-np.polyval(np.polyfit(x,y,1),x),ddof=1)
    out['estimators']={}
    for k in ['flat','local','linear']:
        v=d['at_'+k].to_numpy()
        a=d.a0_native.to_numpy()
        q=v/a
        logq=np.log10(q)
        med_boot=np.median(logq[idx],axis=1)
        ci=10**np.quantile(med_boot,[.025,.975])
        qmed_boot=np.median(v[idx],axis=1)/np.median(a[idx],axis=1)
        diff=logq-z
        out['estimators'][k]=dict(median_paired=float(np.median(q)),paired95=ci.tolist(),
                ratio_of_medians=np.median(v)/np.median(a),ratio_of_medians95=np.quantile(qmed_boot,[.025,.975]).tolist(),
                median_at=np.median(v),sd_log_paired=np.std(logq,ddof=1),
                pearson_log_with_a0=pearsonr(np.log10(v),np.log10(a)).statistic,median_log_paired_shift=np.median(diff),
                shift95=np.quantile(np.median(diff[idx],axis=1),[.025,.975]).tolist(),
                share_lower_than_flat=float(np.mean(v<d.at_flat.to_numpy())),
                equivalent_within_point1dex={str(ref):bool(np.all(np.abs(np.log10(ci/ref))<=.1)) for ref in (1.,1.42,2.25)})
    return out


def design(d,features):
    return np.column_stack([np.ones(len(d)),*[d[k].to_numpy() for k in features]])


def fit(d,features):
    X=design(d,features)
    beta=np.linalg.lstsq(X,d.residual,rcond=None)[0]
    u=d.residual.to_numpy()-X@beta
    C=np.linalg.inv(X.T@X)
    lev=np.sum((X@C)*X,axis=1)
    Xw=X*(u/(1-lev))[:,None]
    se=np.sqrt(np.diag(C@(Xw.T@Xw)@C))
    df=len(d)-X.shape[1]
    crit=t.ppf(.975,df)
    return beta,dict(R2=1-u@u/np.sum((d.residual-d.residual.mean())**2),
                     coefficients={name:dict(beta=b,HC3_95=[b-crit*s,b+crit*s],p=2*t.sf(abs(b/s),df))
                          for name,b,s in zip(['intercept',*features],beta,se)})


def regression(d):
    models={'base':[], 'gas':['fgas'],'requested_v1':['fgas','log_Rt_RHI'],
            'requested':['fgas','log_Rt_RHI','C82'],'independent_v1':['fgas','log_RHI_Rd'],
            'independent':['fgas','log_RHI_Rd','C82'],'no_Rt_shared_speed':['fgas','log_Rgrav_RHI'],
            'slope_base':['log_a0_center'],'independent_slope':['log_a0_center','fgas','log_RHI_Rd','C82']}
    required=sorted({s for f in models.values() for s in f})
    complete=d.dropna(subset=required).copy()
    train=complete[complete.split=='train']
    test=complete[complete.split=='test']
    rows=[]
    rng=np.random.default_rng(143)
    idx=rng.integers(len(test),size=(DRAWS,len(test)))
    summary={}
    predictions={}
    for name,features in models.items():
        beta,_=fit(train,features)
        pred=design(test,features)@beta
        errors=(pred-test.residual.to_numpy())**2
        predictions[name]=errors
        _,desc=fit(complete,features)
        summary[name]=dict(all_complete=desc,beta_train=dict(zip(['intercept',*features],beta)),
                           test_MSE=errors.mean(),test_RMSE=np.sqrt(errors.mean()))
        for gal,obs,v in zip(test.Galaxy,test.residual,pred):
            rows.append(dict(Galaxy=gal,model=name,observed_residual=obs,predicted_residual=v))
    for k,v in summary.items():
        delta=predictions[k]-predictions['slope_base' if k=='independent_slope' else 'base']
        v.update(delta_test_MSE=delta.mean(),bootstrap95=np.quantile(delta[idx].mean(axis=1),[.025,.975]).tolist())
    # Preserve exactly q_geom = log(Rgrav/RHI) - log(at/a0) when making a null with no galaxy pairing.
    f=complete.fgas.to_numpy()
    c=complete.C82.to_numpy()
    ratio=complete.log_Rgrav_RHI.to_numpy()
    z=complete.residual.to_numpy()
    np.testing.assert_allclose(complete.log_Rt_RHI,ratio-(z+CENTER),atol=2e-12)
    rng=np.random.default_rng(143)
    fake=[]
    for _ in range(DRAWS):
        perm=rng.permutation(z)
        X=np.column_stack([np.ones(len(z)),f,ratio-(perm+CENTER),c])
        beta=np.linalg.lstsq(X,perm,rcond=None)[0]
        fake.append(1-np.sum((perm-X@beta)**2)/np.sum((perm-perm.mean())**2))
    observed=summary['requested']['all_complete']['R2']
    audit=dict(n=len(complete),train=len(train),test=len(test),excluded=d.loc[~d.Galaxy.isin(complete.Galaxy),'Galaxy'].tolist(),
               coupling_null_R2_median=np.median(fake),coupling_null_R2_95=np.quantile(fake,[.025,.975]).tolist(),
               coupling_null_p=(1+np.sum(np.array(fake)>=observed))/(DRAWS+1),models=summary)
    pd.DataFrame(rows).to_csv(HERE/'regression_holdout.csv',index=False)
    return audit


def run(donor,data,phot):
    sys.path.insert(0,str(donor.resolve()))
    os.environ['SPARC_DATA']=str(data.resolve())
    import ccc_core as cc
    import sparc_io as io
    lock=json.loads((HERE/'LOCK.json').read_text())
    for key,src in [('table1',io.T1),('table2',io.T2)]:
        assert hashlib.sha256(Path(src).read_bytes()).hexdigest()==lock['SPARC'][key]
    assert hashlib.sha256(phot.read_bytes()).hexdigest()==json.loads((HERE/'AMENDMENT.json').read_text())['phot_sha256']
    source=HERE.parent/'external14/scale_by_galaxy.csv'
    assert hashlib.sha256(source.read_bytes()).hexdigest()==lock['input_hashes']['followup/external14/scale_by_galaxy.csv']
    prior=pd.read_csv(source).query('extended_resolved')
    assert len(prior)==91
    t1,t2=io.load_table1(),io.load_table2()
    split=pd.read_csv(SPARC/'samples.csv').set_index('Galaxy').split
    records=[]
    with ZipFile(phot) as z:
        for _,p in prior.iterrows():
            g=p.Galaxy
            trow=t1.loc[g]
            obs=t2[t2.Galaxy==g].sort_values('R')
            rad=obs.R.to_numpy()
            vel=obs.Vobs.to_numpy()
            sp=cc.smooth_vobs(rad,vel,obs.e_Vobs.to_numpy(),s_factor=.1)
            rt=p.extended_Rt_kpc
            a=p.a0_native_m_s2
            vf=trow.Vflat
            flat=vf**2*ACC/rt
            np.testing.assert_allclose(p.extended_at_m_s2/flat,1,rtol=1e-11)
            local=float(sp(rt))
            vlin=np.interp(rt,rad,vel)
            r20,r80,c,n=concentration(z.read(g+'.sfb')) if g+'.sfb' in z.namelist() else (np.nan,np.nan,np.nan,0)
            rhi=trow.RHI
            fgas=1.33*trow.MHI/(1.33*trow.MHI+.5*trow.L36)
            records.append(dict(Galaxy=g,split=split.at[g],Rt=rt,RHI=rhi,Rdisk=trow.Rdisk,fgas=fgas,C82=c,
                R20_arcsec=r20,R80_arcsec=r80,Nphot=n,Vflat=vf,Vlocal=local,Vlinear=vlin,
                a0_native=a,at_flat=flat,at_local=local**2*ACC/rt,at_linear=vlin**2*ACC/rt,
                residual=np.log10(flat/a)-CENTER,log_Rt_RHI=np.log10(rt/rhi) if rhi>0 else np.nan,
                log_RHI_Rd=np.log10(rhi/trow.Rdisk) if rhi>0 and trow.Rdisk>0 else np.nan,
                log_Rgrav_RHI=np.log10(vf**2*ACC/(a*rhi)) if rhi>0 else np.nan,
                log_a0_center=np.log10(a/1e-10)))
    d=pd.DataFrame(records)
    d.to_csv(HERE/'historical91.csv',index=False)
    out=stats_local(d)
    out['regression']=regression(d)
    out['fixed_calibration_median_at_over_a0']={k:{m:np.median(d['at_'+m])/a for m in ['flat','local','linear']}
                                                for k,a in lock['thresholds'].items()}
    (HERE/'residual_summary.json').write_text(json.dumps(out,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ['donor','data','photometry_zip']:
        parser.add_argument(key,type=Path)
    args=parser.parse_args()
    run(args.donor,args.data,args.photometry_zip)
