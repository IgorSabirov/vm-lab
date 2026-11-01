"""Immutable inventory, staged work selection and fail-closed provenance."""
import hashlib
import json
import re
from pathlib import Path
import math
from datetime import datetime
import os
from .runtime import ROOT, kernel_hash, compare_environment, memory_preflight


def inventory():
    return json.loads((ROOT/'experiments/e002e/case_inventory_v003.json').read_text())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pinned_file(spec):
    path = Path(spec['path'])
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Pinned input must be within source tree')
    path = ROOT/path
    if not re.fullmatch(r'[0-9a-f]{64}', spec['sha256']) or digest(path) != spec['sha256']:
        raise ValueError('Pinned input hash mismatch')
    return json.loads(path.read_text())


def full_physical_key(case, undeformed=False):
    # All fixed and varied full-model parameters belong to the case identity.
    # Extra unsupported physical overrides are rejected, not silently ignored.
    allowed = {'id', 'block', 'tasks', 'model', 'phi_over_pi', 'epsilon', 'node_noise', 'm6_v_over_J'}
    if set(case)-allowed:
        raise ValueError('Unsupported full-case fields: '+str(sorted(set(case)-allowed)))
    from e002c_exp.model import BASE, RR
    from .model import IC_ALPHA
    physics = dict(BASE, model=case['model'], phi_over_pi=float(case['phi_over_pi']),
                   epsilon=float(case['epsilon']), phi_n=float(case['node_noise']),
                   m6_v_over_J=1. if undeformed else float(case['m6_v_over_J']))
    if case['model'] == 'RR_QS':
        physics.update(g=0., gamma_r=0., rr_rates=RR)
    if case['model'] == 'IC1_QS':
        physics.update(g=0., ic_alpha=IC_ALPHA)
    return json.dumps(physics, sort_keys=True, separators=(',', ':'))


def timestamp(value):
    try:
        t = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (AttributeError, ValueError):
        raise ValueError('Invalid timestamp') from None
    if t.tzinfo is None:
        raise ValueError('Timestamp must include timezone')
    return t


def selected_work(stage):
    inv = inventory()
    if stage == 'G':
        return dict(small=inv['small_main']+inv['small_weak_G1']+inv['small_peer'], full=[], frequency=[], correlations=[])
    if stage not in ('baseline', 'F2'):
        raise ValueError('Stage must be G, baseline, or F2')
    return dict(small=[], full=[c for c in inv['full_static'] if (c['block'] == 'F2') == (stage == 'F2')],
                frequency=inv['frequency'] if stage == 'baseline' else [],
                correlations=inv['correlations'] if stage == 'baseline' else [])


def workload(work):
    return dict(small_NESS=len(work['small']), full_NESS=len(work['full']),
                static_responses=sum(len(c['tasks'])-1 for c in work['full']),
                frequency_responses=len(work['frequency']), correlation_inputs=len(work['correlations']),
                refinement_NESS=len(work['small'])+len(work['full']),
                refinement_static_responses=sum(len(c['tasks'])-1 for c in work['full']),
                refinement_frequency_responses=len(work['frequency']))


