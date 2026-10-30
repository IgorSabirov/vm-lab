"""Offline analysis of pinned E002c GitHub exports; no time evolution.

Usage: python triplet_analyze.py --baseline-report DIR --retry-report DIR --out DIR
Each input DIR contains run.json and its files/ exports. Obtain the two reports
from the exact commits in SOURCES; run.json SHA-256 is pinned below as well.
Only the input artifacts actually used here are revalidated, not the entire
baseline experiment. The original scientific acceptance is not replaced.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

import numpy as np
from scipy.integrate import simpson

SOURCES = {
    'baseline': ('E002c_REPAIR_v001_r001', '7fd36d60044b436484e81a5e92a80163c4688b45'),
    'retry': ('E002c_IC_RETRY_v001_r001', '3839e9229ef97c230479f024d055a8507ae86fa5'),
}
RUN_HASHES = {'baseline': '8befe7fd26bd8b8763d80fc2feab55386f89f882560e81db680c8c1391444176', 'retry': 'abf8d3bffca735b75377aafa250e0a211d5bb5515925edd8f634b6a0c49c5e36'}
CASES = {'QS': ('baseline', 'QS_P05_dt005'),
         'IC': ('retry', 'RETRY_VALIDATE_0.005'),
         'RR': ('baseline', 'RR_QS_P05_dt005')}
PAIRS = [(0, 1), (1, 2), (0, 2)]
ONE = [4, 2, 1]
COHERENCES = [(1, 2), (5, 6), (1, 4), (3, 6), (2, 4)]


def pair(z):
    return [float(z.real), float(z.imag)]


def dark(mask):
    h = np.zeros((3, 3))
    for e, (i, j) in enumerate(PAIRS):
        if mask & (1 << e):
            h[i, j] = h[j, i] = 1.
    sink = np.array([[0., 0., 1.]])
    constraint = np.vstack([sink, sink @ h, sink @ h @ h])
    _, singular, vh = np.linalg.svd(constraint, full_matrices=True)
    rank = np.count_nonzero(singular > 1e-10 * max(1., singular[0]))
    basis = vh[rank:].T
    projector = basis @ basis.T
    connected = {2}
    for _ in range(3):
        connected |= {j for i in list(connected) for j in range(3) if abs(h[i, j]) > 1e-12}
    isolated = np.diag([float(i not in connected) for i in range(3)])
    return isolated, projector - isolated


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline-report', type=Path, required=True)
    parser.add_argument('--retry-report', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    roots = {'baseline': args.baseline_report, 'retry': args.retry_report}
    manifests = {}
    checked = []
    for name, root in roots.items():
        raw = (root / 'run.json').read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        assert digest == RUN_HASHES[name], ('run.json hash', name)
        run = json.loads(raw)
        assert run['run_id'] == SOURCES[name][0]
        assert run['repository'] == 'IgorSabirov/vm-lab' and run['export_errors'] == []
        assert run['job']['state'] == 'completed' and run['job']['exit_code'] == 0
        manifests[name] = run

    def read(name, path):
        b = (roots[name] / path).read_bytes()
        expected = manifests[name]['files'][path]
        digest = hashlib.sha256(b).hexdigest()
        assert len(b) == expected['bytes'] and digest == expected['sha256'], path
        checked.append({'report': name, 'path': path, 'sha256': digest, 'bytes': len(b)})
        return b

    schemas = {name: json.loads(read(name, 'files/schema.json')) for name in roots}
    assert schemas['baseline']['series'] == schemas['retry']['series']
    assert schemas['baseline']['diagnostics'] == schemas['retry']['diagnostics']
    schema = schemas['retry']
    metrics = json.loads(read('retry', 'files/metrics.json'))
    baseline_cases = {r['id']: r for r in csv.DictReader(io.StringIO(read('baseline', 'files/cases.csv').decode()))}
    retry_cases = {r['case']['id']: r['case'] for r in metrics['trajectory_summaries']}
    check_errors = {}
    results = {}
    for label, (source, case) in CASES.items():
        case_info = baseline_cases[case] if source == 'baseline' else retry_cases[case]
        assert float(case_info['dt']) == .005 and float(case_info['horizon']) == 200.
        assert float(case_info['phi_over_pi']) == 0. and float(case_info['detuning']) == 0.
        assert float(case_info['dephasing']) == .05
        arrays = {}
        for category in ('series', 'diagnostics', 'evidence'):
            with np.load(io.BytesIO(read(source, f'files/{category}/{case}.npz')), allow_pickle=False) as z:
                arrays[category] = {key: z[key] for key in z.files}
        series, diag, ev = arrays['series']['values'], arrays['diagnostics']['values'], arrays['evidence']
        si = {key: i for i, key in enumerate(schema['series'])}
        di = {key: i for i, key in enumerate(schema['diagnostics'])}
        assert np.sum(ev['time'] == 200.) == 1
        blocks = ev['blocks'][np.flatnonzero(ev['time'] == 200.)[0]]
        assert blocks.shape == (9, 8, 8)
        scalar = series[np.flatnonzero(series[:, 0] == 200.)[0]]
        diagnostic = diag[np.flatnonzero(diag[:, 0] == 200.)[0]]
        errors = [np.max(np.abs(blocks[0] - blocks[1:].sum(axis=0))),
                  abs(np.trace(blocks[0]) - 1.),
                  np.max(np.abs(blocks - blocks.conj().transpose(0, 2, 1)))]
        masks = []
        for mask, b in enumerate(blocks[1:]):
            p = float(np.trace(b).real)
            assert p > 1e-6
            i12_1 = -2 * b[1, 2].imag if mask & 2 else 0.
            i12_2 = -2 * b[5, 6].imag if mask & 2 else 0.
            i02_1 = -2 * b[1, 4].imag if mask & 4 else 0.
            i02_2 = -2 * b[3, 6].imag if mask & 4 else 0.
            h1, h2 = float(i12_1 + i02_1), float(i12_2 + i02_2)
            iso, inter = dark(mask)
            one = b[np.ix_(ONE, ONE)]
            isolated, interference = float(np.trace(one @ iso).real), float(np.trace(one @ inter).real)
            w1 = float(np.trace(one).real)
            row = {'mask': mask, 'active_edges': [e for i, e in enumerate(['01','12','02']) if mask & (1 << i)],
                   'p': p, 'h': h1+h2, 'j': (h1+h2)/p,
                   'h_N1': h1, 'h_N2': h2, 'w_N1': w1,
                   'isolated_weight_N1': isolated, 'interference_weight_N1': interference,
                   'isolated_fraction_within_N1': isolated/w1 if w1 > 1e-6 else None,
                   'interference_fraction_within_N1': interference/w1 if w1 > 1e-6 else None,
                   'rho_entries': {f'{i},{j}': pair(b[i,j]) for i,j in COHERENCES},
                   'conditional_rho_entries': {f'{i},{j}': pair(b[i,j]/p) for i,j in COHERENCES},
                   'C01': pair(b[2,4]), 'c01': pair(b[2,4]/p),
                   'abs_c01': float(abs(b[2,4])/p),
                   'current_components': list(map(float,[i12_1,i12_2,i02_1,i02_2]))}
            masks.append(row)
            errors.extend([abs(p-scalar[si[f'p_m{mask}']]),
                           abs(h1+h2-diagnostic[di[f'I12_m{mask}']]-diagnostic[di[f'I02_m{mask}']]),
                           abs(isolated-diagnostic[di[f'd_isolated_m{mask}']]),
                           abs(interference-diagnostic[di[f'd_interference_m{mask}']])])
            if mask in (6,7):
                errors.extend([abs(b[2,4]-complex(diagnostic[di[f'C01_m{mask}_re']],diagnostic[di[f'C01_m{mask}_im']])),
                               abs(b[2,4]/p-complex(diagnostic[di[f'c01_m{mask}_re']],diagnostic[di[f'c01_m{mask}_im']]))])
        total = {key: float(sum(row[key] for row in masks)) for key in
                 ('h','h_N1','h_N2','isolated_weight_N1','interference_weight_N1')}
        errors.append(abs(total['h']-scalar[si['h']]))
        min_eig = min(float(np.linalg.eigvalsh(b).min()) for b in blocks)
        assert min_eig >= -1e-8
        check_errors[label] = {'max_reconstruction_abs_error': float(max(errors)), 'minimum_block_eigenvalue':min_eig}
        assert max(errors) < 1e-10, (label, errors)
        tail = series[(series[:,0]>=190.) & (series[:,0]<=200.)]
        assert np.array_equal(tail[:,0],np.arange(190.,201.,2.))
        mean = simpson(tail,x=tail[:,0],axis=0)/10.
        total.update({f'abs_c01_m{mask}': masks[mask]['abs_c01'] for mask in (6,7)})
        results[label] = {'case':case,'integration_dt':0.005,'observation_time':200.,
                          'evidence_times':ev['time'].tolist(),
                          'extreme_times':ev['extreme_time'].tolist(),
                          'series_times_in_window':tail[:,0].tolist(),
                          'diagnostic_times_in_window':diag[(diag[:,0]>=190.)&(diag[:,0]<=200.),0].tolist(),
                          'totals_t200':total,'masks_t200':masks,
                          'unconditional_rho_entries':{f'{i},{j}':pair(blocks[0,i,j]) for i,j in COHERENCES},
                          'scalar_means_190_200':dict(zip(schema['series'],mean.tolist())),
                          'h_t200_minus_window_mean':float(total['h']-mean[si['h']]),
                          'h_range_exported_window':float(np.ptp(tail[:,si['h']]))}
    comparisons={}
    for other in ('IC','RR'):
        q, r = results['QS']['masks_t200'], results[other]['masks_t200']
        gap=results['QS']['totals_t200']['h']-results[other]['totals_t200']['h']
        bymask=[]
        for a,b in zip(q,r):
            pop=(a['p']-b['p'])*(a['j']+b['j'])/2
            cond=(a['p']+b['p'])*(a['j']-b['j'])/2
            bymask.append({'mask':a['mask'],'gap':a['h']-b['h'],'population':pop,'conditional_current':cond,
                           'gap_N1':a['h_N1']-b['h_N1'],'gap_N2':a['h_N2']-b['h_N2']})
        pop=sum(x['population'] for x in bymask);cond=sum(x['conditional_current'] for x in bymask)
        assert abs(gap-pop-cond)<1e-12
        comparisons['QS-'+other]={'gap':gap,'relative_gap_denominator_QS':gap/results['QS']['totals_t200']['h'],
          'mask_total_variation':sum(abs(a['p']-b['p']) for a,b in zip(q,r))/2,
          'population_share':pop/gap,'conditional_current_share':cond/gap,
          'N2_share':sum(x['gap_N2'] for x in bymask)/gap,'by_mask':bymask}
    runtime=manifests['retry']['job']['finished']-manifests['retry']['job']['started']
    output={'scope':'offline t=200 comparison; not reconstruction of window-averaged matrices or sector currents',
            'sources':{k:{'run_id':v[0],'report_commit':v[1],'run_json_sha256':RUN_HASHES[k]} for k,v in SOURCES.items()},
            'runtime_existing_IC_retry':{'forecast_seconds':1072.671632,'external_actual_seconds':runtime,
              'interval_seconds':[643.602979,1501.740284],'gate':'PASS'},
            'identity':'h=sum_m p_m*j_m; J=1, phi=0; sink currents from mask-weighted Im rho',
            'complex_encoding':'[real,imaginary]; rho_entries and C01 unnormalized mask blocks; c01=C01/p',
            'checked_artifacts':checked,'reconstruction_checks':check_errors,'models':results,'comparisons_t200':comparisons,
            'original_IC_status':metrics['ic_status'],'new_VM_jobs':0}
    args.out.mkdir(parents=True,exist_ok=True)
    (args.out/'findings.json').write_text(json.dumps(output,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'totals':{k:v['totals_t200'] for k,v in results.items()},
                      'checks':check_errors,'comparisons':{k:{a:b for a,b in v.items() if a!='by_mask'} for k,v in comparisons.items()},
                      'window_differences':{k:v['h_t200_minus_window_mean'] for k,v in results.items()}},indent=2))


if __name__ == '__main__':
    main()
