#!/usr/bin/env python3
"""Import a prepared, weighted IsingCauset/CDT ensemble into the SAME protocol.

This changes source hashes and invalidates earlier review/calibration receipts.
It does not run the model, select j*, or turn MCMC iteration into a clock.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from fractions import Fraction

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from nowexp.carrier import Carrier


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('input', type=Path)
    args = parser.parse_args()
    raw = args.input.read_bytes()
    if len(raw) > 16*1024**2:
        raise ValueError('prepared ensemble exceeds import envelope')
    supplied = json.loads(raw)
    if supplied['family'] not in ('IsingCauset', 'CDT'):
        raise ValueError('unsupported prepared ensemble family')
    for key in ('ensemble_id', 'measure', 'preparation', 'diagnostics', 'source_commit'):
        if not supplied.get(key):
            raise ValueError('missing provenance: '+key)
    members = supplied['members']
    if not 1 <= len(members) <= 16 or len({m['id'] for m in members}) != len(members):
        raise ValueError('1..16 distinct prepared geometries required')
    weights = [Fraction(str(m['weight'])) for m in members]
    if any(w <= 0 for w in weights) or sum(weights) != 1:
        raise ValueError('explicit positive normalized rational geometry weights required')
    paths = {name: ROOT/'preregistration'/name for name in
             ('CASES.json', 'PROTOCOL.json', 'PREPARED_GEOMETRIES.json', 'FOUR_CANDIDATE_AMENDMENT.json')}
    cases, plan, bank, amendment = [json.loads(paths[name].read_text()) for name in paths]
    templates = [c for c in cases['cases'] if c['id'].startswith('patch::flat::full_')]
    if len(templates) != 8:
        raise ValueError('eight existing patch templates required')
    ensemble_id = supplied['ensemble_id']
    if not isinstance(ensemble_id, str) or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in ensemble_id):
        raise ValueError('simple stable ensemble ID required')
    if ensemble_id in bank['ensembles']:
        raise ValueError('ensemble already imported; do not overwrite a frozen input')
    expected = {}
    for member, weight in zip(members, weights):
        key = ensemble_id+'::'+member['id']
        if member['geometry']['kind'] != 'prepared_order':
            raise ValueError('an ensemble member must provide an actual future-link graph')
        Carrier(member['geometry'], ['donor', 'MA', 'MB', 'N0', 'N1', 'N2'])
        bank['geometries'][key] = member['geometry']
        for template in templates:
            new = json.loads(json.dumps(template))
            name = 'patch::ensemble::'+key+'::'+template['parent_case']
            if any(c['id'] == name for c in cases['cases']):
                raise ValueError('case ID already exists')
            new.update(id=name, geometry_scope='supplied_weighted_ensemble')
            new['config']['geometry'] = dict(prepared_id=key, ensemble=dict(id=ensemble_id,
                member=member['id'], weight=str(weight), template=template['parent_case']))
            cases['cases'].append(new)
            expected[name] = str(weight)
            amendment['new_cases'].append(name)
            for phase in ('reviewer', 'smoke', 'calibrate'):
                plan['phase_limits'][phase]['cases'].append(name)
            if template['parent_case'] != 'full_base':
                contrast=dict(id=name+'::effect', cases=['patch::ensemble::'+key+'::full_base', name],
                              weights=[1, -1], metric='mean_task_success')
                cases['contrasts'].append(contrast)
                amendment['new_contrasts'].append(contrast['id'])
    bank['ensembles'][ensemble_id] = dict(supplied, members=[dict(id=m['id'], weight=str(w)) for m, w in zip(members, weights)],
                                        input_sha256=hashlib.sha256(raw).hexdigest(), expected_cases=expected,
                                        diagnostics_status='SUPPLIED_NOT_INDEPENDENTLY_VERIFIED')
    plan['freeze_state'] = 'REVIEW_CANDIDATE_NOT_FROZEN'
    info = plan['four_candidate_amendment']
    info.update(total_cases=len(cases['cases']), added_cases=len(cases['cases'])-123,
                added_contrasts=len(cases['contrasts'])-84, review='PENDING_AFTER_IMPORT')
    amendment.update(main_task_count=len(cases['cases'])+192+11, production_frozen=False,
                     status='IMPLEMENTED_PENDING_REVIEW_AFTER_IMPORT')
    # All validation precedes writes; replacements are atomic per file.
    for name, value in zip(paths, (cases, plan, bank, amendment)):
        temp = paths[name].with_suffix('.json.tmp')
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
        temp.replace(paths[name])
    print(json.dumps(dict(ensemble=ensemble_id, new_cases=len(expected),
                          total_cases=len(cases['cases']), receipts_invalidated=True)))


if __name__ == '__main__':
    main()
