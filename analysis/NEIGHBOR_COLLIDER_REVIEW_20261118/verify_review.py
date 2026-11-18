"""Conditional arithmetic/linear-algebra checks; no HNL, BBN or LINX solver run."""
from fractions import Fraction as F
from pathlib import Path
import hashlib
import json
import math
import time

GF = 1.1663787e-5  # GeV^-2, supplied review convention
HBAR = 6.582119569e-25  # GeV s
K = GF**2 / (96 * math.pi**3)


def lifetime(mass_GeV, mixing_squared, channel_factor=10):
    if not 0 < mass_GeV < 80.4 or mixing_squared <= 0 or channel_factor <= 0:
        raise ValueError('Contact-width estimate only; W threshold is outside its domain')
    return HBAR / (channel_factor * K * mass_GeV**5 * mixing_squared)


def run():
    start = time.perf_counter()
    rows = []
    for mass, u2 in ((1.6, 1e-6), (5.5, 1e-6), (20., 5e-6)):
        tau = lifetime(mass, u2)
        rows.append({'mass_GeV': mass, 'illustrative_U2_not_measured_contour': u2,
                     'tau_s_C10': tau, 'ctau_cm': 2.99792458e10 * tau,
                     'constant_gstar_10_75_temperature_GeV': math.sqrt(.738 / tau) / 1000})
    # Internal contradiction in the supplied constant-g* estimate, not a prediction
    # of a physical decay epoch: proper lifetime != cosmological production time.
    assert rows[0]['constant_gstar_10_75_temperature_GeV'] < 3
    assert rows[1]['constant_gstar_10_75_temperature_GeV'] < 100
    assert math.isclose(lifetime(1.6, 1e-6, 20), lifetime(1.6, 1e-6, 10) / 2)
    try:
        lifetime(100, 1e-6)
    except ValueError:
        threshold_rejected = True
    else:
        raise AssertionError('Invalid contact-width point accepted')

    # Exact counterexample to "one q per reaction forces independence".
    # For independent unit-variance z, q=Lz has nonzero off-diagonal covariance.
    L = [[F(1), F(0)], [F(3, 5), F(4, 5)]]
    C = [[sum(L[i][k] * L[j][k] for k in range(2)) for j in range(2)] for i in range(2)]
    assert C == [[F(1), F(3, 5)], [F(3, 5), F(1)]]
    # Single amplitude cannot express arbitrary temperature-shape uncertainty.
    s = [F(1), F(2)]
    temp_cov = [[a*b for b in s] for a in s]
    assert temp_cov[0][0]*temp_cov[1][1] - temp_cov[0][1]*temp_cov[1][0] == 0

    sigma_nue = GF**2 * (2 * .51099895e-3 * 10e-3) / math.pi * .389379e-27
    sigma_nucleon = .68e-38 * 228
    ratio = sigma_nucleon / sigma_nue
    assert 6 < math.log10(ratio) < 8  # about seven, not nine orders
    return {'schema':'vm-lab-neighbor-conditional-checks-v1', 'status':'PASS',
            'mode':'CONDITIONAL_ARITHMETIC_AND_EXACT_LINEAR_ALGEBRA',
            'physical_solver_runs':0, 'LINX_executed':False,
            'conditional_width':{'C':10, 'K_GeV_minus4':K, 'rows':rows,
              'm100GeV_rejected':threshold_rejected,
              'limits':['C is an assumed constant, not a calculated flavor/threshold-dependent width',
                        'Points are illustrative, not digitized collider contours',
                        'Constant g*=10.75 temperatures are internal consistency checks, not physical predictions',
                        'Production, boosts, inverse reactions and thermalization not calculated']},
            'correlated_q':{'L':[[str(v) for v in row] for row in L],
                            'covariance':[[str(v) for v in row] for row in C],
                            'independence_forced_by_vector_API':False,
                            'one_amplitude_temperature_covariance_rank':1,
                            'full_rate_posterior_reconstructed':False},
            'cross_section_scale_check':{'sigma_nue_cm2':sigma_nue,
                'sigma_nucleon_cm2':sigma_nucleon,'ratio':ratio,'log10_ratio':math.log10(ratio),
                'scope':'Dimensional estimate with omitted coupling/flux/target corrections; not an SND fit or measurement comparison'},
            'elapsed_seconds':time.perf_counter()-start,
            'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


if __name__ == '__main__':
    result = run()
    Path(__file__).with_name('CHECKS.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
