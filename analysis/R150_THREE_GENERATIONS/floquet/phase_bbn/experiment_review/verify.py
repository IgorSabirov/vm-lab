"""Check packaged files, numeric contrasts, trajectories and reproducibility of the two main runs."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'results'


def read(path):
    return json.loads(path.read_text())


def verify_summary(path, reference):
    run = read(path)
    saved = read(reference)
    assert run['rtol'] == saved['rtol'] and run['outputs'] == saved['outputs']
    assert run['cases'].keys() == saved['cases'].keys() and len(run['cases']) == 17
    assert max(r['max_baryon_error'] for r in run['cases'].values()) < 1e-9
    for obs in run['signal'].values():
        assert all(record['pre_max_abs'] == 0 for record in obs.values())
    assert run['signal']['f1r1']['p_periodic']['peak']['value'] < -5e-8
    assert abs(run['signal']['f1r0']['p_periodic']['final']) < 1e-10
    placebo = run['placebo']['decorrelated']
    assert abs(placebo['correlation_nD']) < .05 and abs(placebo['original_correlation_nD']) > .4
    assert max(abs(x) for x in run['prescribed_minus_live_ln']['pulse']) < 1e-6
    outputs = run['outputs']
    def vector(label, arm):
        return np.log([run['cases'][f'{label}_{arm}'][key] for key in outputs])
    modes = {'intervention_on_mixed_ln': ('f1r1','f1r0','f0r1','f0r0'),
             'intervention_on_graph_interaction_ln': ('f1r1','f1r0','lambda0','zero_contact')}
    for key, labels in modes.items():
        def contrast(arm):
            a,b,c,d = [vector(label, arm) for label in labels]
            return a-b-c+d
        np.testing.assert_allclose(contrast('pulse')-contrast('off'),run[key],rtol=0,atol=2e-14)
        # Different BLAS/ODE versions can shift the smallest graph residual.
        np.testing.assert_allclose(run[key],saved[key],rtol=.005,atol=8e-8)
    return run


def check_package():
    for line in (ROOT/'SHA256SUMS').read_text().splitlines():
        expected, filename = line.split('  ',1)
        assert hashlib.sha256((ROOT/filename).read_bytes()).hexdigest() == expected, filename
    fine = read(DATA/'e6_fine.json')
    with ZipFile(DATA/'e6_trajectories.zip') as archive:
        assert archive.testzip() is None
        def history(name):
            with archive.open(name+'.csv') as file:
                return list(csv.DictReader(io.TextIOWrapper(file)))
        for branch in fine['signal']:
            baseline, pulse = history(branch+'_off'), history(branch+'_pulse')
            assert len(baseline) == len(pulse)
            for key, limits in fine['signal'][branch].items():
                T = np.array([float(a['Tgamma_MeV']) for a in baseline])
                delta = np.array([float(b[key])-float(a[key]) for a,b in zip(baseline,pulse)])
                np.testing.assert_allclose(max(abs(delta[T>.08])),limits['pre_max_abs'],atol=1e-17)
                np.testing.assert_allclose(max(abs(delta)),abs(limits['peak']['value']),atol=1e-17)
                np.testing.assert_allclose(delta[-1],limits['final'],atol=1e-17)
    for tag in ['conv_1','conv_2']:
        doc = read(DATA/(tag+'.json'))
        for mode in ['off','pulse']:
            arrays = [np.log([doc['cases'][label+'_'+mode][k] for k in doc['outputs']])
                      for label in ['coupled','mediated','self_only','zero_contact']]
            a,b,c,d = arrays
            np.testing.assert_allclose(a-b-c+d,doc['graph_interaction'][mode],atol=2e-14)
        np.testing.assert_allclose(np.subtract(doc['graph_interaction']['pulse'],doc['graph_interaction']['off']),
                                   doc['intervention_on_graph_interaction_ln'],atol=2e-14)
    for filename in ['weak_results','weak_refined']:
        doc = read(DATA/(filename+'.json'))
        for name in ['binding_only','unification','strong_control']:
            assert abs(doc[name+'_comparison']['D_relative_mismatch']) < 5e-7


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--base',type=Path,default=DATA/'e6_base.json')
    parser.add_argument('--fine',type=Path,default=DATA/'e6_fine.json')
    args = parser.parse_args()
    check_package()
    verify_summary(args.base,DATA/'e6_base.json')
    verify_summary(args.fine,DATA/'e6_fine.json')
    print('OK: checksums, paired histories, null controls, published contrasts and D/H fits')
