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
from e002_exp.model import maxabs, adjoint_jump
from e002c_exp.model import operators
from e002e_exp.model import make_full
from e002e_exp.numerics import Bordered, state_checks, values, refinement_check
from e002e_exp.export import serial, real_values, write_manifest
from e002e_exp.runtime import environment, runtime_gate, kernel_hash
from .core import prepare, propagate, analyze
from .plan import (PROTOCOL, SOLVERS, LIMITS, preflight, implementation_hash, protocol_hash,
                   implementation_manifest, storage_preflight, workload)
from .reporting import render_result


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
            if op.shape != (216,216):
                raise ValueError('edge_L operator must already be lifted by the pinned builder')
            result['edge_L_'+str(i)] = op
        for m in range(8):
            result['mask_'+str(m)] = sp.kron(sp.eye(8), o['masks'][m], format='csr')
    if any(op.shape != (model['space'].d,model['space'].d) for op in result.values()):
        raise ValueError('Observable dimension mismatch')
    return dict(model, observables=result)


def output_balance(model):
    if model['space'].d != 216:
        return dict(status='SYNTHETIC_MODEL_NOT_FULL_OUTPUT_BALANCE')
    sinks = [c for name,c in model['jumps'] if name == 'sink_2']
    if len(sinks) != 1:
        raise ValueError('Missing/ambiguous sink operator')
    n = model['n'][2]; loss = sinks[0].getH()@sinks[0]
    kappa = float(loss.diagonal().sum().real/n.diagonal().sum().real)
    F = model['observables']['F']; J = model['observables']['J_h']; H = model['H']
    adj = 1j*(H@F-F@H)+sum(adjoint_jump(c,F) for _,c in model['jumps'])
    residual = max(maxabs(loss-kappa*n),maxabs(F-kappa*n),maxabs(adj-kappa*(J-F)))
    if kappa <= 0 or residual > PROTOCOL['operator_tolerance']:
        raise ArithmeticError('Full output-balance operator identity failed')
    return dict(status='OPERATOR_IDENTITY_VERIFIED',kappa_out=kappa,residual=residual)


def preparation_diagnostics(model, initial, baseline, prep, balance):
    initial_values = real_values(values(model,initial[:,1]))
    if abs(initial_values['F']-baseline['F']) > PROTOCOL['operator_tolerance']:
        raise ArithmeticError('Marginal-preserving intervention changed initial flux')
    derivative = model['L']@(initial[:,1]-initial[:,0])
    df = complex(model['space'].row(model['observables']['F'])@derivative)
    if abs(df.imag) > PROTOCOL['operator_tolerance']:
        raise ArithmeticError('Initial flux derivative is complex')
    prep.update(delta_flux_derivative_at_zero=float(df.real),
                delta_h_at_zero=initial_values['J_h']-baseline['J_h'],
                initial_observables=initial_values, output_balance=balance)
    if balance['status'] == 'OPERATOR_IDENTITY_VERIFIED':
        residual = abs(df.real-balance['kappa_out']*prep['delta_h_at_zero'])
        if residual > PROTOCOL['operator_tolerance']:
            raise ArithmeticError('Initial output balance identity failed')
        prep['initial_balance_residual'] = float(residual)


def atomic_npz(path, **arrays):
    path = Path(path); temp = path.with_name(path.stem+'.tmp.npz')
    try:
        np.savez_compressed(temp, **arrays)
        os.replace(temp,path)
    finally:
        temp.unlink(missing_ok=True)


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
    preparation_started = time.perf_counter()
    balance = output_balance(model)
    if mode == 'production':
        initial, prep = prepare(model, states[0], dimensions, PROTOCOL['operator_tolerance'])
        initial_ref, prep_ref = prepare(model, states[1], dimensions, PROTOCOL['operator_tolerance'])
        for x,b,p in ((initial,raw[0],prep),(initial_ref,raw[1],prep_ref)):
            preparation_diagnostics(model,x,b,p,balance)
    elif mode == 'calibration':
        initial = np.column_stack((states[0], states[0]))
        initial_ref = np.column_stack((states[1], states[1]))
        prep = dict(status='KNOWN_BASELINE_SHAM_ONLY_NO_NEW_INTERVENTION')
        prep_ref = prep.copy()
    else:
        raise ValueError('Unsupported mode')
    if output:
        atomic_npz(output/'initial.npz', primary=initial, independent=initial_ref)
    preparation_seconds = time.perf_counter()-preparation_started
    runs = []
    for label, start, dt in (('fine', initial, PROTOCOL['dt_fine']),
                             ('coarse', initial, PROTOCOL['dt_coarse']),
                             ('reference', initial_ref, PROTOCOL['dt_fine'])):
        io = dict(seconds=0.,writes=0,bytes_written=0)
        def checkpoint(step, t, y):
            if output:
                tick = time.perf_counter(); path = output/(label+'_checkpoint.npz')
                atomic_npz(path,state=y,step=step,time=t)
                io['seconds'] += time.perf_counter()-tick
                io['writes'] += 1; io['bytes_written'] += path.stat().st_size
        runs.append(propagate(model, start, horizon=horizon, dt=dt,
                              sample_interval=PROTOCOL['sample_interval'],
                              physicality_interval=PROTOCOL['physicality_interval'],
                              tolerance=PROTOCOL['state_tolerance'], checkpoint=checkpoint))
        runs[-1]['checkpoint_io'] = io
    result = analyze(*runs, baseline_flux=raw[0]['F'], reference_flux=raw[1]['F'], policy=PROTOCOL)
    if mode == 'calibration':
        result.pop('primary')
        result['scientific_status'] = 'NO_INTERVENTION_VERDICT_DURING_CALIBRATION'
    result.update(preparation=prep, reference_preparation=prep_ref, preparation_seconds=preparation_seconds)
    return runs, result


