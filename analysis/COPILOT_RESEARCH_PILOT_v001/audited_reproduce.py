#!/usr/bin/env python3
"""Reanalyse published E002c data. No evolution, fitting, VM or network access."""
from pathlib import Path
import csv
import hashlib
import json
import numpy as np

ROOT = Path(__file__).resolve().parent
COMMIT = '7fd36d60044b436484e81a5e92a80163c4688b45'
SECTORS = {1: [1, 2, 4], 2: [3, 5, 6]}

def read_json(name):
    return json.loads((ROOT / name).read_text())

def validate_file(relative, manifest):
    data = (ROOT / 'source' / relative).read_bytes()
    expected = manifest['files']['files/' + relative]
    assert len(data) == expected['bytes'], relative
    assert hashlib.sha256(data).hexdigest() == expected['sha256'], relative

def rates(jumps):
    return sum(0.5 * (v[:, None] - v[None, :])**2 for v in jumps)

def check_controls():
    # Node-major order, edge basis (01,12,02), qutrit value 2 = L.
    masks = []
    for e in range(27):
        digits = (e // 9, (e // 3) % 3, e % 3)
        masks.append(sum((1 << k) for k, value in enumerate(digits) if value == 2))
    target, control = [], []
    expected = np.zeros((216, 216))
    for mask, a, b in [(2, 5, 6), (4, 3, 6)]:
        minus, plus = np.zeros(216), np.zeros(216)
        aa, bb = [], []
        for e, m in enumerate(masks):
            if m == mask:
                ia, ib = 27*a + e, 27*b + e
                minus[ia], minus[ib] = 1, -1
                plus[ia], plus[ib] = 1, 1
                aa.append(ia); bb.append(ib)
        expected[np.ix_(aa, bb)] += 2
        expected[np.ix_(bb, aa)] += 2
        target.append(minus); control.append(plus)
    difference = rates(target) - rates(control)
    error = float(np.max(np.abs(difference - expected)))
    assert error == 0
    combined = rates([sum(target)]) - rates([sum(control)])
    return {
        'gamma_units': 1,
        'independent_jumps': True,
        'dimension': 216,
        'tested_ordered_density_entries': 216**2,
        'different_entries': int(np.count_nonzero(difference)),
        'expected_difference_error': error,
        'combined_jump_collateral_difference_max': float(np.max(np.abs(combined - expected))),
        'interpretation': 'Exact generator-rate matching outside intended target blocks; not matching of final stationary amplitudes.'
    }

def main():
    manifest = read_json('source/run.json')
    cases = read_json('source/selected_cases.json')
    schema = read_json('source/schema.json')
    columns = {name: i for i, name in enumerate(schema['diagnostics'])}
    rows, detailed = [], []
    max_trace_error = max_sum_error = max_current_error = max_rhs = 0.0
    min_block_eigenvalue = float('inf')
    for case in sorted(cases, key=lambda c: (float(c['phi_over_pi']), float(c['detuning']))):
        cid = case['id']
        for subdir in ['evidence', 'diagnostics']:
            validate_file(f'{subdir}/{cid}.npz', manifest)
        evidence = np.load(ROOT/'source'/'evidence'/f'{cid}.npz', allow_pickle=False)
        diagnostics = np.load(ROOT/'source'/'diagnostics'/f'{cid}.npz', allow_pickle=False)['values']
        time = float(evidence['time'][-1])
        blocks = evidence['blocks'][-1]
        assert abs(time - 200) < 1e-12
        di = diagnostics[np.argmin(np.abs(diagnostics[:, columns['time']] - time))]
        assert abs(di[columns['time']] - time) < 1e-12
        phase = np.pi * float(case['phi_over_pi'])
        sector = np.zeros((8, 2))
        w = np.zeros((8, 2))
        p = np.trace(blocks[1:], axis1=-2, axis2=-1).real
        max_trace_error = max(max_trace_error, abs(float(np.trace(blocks[0]).real) - 1))
        max_sum_error = max(max_sum_error, float(np.max(np.abs(blocks[0] - blocks[1:].sum(axis=0)))))
        min_block_eigenvalue = min(min_block_eigenvalue, float(np.min(np.linalg.eigvalsh(blocks))))
        max_rhs = max(max_rhs, abs(float(di[columns['rhs']])))
        for m in range(8):
            b = blocks[m+1]
            i12 = -2*np.imag([b[1,2], b[5,6]]) if m & 2 else np.zeros(2)
            i02 = -2*np.imag(np.exp(-1j*phase)*np.array([b[1,4], b[3,6]])) if m & 4 else np.zeros(2)
            sector[m] = i12 + i02
            for name, val in [('I12', i12.sum()), ('I02', i02.sum())]:
                max_current_error = max(max_current_error, abs(float(val) - float(di[columns[f'{name}_m{m}']])))
            for n, indices in SECTORS.items():
                w[m,n-1] = float(np.trace(b[np.ix_(indices, indices)]).real)
                h = float(sector[m,n-1])
                detailed.append(dict(case=cid, phi_pi=float(case['phi_over_pi']), epsilon=float(case['detuning']),
                    mask=m, N=n, h=h, p_mask=float(p[m]), w_mask_sector=float(w[m,n-1]),
                    h_given_mask=h/p[m], h_given_mask_sector=h/w[m,n-1]))
        rows.append(dict(case=cid, phi_pi=float(case['phi_over_pi']), epsilon=float(case['detuning']),
            h=float(sector.sum()), sector=sector.tolist(), p=p.tolist(), w=w.tolist(),
            h_given_mask=(sector/p[:,None]).tolist(), h_given_mask_sector=(sector/w).tolist()))
    assert max_current_error < 1e-12
    assert max_trace_error < 1e-10
    assert max_sum_error < 1e-12
    symmetry = []
    for phi in [0.0, 0.5]:
        selected = {r['epsilon']: r for r in rows if r['phi_pi'] == phi}
        worst_sector = worst_total = 0.0
        worst_location = None
        for eps in [.25, .5, 1., 2.]:
            odd = (np.array(selected[eps]['sector']) - np.array(selected[-eps]['sector'])) / 2
            total = abs(selected[eps]['h'] - selected[-eps]['h'])/2
            loc = np.unravel_index(np.argmax(np.abs(odd)), odd.shape)
            if abs(odd[loc]) > worst_sector:
                worst_sector = float(abs(odd[loc])); worst_location = dict(epsilon=eps, mask=int(loc[0]), N=int(loc[1]+1))
            worst_total = max(worst_total, total)
        symmetry.append(dict(phi_pi=phi, max_abs_odd_sector=worst_sector, max_abs_odd_total=worst_total, largest_component_location=worst_location))
    local_shapes = []
    for phi in [0.0, .5]:
        selected = {r['epsilon']: r for r in rows if r['phi_pi'] == phi}
        for mask in [6, 7]:
            entry = dict(phi_pi=phi, mask=mask, N=2, epsilons=[-.25, 0, .25])
            for key in ['sector', 'h_given_mask', 'h_given_mask_sector']:
                entry[key] = [selected[e][key][mask][1] for e in [-.25, 0, .25]]
            local_shapes.append(entry)
    checks = dict(source_commit=COMMIT, scope='QS only; dephasing .05; dt .01; endpoint T200; exploratory screen, not Fano identification',
        verified_npz_files=2*len(cases), case_count=len(cases), max_trace_error=max_trace_error,
        max_mask_sum_error=max_sum_error, min_node_block_eigenvalue=min_block_eigenvalue,
        max_published_current_reconstruction_error=max_current_error, max_published_endpoint_rhs=max_rhs,
        symmetry=symmetry, local_shapes=local_shapes, matched_control_algebra=check_controls(),
        limits=['No RR scan reanalysed here', 'No fresh dt refinement or trajectories', 'No Fano fitting or modal spectrum',
                'Existing grid has nine detunings; narrower features and true extrema unresolved'])
    (ROOT/'results.json').write_text(json.dumps(dict(checks=checks, rows=rows), indent=2)+'\n')
    with (ROOT/'components.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(detailed[0])); writer.writeheader(); writer.writerows(detailed)
    print(json.dumps(checks, indent=2))

if __name__ == '__main__':
    main()
