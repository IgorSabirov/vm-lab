"""Compare source tables and propagate a declared spectral covariance on a saved BBN history."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

import numpy as np
from scipy import constants
from response import trajectory_response
from resonance import he3d_rates

HERE = Path(__file__).resolve().parent
MAP = json.loads((HERE / 'NETWORK_MAP.json').read_text()) if (HERE / 'NETWORK_MAP.json').exists() else json.loads(
    (HERE.parents[1] / 'PRIMAT_LINX_BBN_BRIDGE_20261117/NETWORK_MAP.json').read_text())
BASE = 'd503ee0f1f89c99c8560803dc46277d544ef15ba'
PDF_PIN = 'c658d7c5e007cdf2862f177b922c03362fd8603f'
RATE_T = np.array([0.2,0.3,0.5,0.8,1.0])
# de Souza et al., Table 3 (median at five explicitly selected BBN temperatures).
SOUZA = np.array([1.2778e6,5.4933e6,2.4479e7,6.4133e7,8.7989e7])
CHANNELS = ['dpHe3g','He3dap','ddHe3n','ddtp']


def git(repo, *args):
    return subprocess.check_output(['git','-C',str(repo),*args])


def pinned_files(repo, *paths):
    # Include the index and worktree in the check, not just the symbolic HEAD.
    git(repo, 'diff', '--quiet', 'HEAD', '--', *paths)


def archive_baseline(repo, target):
    prefix = 'reproductions/BBN_COSMO_20261120/results/44719756079/'
    manifest = git(repo,'show',BASE+':'+prefix+'MANIFEST.sha256').decode()
    hashes = {name.strip():sha for sha,name in (line.split(None,1) for line in manifest.splitlines())}
    for name in ['canonical.json','plasma.npz','primat.npz','rate_parameters.npz']:
        path = 'cases/baseline/'+name
        raw = git(repo,'show',BASE+':'+prefix+path)
        assert hashlib.sha256(raw).hexdigest() == hashes[path]
        (target/name).write_bytes(raw)


MOSSA = dict(coefficients_ascending=[0.2121, 0.005973, 5.449e-6, -1.656e-9],
             energy_unit='keV', S_unit='eV barn', valid_keV=[2, 2000],
             measured_keV=[32, 263], source='https://doi.org/10.1038/s41586-020-2878-4')


def thermal(t9, energy):
    # Bare p,d masses and the Mossa et al. Eq. (2) S factor, valid from 2 to 2000 keV.
    mp = constants.physical_constants['proton mass energy equivalent in MeV'][0]
    md = constants.physical_constants['deuteron mass energy equivalent in MeV'][0]
    mu = 1000*mp*md/(mp+md)
    sf = np.polynomial.polynomial.polyval(energy,MOSSA['coefficients_ascending'])*1e-3
    kt = constants.Boltzmann/constants.electron_volt*1e6*t9[:,None]
    w = sf*np.exp(-energy/kt-2*np.pi*constants.alpha*np.sqrt(mu/(2*energy)))
    de = energy[1]-energy[0]
    integral = w.sum(axis=1)*de
    factor = constants.Avogadro*1e-22*constants.c*np.sqrt(8/(np.pi*mu))
    return factor*integral/kt[:,0]**1.5, w/integral[:,None]


def tables(primat, linx):
    sources = {'primat':primat,'linx':linx}
    for key,repo in sources.items():
        assert git(repo,'rev-parse','HEAD').decode().strip() == MAP['sources'][key]['commit']
    pinned_files(primat, 'primat/network_builder.py', 'primat/data/nuclear')
    pinned_files(linx, 'linx/data/nuclear_rates/key_PRIMAT_2023')
    native_network = primat / MAP['sources']['primat']['network_path']
    native_ids = [row.split(',')[0].strip() for row in native_network.read_text().splitlines() if row.strip()]
    assert native_ids == [reaction['primat_id'] for reaction in MAP['reactions']]
    audit = {}
    for reaction in MAP['reactions']:
        key,name = reaction['linx_id'],reaction['primat_id']
        paths = [primat/'primat/data/nuclear/tables'/name/(name+'_primat.txt'),
                 linx/'linx/data/nuclear_rates/key_PRIMAT_2023'/(key+'.txt')]
        arrays = [np.loadtxt(p) for p in paths]
        assert all(x.shape[1]==3 and (np.diff(x[:,0])>0).all() for x in arrays)
        audit[key] = {'references':[[s.lstrip('# ').strip() for s in p.read_text().splitlines() if s.startswith('#')] for p in paths],
                      'table_blobs':[git(src,'hash-object',str(p.resolve())).decode().strip()
                                     for src,p in zip(sources.values(),paths)]}
        if key in ('He3dap','dpHe3g'):
            audit[key]['rates'] = [np.interp(RATE_T,x[:,0],x[:,1]).tolist() for x in arrays]
            audit[key]['uncertainty_factors'] = [np.interp(RATE_T,x[:,0],x[:,2]).tolist() for x in arrays]
    return audit


def ensemble_covariance(filters, de, spacing, ensemble, padded_keV):
    # Infinite stationary unfolded bulk, unit mean intensity in x=E/spacing.
    n = round(padded_keV/de)
    k = np.fft.rfftfreq(n,de)
    tau = spacing*k
    if ensemble=='GOE':
        spectrum = np.empty_like(tau)
        lo = tau<=1
        spectrum[lo] = 2*tau[lo]-tau[lo]*np.log1p(2*tau[lo])
        spectrum[~lo] = 2-tau[~lo]*np.log1p(2/(2*tau[~lo]-1))
    elif ensemble=='GUE':
        spectrum = np.minimum(tau,1.)
    elif ensemble=='Poisson':
        spectrum = np.ones_like(tau)
    else:
        raise ValueError(ensemble)
    fourier = de*np.fft.rfft(filters,n=n,axis=-1)
    measure = 2*spacing/padded_keV*spectrum
    measure[[0,-1]] /= 2
    cov = ((fourier*measure)@fourier.conj().T).real
    if ensemble=='Poisson':
        assert np.allclose(cov,spacing*de*filters@filters.T,rtol=2e-10,atol=1e-16)
    return cov


def project(t9, sens, step, padded, spacings):
    energy = np.arange(2+step/2,2000,step)
    _,w = thermal(t9,energy)
    kernels = sens[:,:,0]@w
    assert np.allclose(kernels.sum(axis=1)*step,sens[:,:,0].sum(axis=1))
    _,windows = thermal(np.array([0.5,0.8]),energy)
    filters = np.vstack((windows,kernels))
    output = {}
    for spacing in spacings:
        row = {}
        for name in ('GOE','GUE','Poisson'):
            c = ensemble_covariance(filters,step,spacing,name,padded)
            assert np.linalg.eigvalsh(c).min()>-1e-14
            row[name] = {'sd_unit_fraction':np.sqrt(np.diag(c)).tolist(),
                         'cov_ln_DH_ln_Yp_unit_fraction':c[2:,2:].tolist()}
        output[str(spacing)] = row
    return output


def atlas_data(atlas):
    assert git(atlas,'rev-parse','HEAD').decode().strip()==PDF_PIN
    pdf=atlas/'Sensitivity_Summary_Tables/Sensitivity_Summary_Tables - Tau_n_Weak_Norm.pdf'
    pinned_files(atlas, str(pdf.relative_to(atlas)))
    text=subprocess.check_output(['pdftotext','-layout',str(pdf),'-']).decode().splitlines()
    output={}
    for channel in ['dpHe3g','He3dap','Be7nLi7p']:
        idx=next(i for i,s in enumerate(text) if s.strip().startswith('p_'+channel+' ') and 'primat' in s)
        output[channel]={}
        for i,obs in enumerate(['Yp','DH']):
            row=text[idx+i].split(); j=row.index(obs)
            ref,deriv=map(float,row[j+1:j+3])
            obs_error={'Yp':0.003,'DH':0.029}[obs]  # DH in units 1e-5
            output[channel][obs]={'fiducial':ref,'per_q':deriv,'dlnO_dq':deriv/ref,
                'absolute_shift_over_observational_sigma':abs(deriv)/obs_error,
                'flatness_flag':row[-1].endswith('*')}
    return output


def compare_saved(actual, expected, path="root"):
    if isinstance(actual, dict):
        assert actual.keys() == expected.keys(), path
        for key in actual:
            compare_saved(actual[key], expected[key], f"{path}.{key}")
    elif isinstance(actual, list):
        assert len(actual) == len(expected), path
        for i, (left, right) in enumerate(zip(actual, expected)):
            compare_saved(left, right, f"{path}[{i}]")
    elif isinstance(actual, float):
        np.testing.assert_allclose(actual, expected, rtol=1e-5, atol=1e-11, err_msg=path)
    else:
        assert actual == expected, path


def main():
    p=argparse.ArgumentParser()
    for key in ['vm_lab','primat','linx','atlas']:
        p.add_argument('--'+key,required=True,type=Path)
    p.add_argument('--check', action='store_true', help='Compare with the archived CHECKS.json')
    a=p.parse_args()
    audit=tables(a.primat,a.linx)
    with tempfile.TemporaryDirectory() as tmp:
        folder=Path(tmp)
        archive_baseline(a.vm_lab,folder)
        t9,sens,q=trajectory_response(a.primat,folder,4,2.)
        tc,sc,_=trajectory_response(a.primat,folder,2,2.)
        th,sh,_=trajectory_response(a.primat,folder,4,2.2)
        with np.load(folder/'primat.npz') as arr:
            y = arr['Y'][-1]
    shape=project(t9,sens,0.5,32768,[5,10,20])
    coarse=project(tc,sc,1,16384,[10])
    wide=project(th,sh,0.5,32768,[10])
    def sd(out):
        return np.asarray(out['10']['GOE']['sd_unit_fraction'])
    grid_changes=np.abs(sd(coarse)/sd(shape)-1)
    cutoff_changes=np.abs(sd(wide)/sd(shape)-1)
    assert max(grid_changes)<0.015 and max(cutoff_changes)<0.01
    energies=np.arange(2.25,2000,.5)
    empirical,w=thermal(RATE_T,energies)
    point_rates = he3d_rates(RATE_T)
    quadrature_error = np.abs(he3d_rates(RATE_T, 256, 0.0005, 3.) / point_rates - 1)
    assert quadrature_error.max() < 1e-8
    assert np.max(np.abs(point_rates/SOUZA - 1)) < 0.003
    assert np.max(np.abs(np.array(audit['He3dap']['rates'])/SOUZA - 1)) < 0.0003
    assert np.max(np.abs(empirical/np.array(audit['dpHe3g']['rates'][1]) - 1)) < 0.003
    def rows(x):
        return {channel: values.tolist() for channel, values in zip(CHANNELS, x.T)}
    computed_q=np.einsum('ijk,jk->ik',sens,q)
    ref_q=np.array([[-0.00593897,-0.00498537],[0.00006648,0.00005778]])
    dd_error=np.abs(computed_q[:,2:]/ref_q-1)
    assert dd_error.max()<0.03
    example_fraction = 0.10
    obs_sigma = np.array([0.29e-6, 0.003])
    base = np.array([y[2]/y[1], 4*y[5]])
    ratios = {spacing: {ensemble: (example_fraction * base * np.array(record['sd_unit_fraction'][2:]) / obs_sigma).tolist()
                        for ensemble, record in group.items()} for spacing, group in shape.items()}
    result = dict(trajectory_commit=BASE, donor_commits={name: MAP['sources'][name]['commit'] for name in ('primat', 'linx')},
        atlas_commit=PDF_PIN, Mossa_S_factor=MOSSA, example_fraction=example_fraction, observational_sigma=obs_sigma.tolist(),
        example_sd_over_observational_sigma=ratios, T9=RATE_T.tolist(),table_audit=audit,
        He3dap_paper=SOUZA.tolist(), He3dap_point_Rmatrix=point_rates.tolist(),
        He3dap_point_quadrature_change=quadrature_error.tolist(),dp_Mossa_rates=empirical.tolist(),
        dp_Mossa_fraction_32_263_keV=(w[:,(energies>=32)&(energies<=263)].sum(axis=1)*.5).tolist(),
        output_order=['D/H','Yp'],baseline=[y[2]/y[1],4*y[5]],
        dlnO_dln_rate=rows(sens.sum(axis=1)),dlnO_dq=rows(computed_q),
        atlas=atlas_data(a.atlas),dd_relative_error=dd_error.tolist(),
        projected_order=['rate at T9=0.5','rate at T9=0.8','D/H','Yp'],
        projected=shape,grid_relative_change=grid_changes.tolist(),
        upper_T9_relative_change=cutoff_changes.tolist())
    if a.check:
        compare_saved(result, json.loads((HERE / 'CHECKS.json').read_text()))
        print('R141 BBN replay passed')
    else:
        print(json.dumps(result, indent=2, allow_nan=False))


if __name__=='__main__':
    main()
