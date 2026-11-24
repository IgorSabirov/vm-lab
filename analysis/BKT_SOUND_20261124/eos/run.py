"""Rebuild the stage-2 tables directly from the Cambridge Fig. 3a members."""
import csv
import hashlib
import io
import itertools
import json
import zipfile
from dataclasses import asdict
import numpy as np
from scipy.stats import chi2
from inversion import HERE, D0, EquationOfState, DomainError, evaluate
from joint import CAL_SIGMA, NAMES, fit

def measured_rows():
    root=HERE.parent
    raw=(root/'data'/'cambridge.zip').read_bytes()
    manifest=json.loads((root/'data'/'manifest.json').read_text())
    assert hashlib.sha256(raw).hexdigest()==manifest['archive_sha256']
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        def table(n):
            return np.loadtxt(io.BytesIO(z.read('Figure 3/'+n)),skiprows=1)
        fast=table('Fig3a_firstSound_redData.txt');slow=table('Fig3a_secondSound_blueData.txt')
    assert np.allclose(fast[:,:2],slow[:,:2],atol=1e-8,rtol=0)
    keys=['T_over_Tc','err_T','c1','err_c1','c2','err_c2']
    return [dict(zip(keys,np.r_[fast[i],slow[i,2:]])) for i in np.argsort(fast[:,0])]

def prepared(row):
    central,state=evaluate(row,profile=True)
    t,dt=row['T_over_Tc'],row['err_T']
    corr={str(rho):evaluate(row,rho=rho,profile=True)[0] for rho in [-.99,-.9,-.5,0,.44,.5,.9,.99]}
    shifts={}
    derivatives=[]
    for j,name in enumerate(NAMES):
        unit=np.eye(4)[j]*CAL_SIGMA[j]
        shifts[name]=[evaluate(row,scales=1-unit),evaluate(row,scales=1+unit)]
        step=unit*.005
        derivatives.append((evaluate(row,scales=1+step)-evaluate(row,scales=1-step))/.01)
    corners=[]
    for signs in itertools.product([-1,1],repeat=4):
        try:
            ds=evaluate(row,scales=1+np.array(signs)*CAL_SIGMA)
        except DomainError:
            ds=None
        corners.append({'signs':signs,'Ds':ds})
    ranges=[v['Ds'] for v in corners if v['Ds'] is not None]
    relative,rs=evaluate(row,relative_axis=True,profile=True)
    alt,ast=evaluate(row,eos=EquationOfState(anchor=-.5),profile=True)
    coarse=evaluate(row,eos=EquationOfState(omit_inner=True),profile=True)[0]
    return dict(measurement=row,nominal=central,EOS=asdict(state),rho_sensitivity=corr,
                T_at_minus_plus_one_error=[evaluate(row,temperature=t-dt),evaluate(row,temperature=t+dt)],
                shared_shifts=shifts,scale_gradient_per_sigma=derivatives,
                corner_range=[min(ranges),max(ranges)],corner_scenarios=corners,
                critical_density_axis=dict(D=rs.D,**relative),alternate_pressure=dict(P=ast.pressure,**alt),
                thinned_theta=coarse,T_over_Tc_bulk_if_box_shift_0_to_10pct=[t,1.1*t])

def output():
    all_rows=measured_rows()
    rows=[r for r in all_rows if r['c2']>0]
    excluded=[r['T_over_Tc'] for r in all_rows if r['c2']==0]
    records=[prepared(row) for row in rows]
    J=np.array([r['scale_gradient_per_sigma'] for r in records])
    joint={key:fit(sub,rho,anchor,extra_starts=6) for key,sub,rho,anchor in [
            ('baseline',rows,0.,0.),('rho_minus_0.9',rows,-.9,0.),('rho_plus_0.9',rows,.9,0.),
            ('warmer_four',rows[2:],0.,0.),('alternate_pressure',rows,0.,-.5)]}
    # Control values are read only after fitting all rows and joint calibrations.
    with zipfile.ZipFile(HERE.parent/'data'/'cambridge.zip') as z:
        author=np.loadtxt(io.BytesIO(z.read('Figure 3/Fig3b_superfluid_density.txt')),skiprows=1)
    for r in records:
        t=r['measurement']['T_over_Tc']; ix=np.flatnonzero(abs(author[:,0]*t-1)<1e-7)
        assert len(ix)==1
        r['author_Ds'],r['author_sd']=author[ix[0],2:]
    result=dict(D0_absolute=D0,Dc_weak_coupling=np.log(380/.64),records=records,
                excluded_classification_zeros=excluded,local_shared_covariance=J@J.T,
                calibration_columns=NAMES,joint_fits=joint)
    return result

def dump(data):
    path=HERE/'results.json'
    def encode(x):
        return x.tolist() if hasattr(x,'tolist') else float(x)
    path.write_text(json.dumps(data,default=encode,indent=2,allow_nan=False)+'\n')
    cols=['T_over_Tc','D','Ds','speed_profile_low','speed_profile_high','chi2_1df',
          'reference_p','Ds_relative_axis','Ds_alt_pressure','Ds_shared_fit','author_Ds']
    with (HERE/'summary.csv').open('w',newline='') as f:
        w=csv.writer(f,lineterminator='\n');w.writerow(cols)
        for r,gj in zip(data['records'],data['joint_fits']['baseline']['Ds']):
            c=r['nominal']
            assert len(c['interval95'])==1
            w.writerow([format(v,'.9g') for v in [r['measurement']['T_over_Tc'],r['EOS']['D'],
                      c['Ds'],*c['interval95'][0],c['chi2'],chi2.sf(c['chi2'],1),
                      r['critical_density_axis']['Ds'],r['alternate_pressure']['Ds'],gj,r['author_Ds']]])

if __name__=='__main__': dump(output())
