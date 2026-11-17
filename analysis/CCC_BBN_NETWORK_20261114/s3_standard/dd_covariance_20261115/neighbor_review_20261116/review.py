#!/usr/bin/env python3
"""Recompute the neighbor review from the frozen nine-run package; no ODE runs.

Usage in a repository checkout:
  python review.py --package /path/to/dd_covariance_20261115 --output REVIEW_NUMBERS.json
For the downloaded review inputs: --inputs /path/to/inputs.
Requires NumPy. Hash checks cover SUMMARY and all nine RESULT files.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import numpy as np

CHANNELS = ['ddHe3n', 'ddtp']
OBS = ['D_H', 'Yp', 'He3_H_late', 'Li7_H_late']
RESULT_SHA = '1ce668ca5bd1d79a128f0c1f761c1ff93ebe3464'
SOURCE_SHA = '5853977d2f2b03e9cf0b2b0cae69ada64421f8c6'

def read(path):
    return json.loads(path.read_text())

def close(x, y):
    assert math.isclose(float(x), float(y), rel_tol=2e-12, abs_tol=2e-15), (x, y)

def kappa(a):
    return float(2*a[0]*a[1]/np.dot(a, a))

def gap(a, b):
    return float(abs(a-b)/max(abs(a), abs(b)))

def observables(r):
    n, H, d, t, he3, he4, li7, be7 = r['final']
    return dict(zip(OBS, [d/H, 4*he4, (he3+t)/H, (li7+be7)/H]))

def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--inputs', type=Path)
    g.add_argument('--package', type=Path)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    root = args.inputs or args.package/'results/S3_DD_RESPONSE_20261115_r1'
    contract_path = (args.inputs or args.package)/'CONTRACT.json'
    summary, manifest = read(root/'SUMMARY.json'), read(root/'ARTIFACTS.json')
    selected = [x for x in manifest['files'] if x['path']=='SUMMARY.json' or x['path'].endswith('/RESULT.json')]
    assert len(selected)==10
    hashes = {}
    for entry in selected:
        raw = (root/entry['path']).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        assert digest==entry['sha256'] and len(raw)==entry['bytes'], entry['path']
        hashes[entry['path']] = digest
    runs = {str(p.parent.relative_to(root)): read(p) for p in root.glob('*/RESULT.json')}
    assert len(runs)==9
    baseline = runs['baseline']
    for name, r in runs.items():
        assert r['source_sha']==SOURCE_SHA and r['q_other_reactions']==0
        assert r['background_sha256']==baseline['background_sha256']
        assert r['contract_sha256']==hashlib.sha256(contract_path.read_bytes()).hexdigest()
        for key, value in observables(r).items():
            close(value, r['observables'][key])
        if name!='baseline':
            ch, sign, whole, decimal = name.split('_')
            assert r['perturbation']['channel']==ch
            close(r['perturbation']['q'], float(whole+'.'+decimal)*(1 if sign=='plus' else -1))
    out = {'result_commit': RESULT_SHA, 'source_commit': SOURCE_SHA,
           'hash_checks': hashes, 'new_integrations': 0,
           'scientific_acceptance': False, 'results': {}}
    vectors = []
    for key in OBS:
        s = summary['results'][key]
        close(observables(baseline)[key], s['baseline_observable'])
        by_step = {}
        for h in [1.0, .5]:
            suffix = str(h).replace('.', '_')
            a = np.array([(math.log(runs[f'{ch}_plus_{suffix}']['observables'][key])-
                           math.log(runs[f'{ch}_minus_{suffix}']['observables'][key]))/(2*h)
                          for ch in CHANNELS])
            for i,ch in enumerate(CHANNELS):
                close(a[i], s['derivatives'][ch][str(h)])
            norm2 = float(np.dot(a,a))
            close(kappa(a), s['by_step'][str(h)]['kappa'])
            close(norm2, s['by_step'][str(h)]['independent_quadratic_form'])
            for rho in s['rho_grid']:
                var = norm2+2*rho*a[0]*a[1]
                close(var, s['by_step'][str(h)]['correlated_quadratic_form'][str(rho)])
                close(math.sqrt(max(0,var)/norm2), s['by_step'][str(h)]['sigma_ratio'][str(rho)])
            by_step[h] = a
        big, small = by_step[1.0], by_step[.5]
        for i,ch in enumerate(CHANNELS):
            close(gap(big[i],small[i]),s['step_diagnostics'][ch]['relative_discrepancy'])
        rich = (4*small-big)/3
        coeff = (big-small)/.75
        pred25, pred125 = rich+coeff*.25**2, rich+coeff*.125**2
        out['results'][key] = {
            'a_h1': big.tolist(), 'a_h0_5': small.tolist(),
            'a_Richardson': rich.tolist(), 'kappa_h0_5': kappa(small),
            'kappa_Richardson': kappa(rich),
            'Richardson_relative_changes_percent': (100*(rich-small)/small).tolist(),
            'quadratic_model_ONLY': {
                'predicted_a_h0_25': pred25.tolist(), 'predicted_a_h0_125': pred125.tolist(),
                'predicted_gap_h0_5_to_h0_25_percent': [100*gap(a,b) for a,b in zip(small,pred25)],
                'predicted_gap_h0_25_to_h0_125_percent': [100*gap(a,b) for a,b in zip(pred25,pred125)]},
            'directional_hypothesis': s['directional_hypothesis']}
        vectors.append(small)
    J = np.array(vectors)
    def cosine(a,b):
        return float(np.dot(a,b)/(np.linalg.norm(a)*np.linalg.norm(b)))
    geometry = {'metric': 'Euclidean in declared standardized (q_ddHe3n,q_ddtp) coordinates',
                'column_cosines': {}, 'row_pairs': {}}
    for label, indices in [('all', [0,1,2,3]), ('without_Li7',[0,1,2]), ('D_and_Yp',[0,1])]:
        j = J[indices,:]
        geometry['column_cosines'][label] = cosine(j[:,0],j[:,1])
    geometry['Li7_fraction_of_column1_squared_norm'] = float(J[3,0]**2/np.dot(J[:,0],J[:,0]))
    for idx in [1,2,3]:
        pair = J[[0,idx],:]
        u = pair/np.linalg.norm(pair,axis=1)[:,None]
        cos = np.clip(cosine(pair[0],pair[1]),-1,1)
        geometry['row_pairs']['D_H_and_'+OBS[idx]] = {
            'oriented_angle_deg': math.degrees(math.acos(cos)),
            'unoriented_axis_angle_deg': math.degrees(math.acos(abs(cos))),
            'condition_number_raw': float(np.linalg.cond(pair)),
            'condition_number_unit_rows': float(np.linalg.cond(u)),
            'raw_determinant': float(np.linalg.det(pair))}
    geometry['sum_difference'] = {}
    for key,a in zip(OBS,J):
        su,di=(a[0]+a[1])/math.sqrt(2),(a[0]-a[1])/math.sqrt(2)
        geometry['sum_difference'][key] = {'sum_component':su,'difference_component':di,
            'minor_to_major_amplitude_ratio':min(abs(su),abs(di))/max(abs(su),abs(di))}
    geometry['He3_alignment_with_D_null_axis_abs_cos'] = abs(cosine(J[2],np.array([-J[0,1],J[0,0]])))
    out['geometry'] = geometry
    # Exact decomposition of the finite-window LOG derivative of a sum.
    # Components are divided by their OWN H, so proton response is included.
    decomposition = {}
    for key, species in [('He3_H_late', [('He3',4),('T',3)]),
                         ('Li7_H_late', [('Li7',6),('Be7',7)])]:
        decomposition[key] = {}
        for ch in CHANNELS:
            decomposition[key][ch] = {}
            for h in [1.,.5]:
                suffix=str(h).replace('.','_')
                plus,minus = [runs[f'{ch}_{s}_{suffix}']['final'] for s in ['plus','minus']]
                xp=np.array([plus[i]/plus[1] for _,i in species])
                xm=np.array([minus[i]/minus[1] for _,i in species])
                sp,sm = float(sum(xp)),float(sum(xm))
                logdiff = math.log(sp)-math.log(sm)
                logmean = (sp-sm)/logdiff if logdiff else sp
                contributions = (xp-xm)/(2*h*logmean)
                close(sum(contributions),summary['results'][key]['derivatives'][ch][str(h)])
                decomposition[key][ch][str(h)] = dict(zip([x[0] for x in species],contributions.tolist()))
    out['exact_finite_window_component_decomposition'] = decomposition
    y=baseline['final']
    out['endpoint_parent_fractions']={'T_in_He3_plus_T':y[3]/(y[3]+y[4]),
                                    'Be7_in_Li7_plus_Be7':y[7]/(y[6]+y[7])}
    out['Yp_absolute_delta_method_sigma'] = {
        'rho_zero': float(4*y[5]*np.linalg.norm(J[1])),
        'maximum_over_rho': float(4*y[5]*sum(abs(J[1])))}
    wall=[r['supervisor']['wall_seconds'] for name,r in runs.items() if name!='baseline']
    out['historical_perturbation_wall_seconds']={'min':min(wall),'max':max(wall),
        'mean':sum(wall)/8,'sum':sum(wall),
        'eight_run_forecast_at_same_per_run_cost':sum(wall),
        'eight_run_forecast_at_baseline_cost':8*baseline['supervisor']['wall_seconds'],
        'note':'Compute only; hardware/setup dependent, not a hard cap or admission.'}
    args.output.write_text(json.dumps(out,indent=2,allow_nan=False)+'\n')
    print('PASS: 10 artifact hashes; nine raw vectors; 16 derivatives; eight kappas; all rho tables; eight step discrepancies.')
    print(json.dumps({k:out[k] for k in ['results','geometry','exact_finite_window_component_decomposition','Yp_absolute_delta_method_sigma','historical_perturbation_wall_seconds']},indent=2))

if __name__=='__main__':
    main()