def _run(config, output):
    started = time.perf_counter(); report = output/'report'; full = output/'full'
    report.mkdir(); full.mkdir(); env = environment()
    save(report/'config.json', config); save(report/'environment_before.json', env)
    gate = preflight(config, env)  # Must precede assembly or any solve.
    gate['storage'] = storage_preflight(output)
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
            actual['checkpoint_writes'] += r['checkpoint_io']['writes']
            actual['block_rhs_calls'] += r['block_rhs_calls']; actual['scalar_rhs_equivalents'] += r['scalar_rhs_equivalents']
        arrays = {'names':np.array(runs[0]['names']), 'raw_uncertainty':result.pop('raw_uncertainty')}
        for label, r in zip(('fine', 'coarse', 'reference'), runs):
            for n in ('time', 'time_index', 'dt', 'flux', 'sample_time', 'sample_index', 'raw'):
                arrays[label+'_'+n] = r[n]
            save(report/(case['id']+'_'+label+'_physicality.json'), r['checks'])
        np.savez_compressed(report/(case['id']+'_series.npz'), **arrays)
        record = dict(id=case['id'], case=case, baseline=raw, numerical=numerical, result=result,
                      hilbert_dimension=model['space'].d, liouville_dimension=model['space'].size,
                      role='PRIMARY' if case['model'] == PROTOCOL['primary_model'] else 'COMPARATIVE_CONTROL')
        save(report/(case['id']+'_case.json'), record); records.append(record)
        phases.append(dict(id=case['id'], assembly=assembly, baseline=numerical['seconds'],
                           propagation=sum(r['elapsed_seconds'] for r in runs), total=time.perf_counter()-begin,
                           checkpoint_io_seconds=sum(r['checkpoint_io']['seconds'] for r in runs),
                           checkpoint_bytes_written=sum(r['checkpoint_io']['bytes_written'] for r in runs),
                           preparation_and_initial_io_seconds=result['preparation_seconds'],
                           factor_bytes=max(m['factor_storage_bytes'] for m in numerical['solvers'])))
        save(report/'progress.json', dict(actual_counts=actual, phases=phases))
        print('DONE', case['id'], flush=True)
        del model, states, runs; gc.collect()
    if actual != gate['counts']:
        raise ArithmeticError('Executed workload differs from contract')
    export_started = time.perf_counter()
    comparisons = []
    if config['mode'] == 'production':
        by_model = {r['case']['model']:r['result']['primary'] for r in records}
        q = by_model['QS']
        for name in ('RR_QS', 'IC1_QS'):
            c = by_model[name]; value = q['value']-c['value']; u = q['uncertainty']+c['uncertainty']
            comparisons.append(dict(comparison='QS_minus_'+name, delta_relative_response=value,
                uncertainty=u, interval=[value-u,value+u], role='SECONDARY_DIFFERENT_INITIAL_PERTURBATIONS',
                interpretation='RELATIVE_SENSITIVITY_NOT_QUANTUM_ADVANTAGE_OR_RECOVERY_SPEED'))
    save(report/'comparisons.json', comparisons)
    entries = []
    import hashlib
    hashing_started = time.perf_counter()
    for p in sorted(full.rglob('*')):
        if p.is_file():
            if '.tmp' in p.name:
                raise ValueError('Temporary checkpoint cannot enter successful manifest')
            entries.append(dict(path=p.relative_to(full).as_posix(), size=p.stat().st_size,
                                sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    hashing_seconds = time.perf_counter()-hashing_started
    save(report/'full_manifest.json', dict(files=entries, total_bytes=sum(e['size'] for e in entries)))
    save(report/'data_manifest.json', dict(full_files=entries, full_total_bytes=sum(e['size'] for e in entries),
         selection='All-step flux and declared sampled observables published; initial states and LAST rolling checkpoint per propagation retained on VM; NO RESUME',
         full_states_published=False, checkpoint_retention='LAST_ONLY_NO_RESUME',
         root_manifest_integrity='PINNED_BY_ENCLOSING_SERVICE_MANIFEST_AND_GIT_COMMIT'))
    save(report/'dependencies.json', implementation_manifest())
    save(report/'status.json', dict(status='COMPLETED_NOT_ACCEPTED', mode=config['mode']))
    after = environment()
    rt = runtime_gate(config['forecast'], time.perf_counter()-started, gate['counts'], actual,
                      gate['environment']['comparable'], config['mode'] == 'production')
    metrics = dict(runtime_gate=rt, actual_counts=actual, phases=phases, environment_after=after,
                   kernel_sha256=kernel_hash(), implementation_sha256=implementation_hash(),
                   protocol_sha256=protocol_hash(), source_commit=config['source_commit'],
                   full_manifest_hashing_seconds=hashing_seconds,
                   science='FINITE_WINDOW_INTERVENTION_ONLY_NO_AUTOMATIC_ACCEPTANCE')
    def publish_summary():
        save(report/'metrics.json',metrics)
        text = render_result(config,metrics,records)
        (report/'RESULT.md').write_text(text); (report/'README.md').write_text(text)
        write_manifest(report)
    publish_summary()
    export_seconds = time.perf_counter()-export_started
    from .verify import verify_report
    verify_started = time.perf_counter()
    verify_report(report)
    verification_seconds = time.perf_counter()-verify_started
    metrics.update(report_export_seconds=export_seconds, verification_seconds=verification_seconds,
                   timing_scope='THROUGH_FIRST_VERIFICATION; final summary/manifest rewrite and second verification require enclosing service time')
    metrics['runtime_gate'] = runtime_gate(config['forecast'], time.perf_counter()-started, gate['counts'], actual,
                                           gate['environment']['comparable'], config['mode'] == 'production')
    if config['mode'] == 'calibration':
        # Compute and I/O scale by their own work counts; verification and
        # report export are measured, not omitted. Calibration is sham only.
        step_scale = PROTOCOL['horizon']/gate['horizon']
        io_scale = workload()['checkpoint_writes']/actual['checkpoint_writes']
        components = dict(setup_and_solvers=sum(p['assembly']+p['baseline'] for p in phases),
             propagation_compute=step_scale*sum(max(0.,p['propagation']-p['checkpoint_io_seconds']) for p in phases),
             checkpoint_io=io_scale*sum(p['checkpoint_io_seconds'] for p in phases),
             case_export_and_diagnostics=step_scale*sum(max(0.,p['total']-p['assembly']-p['baseline']-p['propagation']) for p in phases),
             report_export=step_scale*export_seconds, verification=2*step_scale*verification_seconds,
             preparation_reserve=8.)
        predicted = sum(components.values())
        memory = dict(config['memory_budget'])
        memory.update(measured_peak_rss_bytes=after['max_rss_kib']*1024,
                      measured_peak_vm_bytes=after['process_vm_size_bytes'],
                      simultaneous_factor_storage_bytes=max(p['factor_bytes'] for p in phases))
        memory['peak_additional_bytes'] = max(memory['peak_additional_bytes'],memory['measured_peak_rss_bytes'],memory['measured_peak_vm_bytes'])
        save(report/'calibration.json',dict(status='CALIBRATION_COMPLETE',runtime_review_status='PENDING',
             report_commit=None,counts=actual,protocol_sha256=protocol_hash(),implementation_sha256=implementation_hash(),
             environment=env,memory_budget=memory,forecast_components_seconds=components,
             checkpoint_measurement=dict(writes=actual['checkpoint_writes'],
                 bytes_written=sum(p['checkpoint_bytes_written'] for p in phases),retained_full_bytes=sum(e['size'] for e in entries)),
             production_forecast=dict(expected_seconds=predicted,lower_seconds=.5*predicted,upper_seconds=2.*predicted,
                 basis='Measured matching setup/solves, step-scaled compute, count-scaled checkpoint I/O, export, two verifications, explicit 8s preparation reserve; full process review remains mandatory')))
    publish_summary()
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
