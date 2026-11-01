"""Immutable science and fail-closed launch requirements for CORR v001."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import numpy as np
from e002e_exp.runtime import ROOT, kernel_hash, kernel_files, compare_environment, memory_preflight
from e002e_exp.plan import pinned_file, selected_work

MODELS = ('QS', 'RR_QS', 'IC1_QS')
PROTOCOL = dict(version='E002e_CORR_v001', models=list(MODELS), primary_model='QS', phi_over_pi=.5,
                epsilon=0., m6_v_over_J=1., node_noise=.05, dimensions=[8, 27],
                horizon=20., dt_fine=.005, dt_coarse=.01, sample_interval=.02,
                physicality_interval=1., primary='integral_abs_delta_F_over_H_Fss',
                primary_threshold=.001, maximum_metric_uncertainty=.0001,
                absolute_floor=1e-10, safety=3., raw_absolute_tolerance=1e-8,
                raw_relative_tolerance=1e-5, maximum_sham_drift=1e-8,
                state_tolerance=1e-9, operator_tolerance=1e-10,
                physicality_mode='FULL_PSD_AT_DECLARED_CHECKPOINTS',
                sector_contract='COMPLETE_Q0_CHARGE_BLOCKS_NO_PROJECTION',
                checkpoint_interval=1., checkpoint_retention='LAST_ONLY_NO_RESUME',
                calibration_horizon=2., negative_result='finite_window_operational_non_rejection',
                initial_preparation='replace_edges_by_fixed_own_baseline_marginal',
                no_infinite_tail_or_quantum_specificity_claim=True)
SOLVERS = (dict(method='lu', rtol=1e-11, atol=1e-13),
           dict(method='gmres_ilu', rtol=1e-11, atol=1e-13, restart=100, maxiter=400,
                ilu_drop_tol=1e-5, ilu_fill_factor=10.))
LIMITS = dict(vector_inf=1e-9, observable_absolute=1e-9, observable_relative=1e-7)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def protocol_hash():
    return hashlib.sha256(canonical(dict(science=PROTOCOL, solvers=SOLVERS, refinement=LIMITS)).encode()).hexdigest()


def implementation_manifest():
    # kernel_files already covers numerics, space, export, runtime, compat,
    # full-model builders, inventory and scientific constants. Include import
    # package initializers explicitly; publish this dependency inventory.
    files = set(kernel_files()) | set((ROOT/'e002e_corr_exp').glob('*.py'))
    files.add(ROOT/'experiments/e002e_corr/input_integrity.json')
    files |= {ROOT/pkg/'__init__.py' for pkg in ('e002_exp','e002c_exp','e002d_exp')}
    return [dict(path=p.relative_to(ROOT).as_posix(), sha256=hashlib.sha256(p.read_bytes()).hexdigest())
            for p in sorted(files)]


def implementation_hash():
    return hashlib.sha256(canonical(implementation_manifest()).encode()).hexdigest()


def thread_preflight(current):
    requested = current.get('requested_threads', {})
    if any(requested.get(k) != '1' for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS')):
        raise ValueError('Exactly one requested BLAS/OpenMP thread is required')
    pools = current.get('threadpools')
    if not pools or any(p.get('num_threads') != 1 for p in pools):
        raise ValueError('Measured BLAS/OpenMP thread count must be one')
    return dict(status='PASS', requested=requested, measured=pools)


def storage_preflight(destination):
    # Retained data: 3 initial pairs + 9 rolling checkpoints (<8 MB raw),
    # full sampled series ~12 MB, JSON diagnostics/manifests. Bound also
    # covers one atomic temporary file; no 30000-checkpoint history is kept.
    required = 128*2**20; reserve = 2**30
    available = shutil.disk_usage(destination).free
    if available < required+reserve:
        raise OSError('Insufficient report/checkpoint storage reserve')
    return dict(status='PASS', required_bytes=required, reserve_bytes=reserve,
                available_bytes=available, retention='LAST_ONLY_NO_RESUME')


def cases():
    out = []
    for name in MODELS:
        matches = [c for c in selected_work('baseline')['full'] if c['model'] == name
                   and c['phi_over_pi'] == .5 and c['epsilon'] == 0 and c['node_noise'] == .05
                   and c['m6_v_over_J'] == PROTOCOL['m6_v_over_J']]
        if len(matches) != 1:
            raise ValueError('Baseline identity ambiguous')
        out.append(dict(matches[0], tasks=['NESS']))
    return out


def workload(horizon=20.):
    fine = round(horizon/PROTOCOL['dt_fine']); coarse = round(horizon/PROTOCOL['dt_coarse'])
    return dict(NESS=3, refinement_NESS=3, propagations=9, block_steps=3*(2*fine+coarse),
                checkpoint_writes=9*(round(horizon/PROTOCOL['checkpoint_interval'])+1),
                block_rhs_calls=12*(2*fine+coarse), scalar_rhs_equivalents=24*(2*fine+coarse))


def preflight(config, current):
    mode = config.get('mode')
    if mode not in ('calibration', 'production'):
        raise ValueError('Explicit supported mode required')
    if config.get('protocol_sha256') != protocol_hash() or config.get('implementation_sha256') != implementation_hash():
        raise ValueError('Unpinned or changed protocol/implementation')
    source = config.get('source_commit')
    if not re.fullmatch('[0-9a-f]{40}', source or '') or os.environ.get('VM_SOURCE_COMMIT') != source:
        raise ValueError('VM checkout/source identity mismatch')
    # These settings are fixed in code; configuration cannot relax their caps.
    allowed = {'mode', 'protocol_sha256', 'implementation_sha256', 'source_commit',
               'technical_review', 'evidence', 'calibration', 'forecast', 'memory_budget'}
    if set(config)-allowed:
        raise ValueError('Unsupported configuration override')
    threads = thread_preflight(current)
    review = pinned_file(config['technical_review'])
    if (review.get('status') != 'REVIEWED_AND_CHECKED' or review.get('implementation_sha256') != implementation_hash()
            or not re.fullmatch('[0-9a-f]{40}', review.get('reviewed_source_commit', ''))):
        raise ValueError('Technical review missing for current implementation')
    evidence = pinned_file(config['evidence'])
    if evidence.get('schema') != 'E002e_CORR_evidence_v1' or evidence.get('protocol_sha256') != protocol_hash():
        raise ValueError('Evidence/protocol mismatch')
    records = {}
    for item in evidence['baselines']:
        record = pinned_file(item)
        if item['case_id'] in records or record['id'] != item['case_id']:
            raise ValueError('Duplicate/mismatched evidence')
        records[item['case_id']] = record
    if set(records) != {c['id'] for c in cases()}:
        raise ValueError('Incomplete baseline evidence')
    for case in cases():
        record = records[case['id']]
        if any(record['case'][k] != case[k] for k in ('model', 'epsilon', 'phi_over_pi', 'node_noise', 'm6_v_over_J')):
            raise ValueError('Baseline physics mismatch')
        if not record['quality']['pass'] or not record['refinement']['gate']['pass_gate']:
            raise ValueError('Unverified published baseline')
    horizon = PROTOCOL['horizon'] if mode == 'production' else PROTOCOL['calibration_horizon']
    if mode == 'production':
        cal = pinned_file(config['calibration'])
        if (cal.get('status') != 'CALIBRATION_COMPLETE' or cal.get('runtime_review_status') != 'REVIEWED'
                or not re.fullmatch('[0-9a-f]{40}', cal.get('report_commit', ''))
                or cal.get('implementation_sha256') != implementation_hash()
                or cal.get('protocol_sha256') != protocol_hash() or cal.get('counts') != workload(PROTOCOL['calibration_horizon'])):
            raise ValueError('Calibration identity/coverage mismatch')
        env = compare_environment(cal['environment'], current)
        if not env['comparable']:
            raise ValueError('Production environment differs from measured calibration')
        if config['forecast'] != cal['production_forecast'] or config['memory_budget'] != cal['memory_budget']:
            raise ValueError('Budget is not the pinned measured budget')
    else:
        env = dict(comparable=False, reason='BOUNDED_FIRST_CALIBRATION_NO_CORRELATION_CUT')
    f = config['forecast']
    if (not all(np.isfinite(f[k]) for k in ('expected_seconds', 'lower_seconds', 'upper_seconds'))
            or not 0 < f['lower_seconds'] <= f['expected_seconds'] <= f['upper_seconds']):
        raise ValueError('Invalid runtime forecast')
    memory = memory_preflight(config['memory_budget'], current)
    return dict(cases=cases(), evidence=records, environment=env, memory=memory, threads=threads,
                counts=workload(horizon), horizon=horizon)
