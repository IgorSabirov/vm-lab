"""Static source/document checks only. Never import or execute NOW models/tests."""
import argparse
import ast
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--baseline-docs', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    a = parser.parse_args()
    root, before, base = a.repo_root, a.baseline_docs, a.source_root
    E = Path('experiments/now_integrated_v1')
    P = Path('analysis/INTEGRATED_EXPERIMENT_20261107')
    R = Path('analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.json')
    def load(p):
        return json.loads(p.read_text())
    spec = load(root/E/'preregistration/FOUR_CANDIDATE_AMENDMENT.json')
    cases = load(root/E/'preregistration/CASES.json')
    old = load(base/E/'preregistration/CASES.json')
    plan = load(root/E/'preregistration/PROTOCOL.json')
    oldplan = load(base/E/'preregistration/PROTOCOL.json')
    reg, oldreg = load(root/R), load(before/R)
    checks = {}
    syntax = list((root/E).rglob('*.py'))
    for f in syntax:
        ast.parse(f.read_text(), filename=str(f))
    checks['python_syntax_without_execution'] = True
    for f in (root/E).rglob('*.json'):
        load(f)
    checks['json_parses'] = True
    checks['same_experiment'] = spec['experiment_id'] == plan['experiment'] == 'NOW_INTEGRATED_CONTINUATION_V1'
    checks['not_frozen_for_main'] = not spec['production_frozen'] and plan['freeze_state'] == 'REVIEW_CANDIDATE_NOT_FROZEN'
    checks['all_123_legacy_cases_unchanged'] = cases['cases'][:123] == old['cases'] and len(old['cases']) == 123
    checks['all_84_legacy_contrasts_unchanged'] = cases['contrasts'][:84] == old['contrasts'] and len(old['contrasts']) == 84
    checks['legacy_11_controls_unchanged'] = plan['design_controls'] == oldplan['design_controls'] and len(plan['design_controls']) == 11
    checks['correct_counts'] = len(cases['cases']) == 123+len(spec['new_cases']) and len(cases['contrasts']) == 84+len(spec['new_contrasts']) and spec['main_task_count'] == len(cases['cases'])+192+11
    ids = {c['id'] for c in cases['cases']}
    checks['unique_cases_and_resolved_contrasts'] = len(ids) == len(cases['cases']) and all(set(c['cases']) <= ids for c in cases['contrasts'])
    checks['new_input_not_forced_11'] = all(c['config'].get('forced_content') is None for c in cases['cases'][123:])
    checks['new_primary_metric_not_health'] = all(c['metric'] == 'mean_task_success' for c in cases['contrasts'][84:])
    checks['all_eight_N_mapped_to_existing_X'] = set(spec['N_to_X']) == {f'N{i:02d}' for i in range(1, 9)} and all(set(v) <= {f'X{i:02d}' for i in range(1,17)} for v in spec['N_to_X'].values())
    checks['all_registry_IDs_preserved'] = [v['id'] for v in reg['results']] == [v['id'] for v in oldreg['results']] and len(reg['results']) == 127
    checks['first_125_results_unchanged'] = reg['results'][:125] == oldreg['results'][:125]
    checks['all_42_constructs_unchanged'] = reg['constructs'] == oldreg['constructs'] and len(reg['constructs']) == 42
    checks['all_10_links_unchanged'] = reg['open_links'] == oldreg['open_links'] and len(reg['open_links']) == 10
    checks['existing_lineage_edges_unchanged'] = all(reg[k] == oldreg[k] for k in ('lineage_edges','planned_experiment_edges','result_children','result_to_constructs'))
    source = load(root/P/'PATCH_SOURCE_INDEX.json')
    verified = []
    for v in source['source_code_files']:
        b = (base/v['path']).read_bytes()
        verified.append(hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest() == v['blob'])
    checks['35_base_source_blobs_verified'] = len(verified) == 35 and all(verified)
    supplied = source['cross_account_report']
    checks['provided_report_preserved'] = hashlib.sha256((root/supplied['path']).read_bytes()).hexdigest() == supplied['sha256']
    tests = ast.parse((root/E/'tests/test_four_candidate_patch.py').read_text())
    count = sum(isinstance(n, ast.FunctionDef) and n.name.startswith('test_') for n in ast.walk(tests))
    checks['18_patch_tests_present'] = count == 18
    checks['no_theorem_gate_for_NOW'] = load(root/'analysis/FOUR_CANDIDATE_INTEGRATION_20261108/DESIGN.json')['add_operational_law']['author_theorem_study_required'] is False
    checks['no_equilibrium_samples_invented'] = not load(root/E/'preregistration/PREPARED_GEOMETRIES.json')['ensembles']
    out = dict(status='PASS' if all(checks.values()) else 'FAIL', checks=checks,
               count=len(checks), python_files_parsed=len(syntax), models_executed=0,
               unit_tests_executed=0, new_smoke_runs=0, vm_runs=0,
               scope='static syntax/source/manifest/registry validation only; no numerical or model execution')
    (root/P/'PATCH_CHECKS.json').write_text(json.dumps(out, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
