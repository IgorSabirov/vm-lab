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
        from .vendor_threadpoolctl import threadpool_info
        pools = [{k: p.get(k) for k in ('user_api', 'internal_api', 'num_threads', 'version', 'architecture')} for p in threadpool_info()]
    status = dict(x.split(':', 1) for x in (read_optional('/proc/self/status') or '').splitlines() if ':' in x)
    maps = read_optional('/proc/self/maps') or ''
    libraries = sorted({line.split()[-1] for line in maps.splitlines() if '/' in line and
                        any(k in line.lower() for k in ('blas', 'lapack', 'libomp', 'libgomp', 'libmkl'))})
    blas_identity = [{'path':p, 'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest()} for p in libraries]
    return dict(observed_at_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                python=sys.version, executable=sys.executable, platform=platform.platform(), machine=platform.machine(),
                cpu_model=cpu, logical_cpus=os.cpu_count(), affinity=sorted(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else None,
                cpu_quota=read_optional('/sys/fs/cgroup/cpu.max'), memory_limit=read_optional('/sys/fs/cgroup/memory.max'),
                memory_current=read_optional('/sys/fs/cgroup/memory.current'),
                memory_available=mem.get('MemAvailable', None), memory_total=mem.get('MemTotal', None),
                load_average=list(os.getloadavg()) if hasattr(os, 'getloadavg') else None,
                numpy=np.__version__, scipy=scipy.__version__, threadpools=pools,
                requested_threads={k: os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')},
                optimize=sys.flags.optimize, cache_state='OS_CACHE_NOT_CONTROLLED',
                infrastructure_unknowns=['physical host contention', 'CPU frequency history', 'storage contention'],
                max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                address_space_rlimit=list(resource.getrlimit(resource.RLIMIT_AS)),
                process_vm_size_bytes=int(status['VmSize'].split()[0])*1024 if 'VmSize' in status else None,
                blas_library_identity=blas_identity,
                cgroup_membership=read_optional('/proc/self/cgroup'),
                cgroup_visibility='VISIBLE' if read_optional('/sys/fs/cgroup/memory.max') is not None else 'NOT_MOUNTED_IN_JOB_NAMESPACE')


def memory_preflight(budget, current):
    required = ('peak_additional_bytes', 'reserve_bytes', 'measured_peak_rss_bytes', 'simultaneous_factor_storage_bytes')
    if any(isinstance(budget.get(k), bool) or not isinstance(budget.get(k), (int, float)) or not np.isfinite(budget[k]) or budget[k] <= 0 for k in required):
        raise ValueError('Memory budget lacks measured peak/factor storage and positive reserve')
    if budget['peak_additional_bytes'] < budget['simultaneous_factor_storage_bytes']:
        raise ValueError('Memory budget cannot be smaller than simultaneous factors')
    if budget['peak_additional_bytes'] < budget['measured_peak_rss_bytes']:
        raise ValueError('Memory forecast below measured reference peak')
    try:
        available = int(current['memory_available'].split()[0])*1024
    except (KeyError, TypeError, ValueError):
        raise ValueError('Host available memory is not measurable') from None
    if current.get('memory_limit') is not None and current.get('memory_current') is not None:
        try:
            limit=int(current['memory_limit']); used=int(current['memory_current'])
        except (TypeError,ValueError):
            raise ValueError('Cgroup memory values are not finite limits') from None
        mode='CGROUP_AND_HOST'
    else:
        limits=current.get('address_space_rlimit',[])
        used=current.get('process_vm_size_bytes')
        peak_vm=budget.get('measured_peak_vm_bytes')
        if (current.get('cgroup_visibility') != 'NOT_MOUNTED_IN_JOB_NAMESPACE' or len(limits)!=2
                or any(type(x) is not int or x<=0 for x in limits) or limits[0]!=limits[1]
                or type(used) is not int or used<=0 or not isinstance(peak_vm,(int,float))
                or not np.isfinite(peak_vm) or peak_vm<=0 or budget['peak_additional_bytes']<peak_vm):
            raise ValueError('Missing finite enforced address-space limit and measured virtual-memory budget')
        limit=limits[0];mode='HARD_RLIMIT_AS_AND_HOST_CGROUP_UNOBSERVED'
    remaining = min(limit-used, available)
    needed = budget['peak_additional_bytes']+budget['reserve_bytes']
    if needed > remaining:
        raise MemoryError(f'Memory budget needs {needed} bytes, available {remaining}')
    return dict(needed_bytes=needed, available_bytes=remaining, status='PASS',resource_mode=mode,
                caveat='Unknown ancestor cgroup cannot be measured inside namespace' if mode.startswith('HARD') else None)


def kernel_files():
    return [ROOT/'run.py', ROOT/'e002_exp/model.py', ROOT/'e002c_exp/model.py', ROOT/'e002d_exp/plan.py',
            ROOT/'experiments/e002e/case_inventory_v003.json', *sorted((ROOT/'e002e_exp').glob('*.py'))]


def kernel_hash():
    h = hashlib.sha256()
    for path in kernel_files():
        h.update(path.relative_to(ROOT).as_posix().encode()+b'\0'+path.read_bytes())
    return h.hexdigest()


def compare_environment(reference, current):
    required = ('python', 'platform', 'machine', 'cpu_model', 'logical_cpus', 'affinity',
                'numpy', 'scipy', 'threadpools', 'requested_threads', 'blas_library_identity',
                'cgroup_visibility', 'address_space_rlimit')
    missing = [k for k in required if reference.get(k) is None or current.get(k) is None]
    differences = [k for k in required if reference.get(k) != current.get(k)]
    for k in ('cpu_quota','memory_limit'):
        if reference.get(k)!=current.get(k):differences.append(k)
    for value in (reference,current):
        if value.get('cgroup_visibility')=='NOT_MOUNTED_IN_JOB_NAMESPACE':
            limits=value.get('address_space_rlimit',[])
            if len(limits)!=2 or any(type(x) is not int or x<=0 for x in limits) or limits[0]!=limits[1]:missing.append('enforced_address_space_limit')
        elif value.get('cpu_quota') is None or value.get('memory_limit') is None:
            missing.append('cgroup_limits')
        if not value.get('blas_library_identity'):missing.append('blas_library_identity')
    return dict(comparable=not missing and not differences, missing=missing, differences=differences,
                note='Matching manifest does not eliminate unobserved host/cgroup contention; inspect runtime deviations')


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
