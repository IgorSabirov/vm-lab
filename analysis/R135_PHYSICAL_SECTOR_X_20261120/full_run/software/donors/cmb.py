"""Validate the original ACT/SPT data layout and reconstruct the Planck nuisance policy."""
import argparse
import json
from pathlib import Path
import re

import numpy as np
from astropy.io import fits
import yaml

from fetch import HERE, acquire


def planck_policy(files):
    policy = json.loads((HERE.parent / 'planck_pr3/nuisance.json').read_text())
    params = {}
    for name in ('planck_calib','params_calib_temp','params_calib_pol','params_TT','params_TE','params_EE'):
        for key, spec in yaml.safe_load(files['cobaya-'+name].read_bytes()).items():
            if key in params:
                raise ValueError(f'Duplicate Planck parameter {key}')
            if isinstance(spec,dict) and 'prior' in spec:
                params[key] = {'prior':spec['prior']}
            else:
                params[key] = {'fixed':spec['value'] if isinstance(spec,dict) else spec}
    sz_expr = yaml.safe_load(files['cobaya-prior_SZ'].read_bytes())['SZ']
    match = re.fullmatch(r'lambda ksz_norm, A_sz: stats\.norm\.logpdf\(ksz_norm\+([\d.]+)\*A_sz, loc=([\d.]+), scale=([\d.]+)\)',sz_expr)
    if not match:
        raise ValueError('Unrecognized joint SZ prior')
    weight,mean,sigma = map(float,match.groups())
    sz = dict(weights={'ksz_norm':1,'A_sz':weight},mean=mean,sigma=sigma)
    if params != policy['parameters'] or sz != policy['joint_SZ']:
        raise ValueError('Planck policy differs from Cobaya sources')
    return dict(varied=sum('prior' in x for x in params.values()),fixed=sum('fixed' in x for x in params.values()),
                joint_SZ=sz)


def check_covariance(matrix, n):
    if matrix.shape != (n,n) or not np.isfinite(matrix).all() or not np.allclose(matrix,matrix.T):
        raise ValueError('Invalid covariance')
    np.linalg.cholesky(matrix)


def validate(files):
    with fits.open(files['act-act_dr6_cmb_sacc.fits']) as hdus:
        bins = {k:len(hdus['data:'+k].data) for k in ('cl_00','cl_0e','cl_ee')}
        check_covariance(hdus['covariance'].data, sum(bins.values()))
        act = dict(bins=bins,covariance=list(hdus['covariance'].data.shape))
    spec = yaml.safe_load(files['spt-SPT3G_D1_TnE_lite.yaml'].read_bytes())
    bands = np.loadtxt(files['spt-'+spec['band_power_file']])
    cov = np.loadtxt(files['spt-'+spec['covariance_file']])
    expected = {name.split()[0]:n for item in spec['spectra_info'] for name,n in item.items()}
    if sum(expected.values()) != len(bands) or not np.isfinite(bands).all():
        raise ValueError('Invalid SPT bandpowers')
    check_covariance(cov, len(bands))
    window_shapes = {}
    for name,n in expected.items():
        w = np.loadtxt(files['spt-'+name+'_lxl_window_functions.txt'])
        if w.shape[1] != n+1 or not np.isfinite(w).all() or not np.all(np.diff(w[:,0])>0):
            raise ValueError('Invalid SPT windows')
        window_shapes[name] = list(w.shape)
    return dict(ACT=act,SPT=dict(bins=expected,covariance=list(cov.shape),windows=window_shapes,
                                 priors=spec['priors']),Planck=planck_policy(files))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache',type=Path,required=True)
    parser.add_argument('--offline',action='store_true')
    args = parser.parse_args()
    paths = acquire(args.cache,{'cmb_extra','planck_priors'},args.offline)
    print(json.dumps(validate(paths),indent=2))
