"""Resolve changes in sound and temperature with arbitrary between-row correlation."""
import json
import numpy as np
from scipy.constants import hbar
from inversion import HERE, MASS, evaluate

def difference(a,ea,b,eb):
    d=abs(a-b)
    low,high=abs(ea-eb),ea+eb
    return dict(delta=d,sd_at_zero_correlation=np.hypot(ea,eb),
                sd_all_correlation=[low,high],z_all_correlation=[d/high,d/low if low else None])

def compute(data):
    near=[r['measurement'] for r in data['records'][-2:]]
    left,right=near
    joint=data['joint_fits']['baseline']
    fixed=[evaluate(r['measurement'],scales=joint['relative_scales'],profile=True)[0]['chi2']
           for r in data['records']]
    q=np.pi/33e-6
    cB=hbar*np.sqrt(3.e12*.64)/MASS
    return dict(near_T=[left['T_over_Tc'],right['T_over_Tc']],
                temperature=difference(left['T_over_Tc'],left['err_T'],right['T_over_Tc'],right['err_T']),
                second_speed=difference(left['c2'],left['err_c2'],right['c2'],right['err_c2']),
                nominal_33um_q_per_m=q,nominal_frequency_B_Hz=q*cB/(2*np.pi),
                indicative_near_second_f_Hz=[r['c2']*q*cB/(2*np.pi) for r in near],
                reweighted_shared_scales_fixed_row_temperatures_chi2=fixed,
                global_calibration_chi2=joint['chi2_calibration'],
                fitted_near_T=joint['fitted_T_over_Tc'][-2:],
                finite_size_scenario_near_T=[r['T_over_Tc']*1.10 for r in near],
                static_jump_status='unresolved')

if __name__=='__main__':
    d=compute(json.loads((HERE/'results.json').read_text()))
    (HERE/'resolution.json').write_text(json.dumps(d,indent=2,allow_nan=False)+'\n')
