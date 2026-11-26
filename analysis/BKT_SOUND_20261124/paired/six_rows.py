"""Descriptive contrasts of Cambridge summary rows, with unknown covariances.

Run from any directory. The reported error bounds use published marginal
standard errors and first-order propagation for the ratio of the two modes.
"""
import csv
import json
import math
from pathlib import Path
from statistics import NormalDist

ROOT = Path(__file__).resolve().parents[1]


def read_table(path):
    with path.open() as stream:
        return list(csv.DictReader(stream))


def compare():
    measurements = read_table(ROOT / 'results' / 'THERMO_INPUTS.csv')
    inversion = read_table(ROOT / 'eos' / 'summary.csv')
    rows = []
    for data in measurements:
        if data['spectral_status'] != 'two_sound_speeds':
            continue
        t = float(data['T_over_Tc'])
        matched = [item for item in inversion
                   if abs(float(item['T_over_Tc']) - t) < 1e-8]
        if len(matched) != 1:
            raise ValueError(f'No unique EOS match for {t}')
        eos = matched[0]
        u1, u2, s1, s2 = (float(data[k]) for k in ('c1', 'c2', 'err_c1', 'err_c2'))
        ratio = u2 / u1
        # Triangle bounds for the SD of a linear combination at arbitrary correlation.
        rows.append(dict(t=t, u1=u1, u2=u2, f2=float(data['author_f2']),
                         sf2=float(data['err_f2']), st=float(data['err_T']), su2=s2,
                         ratio=ratio, ratio_sd_max=(s2 + ratio*s1) / u1,
                         Ds=float(eos['Ds']), Ds_shared=float(eos['Ds_shared_fit']),
                         Ds_alt_pressure=float(eos['Ds_alt_pressure']),
                         Ds_relative_axis=float(eos['Ds_relative_axis'])))
    if len(rows) != len(inversion) or len({r['t'] for r in rows}) != len(rows):
        raise ValueError('Unmatched or duplicate temperatures')
    rows.sort(key=lambda r: r['t'])
    a, b = rows[-2:]
    dt = b['t'] - a['t']
    sd_min = abs(b['st'] - a['st'])
    critical = NormalDist().inv_cdf(0.975)
    sd_target = dt / critical
    eps_g_log = (.03/.64) / math.log(380/.64)
    fixed_scale = math.hypot(.15, .10, .047, .021)  # Proposal scenario, not an estimate.
    def lower_z(k, sk):
        return abs(a[k] - b[k]) / (a[sk] + b[sk])
    return dict(rows=rows, reduced_delta=dt, reduced_sd_min=sd_min,
                reduced_z_max=dt/sd_min, reduced_sd_target=sd_target,
                per_row_equal_independent=sd_target/math.sqrt(2),
                per_row_example_with_scale=math.sqrt(sd_target**2-(dt*fixed_scale)**2)/math.sqrt(2),
                coupling_log_fractional_sd=eps_g_log,
                f2_ratio=a['f2']/b['f2'], f2_min_z=lower_z('f2','sf2'),
                u2_min_z=lower_z('u2','su2'), mode_ratio_min_z_linear=lower_z('ratio','ratio_sd_max'),
                mode_ratio_min_z_first_last_linear=abs(rows[0]['ratio']-b['ratio']) /
                (rows[0]['ratio_sd_max']+b['ratio_sd_max']))


if __name__ == '__main__':
    print(json.dumps(compare(), indent=2, allow_nan=False))
