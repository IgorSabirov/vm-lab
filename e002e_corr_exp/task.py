"""Standalone VM worker; calibration never constructs the held-out product state."""
import argparse
import gc
import json
import os
from pathlib import Path
import time
import traceback
import numpy as np
from scipy import sparse as sp
from e002c_exp.model import operators
from e002e_exp.model import make_full
from e002e_exp.numerics import Bordered, state_checks, values, refinement_check
from e002e_exp.export import serial, real_values, write_manifest
from e002e_exp.runtime import environment, runtime_gate, kernel_hash
from .core import prepare, propagate, analyze
from .plan import PROTOCOL, SOLVERS, LIMITS, preflight, implementation_hash, protocol_hash


def save(path, value):
    Path(path).write_text(json.dumps(serial(value), ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def select_observables(model):
    names = ('F', 'J_h', 'source', 'inventory', 'h6', 'P_m6_N2', 'K')
    result = {n:model['observables'][n] for n in names}
    result.update({n:o for n,o in model['observables'].items() if n.startswith('C_')})
    for i, op in enumerate(model['n']):
        result['node_'+str(i)] = op
    for i, op in enumerate(model['currents']):
        result['current_'+str(i)] = op
    # Preserve the public model builder; local marginal diagnostics only.
    if model['space'].d == 216:
        o = operators()
        for i, op in enumerate(o['pl']):
            result['edge_L_'+str(i)] = op
        for m in range(8):
            result['mask_'+str(m)] = sp.kron(sp.eye(8), o['masks'][m], format='csr')
    return dict(model, observables=result)


def solve_baseline(model):
    solutions = []; checks = []; metrics = []; prim = []
    started = time.perf_counter()
    for options in SOLVERS:
        solver = Bordered(model['L'], model['space'], **options)
        state, equation = solver.solve(trace=1.)
        quality = state_checks(model['L'], model['space'], state, PROTOCOL['state_tolerance'])
        if not quality['pass']:
            raise ArithmeticError('NESS quality failed')
        solutions.append(state); prim.append(real_values(values(model, state)))
        checks.append(dict(equation=equation, quality=quality)); metrics.append(solver.metrics())
        del solver
    comparison = refinement_check(*solutions, *prim, LIMITS)
    if not comparison['pass_gate']:
        raise ArithmeticError('Independent NESS methods disagree')
    for raw in prim:
        if abs(raw['F']-raw['J_h']) > 1e-9 or abs(raw['F']-raw['source']) > 1e-9:
            raise ArithmeticError('Stationary flux balance failed')
    return solutions, prim, dict(checks=checks, comparison=comparison, solvers=metrics,
                                  seconds=time.perf_counter()-started)


def run_case(model, states, raw, *, mode, horizon, output=None, dimensions=(8, 27)):
    """Scientific routine also tested on independently solvable small models."""
    if mode == 'production':
        initial, prep = prepare(model, states[0], dimensions, PROTOCOL['operator_tolerance'])
        initial_ref, prep_ref = prepare(model, states[1], dimensions, PROTOCOL['operator_tolerance'])
        initial_values = real_values(values(model, initial[:, 1]))
        if abs(initial_values['F']-raw[0]['F']) > PROTOCOL['operator_tolerance']:
            raise ArithmeticError('Marginal-preserving intervention changed initial flux')
        derivative = model['L']@(initial[:, 1]-initial[:, 0])
        prep['delta_flux_derivative_at_zero'] = float((model['space'].row(model['observables']['F'])@derivative).real)
        prep['delta_h_at_zero'] = initial_values['J_h']-raw[0]['J_h']
        # Full model exact balance: dF/dt = kappa_out (J_h-F).
        if model['space'].d == 216 and abs(prep['delta_flux_derivative_at_zero']-.5*prep['delta_h_at_zero']) > 1e-10:
            raise ArithmeticError('Initial output balance identity failed')
        prep['initial_observables'] = initial_values
    elif mode == 'calibration':
        initial = np.column_stack((states[0], states[0]))
        initial_ref = np.column_stack((states[1], states[1]))
        prep = dict(status='KNOWN_BASELINE_SHAM_ONLY_NO_NEW_INTERVENTION')
        prep_ref = prep.copy()
    else:
        raise ValueError('Unsupported mode')
    if output:
        np.savez_compressed(output/'initial.npz', primary=initial, independent=initial_ref)
    runs = []
    for label, start, dt in (('fine', initial, PROTOCOL['dt_fine']),
                             ('coarse', initial, PROTOCOL['dt_coarse']),
                             ('reference', initial_ref, PROTOCOL['dt_fine'])):
        def checkpoint(step, t, y):
            if output:
                temp = output/(label+'_checkpoint.tmp.npz')
                np.savez_compressed(temp, state=y, step=step, time=t)
                os.replace(temp, output/(label+'_checkpoint.npz'))
        runs.append(propagate(model, start, horizon=horizon, dt=dt,
                              sample_interval=PROTOCOL['sample_interval'],
                              physicality_interval=PROTOCOL['physicality_interval'],
                              tolerance=PROTOCOL['state_tolerance'], checkpoint=checkpoint))
    result = analyze(*runs, baseline_flux=raw[0]['F'], reference_flux=raw[1]['F'], policy=PROTOCOL)
    if mode == 'calibration':
        result.pop('primary')
        result['scientific_status'] = 'NO_INTERVENTION_VERDICT_DURING_CALIBRATION'
    result.update(preparation=prep, reference_preparation=prep_ref)
    return runs, result


def _run(config, output):
    started = time.perf_counter(); report = output/'report'; full = output/'full'
    report.mkdir(); full.mkdir(); env = environment()
    save(report/'config.json', config); save(report/'environment_before.json', env)
    gate = preflight(config, env)  # Must precede assembly or any solve.
    save(report/'preflight.json', gate)
    actual = dict.fromkeys(gate['counts'], 0); records = []; phases = []
    for case in gate['cases']:
        begin = time.perf_counter(); print('START', case['id'], flush=True)
        model = select_observables(make_full(case)); assembly = time.perf_counter()-begin
        states, raw, numerical = solve_baseline(model)
        actual['NESS'] += 1; actual['refinement_NESS'] += 1
        published = gate['evidence'][case['id']]['raw']
        for n in ('F', 'J_h', 'h6', 'P_m6_N2', 'inventory'):
            if abs(raw[0][n]-published[n]) > 1e-8:
                raise ArithmeticError('Published baseline mismatch: '+n)
        case_dir = full/case['id']; case_dir.mkdir()
        runs, result = run_case(model, states, raw, mode=config['mode'], horizon=gate['horizon'], output=case_dir,
                                dimensions=tuple(PROTOCOL['dimensions']))
        for r in runs:
            actual['propagations'] += 1; actual['block_steps'] += r['steps']
            actual['block_rhs_calls'] += r['block_rhs_calls']; actual['scalar_rhs_equivalents'] += r['scalar_rhs_equivalents']
        arrays = {'names':np.array(runs[0]['names']), 'raw_uncertainty':result.pop('raw_uncertainty')}
        for label, r in zip(('fine', 'coarse', 'reference'), runs):
            for n in ('time', 'flux', 'sample_time', 'raw'):
                arrays[label+'_'+n] = r[n]
            save(report/(case['id']+'_'+label+'_physicality.json'), r['checks'])
        np.savez_compressed(report/(case['id']+'_series.npz'), **arrays)
        record = dict(id=case['id'], case=case, baseline=raw, numerical=numerical, result=result)
        save(report/(case['id']+'_case.json'), record); records.append(record)
        phases.append(dict(id=case['id'], assembly=assembly, baseline=numerical['seconds'],
                           propagation=sum(r['elapsed_seconds'] for r in runs), total=time.perf_counter()-begin,
                           factor_bytes=max(m['factor_storage_bytes'] for m in numerical['solvers'])))
        save(report/'progress.json', dict(actual_counts=actual, phases=phases))
        print('DONE', case['id'], flush=True)
        del model, states, runs; gc.collect()
    after = environment()
    rt = runtime_gate(config['forecast'], time.perf_counter()-started, gate['counts'], actual,
                      gate['environment']['comparable'], config['mode'] == 'production')
    if actual != gate['counts']:
        raise ArithmeticError('Executed workload differs from contract')
    metrics = dict(runtime_gate=rt, actual_counts=actual, phases=phases, environment_after=after,
                   kernel_sha256=kernel_hash(), implementation_sha256=implementation_hash(),
                   protocol_sha256=protocol_hash(), source_commit=config['source_commit'],
                   science='FINITE_WINDOW_INTERVENTION_ONLY_NO_AUTOMATIC_ACCEPTANCE')
    save(report/'metrics.json', metrics)
    if config['mode'] == 'calibration':
        # Extrapolate ONLY matching method/columns/checkpoint workload. Export
        # and preparation reserve is explicit; initial range is engineering.
        predicted = sum(p['assembly']+p['baseline']+10*p['propagation']+2. for p in phases)+2.
        memory = dict(config['memory_budget'])
        memory.update(measured_peak_rss_bytes=after['max_rss_kib']*1024,
                      measured_peak_vm_bytes=after['process_vm_size_bytes'],
                      simultaneous_factor_storage_bytes=max(p['factor_bytes'] for p in phases))
        memory['peak_additional_bytes'] = max(memory['peak_additional_bytes'], memory['measured_peak_rss_bytes'], memory['measured_peak_vm_bytes'])
        save(report/'calibration.json', dict(status='CALIBRATION_COMPLETE', counts=actual,
             protocol_sha256=protocol_hash(), implementation_sha256=implementation_hash(), environment=env,
             memory_budget=memory, production_forecast=dict(expected_seconds=predicted,
             lower_seconds=.5*predicted, upper_seconds=2.*predicted,
             basis='3 measured setups + 6 NESS + 10x two-second matching propagations/checkpoints + 8s preparation/export reserve; inspect range after first run')))
    lines = [f"Время: прогноз {rt['expected_seconds']:.6g} с; внутренний факт {rt['actual_seconds']:.6g} с; статус {rt['status']}.",
             'Полное время процесса проверяется отдельно по run.json.', '', '# E002e CORR v001', '',
             'Режим: '+config['mode']+'. Никакой автоматической научной приёмки.',
             'Источник: '+config['source_commit']+'.',
             'План/факт: '+json.dumps(gate['counts'])+' / '+json.dumps(actual)+'.', '',
             '| Модель | Среднее относительное отклонение потока за H=20 | Вердикт |', '|---|---:|---|']
    for r in records:
        v = r['result'].get('primary')
        lines.append(f"|{r['case']['model']}|{v['value'] if v else '—'}|{v['status'] if v else 'CALIBRATION_SHAM_ONLY'}|")
    lines += ['', 'Ненулевой эффект относится ко всем межподсистемным корреляциям, включая классические.',
              'Локальные состояния сохранены только в начальный момент. Энергия взаимодействия может изменяться.',
              'Сравнения между моделями разведочные: исходные возмущения и генераторы различаются.',
              'Хвост за H не оценён. Время восстановления, Фано и автопоэзис не назначаются.',
              'Численные интервалы инженерные, не строгие границы и не статистические сигмы.']
    text = '\n'.join(lines)+'\n'
    (report/'RESULT.md').write_text(text); (report/'README.md').write_text(text)
    # Nested checkpoint paths are published as hashes only, never raw matrices.
    entries = []
    import hashlib
    for p in sorted(full.rglob('*')):
        if p.is_file():
            entries.append(dict(path=p.relative_to(full).as_posix(), size=p.stat().st_size,
                                sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    save(report/'full_manifest.json', dict(files=entries, total_bytes=sum(e['size'] for e in entries)))
    save(report/'data_manifest.json', dict(full_files=entries, full_total_bytes=sum(e['size'] for e in entries),
         selection='Every declared sampled observable and all-step flux published; full states/checkpoints retained on VM'))
    save(report/'status.json', dict(status='COMPLETED_NOT_ACCEPTED', mode=config['mode']))
    write_manifest(report)
    from .verify import verify_report
    verify_report(report)
    return metrics


def run(config, output):
    output = Path(output)
    if (output/'report').exists() or (output/'full').exists():
        raise FileExistsError('Refusing to overwrite existing run')
    output.mkdir(parents=True, exist_ok=True); started = time.perf_counter()
    try:
        return _run(config, output)
    except Exception as exc:
        report = output/'report'; report.mkdir(exist_ok=True)
        save(report/'failure.json', dict(type=type(exc).__name__, message=str(exc),
             elapsed_seconds=time.perf_counter()-started, traceback=traceback.format_exc()))
        save(report/'status.json', dict(status='FAILED', scientific_acceptance=False))
        text = 'Время: NOT_EVALUABLE; аварийное завершение.\n\n'+str(exc)+'\nЧастичные данные не приняты.\n'
        (report/'RESULT.md').write_text(text); (report/'README.md').write_text(text)
        write_manifest(report)
        raise


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--config', required=True); parser.add_argument('--output', required=True)
    args = parser.parse_args(); run(json.loads(Path(args.config).read_text()), Path(args.output))


if __name__ == '__main__':
    main()
