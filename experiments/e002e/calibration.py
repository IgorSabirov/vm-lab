"""Bounded target-VM calibration, never a production/F2 launcher."""
import hashlib
import inspect
import json
import os
from pathlib import Path
import resource
import shutil
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]

def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n')

def read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None

def run(config):
    started = time.perf_counter()
    report = Path('report'); report.mkdir(exist_ok=False)
    metrics = {'run_id': config['run_id'], 'source_commit': config['source_commit'],
               'phase': config['calibration_phase'], 'production_started': False,
               'F2_started': False, 'forecast': config['forecast']}
    failure = None
    try:
        from e002e_exp.runtime import environment, kernel_hash
        import numpy as np
        from scipy.sparse.linalg import gmres
        env = environment()
        metrics.update(environment=env, kernel_sha256=kernel_hash(),
                       launcher_binding=config['source_commit_binding'],
                       source_root_matches=Path(os.environ['VM_SOURCE_DIR']).resolve() == ROOT)
        if not metrics['source_root_matches']:
            raise ValueError('Launcher source root mismatch')
        mismatches = [p for p, h in config['reviewed_scientific_files'].items()
                      if hashlib.sha256((ROOT/p).read_bytes()).hexdigest() != h]
        metrics['reviewed_scientific_file_mismatches'] = mismatches
        if mismatches:
            raise ValueError('Reviewed scientific source differs: '+str(mismatches))
        if config['calibration_phase'] != 'environment':
            raise ValueError('Undeclared calibration phase')
        metrics['resources'] = dict(
            free_disk_bytes=shutil.disk_usage('.').free,
            cgroup_membership=read('/proc/self/cgroup'),
            proc_limits=read('/proc/self/limits'),
            address_space_rlimit=list(resource.getrlimit(resource.RLIMIT_AS)),
            data_rlimit=list(resource.getrlimit(resource.RLIMIT_DATA)))
        metrics['compatibility'] = dict(
            gmres_signature=str(inspect.signature(gmres)),
            gmres_accepts_rtol='rtol' in inspect.signature(gmres).parameters,
            numpy_has_trapezoid=hasattr(np, 'trapezoid'),
            blas_threadpools_observed=env['threadpools'] is not None)
        metrics['status'] = 'ENVIRONMENT_MEASURED_NOT_NUMERICALLY_CALIBRATED'
    except Exception as exc:
        failure = type(exc).__name__+': '+str(exc)
        metrics.update(status='FAILED', failure=failure, traceback=traceback.format_exc())
    elapsed = time.perf_counter()-started
    metrics['runtime'] = dict(actual_seconds=elapsed, status='NOT_EVALUABLE',
        reason='FIRST_TARGET_ENVIRONMENT_PROBE_UNCALIBRATED_ESTIMATE',
        deviation_seconds=elapsed-config['forecast']['expected_seconds'])
    save(report/'config.json', config)
    save(report/'metrics.json', metrics)
    save(report/'data_manifest.json', {'full_data': [], 'selection': 'Complete environment probe; no numerical trajectory', 'omissions': []})
    (report/'README.md').write_text('E002e target VM environment probe. No production or F2. Exact data: metrics.json.\n')
    (report/'RESULT.md').write_text('Время: ориентир '+str(config['forecast']['expected_seconds'])+
        ' с; факт '+str(elapsed)+' с; NOT_EVALUABLE — первый замер.\n\n'+
        'Статус: '+metrics['status']+'. Численные расчёты не запускались.\n'+
        ('Ошибка: '+failure+'\n' if failure else 'Паспорт, совместимость библиотек и происхождение кода: metrics.json.\n'))
    print(json.dumps(metrics, ensure_ascii=False), flush=True)
    if failure:
        raise RuntimeError(failure)
