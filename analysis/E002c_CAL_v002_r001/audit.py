"""Audit caches fetched from pinned GitHub commits; never access the VM."""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

RUN = 'E002c_CAL_v002_r001'
SOURCE = 'ca15a197834bc3193f3da87d1bbd9ab1a538bf90'
REPORT = '26ddea1e48f1c48d8ae767d389452297376a5b1f'
REPO = Path(__file__).resolve().parents[2]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--github-cache', type=Path, required=True)
    p.add_argument('--source-cache', type=Path, required=True)
    p.add_argument('--output', type=Path, default=Path(__file__).resolve().parent)
    args = p.parse_args()
    sys.path.insert(0, str(REPO / 'infra'))
    from github_result_reader import read_github_result
    raw = json.loads((args.github_cache / 'run.json').read_text())
    prefix = 'results/' + RUN + '/'
    def fetch(repository, path, ref):
        assert repository == 'IgorSabirov/vm-lab' and ref == REPORT
        assert path.startswith(prefix)
        return (args.github_cache / path[len(prefix):]).read_bytes()
    result = read_github_result(fetch, repository='IgorSabirov/vm-lab',
        result_commit=REPORT, run_id=RUN, source_commit=SOURCE)
    assert result['execution_succeeded'] and raw['full_data_inventory_errors'] == []
    for name, expected in raw['input_sha256'].items():
        assert hashlib.sha256((args.source_cache / name).read_bytes()).hexdigest() == expected, name
    sys.path.insert(0, str(args.source_cache))
    from e002c_exp.verify import verify
    exported = args.github_cache / 'files'
    metrics = json.loads((exported / 'metrics.json').read_text())
    checks = json.loads((exported / 'checks.json').read_text())
    config = json.loads((args.source_cache / 'config.json').read_text())
    plan = json.loads((args.source_cache / 'experiments/e002c/calibration_v002.json').read_text())
    job = raw['job']; actual = job['finished'] - job['started']
    rt = checks['runtime_gate']
    assert config['forecast'] == plan['forecast']
    assert metrics['identity'] == dict(run_id=RUN, source_commit=SOURCE)
    time_gate = dict(expected_seconds=rt['expected_seconds'], actual_seconds=actual,
        lower_seconds=rt['lower_seconds'], upper_seconds=rt['upper_seconds'],
        actual_over_expected=actual/rt['expected_seconds'],
        deviation_percent=(actual/rt['expected_seconds']-1)*100,
        queue_seconds=job['started']-job['created'],
        internal_seconds=rt['actual_seconds'],
        status='PASS' if rt['lower_seconds']<=actual<=rt['upper_seconds'] else 'REVIEW_REQUIRED')
    print(json.dumps(dict(time_first=time_gate)))
    assert time_gate['status'] == rt['status'] == 'REVIEW_REQUIRED'
    verified = verify(exported)
    assert checks['failures'] == [] and checks['work_volume_pass']
    assert metrics['fit'] is None and metrics['ic_structural_status'] == 'not_run'
    assert checks['pairs'] == {} and metrics['numerical_valid'] is False
    expected_cases = {c['id']: c for c in plan['cases']}
    assert set(expected_cases) == {s['case']['id'] for s in metrics['cases']}
    expected_work = dict(trajectories=12, fit_trajectories=0, steps=25000,
        expected_steps=25000, rhs_calls=100000, scalar_records=1262,
        diagnostic_records=136, snapshots=80)
    assert metrics['work'] == expected_work
    snap_times = (0,.2,1,2,5,10,20,50,100,190,200,300,390,400)
    for s in metrics['cases']:
        c = s['case']; T = c['horizon']
        assert c == expected_cases[c['id']] and s['failed'] is None
        assert s['horizon'] == T and s['extended'] is False
        assert s['steps'] == round(T/c['dt']) and s['rhs_calls'] == 4*s['steps']
        assert s['scalar_records'] == round(T/.2)+1
        assert s['diagnostic_records'] == math.floor(T/2)+1
        assert s['snapshots'] == sum(t<=T for t in snap_times)
    paths = ['e002_exp/model.py','data/e002b_targets.json','experiments/e002c/plan.json',
             'experiments/e002c/calibration_v002.json','e002c_exp/provenance.json']
    paths += sorted(p.relative_to(args.source_cache).as_posix()
                    for p in (args.source_cache/'e002c_exp').glob('*.py'))
    kernel = hashlib.sha256()
    for path in paths:
        kernel.update(path.encode()+b'\0'+(args.source_cache/path).read_bytes())
    assert kernel.hexdigest() == metrics['environment']['kernel_sha256']
    cases = metrics['cases']
    elapsed = sum(s['elapsed_seconds'] for s in cases)
    integration = sum(s['integrator_seconds'] for s in cases)
    diagnostic = sum(s['diagnostic_seconds'] for s in cases)
    timing = dict(integration_seconds=integration, diagnostic_seconds=diagnostic,
        other_trajectory_seconds=elapsed-integration-diagnostic,
        outside_trajectory_seconds=actual-elapsed,
        other_trajectory_includes='build, scalar sampling, snapshots/PT, I/O and loop overhead; not separately instrumented',
        outside_trajectory_includes='imports, preflight, exports and final report verification; not separately instrumented')
    per_case = [dict(id=s['case']['id'], model=s['case']['model'], horizon=s['horizon'],
        steps=s['steps'], elapsed_seconds=s['elapsed_seconds'],
        integrator_seconds=s['integrator_seconds'], diagnostic_seconds=s['diagnostic_seconds']) for s in cases]
    coefficient = actual / expected_work['steps']
    branches = {}
    for name, steps in [('mandatory_only',1600000),('fit_maximum',480000),
        ('validation_base',60000),('transfer_base',560000),('all_IC_additions_maximum_base',1100000),
        ('all_base_stages_maximum',2700000),('all_stages_with_all_extensions',4920000)]:
        seconds = coefficient*steps
        branches[name] = dict(steps=steps,expected_seconds=seconds,
            lower_seconds=.6*seconds,upper_seconds=1.4*seconds)
    forecast = dict(status='CANDIDATE_PENDING_USER_ACCEPTANCE',accepted_by_user=False,
        production_submitted=False,source_commit=SOURCE,report_commit=REPORT,
        kernel_sha256=kernel.hexdigest(),numpy_version=metrics['environment']['numpy'],
        scipy_version=metrics['environment']['scipy'],seconds_per_step=coefficient,
        fixed_seconds=0.,relative_band=.4,
        formula='T_seconds = 0 + total_executed_RK4_steps * seconds_per_step',
        basis='Complete external process duration / 25000 steps. All calibration setup, diagnostics, I/O and report costs are amortized; do not add them again.',
        limitations=['One complete calibration run, no timing confidence interval.',
          'Constant coefficient approximates different models and dt; fit dt=.02 and production dt=.005 were not timed here.',
          'Short calibration has more setup and snapshots per step; long-horizon cost and future load remain uncertain.',
          'The +/-40% interval is a declared engineering band, not a statistical guarantee.',
          'T40 gamma=0 probes do not determine how many T200 trajectories need extension.'],
        branches=branches)
    quality = {}
    import numpy as np
    schema = json.loads((exported/'schema.json').read_text())['diagnostics']
    arrays = [np.load(exported/'diagnostics'/f"{s['case']['id']}.npz",allow_pickle=False)['values'] for s in cases]
    for name in ('trace','hermiticity','min_eigen','rhs'):
        vals = np.concatenate([a[:,schema.index(name)] for a in arrays])
        quality[name] = dict(minimum=float(vals.min()), maximum=float(vals.max()),
                            scope='published diagnostic rows only')
    audit = dict(run_id=RUN,report_commit=REPORT,source_commit=SOURCE,
        time_first=time_gate,technical_status='VERIFIED_EXPORTED_ARRAYS',
        deviation_review=dict(status='EXPLAINED_PENDING_USER_ACCEPTANCE',
            cause='Uncalibrated engineering forecast overestimated the measured full-cycle cost. No reduced workload, resumed run or omitted output detected.',
            original_runtime_status_preserved=True,user_acceptance=None),
        source_files_verified=len(raw['input_sha256']),exported_files_verified=len(raw['files']),
        exported_bytes=sum(x['bytes'] for x in raw['files'].values()),
        full_data_accessed=False,work=expected_work,kernel_sha256=kernel.hexdigest(),
        environment=metrics['environment'],timing=timing,per_case=per_case,
        quality_on_published_rows=quality,independent_verifier=verified,
        dt_refinement_measured_on_VM=False,production_submitted=False)
    args.output.mkdir(parents=True,exist_ok=True)
    for name,value in [('audit.json',audit),('forecast_candidate.json',forecast)]:
        (args.output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(technical_status=audit['technical_status'],work=expected_work,
                         source_files=audit['source_files_verified'],output_files=audit['exported_files_verified'])))

if __name__ == '__main__':
    main()
