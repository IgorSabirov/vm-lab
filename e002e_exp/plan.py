"""Immutable inventory, staged work selection and fail-closed provenance."""
import hashlib
import json
import re
from pathlib import Path
import math
from .runtime import ROOT, kernel_hash, compare_environment


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


def validate_predictions(record, expected_code_commit):
    inv = inventory(); expected = set(inv['F2_gate']['heldout_case_ids'])
    if record.get('status') != 'FROZEN' or record.get('code_commit') != expected_code_commit:
        raise ValueError('F2 predictions not frozen for this reviewed implementation')
    if record.get('concept_sha256') != digest(ROOT/'experiments/e002e/CONCEPT_v003.md'):
        raise ValueError('Prediction concept differs')
    if set(record.get('heldout_case_ids', [])) != expected or len(record['heldout_case_ids']) != len(expected):
        raise ValueError('Held-out coverage differs')
    if not record.get('frozen_at_utc') or not record.get('created_at_utc'):
        raise ValueError('Freeze timestamps missing')
    inputs = record.get('training_inputs', []); ids = set()
    for item in inputs:
        if item.get('block') not in record.get('allowed_training_blocks', []) or item.get('block', '').startswith('F2'):
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
            if not isinstance(rule, dict) or rule.get('absolute_tolerance', -1) < 0 or rule.get('error_rule') != 'interval_with_numerical_uncertainty':
                raise ValueError('Confirmatory prediction requires explicit numerical error rule')
            if p['prediction_type'] not in ('value', 'sign', 'interval'):
                raise ValueError('Unsupported confirmatory prediction')
            definition = p['observable_definition']
            if not isinstance(definition, dict) or definition.get('kind') not in ('linear_combination', 'baseline_difference') or not definition.get('observable') or not definition.get('linear_terms'):
                raise ValueError('Machine-readable observable definition required')
            for term in definition['linear_terms']:
                if term.get('case_id') not in p['physical_case_ids'] or not math.isfinite(float(term['coefficient'])):
                    raise ValueError('Invalid observable term')
            expected_value = p['expected_value_or_sign_or_interval']
            if p['prediction_type'] == 'sign' and expected_value not in (-1, 1):
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
    if config.get('mode') not in ('calibration', 'production'):
        raise ValueError('Explicit calibration or production mode required')
    if config.get('source_kernel_sha256') != kernel_hash():
        raise ValueError('Running kernel differs from requested source')
    review = pinned_file(config['copilot_review'])
    if review.get('status') != 'REVIEWED_AND_CHECKED' or review.get('kernel_sha256') != kernel_hash():
        raise ValueError('Technical review not completed for this kernel')
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
        if cal.get('numerics') != config.get('numerics'):
            raise ValueError('Numerical method differs from calibration')
        env_check = compare_environment(cal['environment'], current_environment)
        if not env_check['comparable']:
            raise ValueError('Target environment differs: '+str(env_check))
        if cal.get('stage_budgets', {}).get(config['stage']) != config.get('forecast'):
            raise ValueError('Forecast differs from verified stage budget')
    if config['stage'] == 'F2':
        baseline = pinned_file(config['baseline_report'])
        if baseline.get('status') != 'VERIFIED_GITHUB':
            raise ValueError('F2 requires previously verified baseline data')
        predictions = pinned_file(config['predictions'])
        if not re.fullmatch('[0-9a-f]{40}', config['predictions'].get('commit', '')):
            raise ValueError('Frozen prediction commit required')
        validate_predictions(predictions, review['implementation_commit'])
    if config['expected_workload'] != workload(work):
        raise ValueError('Declared workload differs from selected cases')
    return work, env_check