def validate_predictions(record, expected_code_commit, tolerance_caps=None):
    inv = inventory(); expected = set(inv['F2_gate']['heldout_case_ids'])
    if record.get('status') != 'FROZEN' or record.get('code_commit') != expected_code_commit:
        raise ValueError('F2 predictions not frozen for this reviewed implementation')
    if record.get('concept_sha256') != digest(ROOT/'experiments/e002e/CONCEPT_v003.md'):
        raise ValueError('Prediction concept differs')
    if set(record.get('heldout_case_ids', [])) != expected or len(record['heldout_case_ids']) != len(expected):
        raise ValueError('Held-out coverage differs')
    if timestamp(record.get('created_at_utc')) > timestamp(record.get('frozen_at_utc')):
        raise ValueError('Freeze precedes creation')
    inputs = record.get('training_inputs', []); ids = set()
    for item in inputs:
        allowed_training = {'G', 'R_baseline', 'F1_v_equals_J', 'F3_baseline_if_declared', 'T_baseline_if_declared'}
        if item.get('block') not in allowed_training or item.get('block') not in record.get('allowed_training_blocks', []):
            raise ValueError('Undeclared training block')
        if not re.fullmatch('[0-9a-f]{40}', item.get('report_commit', '')) or not re.fullmatch('[0-9a-f]{64}', item.get('sha256', '')):
            raise ValueError('Training input lacks immutable provenance')
        if item.get('id') in ids or not item.get('id'):
            raise ValueError('Duplicate or missing training ID')
        ids.add(item['id'])
    if not inputs:
        raise ValueError('Training inputs must be declared')
    required = json.loads((ROOT/'experiments/e002e/f2_prereg_predictions.template.json').read_text())['required_prediction_fields']
    covered = set(); prediction_ids = set()
    for p in record.get('predictions', []):
        if any(k not in p or p[k] is None for k in required):
            raise ValueError('Incomplete prediction')
        if p['prediction_id'] in prediction_ids:
            raise ValueError('Duplicate prediction ID')
        prediction_ids.add(p['prediction_id'])
        if not set(p['physical_case_ids']) <= expected or not set(p['training_input_ids']) <= ids:
            raise ValueError('Prediction refers to unknown cases or inputs')
        mode = p['confirmatory_or_exploratory']
        if mode not in ('confirmatory', 'exploratory'):
            raise ValueError('Prediction mode missing')
        if mode == 'confirmatory':
            rule = p['tolerance_and_error_rule']
            tol = rule.get('absolute_tolerance') if isinstance(rule, dict) else None
            if isinstance(tol, bool) or not isinstance(tol, (int, float)) or not math.isfinite(tol) or tol < 0 or rule.get('error_rule') != 'interval_with_numerical_uncertainty':
                raise ValueError('Confirmatory prediction requires explicit numerical error rule')
            cap = (tolerance_caps or {}).get(p['prediction_id'])
            if isinstance(cap, bool) or not isinstance(cap, (int, float)) or not math.isfinite(cap) or cap < 0 or tol > cap:
                raise ValueError('Tolerance exceeds independently verified scientific cap or cap missing')
            if p['prediction_type'] not in ('value', 'sign', 'interval'):
                raise ValueError('Unsupported confirmatory prediction')
            definition = p['observable_definition']
            if not isinstance(definition, dict) or definition.get('kind') not in ('linear_combination', 'baseline_difference') or not definition.get('observable') or not definition.get('linear_terms'):
                raise ValueError('Machine-readable observable definition required')
            for term in definition['linear_terms']:
                if term.get('case_id') not in p['physical_case_ids'] or not math.isfinite(float(term['coefficient'])):
                    raise ValueError('Invalid observable term')
            actual_cases = {term['case_id'] for term in definition['linear_terms'] if float(term['coefficient']) != 0.}
            if actual_cases != set(p['physical_case_ids']):
                raise ValueError('Declared prediction coverage differs from nonzero observable terms')
            expected_value = p['expected_value_or_sign_or_interval']
            if p['prediction_type'] == 'sign' and (isinstance(expected_value, bool) or expected_value not in (-1, 1)):
                raise ValueError('Sign must be -1 or +1')
            if p['prediction_type'] == 'interval' and (not isinstance(expected_value, list) or len(expected_value) != 2 or not all(math.isfinite(float(v)) for v in expected_value) or expected_value[0] > expected_value[1]):
                raise ValueError('Invalid prediction interval')
            if p['prediction_type'] == 'value' and not math.isfinite(float(expected_value)):
                raise ValueError('Invalid expected value')
        covered.update(p['physical_case_ids'])
    if covered != expected:
        raise ValueError('Every F2 case requires confirmatory or explicit exploratory coverage')
    return dict(status='FROZEN_FILE_VALID', covered=len(covered), predictions=len(prediction_ids),
                provenance_note='External training reports must also be verified by reviewer before submission')


