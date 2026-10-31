"""Measured environment, source identity and non-retroactive runtime gates."""
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import sys
import time
import numpy as np
import scipy

ROOT = Path(__file__).resolve().parents[1]


def read_optional(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def environment():
    cpuinfo = read_optional('/proc/cpuinfo') or ''
    cpu = next((x.split(':', 1)[1].strip() for x in cpuinfo.splitlines() if x.startswith('model name')), None)
    mem = dict(x.split(':', 1) for x in (read_optional('/proc/meminfo') or '').splitlines() if ':' in x)
    try:
        from threadpoolctl import threadpool_info
        pools = [{k: p.get(k) for k in ('user_api', 'internal_api', 'num_threads', 'version', 'architecture')} for p in threadpool_info()]
    except ImportError:
        pools = None
    return dict(observed_at_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                python=sys.version, executable=sys.executable, platform=platform.platform(), machine=platform.machine(),
                cpu_model=cpu, logical_cpus=os.cpu_count(), affinity=sorted(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else None,
                cpu_quota=read_optional('/sys/fs/cgroup/cpu.max'), memory_limit=read_optional('/sys/fs/cgroup/memory.max'),
                memory_available=mem.get('MemAvailable', None), memory_total=mem.get('MemTotal', None),
                load_average=list(os.getloadavg()) if hasattr(os, 'getloadavg') else None,
                numpy=np.__version__, scipy=scipy.__version__, threadpools=pools,
                requested_threads={k: os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')},
                optimize=sys.flags.optimize, cache_state='OS_CACHE_NOT_CONTROLLED',
                infrastructure_unknowns=['physical host contention', 'CPU frequency history', 'storage contention'],
                max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)


def kernel_files():
    return [ROOT/'run.py', ROOT/'e002_exp/model.py', ROOT/'e002c_exp/model.py', ROOT/'e002d_exp/plan.py',
            ROOT/'experiments/e002e/case_inventory_v003.json', *sorted((ROOT/'e002e_exp').glob('*.py'))]


def kernel_hash():
    h = hashlib.sha256()
    for path in kernel_files():
        h.update(path.relative_to(ROOT).as_posix().encode()+b'\0'+path.read_bytes())
    return h.hexdigest()


def compare_environment(reference, current):
    required = ('python', 'platform', 'machine', 'cpu_model', 'logical_cpus', 'affinity', 'cpu_quota',
                'memory_limit', 'numpy', 'scipy', 'threadpools', 'requested_threads')
    missing = [k for k in required if reference.get(k) is None or current.get(k) is None]
    differences = [k for k in required if reference.get(k) != current.get(k)]
    return dict(comparable=not missing and not differences, missing=missing, differences=differences,
                note='Matching manifest does not eliminate unobserved host contention; inspect runtime deviations')


def runtime_gate(forecast, elapsed, expected_counts, actual_counts, environment_match, calibrated):
    complete = all(k in forecast and np.isfinite(forecast[k]) for k in ('expected_seconds', 'lower_seconds', 'upper_seconds'))
    valid = complete and 0 < forecast['expected_seconds'] and 0 <= forecast['lower_seconds'] <= forecast['expected_seconds'] <= forecast['upper_seconds']
    if not valid:
        raise ValueError('Invalid declared runtime forecast')
    if not calibrated or not environment_match:
        status = 'NOT_EVALUABLE'
    elif expected_counts != actual_counts or not forecast['lower_seconds'] <= elapsed <= forecast['upper_seconds']:
        status = 'REVIEW_REQUIRED'
    else:
        status = 'PASS'
    return dict(**forecast, actual_seconds=elapsed, actual_over_expected=elapsed/forecast['expected_seconds'],
                deviation_seconds=elapsed-forecast['expected_seconds'], status=status,
                expected_counts=expected_counts, actual_counts=actual_counts,
                environment_comparable=environment_match, calibrated=calibrated,
                scope='Worker internal measured interval; enclosing process duration must be checked separately')
