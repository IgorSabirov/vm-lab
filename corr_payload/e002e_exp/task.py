"""Staged VM worker. No network, peer messaging, or automatic production launch."""
import gc
import json
import os
from pathlib import Path
import time
import traceback
import numpy as np
from e002_exp.model import save_json
from .model import make_full, make_small
from .numerics import Bordered, state_checks, values, refinement_check
from .observations import static_response, frequency_response, propagate_qrt, compare_qrt
from .plan import preflight, workload, pinned_file, full_physical_key
from .analysis import renewal_check, symmetry_check, f2_differences, evaluate_predictions, measured_symmetries
from .runtime import environment, runtime_gate, kernel_hash
from .export import serial, real_values, conditional_values, summaries, save_case, save_correlations, write_manifest, write_result, verify_report


def _run(config, output=Path('.')):
    started = time.perf_counter(); output = Path(output)
    report = output/'report'; full = output/'full'
    report.mkdir(parents=True, exist_ok=False); full.mkdir(parents=True, exist_ok=False)
    env_before = environment(); work, env_check = preflight(config, env_before)
    save_json(report/'config.json', config); save_json(report/'environment_before.json', env_before)
    records = []; responses = []; qrts = []; phases = []; failure = None
    actual = dict.fromkeys(config['expected_workload'], 0)
    solver_options = config['numerics']['solver']; quality_tolerance = config['numerics']['state_tolerance']
    refinement_options = config['numerics']['refinement_solver']; error_policy = config['numerics']['error_envelope']
    def error_envelope(a, b):
        return {k: error_policy['absolute_floor']+error_policy['difference_multiplier']*float(abs(v-b[k]))
                for k, v in a.items() if v is not None and b.get(k) is not None}
    try:
        cases = [(f'small_{i:03d}', c, True) for i, c in enumerate(work['small'])]
        cases += [(c['id'], c, False) for c in work['full']]
        for case_id, case, small in cases:
            print('START', case_id, flush=True); start = time.perf_counter()
            model = make_small(case) if small else make_full(case)
            setup_time = time.perf_counter()-start; space = model['space']
            solver = Bordered(model['L'], space, **solver_options)
            state, solve_check = solver.solve(trace=1.)
            quality = state_checks(model['L'], space, state, quality_tolerance)
            if not quality['pass']:
                raise ArithmeticError('Unphysical or nonstationary NESS: '+str(quality))
            independent = Bordered(model['L'], space, **refinement_options)
            ref_state, ref_checks = independent.solve(trace=1.)
            ref_quality = state_checks(model['L'], space, ref_state, quality_tolerance)
            if not ref_quality['pass']:
                raise ArithmeticError('Independent NESS verification failed')
            actual['refinement_NESS'] += 1
            raw = real_values(values(model, state)); ref_raw = real_values(values(model, ref_state))
            refinement_gate = refinement_check(state, ref_state, raw, ref_raw, config['numerics']['refinement_limits'])
            if not refinement_gate['pass_gate']:
                save_json(report/(case_id+'_refinement_failure.json'), serial(refinement_gate))
                raise ArithmeticError('Independent NESS disagreement exceeds calibrated limits')
            errors = error_envelope(raw, ref_raw); conditional = conditional_values(raw, errors)
            if abs(raw['J_h']-raw['F']) > quality_tolerance*10 or abs(raw['source']-raw['F']) > quality_tolerance*10:
                raise ArithmeticError('Stationary flux balance failed')
            rec = dict(id=case_id, case=case, raw=raw, conditional=conditional, quality=quality,
                       physical_key=None if small else full_physical_key(case),
                       solve_check=solve_check, branch=model.get('branch', 'unique_NESS_candidate'),
                       operator_checks=model.get('checks', {}), hilbert_dimension=space.d,
                       liouville_dimension=space.size, generator_nnz=model['L'].nnz,
                       primitive_uncertainty=errors, refinement=dict(quality=ref_quality, solve=ref_checks,
                       gate=refinement_gate,
                       state_difference_inf=float(abs(state-ref_state).max()), error_policy=error_policy,
                       uncertainty_kind='ENGINEERING_TWO_METHOD_ENVELOPE_NOT_RIGOROUS_TOTAL_ERROR_BOUND'),
                       condition=solver.condition_estimate() if config['numerics'].get('estimate_condition', True) else {'status':'NOT_ESTIMATED'})
            rec['renewal'] = renewal_check(model, state) if small else {'status': 'NOT_APPLICABLE'}
            rec['symmetry'] = symmetry_check(model) if not small else {'symmetry_applicable': False, 'parity_status': 'SMALL_GAUGE_TESTED_SEPARATELY'}
            if rec['renewal']['status'] == 'FAIL':
                raise ArithmeticError('G1 renewal identity failed')
            if rec['symmetry'].get('parity_status') == 'OPERATOR_CHECK_FAILED':
                raise ArithmeticError('Declared antiunitary symmetry failed')
            save_case(report, full, rec, state, space); records.append(rec)
            actual['small_NESS' if small else 'full_NESS'] += 1
            for target in case.get('tasks', [])[1:]:
                x, out, checks = static_response(model, state, target, solver)
                xr, outr, checkr = static_response(model, ref_state, target, independent)
                agreement = refinement_check(x, xr, out, outr, config['numerics']['refinement_limits'])
                if not agreement['pass_gate']:
                    save_json(report/(case_id+'_'+target+'_refinement_failure.json'), serial(agreement))
                    raise ArithmeticError('Static response disagreement exceeds calibrated limits')
                responses.append(dict(base_id=case_id, kind='static', target=target, values=out, checks=checks,
                                      refinement_checks=checkr, refinement_gate=agreement, uncertainty=error_envelope(out, outr)))
                actual['static_responses'] += 1
                actual['refinement_static_responses'] += 1
            independent_metrics = independent.metrics(); del independent
            for freq in [f for f in work['frequency'] if f['base_id'] == case_id]:
                x, out, checks, met = frequency_response(model, state, freq['omega_over_J'], solver, **solver_options)
                xr, outr, checkr, metr = frequency_response(model, ref_state, freq['omega_over_J'], None, **refinement_options)
                agreement = refinement_check(x, xr, out, outr, config['numerics']['refinement_limits'])
                if not agreement['pass_gate']:
                    save_json(report/(case_id+'_frequency_refinement_failure.json'), serial(agreement))
                    raise ArithmeticError('Frequency response disagreement exceeds calibrated limits')
                responses.append(dict(base_id=case_id, kind='frequency', omega=freq['omega_over_J'], values=out,
                                      checks=checks, solver=met, refinement_checks=checkr, refinement_solver=metr,
                                      refinement_gate=agreement, uncertainty=error_envelope(out, outr)))
                actual['frequency_responses'] += 1
                actual['refinement_frequency_responses'] += 1
            corr = [c for c in work['correlations'] if c['base_id'] == case_id]
            if corr:
                names = tuple(c['input'] for c in corr); q = config['numerics']['qrt']
                def checkpoint(step, t, y):
                    # Checkpoint is explicit; automatic resume is intentionally not claimed.
                    if step % q['checkpoint_stride_steps'] == 0:
                        tmp = full/(case_id+'_qrt_checkpoint.tmp.npz')
                        np.savez_compressed(tmp, y=y, step=step, time=t, kernel_sha256=kernel_hash())
                        os.replace(tmp, full/(case_id+'_qrt_checkpoint.npz'))
                fine = propagate_qrt(model, state, q['horizon'], q['dt_fine'], q['sample_interval'], names, checkpoint)
                coarse = propagate_qrt(model, state, q['horizon'], q['dt_coarse'], q['sample_interval'], names)
                ref = compare_qrt(fine, coarse, q['absolute_tolerance'], q['relative_tolerance'])
                qrts.append(dict(id=case_id, **save_correlations(report, full, case_id, fine, coarse, ref)))
                actual['correlation_inputs'] += len(corr)
                if not ref['pass_gate']:
                    raise ArithmeticError('QRT refinement failed; finer continuation requires a declared budget')
            phases.append(dict(id=case_id, setup_seconds=setup_time, total_case_seconds=time.perf_counter()-start,
                               solver=solver.metrics(), refinement_solver=independent_metrics))
            save_json(report/'progress.json', dict(last_case=case_id, actual_counts=actual, elapsed_seconds=time.perf_counter()-started))
            print('DONE', case_id, flush=True)
            del solver, model, state; gc.collect()
    except Exception as exc:
        failure = type(exc).__name__+': '+str(exc)
        save_json(report/'failure.json', dict(message=failure, traceback=traceback.format_exc()))
    comparisons = summaries(records)
    symmetry_pairs = measured_symmetries(records, responses)
    save_json(report/'symmetry_pairs.json', serial(symmetry_pairs))
    if any(x['status'] == 'FAIL' for x in symmetry_pairs):
        failure = failure or 'Measured symmetry exceeds propagated numerical tolerance'
    if config['stage'] == 'F2' and not failure:
        differences = f2_differences(records, pinned_file(config['baseline_report']))
        verdicts = evaluate_predictions(pinned_file(config['predictions']), records, differences)
        save_json(report/'f2_differences.json', serial(differences))
        save_json(report/'prediction_verdicts.json', serial(verdicts))
    save_json(report/'contrasts.json', serial(comparisons)); save_json(report/'responses.json', serial(responses))
    elapsed = time.perf_counter()-started
    gate = runtime_gate(config['forecast'], elapsed, config['expected_workload'], actual,
                        env_check['comparable'], config['mode'] == 'production')
    if failure and gate['status'] == 'PASS':
        gate['status'] = 'REVIEW_REQUIRED'
    metrics = dict(runtime_gate=gate, phases=phases, environment_after=environment(),
                   environment_comparison=env_check, actual_counts=actual, qrt=qrts, failure=failure,
                   kernel_sha256=kernel_hash(), source_commit=os.environ.get('VM_SOURCE_COMMIT', config.get('source_commit')),
                   scientific_status='NOT_ACCEPTED_AUTOMATICALLY', full_process_time='USE_SERVICE_RUN_JSON')
    save_json(report/'metrics.json', serial(metrics))
    write_result(report, config, records, failure, gate, comparisons, qrts)
    from .export import write_full_manifest
    write_full_manifest(report, full)
    save_json(report/'status.json', dict(status='COMPLETED_NOT_ACCEPTED' if not failure else 'FAILED', failure=failure))
    write_manifest(report); verification = verify_report(report, full) if not failure else {'status': 'PARTIAL_FAILED_RUN'}
    print(json.dumps(dict(failure=failure, runtime_gate=gate, verification=verification)), flush=True)
    if failure:
        raise RuntimeError(failure)
    return metrics


