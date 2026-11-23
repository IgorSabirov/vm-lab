"""Historical inverse scale audit and independent, fixed M81 group-field check."""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

HERE=Path(__file__).resolve().parent
PRIOR=HERE.parent.parent


def env_test(t2, cc, cm):
    g='UGC04305'
    d=t2[t2.Galaxy==g].sort_values('R').copy()
    r=d.R.to_numpy()
    vb=cc.sparc_vbar(d.Vgas.to_numpy(),d.Vdisk.to_numpy(),d.Vbul.to_numpy())
    canon=1.2e-10
    # Sanchez-Salcedo et al. (2011), Sec. IV, bound-group assumption, cm/s^2 to m/s^2.
    field=.7e-10*.01
    z=vb**2/r*cm.KMS2_KPC_TO_MS2/canon
    scores={}
    for key,gext in [('simple0',0.),('simple_group',field)]:
        e=gext/canon
        a=e*(1+e/2)/(1+e)
        k=z/2-a
        v=np.sqrt(np.maximum(0,canon*(k+np.sqrt(k*k+(1+e)*z))*r/cm.KMS2_KPC_TO_MS2))
        d[key]=v
        scores[key]=np.mean(((v-d.Vobs)/np.maximum(d.e_Vobs,1))**2)
    d[['Galaxy','R','Vobs','e_Vobs','simple0','simple_group']].to_csv(HERE/'ugc04305_radial.csv',index=False)
    old=pd.read_csv(HERE.parent/'threshold_by_galaxy.csv').set_index('Galaxy').loc[g]
    scores.update(CCC_constant=old.constant,CCC_individual=old.loss,RAR_forward=old.mond)
    return dict(Galaxy=g,aliases=['DDO 50','Holmberg II','UGC 4305'],catalog='Annibali et al. 2020 SSH table 1, Karachentsev et al. 2013 tidal indices',
                dist_Mpc=3.39,Theta1=.7,main_disturber='M81',Theta5=1.,group_field_m_s2=field,
                gext_over_canonical_a0=field/canon,n=len(r),R_kpc=[r.min(),r.max()],losses=scores,
                delta_simple=scores['simple_group']-scores['simple0'],
                max_suppression_kms=(d.simple0-d.simple_group).max())


def scatter(frame):
    x=np.log10(frame[['rho_cgs','at_m_s2','a0_native_m_s2']])
    return dict(n=len(x),median_linear=(10**x.median()).to_dict(),sd_dex=x.std(ddof=1).to_dict(),
                NMAD_dex=(1.4826*(x-x.median()).abs().median()).to_dict(),
                spearman_at_a0=spearmanr(x.at_m_s2,x.a0_native_m_s2).statistic,
                paired_median_ratio=float(np.median(frame.at_m_s2/frame.a0_native_m_s2)))


def main(donor,data):
    sys.path.insert(0,str(donor.resolve()))
    os.environ['SPARC_DATA']=str(data.resolve())
    import ccc_core as cc
    import compare_models as cm
    import sparc_io as io
    frozen=json.loads((PRIOR/'freeze.json').read_text())
    for k,f in [('table1',io.T1),('table2',io.T2)]:
        assert hashlib.sha256(Path(f).read_bytes()).hexdigest()==frozen['source'][k]
    t1,t2=io.load_table1(),io.load_table2()
    native=pd.read_csv(PRIOR/'native_replay.csv').set_index('Galaxy')
    rows=[]
    for gal,p in native.iterrows():
        d=t2[t2.Galaxy==gal].sort_values('R')
        r=d.R.to_numpy()
        flat=t1.at[gal,'Vflat']
        sp=cc.smooth_vobs(r,d.Vobs.to_numpy(),d.e_Vobs.to_numpy(),s_factor=.1)
        grid,rho,dm,_=cc.density_profile(sp,r,n_grid=1200,inner_slope=p.inner_slope)
        # The inverse smooth model supplies rho_t. Define the characteristic crossing
        # on the measured domain, also audit the donor's extrapolated first crossing.
        rt0=cc.ccc_model(grid,rho,dm,p.CCC_standard_param)
        mask=grid>=r[0]
        rt1=cc.ccc_model(grid[mask],rho[mask],dm[mask],p.CCC_standard_param)
        row=dict(Galaxy=gal,Vflat_kms=flat,Rmin_kpc=r[0],Rmax_kpc=r[-1],rho_cgs=p.CCC_rhot,
                 rho_Msun_kpc3=p.CCC_standard_param,a0_native_m_s2=p.MOND_smooth_param)
        for key,res in [('measured',rt1),('extended',rt0)]:
            rt=res['Rt'] if res is not None else np.nan
            ok=bool(flat>0 and r[0]<rt<=r[-1])
            row.update({key+'_Rt_kpc':rt,key+'_resolved':ok,key+'_at_m_s2':flat**2/rt*cm.KMS2_KPC_TO_MS2 if ok else np.nan})
        rows.append(row)
    frame=pd.DataFrame(rows)
    frame.to_csv(HERE/'scale_by_galaxy.csv',index=False)
    measured=frame[frame.measured_resolved].rename(columns={'measured_at_m_s2':'at_m_s2'})
    extended=frame[frame.extended_resolved].rename(columns={'extended_at_m_s2':'at_m_s2'})
    # Values printed by the authors in Table 6 and separately in the actual panel (c).
    paper={'table6':dict(n=91,vflat_count=132,rho_cgs=2.1e-24,at_m_s2=2.1e-10,a0_native_m_s2=9.5e-11,
                         sd_dex=[.48,.33,.34],NMAD_dex=[.49,.25,.27]),
           'fig6':dict(at_m_s2=2.14e-10,a0_native_m_s2=9.51e-11,ratio_printed=2.25,sd_dex=[.48,.32,.30],spearman=.83)}
    aa=dict(canonical=1.2e-10,R142=frozen['params']['r142_a0'],R143_forward=frozen['params']['forward_mond'],
            R143_inverse=frozen['params']['inverse_mond'])
    def compare(at,local):
        return {k:at/v for k,v in dict(aa,native_subset_median=local).items()}
    audit=dict(paper=paper,calibrations_m_s2=aa,n_all=len(frame),n_vflat=int((frame.Vflat_kms>0).sum()),
               reconstructed_measured=scatter(measured),reconstructed_extended=scatter(extended),
               ratios_table6=compare(paper['table6']['at_m_s2'],paper['table6']['a0_native_m_s2']),
               ratios_figure6=compare(paper['fig6']['at_m_s2'],paper['fig6']['a0_native_m_s2']),
               ratios_measured=compare(measured.at_m_s2.median(),measured.a0_native_m_s2.median()),
               ratios_extended=compare(extended.at_m_s2.median(),extended.a0_native_m_s2.median()),
               no_crossing_with_flat=frame.loc[(frame.Vflat_kms>0)&frame.extended_Rt_kpc.isna(),'Galaxy'].tolist(),
               n_flat_and_crossing=int(((frame.Vflat_kms>0)&frame.extended_Rt_kpc.notna()).sum()),
               measured_only_ids=frame.loc[frame.measured_resolved&~frame.extended_resolved,'Galaxy'].tolist())
    (HERE/'scale_environment.json').write_text(json.dumps(dict(scale=audit,environment=env_test(t2,cc,cm)),indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('donor',type=Path)
    parser.add_argument('data',type=Path)
    args=parser.parse_args()
    main(args.donor,args.data)
