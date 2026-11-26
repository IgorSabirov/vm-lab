#!/usr/bin/env python3
"""Exact finite checks for the R143 field-content crosswalk; no thermal run.

Python standard library only. Default: recompute and compare the saved receipt.
--write: record the finite calculation. --sources: verify pinned Git file hashes.
All coefficient arithmetic is rational; no fitted parameters or physical data.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
from fractions import Fraction as F
import hashlib
import json
from math import comb
from pathlib import Path
import platform
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def clean(poly):
    return {k: v for k, v in sorted(poly.items()) if v}


def add(*polys):
    out = defaultdict(F)
    for poly in polys:
        for power, coeff in poly.items():
            out[power] += coeff
    return clean(out)


def scale(poly, scalar):
    return clean({k: scalar * v for k, v in poly.items()})


def mul(a, b):
    out = defaultdict(F)
    for i, x in a.items():
        for j, y in b.items():
            out[i + j] += x * y
    return clean(out)


def json_exact(value):
    if isinstance(value, F):
        return str(value)
    if isinstance(value, dict):
        return {str(k): json_exact(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_exact(v) for v in value]
    return value


def worldsheet(data):
    fields = {x['id']: x for x in data['worldsheet_fields']}
    charges = {}
    for key, row in fields.items():
        if row['kind'] == 'first_order_ghost_pair':
            h, other_h = map(F, row['weights'])
            assert h + other_h == 1
            charges[key] = -2 * row['epsilon'] * (6*h*h - 6*h + 1)
        else:
            charges[key] = F(row['central_charge_each'])
    assert charges == {'X': F(1), 'psi': F(1, 2), 'bc': F(-26), 'beta_gamma': F(11)}
    result = {}
    for model in data['worldsheet_models']:
        a = sum((charges[k] for k in model['fields'] if fields[k].get('multiplicity') == 'D'), F(0))
        b = sum((charges[k] for k in model['fields'] if fields[k].get('multiplicity') != 'D'), F(model['additional_c']))
        critical = -b / a
        assert critical == model['expected_critical_D']
        result[model['id']] = {'c_D_coefficient': a, 'c_constant': b, 'critical_D': critical,
                              'd4_required_c_internal': -b - 4*a}
    controls = {
        'bosonic_at_D10': 10*charges['X'] + charges['bc'],
        'RNS_at_D26': 26*(charges['X'] + charges['psi']) + charges['bc'] + charges['beta_gamma'],
        'RNS_D10_without_beta_gamma': 10*(charges['X'] + charges['psi']) + charges['bc'],
        'RNS_D10_wrong_beta_gamma_statistics': 10*(charges['X'] + charges['psi']) + charges['bc'] - charges['beta_gamma'],
    }
    assert list(controls.values()) == [-16, 24, -11, -22]
    assert 1 + (-1) == 0 and not (1 == 0 and -1 == 0)
    return {'central_charges': charges, 'models': result, 'negative_controls': controls,
            'left_right_cancellation_is_insufficient': True,
            'scope': 'One chiral sector; free flat matter and fixed ghosts. No curved-background beta functions.'}


def partial_waves():
    # R134/demo level n=2: s_demo=n-1=1; R2(t)=(t+2)(t+3)/2.
    # Aref ~ R_n/(n-S); hence Res Aref=-R_n, while demo=-Aref.
    s = F(1)
    output = {}
    for name, mass_sq in [('demo_massless', F(0)), ('bosonic_tachyon', F(-1))]:
        a = (s - 4*mass_sq) / 2
        t = {0: -a, 1: a}
        poly = scale(mul(add(t, {0: F(2)}), add(t, {0: F(3)})), F(1, 2))
        rows = []
        for D in range(4, 31):
            P2 = {0: -F(1, D-2), 2: F(D-1, D-2)}
            a2 = poly[2] * F(D-2, D-1)
            a1 = poly.get(1, F(0))
            a0 = poly.get(0, F(0)) + poly[2] / (D-1)
            assert add({0: a0, 1: a1}, scale(P2, a2)) == poly
            if name == 'bosonic_tachyon':
                assert a0 == F(26-D, 8*(D-1))
                assert a2 == F(25*(D-2), 8*(D-1))
                assert (a0 >= 0) == (D <= 26)
            rows.append({'D': D, 'a0': a0, 'a1': a1, 'a2': a2})
        output[name] = {'external_mass_squared': mass_sq, 's_demo': s, 'polynomial_in_z': poly, 'rows': rows}
    assert [output['demo_massless']['rows'][0][k] for k in ('a0', 'a1', 'a2')] == [F(23, 12), 1, F(1, 12)]
    assert [output['bosonic_tachyon']['rows'][0][k] for k in ('a0', 'a1', 'a2')] == [F(11, 12), 0, F(25, 12)]
    r26 = next(x for x in output['bosonic_tachyon']['rows'] if x['D'] == 26)
    r27 = next(x for x in output['bosonic_tachyon']['rows'] if x['D'] == 27)
    assert (r26['a0'], r26['a2'], r27['a0'], r27['a2']) == (0, 3, F(-1, 208), F(625, 208))
    # Independent polynomial-in-D identity, stronger than the finite displayed scan:
    # [8(D-1)(D-2)] * (a0+a2*P2 - R2) vanishes for both z^0 and z^2.
    Dm2, Dm1 = {0: F(-2), 1: F(1)}, {0: F(-1), 1: F(1)}
    constant_identity = add(mul({0: F(26), 1: F(-1)}, Dm2), scale(Dm2, F(-25)), mul(Dm1, Dm2))
    quadratic_identity = add(scale(mul(Dm2, Dm1), F(25)), scale(mul(Dm1, Dm2), F(-25)))
    assert constant_identity == quadratic_identity == {}
    output['rational_identity_for_all_D_greater_than_3'] = True
    output['conclusion'] = 'Necessary level-2 bound D<=26 for the specified bosonic tachyon completion, not D=26 or all-level unitarity.'
    return output


def iib_polarizations(data):
    transverse = 8
    # One real on-shell chiral SO(8) spinor, gamma-traceless vector-spinor.
    spinor = 2**(transverse//2 - 1)
    by_field, counts = {}, defaultdict(int)
    for row in data['iib_fields']:
        kind = row['kind']
        if kind == 'graviton':
            n = transverse * (transverse + 1) // 2 - 1
        elif kind == 'scalar':
            n = 1
        elif kind == 'p_form':
            n = comb(transverse, row['rank'])
        elif kind == 'self_dual_form':
            n = comb(transverse, row['rank']) // 2
        elif kind == 'majorana_weyl_gravitino':
            n = (transverse - 1) * spinor
        elif kind == 'majorana_weyl_spinor':
            n = spinor
        else:
            raise AssertionError(kind)
        by_field[row['field']] = n * row['multiplicity']
        counts[row['sector']] += by_field[row['field']]
    assert dict(counts) == {'NSNS': 64, 'RR': 64, 'NSR/RNS': 128}
    wrong_B = counts['NSNS'] + counts['RR'] + comb(8, 4)//2
    assert wrong_B == 163
    boundary = {'B': 2 + 6, 'F': 4*2}
    pure_su3 = {'B': 2*(3**2-1), 'F': 0}
    assert sum(boundary.values()) == sum(pure_su3.values()) == 16
    assert boundary != pure_su3
    return {'field_polarizations': by_field, 'sectors': dict(counts), 'B': 128, 'F': 128,
            'without_F5_self_duality_B': wrong_B,
            'boundary_N4_per_generator': boundary, 'pure_SU3_local_polarizations': pure_su3,
            'bulk_k1_excluded_by_contract': True,
            'scope': 'Local on-shell polarizations; neither worldsheet c nor full finite-volume singlet state count.'}


def su4_dim(labels):
    a, b, c = labels
    return F((a+1)*(b+1)*(c+1)*(a+b+2)*(b+c+2)*(a+b+c+3), 12)


def primary_numerator(row, shorten=False):
    j1, j2, delta = F(row['j1']), F(row['j2']), F(row['Delta'])
    power = 2*delta  # variable y=sqrt(q), to keep all polynomial powers integer
    assert power.denominator == 1
    m = su4_dim(row['su4']) * row['multiplicity']
    poly = {int(power): m*(2*j1+1)*(2*j2+1)}
    if shorten and row.get('short'):
        assert delta == j1+j2+2 and j1 > 0 and j2 > 0
        poly[int(power)+2] = -m*4*j1*j2
    assert all(v.denominator == 1 for v in poly.values())
    return clean({k: int(v) for k, v in poly.items()})


def kk_character(data):
    rows = data['kk_k2_primaries']
    nulls = data['kk_k2_signed_nulls']
    assert len(rows) == 14 and len(nulls) == 4
    assert len({x['id'] for x in rows + nulls}) == 18
    result = {}
    for stat in ('B', 'F'):
        selected = [r for r in rows if r['statistics'] == stat]
        formal = add(*(primary_numerator(r) for r in selected))
        # S1: shortening inside each conserved positive primary.
        s1 = add(*(primary_numerator(r, shorten=True) for r in selected))
        # S2: independently transcribed signed null representations and long primaries.
        signed_nulls = add(*(primary_numerator(r) for r in nulls if r['statistics'] == stat))
        s2 = add(formal, signed_nulls)
        bad = add(s1, signed_nulls)
        assert s1 == s2 and bad != s1
        levels = []
        for twice_energy in range(4 if stat == 'B' else 5, 41, 2):
            coeff = sum(v*comb((twice_energy-k)//2+3, 3) for k, v in s1.items()
                        if twice_energy >= k and (twice_energy-k) % 2 == 0)
            assert coeff >= 0
            levels.append({'ER': F(twice_energy, 2), 'degeneracy': coeff})
        result[stat] = {'formal_positive_numerator': formal, 'physical_numerator': s1,
                        'signed_null_numerator': signed_nulls, 'BAD_numerator': bad,
                        'formal_components': sum(formal.values()), 'null_components': -sum(signed_nulls.values()),
                        'physical_numerator_at_q1': sum(s1.values()), 'BAD_numerator_at_q1': sum(bad.values()),
                        'levels_through_ER20': levels}
    assert result['B']['physical_numerator'] == {4: 20, 6: 116, 8: -4, 10: -4}
    assert result['F']['physical_numerator'] == {5: 80, 7: 64, 9: -16}
    assert [x['degeneracy'] for x in result['B']['levels_through_ER20'][:5]] == [20, 196, 660, 1540, 2964]
    assert [x['degeneracy'] for x in result['F']['levels_through_ER20'][:5]] == [80, 384, 1040, 2176, 3920]
    assert sum(result[s]['formal_components'] for s in ('B', 'F')) == 291
    assert sum(result[s]['null_components'] for s in ('B', 'F')) == 35
    assert result['B']['physical_numerator_at_q1'] == result['F']['physical_numerator_at_q1'] == 128
    # Independent spacetime polarizations of the 5D massless gauged multiplet.
    b5, f5 = 42 + 15*3 + 12*3 + 5, 48*2 + 8*4
    assert (b5, f5) == (128, 128)
    result.update({'S1_equals_S2_exact_rational_function': True,
                   'physical_denominator_in_y': '(1-y^2)^4; y=sqrt(q)',
                   'physical_5D_polarizations': {'B': b5, 'F': f5},
                   'scope': 'k=2 only, unorbifolded S5. Character diverges at q=1; numerator limit is a polarization count, not total thermal states.'})
    return result


def source_check(manifest, repository_dirs):
    checked = []
    for row in manifest['git_files']:
        root = repository_dirs.get(row['repository'])
        if root is None:
            raise AssertionError('Provide --donor-root for ' + row['repository'])
        raw = subprocess.check_output(['git', '-C', str(root), 'show', row['commit'] + ':' + row['path']])
        assert hashlib.sha256(raw).hexdigest() == row['sha256'], row['id']
        assert len(raw) == row['bytes'], row['id']
        checked.append(row['id'])
    return checked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--sources', action='store_true')
    parser.add_argument('--donor-root', type=Path)
    args = parser.parse_args()
    data = json.loads((HERE/'FIELDS.json').read_text())
    manifest = json.loads((HERE/'SOURCES.json').read_text())
    source_ids = {x['id'] for x in manifest['git_files'] + manifest['public_sources']}
    assert len(data['sectors']) == len({x['id'] for x in data['sectors']}) == 10
    for row in data['sectors']:
        assert all(row[x] for x in ('fields', 'D_input', 'theory_constraint', 'computed_consequence', 'limit', 'sources'))
        assert set(row['sources']) <= source_ids
    t0 = time.perf_counter()
    result = json_exact({'worldsheet': worldsheet(data), 'partial_waves': partial_waves(),
                         'iib_polarizations': iib_polarizations(data), 'kk_k2': kk_character(data)})
    elapsed = time.perf_counter() - t0
    inputs = {name: hashlib.sha256((HERE/name).read_bytes()).hexdigest()
              for name in ('FIELDS.json', 'SOURCES.json', 'verify.py')}
    sources_checked = []
    if args.sources:
        directories = {'IgorSabirov/vm-lab': ROOT}
        if args.donor_root:
            directories['Skabber2000/strings-from-almost-nothing'] = args.donor_root
        sources_checked = source_check(manifest, directories)
    path = HERE/'CHECKS.json'
    if args.write:
        receipt = {'schema':'r143-worldsheet-checks-v1', 'status':'PASS',
                   'scope':'Finite exact arithmetic and source verification; no new thermal simulation or full string calculation.',
                   'execution': {'utc':datetime.now(timezone.utc).isoformat(), 'python':platform.python_version(),
                                 'platform':platform.platform(), 'arithmetic_seconds':elapsed,
                                 'source_ids_verified':sources_checked},
                   'input_sha256':inputs, 'results':result}
        path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    else:
        receipt = json.loads(path.read_text())
        assert receipt['results'] == result, 'Saved finite calculation differs'
        assert receipt['input_sha256'] == inputs, 'Saved receipt has stale code or inputs'
    print(json.dumps({'status':'PASS', 'sectors':len(data['sectors']), 'kk_positive_entries':14,
                      'worldsheet_critical_D':[26,10], 'tachyon_D27_scalar_coefficient':'-1/208',
                      'IIB_and_k2_B_F':[128,128], 'sources_verified':len(sources_checked),
                      'arithmetic_seconds':elapsed, 'new_thermal_runs':0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
