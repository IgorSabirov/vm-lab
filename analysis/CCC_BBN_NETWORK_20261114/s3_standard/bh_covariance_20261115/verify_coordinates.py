"""Independent Decimal audit of the disputed laboratory modes and S_eta reuse.

Uses only Python's standard library; no import of verify_connection.py, no
NumPy, no BBN rerun. Read existing repository artifacts in place. A flat local
input mirror can be supplied with --local-inputs for source-content auditing.
"""
import argparse
from decimal import Decimal as D, localcontext
import hashlib
import json
from pathlib import Path
import platform
import time

started = time.perf_counter()
parser = argparse.ArgumentParser()
parser.add_argument('--local-inputs', type=Path)
args = parser.parse_args()
here = Path(__file__).resolve().parent
root = here.parents[1]
eta = root / 's_eta/results/S_ETA_20261114_r1'
paths = {
    'LEONARD_INPUT.json': here / 'LEONARD_INPUT.json',
    'ORIGINAL_CHECKS.json': here / 'CHECKS.json',
    'S3_RESULT.json': root / 's3_input_audit/results/RESULT.json',
    'ETA_ARTIFACTS.json': eta / 'ARTIFACTS.json',
    'ETA_RESPONSE.json': eta / 'RESPONSE.json',
    'ETA_LOW_INPUT.json': eta / 'ETA_INPUTS/ETA_LOW.json',
    'ETA_HIGH_INPUT.json': eta / 'ETA_INPUTS/ETA_HIGH.json',
    'ETA_LOW_RESULT.json': eta / 'runs/ETA_LOW/RESULT.json',
    'ETA_HIGH_RESULT.json': eta / 'runs/ETA_HIGH/RESULT.json',
}
if args.local_inputs:
    paths = {name: args.local_inputs/name for name in paths}
raw = {name: path.read_bytes() for name, path in paths.items()}
hashes = {name: hashlib.sha256(value).hexdigest() for name, value in raw.items()}
assert hashes['LEONARD_INPUT.json'] == '806b63b8369294a2a1eafbb6d4b19b15ad076fb07e532d1c73971d89569a65ad'
assert hashes['ORIGINAL_CHECKS.json'] == '9b3f0471ee200caf0d9604d9d28ea7b60515eda6ecb4a79939edca649b317615'
assert hashes['S3_RESULT.json'] == '48a81ecf8734e04426d4b3463a0e68deb20c12e8865459272fcdbae4d9858f02'
assert hashes['ETA_ARTIFACTS.json'] == '6ee7a04d208a2232a2b03d4e8603d5073a9c36aa3dd4b09a683de972fad2787e'
objs = {name: json.loads(value, parse_float=D) for name, value in raw.items()}
for name, member in {
    'ETA_RESPONSE.json': 'RESPONSE.json',
    'ETA_LOW_INPUT.json': 'ETA_INPUTS/ETA_LOW.json',
    'ETA_HIGH_INPUT.json': 'ETA_INPUTS/ETA_HIGH.json',
    'ETA_LOW_RESULT.json': 'runs/ETA_LOW/RESULT.json',
    'ETA_HIGH_RESULT.json': 'runs/ETA_HIGH/RESULT.json',
}.items():
    assert hashes[name] == objs['ETA_ARTIFACTS.json']['files'][member]['sha256']

with localcontext() as ctx:
    ctx.prec = 50
    data = objs['LEONARD_INPUT.json']
    M = data['covariance_a0']
    A, B, C = M[7][7], M[15][15], M[7][15]
    p, n = data['cross_section_mb'][7], data['cross_section_mb'][15]
    assert data['lab_energy_keV'][7] == D('112.2')
    assert (A,B,C,p,n) == (D('.0046104'),D('.0053203'),D('.0049029'),D('19.77'),D('21.07'))
    rho = C/(A*B).sqrt()
    def mode(vp, vn, c):
        r = 2*c/(vp+vn)
        plus, minus = (1+r).sqrt(), (1-r).sqrt()
        return {'diagonal_sum':vp+vn, 'cross_covariance':c,
                'rho_effective':r, 'plus_sd_ratio':plus,
                'minus_sd_ratio':minus, 'minus_compression':1/minus}
    absolute = mode(A,B,C)
    # Common (4*pi)^2 factor cancels from the SD ratios.
    logarithmic = mode(A/p**2, B/n**2, C/(p*n))
    reference = objs['ORIGINAL_CHECKS.json']['laboratory_modes_without_extra_1pct_scale'][7]
    assert abs(logarithmic['plus_sd_ratio']-reference['sd_geometric_mean_log_full_over_independent']) < D('1e-14')
    assert abs(logarithmic['minus_sd_ratio']-reference['sd_channel_ratio_log_full_over_independent']) < D('1e-14')
    assert absolute['plus_sd_ratio'].quantize(D('.000001')) == D('1.409760')
    assert absolute['minus_sd_ratio'].quantize(D('.000001')) == D('.112148')
    assert logarithmic['rho_effective'] <= rho  # No inferred correlation > rho.

    lo = objs['ETA_LOW_RESULT.json']['result']
    hi = objs['ETA_HIGH_RESULT.json']['result']
    parent = objs['S3_RESULT.json']['rows']
    response = objs['ETA_RESPONSE.json']['observables']
    for key in ['YPBBN','DoH']:
        assert lo[key] == response[key]['low'] and hi[key] == response[key]['high']
        assert parent[key]['baseline'] == response[key]['baseline']
    eta_lo = objs['ETA_LOW_INPUT.json']['eta_resolved']
    eta_hi = objs['ETA_HIGH_INPUT.json']['eta_resolved']
    span = (eta_hi/eta_lo).ln()
    a = parent['YPBBN']['baseline']*(hi['YPBBN']/lo['YPBBN']).ln()/span
    b = (hi['DoH']/lo['DoH']).ln()/span
    stored_a = parent['YPBBN']['J_dY_dlneta_secant']
    stored_b = parent['DoH']['J_dY_dlneta_secant']/parent['DoH']['baseline']
    assert abs(a-stored_a) < D('1e-13') and abs(b-stored_b) < D('1e-12')
    out = {
        'status':'DISCREPANCY_RESOLVED_DIFFERENT_COORDINATES',
        'reviewed_commit':'dc393897eb63886ab330545959e9cdae9a90fd11',
        'python':platform.python_version(),'decimal_precision':ctx.prec,
        'input_sha256':hashes,'lab_energy_keV':D('112.2'),
        'raw_covariance_entries_a0_squared':{'A':A,'B':B,'C':C},
        'central_cross_sections_mb':{'p':p,'n':n},'rho':rho,
        'absolute_coordinates':absolute,
        'log_coordinates_common_4pi_squared_factor_omitted':logarithmic,
        'eta_response_rebuilt_from_completed_run_outputs':{
            'eta_low':eta_lo,'eta_high':eta_hi,
            'Yp_low':lo['YPBBN'],'Yp_high':hi['YPBBN'],
            'DoH_low':lo['DoH'],'DoH_high':hi['DoH'],
            'a_baseline_times_log_secant':a,'b_log_secant':b,
            'a_difference_from_published':a-stored_a,
            'b_difference_from_published':b-stored_b,
            'a_direct_Yp_secant_different_estimator':(hi['YPBBN']-lo['YPBBN'])/span,
            'RD_neutrino_coefficient_positive_three_quarters_times_b':D('.75')*b,
        },
        'BBN_executed':False,'GP_fitted':False,'scientific_acceptance':False,
        'wall_seconds':time.perf_counter()-started,
    }
print(json.dumps(out, default=str, ensure_ascii=False, indent=2))
