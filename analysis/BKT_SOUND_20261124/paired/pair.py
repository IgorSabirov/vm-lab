"""Audit reduced thermometry in the two near-critical Cambridge rows.

With --blocks, analyse one experimental A/B pair per independent calibration block.
Temperatures must come from an independent thermometer or a calibrated trap setting.
"""
import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
from statistics import NormalDist
from zipfile import ZipFile
import numpy as np
from scipy.constants import hbar, k as kB, atomic_mass
from scipy.stats import t as student

HERE = Path(__file__).resolve().parent
KEYS = (.990300956, 1.000308815)
Z95 = NormalDist().inv_cdf(.975)
FIG3 = 'Figure 3/Fig3a_'
MASS = 38.9637064864*atomic_mass

def locate(table, target):
    found = [row for row in table if abs(row[0]-target)<5e-9]
    if len(found)!=1:
        raise ValueError(f'Expected exactly one T/Tc match for {target}')
    return found[0]

def archive_pair():
    archive = HERE.parent/'data'/'cambridge.zip'
    manifest = json.loads((archive.parent/'manifest.json').read_text())
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=manifest['archive_sha256']:
        raise ValueError('Cambridge archive digest changed')
    with ZipFile(archive) as z:
        def table(name):
            return np.loadtxt(io.BytesIO(z.read(name)),skiprows=1)
        fast=table(FIG3+'firstSound_redData.txt')
        slow=table(FIG3+'secondSound_blueData.txt')
        weights=table('Figure 2/Fig2c_f2_BottomPanel.txt')
        result=[]
        for target in KEYS:
            f,s,w=[locate(a,target) for a in (fast,slow,weights)]
            if not np.allclose(f[:2],s[:2],rtol=0,atol=1e-8):
                raise ValueError('The marginal temperature estimates differ between sound tables')
            result.append(dict(t=f[0],dt=f[1],u1=f[2],du1=f[3],u2=s[2],du2=s[3],f2=w[2]))
    return result

def row_model(row):
    # Statistical sensitivity in the thesis: t proportional to 1/n, u to 1/sqrt(n),
    # at fixed nominal T, g and density-independent dimensional speeds.
    temp,err=row['t'],row['dt']
    values={}
    for j in (1,2):
        u,du=row[f'u{j}'],row[f'du{j}']
        cov=u*err**2/(2*temp)
        variance=du**2/temp-(u*err)**2/(4*temp**3)
        if variance<0:
            raise ValueError('Incompatible density contribution to marginal speed variance')
        values[f'mode{j}']=dict(t_u_cov=cov,t_u_corr=cov/(err*du),
                               u_over_sqrt_t=u/math.sqrt(temp),
                               conditional_sd=math.sqrt(variance))
    return values

def audit():
    a,b=archive_pair()
    delta=b['t']-a['t']
    best_sd=abs(b['dt']-a['dt'])
    worst_sd=b['dt']+a['dt']
    sd_needed=delta/Z95
    required_rho=(a['dt']**2+b['dt']**2-sd_needed**2)/(2*a['dt']*b['dt'])
    ratio=b['t']/a['t']
    ma,mb=map(row_model,(a,b))
    qa,qb=ma['mode2'],mb['mode2']
    dw=qa['u_over_sqrt_t']-qb['u_over_sqrt_t']
    return dict(rows=[a,b],reduced_delta=delta,common_g_t_ratio=ratio,
                crossing_density_ratio=1/ratio,
                examples_TB_over_TA={str(nratio):ratio*nratio for nratio in [1.,1/ratio,.98]},
                sd_range=[best_sd,worst_sd],z_max=delta/best_sd,
                best_case_95_interval=[delta-Z95*best_sd,delta+Z95*best_sd],
                required_rho_for_95=required_rho,strict_max_sd_delta_for_95=sd_needed,
                common_sd_independent_for_95=sd_needed/math.sqrt(2),
                within_row_density_sensitivity=[ma,mb],
                density_cancelled_sound_difference_A_minus_B=dw,
                density_model_lower_z_over_all_between_row_correlations=dw/(qa['conditional_sd']+qb['conditional_sd']),
                reduced_order='unresolved_95',absolute_order='unidentified_without_density_ratio_or_direct_T',
                nominal_geometry_q_per_m={str(L):math.pi/(L*1e-6) for L in [23,33]})

def measured_blocks(path,g):
    if not math.isfinite(g) or not 0<g<380:
        raise ValueError('Positive coupling with positive log(380/g) is required')
    with Path(path).open(newline='') as f:
        rows=list(csv.DictReader(f))
    cols=['T_A_nK','n_A_per_um2','T_B_nK','n_B_per_um2']
    if len(rows)<2:
        raise ValueError('At least two independent paired blocks are required')
    ids=[r['block_id'].strip() for r in rows]
    if not all(ids) or len(set(ids))!=len(ids):
        raise ValueError('One unique nonempty ID per genuine independent pair is required')
    vals=np.array([[float(r[k]) for k in cols] for r in rows])
    if not np.isfinite(vals).all() or np.any(vals<=0):
        raise ValueError('Temperatures and densities must be finite and positive')
    ta,na,tb,nb=vals.T
    coefficient=MASS*kB*1e-9*math.log(380/g)/(2*math.pi*hbar**2*1e12)
    def estimate(d):
        mean=float(d.mean()); se=float(d.std(ddof=1)/math.sqrt(len(d)))
        width=float(student.ppf(.975,len(d)-1))*se
        return dict(mean_B_minus_A=mean,se_between_blocks=se,ci95=[mean-width,mean+width])
    return dict(independent_blocks=len(ids),g_common=g,temperature_nK=estimate(tb-ta),
                reduced_temperature=estimate(coefficient*(tb/nb-ta/na)),
                model='Equal block weights. Paired Student intervals for independent block differences; common scale and differential systematics external.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--blocks',type=Path)
    p.add_argument('--g',type=float,default=.64)
    args=p.parse_args()
    result=measured_blocks(args.blocks,args.g) if args.blocks else audit()
    print(json.dumps(result,indent=2,allow_nan=False))