def preflight(config, current_environment):
    work = selected_work(config['stage'])
    num = config['numerics']
    if num['solver']['method'] == num['refinement_solver']['method']:
        raise ValueError('Independent solution check requires a distinct solver method')
    if num['error_envelope']['absolute_floor'] <= 0 or num['error_envelope']['difference_multiplier'] < 1:
        raise ValueError('Invalid engineering error envelope')
    for key in ('vector_inf', 'observable_absolute', 'observable_relative'):
        value = num['refinement_limits'][key]
        if not math.isfinite(value) or value <= 0:
            raise ValueError('Invalid independent-refinement threshold')
    source_commit = config.get('source_commit')
    if not isinstance(source_commit, str) or not re.fullmatch('[0-9a-f]{40}', source_commit) or os.environ.get('VM_SOURCE_COMMIT') != source_commit:
        raise ValueError('Requested source commit must match VM checkout commit')
    if config.get('mode') not in ('calibration', 'production'):
        raise ValueError('Explicit calibration or production mode required')
    if config.get('source_kernel_sha256') != kernel_hash():
        raise ValueError('Running kernel differs from requested source')
    review = pinned_file(config['copilot_review'])
    if review.get('status') != 'REVIEWED_AND_CHECKED' or review.get('kernel_sha256') != kernel_hash():
        raise ValueError('Technical review not completed for this kernel')
    for key in ('implementation_commit', 'reviewed_source_commit'):
        if not re.fullmatch('[0-9a-f]{40}', review.get(key, '')):
            raise ValueError('Missing immutable review commit')
    if config['mode'] == 'calibration':
        # A bounded, explicit subset; no held-out F2 solutions during calibration.
        if config['stage'] == 'F2':
            raise ValueError('Calibrating on held-out F2 is prohibited')
        selected = set(config['calibration_case_ids'])
        if config['stage'] == 'G':
            if not selected or any(not str(i).isdigit() for i in selected):
                raise ValueError('Small calibration indices required')
            work['small'] = [c for i, c in enumerate(work['small']) if str(i) in selected]
        else:
            work['full'] = [c for c in work['full'] if c['id'] in selected]
            work['frequency'] = [f for f in work['frequency'] if f['base_id'] in selected]
            work['correlations'] = [f for f in work['correlations'] if f['base_id'] in selected]
        if len(work['small'])+len(work['full']) != len(selected):
            raise ValueError('Calibration selection mismatch')
        env_check = dict(comparable=False, reason='FIRST_TARGET_ENVIRONMENT_CALIBRATION')
    else:
        cal = pinned_file(config['calibration_verification'])
        if cal.get('status') != 'VERIFIED_GITHUB' or cal.get('kernel_sha256') != kernel_hash():
            raise ValueError('Calibration has not been verified for current kernel')
        if not cal.get('baseline_equivalence_pass') or not cal.get('observable_accuracy_pass'):
            raise ValueError('Baseline/accuracy verification missing')
        if work['correlations']:
            qrt = cal.get('qrt_validation', {})
            discrepancy = qrt.get('maximum_scaled_discrepancy')
            if qrt.get('status') != 'VERIFIED_GITHUB' or not qrt.get('full_model_representative') or not isinstance(discrepancy, (int, float)) or not math.isfinite(discrepancy) or not 0 <= discrepancy <= 1 or qrt.get('reference_method') not in ('third_RK4_grid', 'independent_exponential_action'):
                raise ValueError('Representative full-model QRT calibration is missing')
        if cal.get('numerics') != config.get('numerics'):
            raise ValueError('Numerical method differs from calibration')
        env_check = compare_environment(cal['environment'], current_environment)
        if not env_check['comparable']:
            raise ValueError('Target environment differs: '+str(env_check))
        if cal.get('stage_budgets', {}).get(config['stage']) != config.get('forecast'):
            raise ValueError('Forecast differs from verified stage budget')
        env_check['memory'] = memory_preflight(cal['stage_memory_budgets'][config['stage']], current_environment)
    if config['stage'] == 'F2':
        baseline = pinned_file(config['baseline_report'])
        if baseline.get('status') != 'VERIFIED_GITHUB':
            raise ValueError('F2 requires previously verified baseline data')
        predictions = pinned_file(config['predictions'])
        if not re.fullmatch('[0-9a-f]{40}', config['predictions'].get('commit', '')):
            raise ValueError('Frozen prediction commit required')
        verification = pinned_file(config['prediction_verification'])
        if verification.get('status') != 'VERIFIED_GITHUB' or verification.get('prediction_sha256') != config['predictions']['sha256'] or verification.get('prediction_commit') != config['predictions']['commit']:
            raise ValueError('Independent prediction provenance verification missing/mismatched')
        if verification.get('training_inputs') != predictions['training_inputs'] or verification.get('kernel_sha256') != kernel_hash():
            raise ValueError('Training verification differs from frozen inputs/kernel')
        if not verification.get('training_contents_hash_checked') or not verification.get('commit_ancestry_checked'):
            raise ValueError('Training contents and commit ordering must be verified through GitHub')
        if verification.get('baseline_sha256') != config['baseline_report']['sha256']:
            raise ValueError('Verified baseline digest differs')
        if timestamp(predictions['frozen_at_utc']) >= timestamp(config['submitted_at_utc']):
            raise ValueError('Predictions must be frozen before submission')
        validate_predictions(predictions, review['implementation_commit'], verification['scientific_tolerance_caps'])
    if config['expected_workload'] != workload(work):
        raise ValueError('Declared workload differs from selected cases')
    return work, env_check
