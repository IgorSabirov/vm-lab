"""Evaluate the locked external transfer. Run after photometry.py or use committed inputs."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import binomtest

HERE=Path(__file__).resolve().parent
FOLLOW=HERE.parent


def paired(delta):
    values=np.asarray(delta)
    n=len(values)
    wins=int(np.sum(values<0))
    losses=int(np.sum(values>0))
    rng=np.random.default_rng(143)
    boot=values[rng.integers(n,size=(10000,n))].mean(axis=1)
    limits=np.quantile(boot,[.025,.975])
    loo=(values.sum()-values)/(n-1)
    return dict(n=n,wins=wins,ties=n-wins-losses,mean=values.mean(),median=np.median(values),
                bootstrap_95=limits.tolist(),pass_upper_lt_zero=bool(limits[1]<0),
                p_sign_one=binomtest(wins,wins+losses,.5,alternative='greater').pvalue,
                p_sign_two=binomtest(wins,wins+losses,.5).pvalue,
                leave_one_out_range=[loo.min(),loo.max()])


def main(donor):
    sys.path.insert(0,str(donor.resolve()))
    import compare_models as cm
    lock=json.loads((HERE/'LOCK.json').read_text())
    for name,expected in lock['input_sha256'].items():
        assert hashlib.sha256((FOLLOW/name).read_bytes()).hexdigest()==expected,name
    b=lock['parameters']
    freeze=json.loads((FOLLOW.parent/'freeze.json').read_text())['params']
    phot=pd.read_csv(HERE/'photometry.csv').set_index('Galaxy',verify_integrity=True)
    radial=pd.read_csv(FOLLOW/'little_radial.csv')
    sample=pd.read_csv(FOLLOW/'little_sample.csv').set_index('Galaxy')
    assert list(phot.index)==lock['ids']==list(sample.query('status=="tested"').index)
    assert set(radial.Galaxy)==set(phot.index) and len(radial)==265 and len(phot)==14
    score_inputs=[]
    results=[]
    curves=[]
    changes={'primary':(1.,1.),'Re_080':(.8,1.),'Re_120':(1.2,1.),'L36_080':(1.,.8),'L36_120':(1.,1.2)}
    for gal,p in phot.iterrows():
        d=radial[radial.Galaxy==gal].copy()
        r=d.R.to_numpy()
        vb=np.sqrt(np.maximum(0,d.Vgas*abs(d.Vgas)+d.Vstar*abs(d.Vstar))).to_numpy()
        grid,rho,_=cm.rho_from_v(r,vb,s=.5*len(r))
        c=cm.ccc_forward(grid,rho,r,freeze['forward_sharp'])[0]
        m=cm.mond_v(vb,r,freeze['forward_mond'])
        np.testing.assert_allclose(c,d.CCC,rtol=1e-8,atol=3e-7)
        np.testing.assert_allclose(m,d.MOND,rtol=1e-8,atol=3e-7)
        def loss(pred):
            return np.mean(((pred-d.Vobs)/np.maximum(1,d.eV))**2)
        score_inputs.append((r,grid,rho,d.Vobs.to_numpy(),np.maximum(d.eV.to_numpy(),1)))
        for scenario,(rscale,lscale) in changes.items():
            sigma=(.5*lscale*p.L36_Lsun+1.33*p.MHI_Msun)/(2*np.pi*(1000*p.Re_kpc*rscale)**2)
            threshold=10**np.clip(b['b0']+b['b1']*np.log10(sigma/100),3,12)
            model=cm.ccc_forward(grid,rho,r,threshold)[0]
            score,base,mond=loss(model),loss(c),loss(m)
            results.append(dict(Galaxy=gal,scenario=scenario,n=len(r),Sigma=sigma,rho_t=threshold,
                                individual=score,constant=base,MOND=mond,delta_constant=score-base,delta_MOND=score-mond))
            if scenario=='primary':
                np.testing.assert_allclose(base-mond,sample.at[gal,'delta'],atol=5e-7)
                d['CCC_individual']=model
                d['residual_individual_kms']=model-d.Vobs
                curves.append(d)
    results=pd.DataFrame(results)
    results.to_csv(HERE/'scores.csv',index=False)
    pd.concat(curves).to_csv(HERE/'radial.csv',index=False)
    summary={k:{key:paired(group['delta_'+key]) for key in ['constant','MOND']}
             for k,group in results.groupby('scenario')}
    primary=results.query("scenario=='primary'")
    summary['frozen_baseline']=paired(primary.constant-primary.MOND)
    summary['mean_losses']=primary[['individual','constant','MOND']].mean().to_dict()
    # Exploratory identity control, after scoring. Permute the frozen thresholds, never the radii.
    thresholds=primary.rho_t.to_numpy()
    n=len(thresholds)
    cross=np.empty((n,n))
    for i,(r,grid,rho,obs,err) in enumerate(score_inputs):
        for j,t in enumerate(thresholds):
            v=cm.ccc_forward(grid,rho,r,t)[0]
            cross[i,j]=np.mean(((v-obs)/err)**2)
    np.testing.assert_allclose(np.diag(cross),primary.individual,atol=1e-8)
    rng=np.random.default_rng(143)
    null=np.array([cross[np.arange(n),rng.permutation(n)].mean() for _ in range(10000)])
    observed=float(np.diag(cross).mean())
    summary['exploratory_permute_thresholds']=dict(draws=len(null),observed=observed,
        null_mean=float(null.mean()),null_95=np.quantile(null,[.025,.975]).tolist(),
        p_lower=(1+int((null<=observed).sum()))/(len(null)+1))
    (HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary['primary'],indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('donor',type=Path)
    main(parser.parse_args().donor)
