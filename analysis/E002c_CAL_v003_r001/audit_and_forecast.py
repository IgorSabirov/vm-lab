"""Reproduce calibration audit and a pre-run component forecast from pinned GitHub caches.

No VM access, numerical trajectories, or changes to the calibrated kernel.
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import nnls

ROOT = Path(__file__).resolve().parents[2]
RUN = 'E002c_CAL_v003_r001'
SOURCE = 'd07886660ce3e5b85ca17b17fb9d7913d5f13548'
REPORT = '5764c8c582c2383e735207b291597f2779ee5afd'
KERNEL = '0e9791fae65f6ec063a1328ab6e71e5b2a8fc3b5a16fa87b3a96c1b2e92002d1'
SNAPS = (0, .2, 1, 2, 5, 10, 20, 50, 100, 190, 200, 300, 390, 400)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--github-cache', type=Path, required=True)
    parser.add_argument('--source-cache', type=Path, required=True)
    args = parser.parse_args()
    raw = json.loads((args.github_cache / 'run.json').read_text())
    checks = json.loads((args.github_cache / 'files/checks.json').read_text())
    job = raw['job']; rt = checks['runtime_gate']
    actual = job['finished'] - job['started']
    time_gate = dict(expected_seconds=52, actual_seconds=actual,
        lower_seconds=30, upper_seconds=90, deviation_seconds=actual-52,
        deviation_percent=100*(actual/52-1), queue_seconds=job['started']-job['created'],
        internal_seconds=rt['actual_seconds'], publication_seconds=None,
        publication_note='Not measured in run.json; excluded from the process-time gate.',
        status='PASS' if 30 <= actual <= 90 else 'REVIEW_REQUIRED')
    print(json.dumps(dict(time_first=time_gate)))
    assert time_gate['status'] == rt['status'] == 'PASS'
    assert (rt['expected_seconds'], rt['lower_seconds'], rt['upper_seconds']) == (52, 30, 90)
    sys.path.insert(0, str(ROOT / 'infra'))
    from github_result_reader import read_github_result
    prefix = 'results/' + RUN + '/'
    def fetch(repository, path, ref):
        assert repository == 'IgorSabirov/vm-lab' and ref == REPORT and path.startswith(prefix)
        return (args.github_cache / path[len(prefix):]).read_bytes()
    result = read_github_result(fetch, repository='IgorSabirov/vm-lab',
        result_commit=REPORT, run_id=RUN, source_commit=SOURCE)
    assert result['execution_succeeded'] and raw['full_data_inventory_errors'] == []
    for name, expected in raw['input_sha256'].items():
        assert hashlib.sha256((args.source_cache / name).read_bytes()).hexdigest() == expected, name
    sys.path.insert(0, str(args.source_cache))
    from e002c_exp.verify import verify
    from e002c_exp.task import kernel_hash
    verified = verify(args.github_cache / 'files')
    metrics = json.loads((args.github_cache / 'files/metrics.json').read_text())
    assert kernel_hash() == metrics['environment']['kernel_sha256'] == KERNEL
    assert metrics['identity'] == dict(run_id=RUN, source_commit=SOURCE)
    assert checks['failures'] == [] and checks['work_volume_pass'] and checks['export_complete']
    work = dict(trajectories=12, fit_trajectories=0, steps=25000, expected_steps=25000,
                rhs_calls=100000, scalar_records=1262, diagnostic_records=136, snapshots=80)
    assert metrics['work'] == work and metrics['fatal'] is None
    cal = json.loads((args.source_cache / 'experiments/e002c/calibration_v002.json').read_text())
    expected_cases = {c['id']: c for c in cal['cases']}
    cases = metrics['cases']
    assert {s['case']['id'] for s in cases} == set(expected_cases)
    for s in cases:
        c = s['case']; T = c['horizon']
        assert c == expected_cases[c['id']] and s['failed'] is None and not s['extended']
        assert s['horizon'] == T and s['steps'] == round(T/c['dt']) and s['rhs_calls'] == 4*s['steps']
        assert s['scalar_records'] == round(T/.2)+1 and s['diagnostic_records'] == math.floor(T/2)+1
        assert s['snapshots'] == sum(t <= T for t in SNAPS)
    names = json.loads((args.github_cache/'files/schema.json').read_text())['diagnostics']
    arrays = [np.load(args.github_cache/'files/diagnostics'/f"{s['case']['id']}.npz")['values'] for s in cases]
    quality = {}
    for name in ('trace', 'hermiticity', 'min_eigen', 'rhs'):
        values = np.concatenate([a[:, names.index(name)] for a in arrays])
        quality[name] = dict(minimum=float(values.min()), maximum=float(values.max()))
    audit = dict(run_id=RUN, source_commit=SOURCE, report_commit=REPORT, time_first=time_gate,
        status=verified['status'], source_files_verified=len(raw['input_sha256']),
        output_files_verified=len(raw['files']), output_bytes=sum(x['bytes'] for x in raw['files'].values()),
        work=work, environment=metrics['environment'], quality_published_rows=quality,
        independent_verifier=verified, full_data_accessed=False,
        stationarity_pass_count=sum(s['stationarity']['pass_gate'] for s in cases),
        stationarity_note='Short calibration probes are timing/physical-quality tests, not stationary production results.',
        dt_refinement_measured_on_VM=False,
        acceptance=dict(scope='v003 technical calibration and permission to launch production if checks pass',
            user_instruction='Проверь результаты и если все прошло дай команду на запуск основного прогона',
            conditions_satisfied=True, old_v002_status_unchanged=True))
    save(Path(__file__).parent/'audit.json', audit)

    # Measured integration and diagnostic components, each counted exactly once.
    rates = {m: sum(s['integrator_seconds'] for s in cases if s['case']['model'] == m) /
                sum(s['steps'] for s in cases if s['case']['model'] == m)
             for m in ('QS', 'RR_QS', 'IC1_QS')}
    diagnostic = sum(s['diagnostic_seconds'] for s in cases)/work['diagnostic_records']
    X = np.array([[1, s['snapshots'], s['scalar_records']] for s in cases])
    remainder = np.array([s['elapsed_seconds']-s['integrator_seconds']-s['diagnostic_seconds'] for s in cases])
    assert np.linalg.matrix_rank(X) == 3
    coefficients, residual_norm = nnls(X, remainder)
    outside = actual-sum(s['elapsed_seconds'] for s in cases)
    assert outside >= 0
    def cost(c, T=200, published=True):
        return (rates[c['model']]*round(T/c['dt']) + diagnostic*(int(T/2)+1) +
            float(coefficients @ [1, sum(t <= T for t in SNAPS), round(T/.2)+1]) +
            (outside/12 if published else 0))
    plan = json.loads((args.source_cache/'experiments/e002c/plan.json').read_text())
    main_cases, transfer = plan['cases'], plan['conditional_ic_cases']
    validation = [dict(model='IC1_QS', dt=dt, phi_over_pi=0, detuning=0, dephasing=.05, _stage='validation') for dt in (.01, .005)]
    fit_case = dict(model='IC1_QS', dt=.02)
    assert len(main_cases) == 72 and sum(round(200/c['dt']) for c in main_cases) == 1600000
    assert len(transfer) == 24 and sum(round(200/c['dt']) for c in transfer) == 560000
    slope = sum(rates[c['model']]*round(200/c['dt']) for c in main_cases)/1600000
    intercept = sum(cost(c) for c in main_cases)-slope*1600000
    def affine(steps): return intercept+slope*steps
    def group(cases):
        groups = {}
        for c in cases:
            key = (c.get('_stage'),) + tuple(c[k] for k in ('model', 'phi_over_pi', 'detuning', 'dephasing'))
            groups.setdefault(key, []).append(c)
        return list(groups.values())
    # For each structural branch and every possible fit count, find exact extrema
    # of component/affine over ALL independent group extension choices. At trial
    # ratio r, maximize/minimize C-r*A by taking each positive/negative increment.
    bounds = []
    scenarios = [('no_selected', main_cases), ('validation_rejected', main_cases+validation),
                 ('validation_passed', main_cases+validation+transfer)]
    for branch, selected in scenarios:
        increments = [(sum(cost(c,400)-cost(c,200) for c in g),
                       slope*sum(round(200/c['dt']) for c in g)) for g in group(selected)]
        for nfit in range(49):  # Includes impossible zero-fit success conservatively.
            steps = sum(round(200/c['dt']) for c in selected)+10000*nfit
            base_c = sum(cost(c) for c in selected)+nfit*cost(fit_case,published=False)
            base_a = affine(steps)
            endpoints = []
            for maximize in (False, True):
                lo, hi = 0., 3.
                for _ in range(60):
                    mid = (lo+hi)/2
                    value = base_c-mid*base_a+sum((max if maximize else min)(0,dc-mid*da) for dc,da in increments)
                    if value > 0: lo = mid
                    else: hi = mid
                endpoints.append((lo+hi)/2)
            bounds.append(dict(branch=branch,fit_computations=nfit,minimum_ratio=endpoints[0],maximum_ratio=endpoints[1]))
    reduction = dict(minimum_ratio=min(x['minimum_ratio'] for x in bounds),
                     maximum_ratio=max(x['maximum_ratio'] for x in bounds),
                     scope='All 3 structural branches, fit count 0..48, every paired-group extension subset; superset of executable branches.')
    assert .85 <= reduction['minimum_ratio'] <= reduction['maximum_ratio'] <= 1.15
    stages = {}
    for name, selected, T, publish in [('main_base',main_cases,200,True), ('main_extended',main_cases,400,True),
            ('fit_maximum', [fit_case]*48,200,False), ('validation_base',validation,200,True),
            ('validation_extended',validation,400,True),('transfer_base',transfer,200,True),('transfer_extended',transfer,400,True)]:
        steps = sum(round(T/c['dt']) for c in selected)
        stages[name] = dict(trajectories=len(selected),horizon=T,steps=steps,
            component_seconds=sum(cost(c,T,publish) for c in selected),
            affine_seconds=(intercept if name.startswith('main') else 0)+slope*steps)
    branches = {}
    for name, selected in scenarios:
        for T in (200,400):
            steps = sum(round(T/c['dt']) for c in selected)+480000
            central = affine(steps)
            branches[f'{name}_fit48_T{T}'] = dict(steps=steps,reported_trajectories=len(selected),fit_trajectories=48,
                component_seconds=sum(cost(c,T) for c in selected)+48*cost(fit_case,published=False),
                expected_seconds=central,lower_seconds=.6*central,upper_seconds=1.4*central)
    assert branches['validation_passed_fit48_T200']['steps'] == 2700000
    assert branches['validation_passed_fit48_T400']['steps'] == 4920000
    forecast = dict(status='FROZEN_BEFORE_PRODUCTION',calibration_report_commit=REPORT,calibration_source_commit=SOURCE,
        kernel_sha256=KERNEL,seconds_per_step=slope,fixed_seconds=intercept,relative_band=.4,
        formula='T_expected = fixed_seconds + seconds_per_step * declared_executed_RK4_steps; gate [0.6*T_expected,1.4*T_expected]',
        component_formula='sum(model_step_rate*N_steps + diagnostic_rate*N_diagnostic + remainder_coefficients@[1,N_snapshots,N_scalar] + outside_seconds/12 for published cases)',
        model_step_rates=rates,diagnostic_rate=diagnostic,remainder_coefficients=coefficients.tolist(),
        remainder_design_columns=['case','snapshot','scalar_record'],remainder_residual_l2_seconds=residual_norm,
        remainder_max_abs_residual_seconds=float(np.max(abs(X@coefficients-remainder))),
        outside_seconds=outside,outside_allocation_per_published_case=outside/12,
        reduction=reduction,stages=stages,branches=branches,
        no_double_counting='Integration/diagnostics subtracted before remainder fit. Outside process cost allocated once to published cases. No additional total-cycle-per-step term.',
        limitations=['Remainder coefficients are an empirical regression, not independently measured setup/snapshot/scalar timers.',
            'Outside process cost is allocated per published case; fixed imports and variable export cannot be separated by this one calibration.',
            'dt=.005 and .02 use the same RK4 kernel but were not separately timed on the VM; IC alpha varies in the search.',
            'T200/T400 costs extrapolate T5/T20/T40. The +/-40% engineering band covers reduction error, load, long-horizon export and uninstrumented search/report overhead; it is not a confidence interval.',
            'Stationarity of T40 does not predict extension counts. No post-hoc threshold or forecast change is permitted.',
            'Pair summary elapsed_seconds overlap because both members are finished after the group; do not sum production elapsed_seconds as independent process time.'])
    save(ROOT/'experiments/e002c/production_v001_forecast.json', forecast)
    print(json.dumps(dict(audit='PASS',kernel=KERNEL,affine=dict(fixed_seconds=intercept,seconds_per_step=slope),reduction=reduction,branches=branches)))


if __name__ == '__main__':
    main()