def run(config, output=Path('.')):
    """Persist failure even in preflight/evaluation/export; never rewrite old runs."""
    output = Path(output); report = output/'report'
    if report.exists() or (output/'full').exists():
        raise FileExistsError('Output already contains a run; refusing to modify it')
    start = time.perf_counter()
    try:
        return _run(config, output)
    except Exception as exc:
        failure = dict(status='FAILED', type=type(exc).__name__, message=str(exc),
                       traceback=traceback.format_exc(), elapsed_seconds=time.perf_counter()-start,
                       scientific_acceptance=False)
        try:
            report.mkdir(parents=True, exist_ok=True)
            save_json(report/'terminal_failure.json', failure)
            save_json(report/'status.json', dict(status='FAILED', failure=failure['message']))
            metrics_path = report/'metrics.json'
            metrics = json.loads(metrics_path.read_text()) if metrics_path.exists() else {}
            metrics.update(failure=failure['message'], terminal_status='FAILED', scientific_status='NOT_ACCEPTED')
            gate = metrics.setdefault('runtime_gate', {})
            gate['status'] = 'REVIEW_REQUIRED' if gate.get('status') == 'PASS' else gate.get('status', 'NOT_EVALUABLE')
            save_json(metrics_path, metrics)
            (report/'RESULT.md').write_text('Время: NOT_EVALUABLE либо требует повторной проверки полного процесса.\n\n'
                'Расчёт завершён с ошибкой. Результат не принят.\n\n'+failure['type']+': '+failure['message']+'\n'
                'Подробности: terminal_failure.json. Частичные файлы сохраняются; прежний манифест не пересоздаётся для их принятия.\n')
        except Exception:
            print('FAILED_TO_PERSIST_TERMINAL_DIAGNOSTICS', traceback.format_exc(), flush=True)
        raise
