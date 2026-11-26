"""Final Rg definition and checks against the independent gas-radius control."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from disk import ACC
from residuals import CENTER, DRAWS, design, fit

HERE=Path(__file__).resolve().parent


def run():
    d=pd.read_csv(HERE/'historical91.csv')
    lock=json.loads((HERE/'LOCK.json').read_text())
    split=d.split.to_numpy()
    train=split=='train'
    test=split=='test'
    assert (train|test).all() and len(d)==91 and d.C82.notna().all()
    base=d.residual[train].mean()
    ytest=d.residual[test].to_numpy()
    rng=np.random.default_rng(143)
    idx=rng.integers(test.sum(),size=(DRAWS,test.sum()))
    zeros={}
    models={}
    testpred=pd.DataFrame({'Galaxy':d.Galaxy[test],'observed':ytest,'baseline':base})
    for name,a in {'native':d.a0_native.to_numpy(),**lock['thresholds']}.items():
        rg=d.Vflat**2*ACC/a
        x=np.log10(d.Rt/rg)
        d['Rg_'+name+'_kpc']=rg
        d['log_Rt_Rg_'+name]=x
        zeros[name]=float(abs(x+np.log10(d.at_flat/a)).max())
        assert zeros[name]<1e-12
        requested=-x+np.log10(a/d.a0_native)-CENTER
        np.testing.assert_allclose(requested,d.residual,atol=1e-12,rtol=0)
        loc=-x+np.log10(a/d.a0_native)+2*np.log10(abs(d.Vlocal)/d.Vflat)-CENTER
        np.testing.assert_allclose(loc,np.log10(d.at_local/d.a0_native)-CENTER,atol=1e-12,rtol=0)
    for name,features in {'native':['fgas','log_Rt_Rg_native','C82'],
                          'canonical':['fgas','log_Rt_Rg_canonical','C82'],
                          'R142':['fgas','log_Rt_Rg_R142','C82'],
                          'independent_gas_concentration':['fgas','C82']}.items():
        X=design(d,features)
        b=np.linalg.lstsq(X[train],d.residual.to_numpy()[train],rcond=None)[0]
        pred=X[test]@b
        testpred[name]=pred
        err=(pred-ytest)**2
        delta=err-(base-ytest)**2
        bfull=np.linalg.lstsq(X,d.residual,rcond=None)[0]
        rss=np.sum((X@bfull-d.residual)**2)
        models[name]=dict(beta_train=dict(zip(['intercept',*features],b)),
                          beta_full=dict(zip(['intercept',*features],bfull)),
                          R2_full=1-rss/np.sum((d.residual-d.residual.mean())**2),
                          test_RMSE=np.sqrt(err.mean()),test_delta_MSE=delta.mean(),
                          delta95=np.quantile(delta[idx].mean(axis=1),[.025,.975]).tolist())
        if name!='native':
            models[name]['HC3_full']=fit(d,features)[1]['coefficients']
    np.testing.assert_allclose(testpred.canonical,testpred.R142,rtol=0,atol=1e-12)
    out=dict(count=len(d),train=int(train.sum()),test=int(test.sum()),native_identity_max_abs_dex=zeros['native'],
             by_scale_max_abs_identity=zeros,intercept_only_test_RMSE=np.sqrt(np.mean((base-ytest)**2)),models=models)
    d[['Galaxy','split','Rt','Vflat','a0_native','residual','Rg_native_kpc','log_Rt_Rg_native',
       'Rg_canonical_kpc','log_Rt_Rg_canonical','Rg_R142_kpc','log_Rt_Rg_R142','RHI']].to_csv(HERE/'gravity_radii.csv',index=False)
    testpred.to_csv(HERE/'gravity_holdout.csv',index=False)
    (HERE/'gravity_summary.json').write_text(json.dumps(out,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':
    run()
