"""Reconstruct the failed forecast from pinned GitHub data, without VM access."""
import argparse
import hashlib
import json
import re
from pathlib import Path

def read(p):return json.loads(p.read_text())
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline-cache',type=Path,required=True)
    p.add_argument('--github-cache',type=Path,required=True)
    p.add_argument('--source-cache',type=Path,required=True)
    p.add_argument('--replay-json',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    oldrun=read(a.baseline_cache/'run.json');old=read(a.baseline_cache/'files/metrics.json')
    run=read(a.github_cache/'run.json');new=read(a.github_cache/'files/metrics.json')
    for cache,r in [(a.baseline_cache,oldrun),(a.github_cache,run)]:
        raw=(cache/'files/metrics.json').read_bytes();declared=r['files']['files/metrics.json']
        assert len(raw)==declared['bytes'] and hashlib.sha256(raw).hexdigest()==declared['sha256']
    for path,sha in run['input_sha256'].items():
        assert hashlib.sha256((a.source_cache/path).read_bytes()).hexdigest()==sha
    generator=(a.source_cache/'experiments/e002c/build_plan.mjs').read_text()
    plan=read(a.source_cache/'experiments/e002c/plan.json')
    calibration=read(a.source_cache/'experiments/e002c/calibration_v002.json')
    assert 'const tStep=422.035/240000;' in generator
    assert 'const estimate=n=>Math.round(n*tStep*1.25+90);' in generator
    assert 'expected_seconds_provisional:120' in generator
    historical_elapsed=sum(s['elapsed_seconds'] for s in old['cases'].values())
    historical_steps=sum(s['steps'] for s in old['cases'].values())
    assert historical_steps==old['actual_steps']==240000
    assert round(historical_elapsed,3)==plan['runtime']['baseline_trajectory_seconds']
    assert new['work']['steps']==25000 and new['work']['trajectories']==12
    tstep=plan['runtime']['seconds_per_step'];factor=plan['runtime']['assumed_new_diagnostics_multiplier']
    old_n=plan['calibration']['main_steps'];new_n=calibration['main_steps']
    old_forecast=plan['calibration']['expected_seconds_provisional']
    total_forecast=calibration['forecast']['expected_seconds'];ratio=new_n/old_n
    known_old=old_n*tstep*factor;unexplained_old=old_forecast-known_old
    known_new=new_n*tstep*factor;scaled_remainder=unexplained_old*ratio
    manual_allowance=total_forecast-old_forecast*ratio
    assert abs(known_new+scaled_remainder+manual_allowance-total_forecast)<1e-10
    actual=run['job']['finished']-run['job']['started']
    assert calibration['forecast']['lower_seconds']>known_new
    assert old['numpy']==new['environment']['numpy'] and old['scipy']==new['environment']['scipy']
    assert oldrun['input_sha256']['e002_exp/model.py']==run['input_sha256']['e002_exp/model.py']
    cases=new['cases'];integration=sum(s['integrator_seconds'] for s in cases)
    diagnostic=sum(s['diagnostic_seconds'] for s in cases)
    elapsed=sum(s['elapsed_seconds'] for s in cases)
    rates={}
    for model in ('QS','RR_QS','IC1_QS'):
        ss=[s for s in cases if s['case']['model']==model]
        rates[model]=dict(steps=sum(s['steps'] for s in ss),
          integration_seconds=sum(s['integrator_seconds'] for s in ss),
          weighted_integration_seconds_per_step=sum(s['integrator_seconds'] for s in ss)/sum(s['steps'] for s in ss),
          min_case_seconds_per_step=min(s['integrator_seconds']/s['steps'] for s in ss),
          max_case_seconds_per_step=max(s['integrator_seconds']/s['steps'] for s in ss))
    replay=read(a.replay_json)
    assert replay['status']=='INSTRUMENTED_LOCAL_REPLAY_MATCHES_VM_EXPORT'
    assert replay['counters']['rk4_calls']==25000 and replay['counters']['rhs_calls']==100000
    output=dict(status='ROOT_CAUSE_DOCUMENTED_AWAITING_USER_ACCEPTANCE',
      runtime_status_preserved='REVIEW_REQUIRED',user_acceptance=None,
      baseline_report_commit='8adfd0564884bdb4b7b2adad7bad2ea5435d25b8',
      report_commit='26ddea1e48f1c48d8ae767d389452297376a5b1f',
      source_commit=run['source_commit'],
      time_first=dict(forecast=total_forecast,lower=calibration['forecast']['lower_seconds'],
        upper=calibration['forecast']['upper_seconds'],actual=actual,deviation_seconds=actual-total_forecast),
      historical_basis=dict(case_seconds=historical_elapsed,steps=historical_steps,
        measured_seconds_per_step=historical_elapsed/historical_steps,
        rounded_seconds_per_step_used_in_plan=tstep,scope='complete old trajectory cycles, not integration-only'),
      forecast_reconstruction=dict(old_workload=old_n,new_workload=new_n,ratio=ratio,
        old_literal_forecast=old_forecast,old_cost_from_measured_basis_plus_25pct=known_old,
        old_forecast_unexplained_remainder=unexplained_old,
        new_workload_from_old_basis=new_n*tstep,
        new_workload_from_old_basis_plus_25pct=known_new,
        scaled_unexplained_remainder=scaled_remainder,
        added_manual_allowance=manual_allowance,total=total_forecast,
        interpretation='Algebraic decomposition of the forecast, not measured physical cost categories. The 120s literal has no derived calibration formula.',
        same_original_generic_formula_including_90s=known_new+90,
        lower_bound_excludes_old_basis_plus_25pct=True,
        counterfactual_not_a_replacement_forecast=True),
      actual_decomposition=dict(integration=integration,diagnostic=diagnostic,
        other_inside_trajectories=elapsed-integration-diagnostic,
        outside_trajectories=actual-elapsed,sum=actual,
        queue=run['job']['started']-run['job']['created']),
      comparison=dict(actual_over_old_cycle_linear_reference=actual/(new_n*tstep),
        actual_minus_old_basis_plus_25pct=actual-known_new,
        same_numpy_and_scipy_as_baseline=True,same_base_model_file=True,
        per_model_integrator_rates=rates),
      execution_check=dict(published_rhs_counter_is_derived_not_independent=True,
        independent_local_replay_counters=replay['counters'],
        replay_series_max_abs_error=max(v['series_max_abs_error'] for v in replay['export_comparison'].values()),
        replay_diagnostics_max_abs_error=max(v['diagnostics_max_abs_error'] for v in replay['export_comparison'].values()),
        replay_does_not_retroactively_count_VM_callbacks=True),
      conclusions=[
        'The forecast mixed an unexplained fixed/variable allowance into a seconds-per-step estimate, scaled it with workload, then added another allowance.',
        'The lower time bound was inconsistent with the already documented old-cycle reference plus 25 percent.',
        'No shortened dynamics or missing requested output was found; pinned source audit and the independent local replay agree with the VM export.',
        'The original runtime gate stays REVIEW_REQUIRED; only the user accepts closure.',
        'The later 55/92/168-minute single-coefficient projection is withdrawn pending a component-aware forecast.'],
      limitations=[
        'Historic CPU utilization/RSS time series were not recorded; load or hardware acceleration is not asserted as the cause.',
        'The 6.15s residual bundles build, scalar sampling, snapshot/PT, I/O and loop costs; their individual times cannot be recovered.',
        'The old-cycle reference has a different model/dt mix; 54.95s is a consistency check, not a newly validated forecast or post-hoc PASS.',
        'No full VM states were read; the replay compares published scalar and diagnostic grids.',
        'No production job was submitted and no runtime rules were changed.'])
    a.output.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(status=output['status'],forecast_parts=[known_new,scaled_remainder,manual_allowance],actual=actual)))

if __name__=='__main__':main()
