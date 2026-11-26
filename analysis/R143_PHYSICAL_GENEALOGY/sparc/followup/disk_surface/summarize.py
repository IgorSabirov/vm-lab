"""Matched galaxy bootstrap for every frozen surface convention."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
B=10000


def paired(frame):
    x=np.log10(frame.q.to_numpy())
    y=np.log10((frame.historical_at/frame.a0).to_numpy())
    idx=np.random.default_rng(143).integers(len(frame),size=(B,len(frame)))
    xd=np.median(x[idx],axis=1)
    ys=np.median(y[idx],axis=1)
    ci=np.quantile(xd,[.025,.975])
    shrink=np.abs(xd)-np.abs(ys)
    shrink_ci=np.quantile(shrink,[.025,.975])
    return dict(n=len(frame),q_disk=10**np.median(x),disk_low=10**ci[0],disk_high=10**ci[1],
                q_spherical=10**np.median(y),sphere_low=10**np.quantile(ys,.025),sphere_high=10**np.quantile(ys,.975),
                shrink_dex=abs(np.median(x))-abs(np.median(y)),shrink_low=shrink_ci[0],shrink_high=shrink_ci[1],
                passes=bool(np.all(abs(ci)<=.10) and shrink_ci[1]<0),local_q=np.median(frame.q_local),
                median_radius_ratio=np.median(frame.Rt_kpc/frame.historical_Rt),
                multiple_down=int((frame.n_down>1).sum()),any_negative=int((frame.negative_fraction>0).sum()))


def main():
    f=pd.read_csv(HERE/'crossings.csv')
    rows=[]
    for (arm,norm,cal),d in f.groupby(['arm','norm','cal']):
        base=d[d.historical91]
        sub=base[base.q.notna()]
        assert len(base)==91 and len(d)==165
        rows.append(dict(arm=arm,norm=norm,cal=cal,Sigma0=d.threshold_Msun_pc2.iloc[0],
                         all165_radial=int((d.crossing=='resolved').sum()),all165_with_flat=int(d.q.notna().sum()),
                         no_flat=int((d.Vflat<=0).sum()),
                         missing91_all_below=int((base.crossing=='all_below').sum()),
                         missing91_inner_then_above=int((base.crossing=='inner_below_then_above').sum()),
                         missing91_all_above=int((base.crossing=='all_above').sum()),**paired(sub)))
    pd.DataFrame(rows).to_csv(HERE/'disk_summary.csv',index=False)
    compare=[]
    for (norm,cal),d in f[f.historical91].groupby(['norm','cal']):
        p=d.pivot(index='Galaxy',columns='arm',values='q')
        for key in ['disk_kepler','disk_pchip','sphere_abel','baryonic_disk']:
            common=p[['disk',key]].dropna()
            x,y=np.log10(common.to_numpy()).T
            indices=np.random.default_rng(143).integers(len(x),size=(B,len(x)))
            a,b=np.median(x[indices],axis=1),np.median(y[indices],axis=1)
            low,high=np.quantile(a-b,[.025,.975])
            compare.append(dict(norm=norm,cal=cal,control=key,n=len(x),median_thin=10**np.median(x),
                                median_control=10**np.median(y),thin_minus_control_dex=np.median(x)-np.median(y),
                                low=low,high=high,n_thin_only=int((p.disk.notna()&p[key].isna()).sum()),
                                n_control_only=int((p.disk.isna()&p[key].notna()).sum())))
    pd.DataFrame(compare).to_csv(HERE/'matched_controls.csv',index=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fine',type=Path,help='Output folder of an independently refined disk.py run')
    args=parser.parse_args()
    main()
    if args.fine:
        keys=['Galaxy','arm','cal','norm']
        base=pd.read_csv(HERE/'crossings.csv').set_index(keys).sort_index()
        fine=pd.read_csv(args.fine/'crossings.csv').set_index(keys).sort_index()
        assert base.index.equals(fine.index)
        primary=base.historical91 & (base.index.get_level_values('arm')=='disk') & (base.index.get_level_values('norm')=='mestel')
        changes=int((base.crossing!=fine.crossing).sum())
        diff=abs(base.Rt_kpc[primary]/fine.Rt_kpc[primary]-1).dropna()
        assert changes==0 and diff.max()<.005
        audit=dict(base_subintervals=8,base_quadrature=12,fine_subintervals=16,fine_quadrature=20,
                   total_crossing_labels=len(base),status_changes=changes,primary_max_relative_radius=diff.max(),
                   primary_median_relative_radius=diff.median())
        (HERE/'resolution_check.json').write_text(json.dumps(audit,indent=2)+'\n')
