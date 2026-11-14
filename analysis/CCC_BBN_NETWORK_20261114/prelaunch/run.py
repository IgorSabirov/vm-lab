"""Single isolated PRIMAT run with strict cache provenance and raw traces.

Only a parent launcher provides budgets. No network/install/automatic retry.
Run from a frozen vm-lab commit with a separately checked upstream checkout.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time

PIN = '6f7e5680614fb119d65a6c9c65a292240b27c61e'
WEAK = {'nTOp_7e3af87bd0404e0a.txt': 'f5111a85112e94a237ed73f28ef860876ee0f8ed',
        'nTOp_thermal_cfdb4d324bb5651f.txt': 'e3a8b6782393df73a9140e05bd3941ff135af2c9'}


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def digest(path):
    b = path.read_bytes()
    return {'sha256': hashlib.sha256(b).hexdigest(), 'git_blob_sha': hashlib.sha1(b'blob ' + str(len(b)).encode() + b'\0' + b).hexdigest(), 'bytes': len(b)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--upstream', required=True, type=Path)
    p.add_argument('--config', required=True, type=Path)
    p.add_argument('--cache', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--mode', choices=['S0', 'S1', 'cooling_only'], default='S0')
    p.add_argument('--f0', type=float, default=3.66)
    p.add_argument('--alpha', type=float, default=0.)
    args = p.parse_args()
    started = time.monotonic()
    root, out, cache = args.upstream.resolve(), args.out.resolve(), args.cache.resolve()
    out.mkdir(parents=True, exist_ok=False)
    cache.mkdir(parents=True, exist_ok=True)
    head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    if head != PIN or subprocess.check_output(['git', '-C', str(root), 'diff', '--name-only', 'HEAD']).strip():
        raise RuntimeError('Upstream identity mismatch or tracked modifications')
    sys.path.insert(0, str(root))
    import numpy as np
    import scipy
    from threadpoolctl import threadpool_info
    from primat.config import PRIMATConfig, DEFAULT_PARAMS
    from primat.cache_utils import fingerprint_hash, resolve_cache_file
    from primat.weak_rates.cache import weak_rate_fingerprint, thermal_fingerprint
    import primat.weak_rates.api as weak_api
    import primat.weak_rates.corrections as corrections
    import primat.nuclear_network as nuclear_module
    from primat.main import PRIMAT
    from s1_adapter import Clock, attach

    params = json.loads(args.config.read_text())
    params.update(cache_dir=str(cache), data_dir=None, user_nuclear_dir=None,
                  weak_rate_cache=True, decay_era=False, verbose=True,
                  output_time_evolution=False, output_final_result=False,
                  output_decay_evolution=False)
    cfg = PRIMATConfig(params)
    hashes = (fingerprint_hash(weak_rate_fingerprint(cfg)), fingerprint_hash(thermal_fingerprint(cfg)))
    names = ('nTOp_' + hashes[0] + '.txt', 'nTOp_thermal_' + hashes[1] + '.txt')
    sources = {}
    for name in names:
        resolved = Path(resolve_cache_file(cfg, 'weak', name)).resolve()
        if name not in WEAK or not resolved.is_file() or digest(resolved)['git_blob_sha'] != WEAK[name]:
            dump(out / 'REJECTION.json', {'status': 'NOT_REPRODUCED_UNDER_IDENTICAL_CACHE', 'file': str(resolved), 'fingerprints': hashes})
            raise RuntimeError('Strict weak-cache identity unavailable')
        sources[name] = {'resolved_path': str(resolved), **digest(resolved)}

    def reject_recompute(*a, **kw):
        raise RuntimeError('Strict run forbids weak-rate recomputation')
    weak_api.ComputeWeakRates = reject_recompute
    corrections._L_CCRTh_compute = reject_recompute
    load_events = []
    original_loadtxt = np.loadtxt

    def traced_loadtxt(fname, *a, **kw):
        if isinstance(fname, (str, Path)) and ('cache_plasma_weak' in str(fname) or str(cache) in str(fname)):
            file = Path(fname).resolve()
            if file.is_file():
                load_events.append({'path': str(file), **digest(file)})
        return original_loadtxt(fname, *a, **kw)
    np.loadtxt = traced_loadtxt
    snapshot = lambda: {str(p.relative_to(cache)): digest(p) for p in sorted(cache.rglob('*')) if p.is_file()}
    before = snapshot()
    source_files = {str(p.relative_to(Path(__file__).parent)): digest(p) for p in Path(__file__).parent.glob('*.py')}
    manifest = {'upstream_commit': head, 'upstream_tree': subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD^{tree}'],text=True).strip(),
                'mode': args.mode, 'clock': {'f0': args.f0, 'alpha_s_inv': args.alpha, 'interpretation': 'conditional kinetic clock; no physical-clock identification claim'},
                'params': params, 'resolved_defaults': {k:getattr(cfg,k) for k in DEFAULT_PARAMS}, 'weak_sources': sources, 'cache_before': before, 'scripts': source_files,
                'environment': {'python': sys.version, 'python_executable': sys.executable,
                                'python_sha256': digest(Path(sys.executable).resolve())['sha256'],
                                'numpy': np.__version__, 'scipy': scipy.__version__, 'platform': platform.platform(),
                                'affinity': sorted(os.sched_getaffinity(0)), 'threadpools': threadpool_info(),
                                'pid': os.getpid()},
                'reference': {'YPBBN': .24699844 if cfg.network == 'small' else .24700179,
                              'DoH': 2.4358977e-5 if cfg.network == 'small' else 2.4366098e-5,
                              'YPBBN_abs_tol': 1e-5, 'DoH_abs_tol': 3e-9},
                'scientific_acceptance': False}
    dump(out / 'S0_EXECUTION_MANIFEST.json', manifest)
    sols = []
    original_solve = nuclear_module.solve_ivp

    def record_solve(fun, t_span, y0, *a, **kw):
        kw['dense_output'] = True
        sol = original_solve(fun, t_span, y0, *a, **kw)
        sols.append(sol)
        return sol
    nuclear_module.solve_ivp = record_solve
    init_start = time.monotonic()
    run = PRIMAT(params)
    init_seconds = time.monotonic() - init_start
    base = run.background
    if args.mode != 'S0':
        attach(run, Clock(args.f0, args.alpha), scale_rates=args.mode == 'S1')
    solve_start = time.monotonic()
    result = run.solve(progress=False)
    solve_seconds = time.monotonic() - solve_start
    if len(sols) != 3 or not all(s.success for s in sols):
        raise RuntimeError('Expected successful HT/MT/LT solves')
    weak_paths = {v['resolved_path'] for v in sources.values()}
    loaded_paths = {e['path'] for e in load_events}
    if not weak_paths <= loaded_paths:
        raise RuntimeError('Expected weak-cache reads were not observed')
    phase_names = [['n', 'p'], run.nucl._mt_net.species, run.nucl._lt_net.species]
    traces, raw = [], []
    for era, sol, species in zip(['HT','MT','LT'], sols, phase_names):
        temperatures = np.geomspace(float(run.background.T_of_t(sol.t[0])), float(run.background.T_of_t(sol.t[-1])), 401)
        times = np.asarray(run.background.t_of_T(temperatures))
        # Round-trip interpolation may place endpoints just outside solver span.
        times[0], times[-1] = sol.t[0], sol.t[-1]
        values = sol.sol(times)
        weights = np.array([sum(cfg.Nuclides[n]) for n in species])
        raw.append({'era': era, 'success': sol.success, 'status': sol.status, 'message': sol.message,
                    'nfev': sol.nfev, 'njev': sol.njev, 'nlu': sol.nlu,
                    'steps': len(sol.t), 'raw_min': float(sol.y.min()),
                    'max_baryon_residual': float(np.max(np.abs(weights @ sol.y - 1)))})
        traces.append({'era': era, 'species': species, 'T_MeV': temperatures.tolist(),
                       't_seconds': times.tolist(), 'Y': values.T.tolist()})
    for k in list(result):
        if isinstance(result[k], np.generic): result[k] = result[k].item()
    result['Y_final'] = dict(run.nuclear.Y_final)
    mass_residual = abs(sum(sum(cfg.Nuclides[n])*v for n,v in result['Y_final'].items())-1)
    reference = manifest['reference']
    checks = {'finite_outputs': all(np.isfinite(v) for v in result.values() if isinstance(v,(float,int))),
              'solver_success': all(s.success for s in sols), 'final_baryon_residual': mass_residual,
              'final_baryon_pass': mass_residual <= 1e-10,
              'raw_positivity_with_1e-12_roundoff_floor': all(x['raw_min'] >= -1e-12 for x in raw),
              'author_YPBBN_residual': result['YPBBN']-reference['YPBBN'],
              'author_DoH_residual': result['DoH']-reference['DoH'],
              'author_reference_pass': abs(result['YPBBN']-reference['YPBBN'])<=1e-5 and abs(result['DoH']-reference['DoH'])<=3e-9}
    if args.mode == 'cooling_only': checks['author_reference_pass_expected'] = False
    after = snapshot()
    for n, info in sources.items():
        if digest(Path(info['resolved_path']))['sha256'] != info['sha256']:
            raise RuntimeError('Weak cache mutated during run')
    report = {'result': result, 'checks': checks, 'eras': raw, 'load_events': load_events,
              'cache_after': after, 'new_cache_files': sorted(set(after)-set(before)),
              'timing': {'init_seconds': init_seconds, 'solve_seconds': solve_seconds,
                         'worker_wall_seconds': time.monotonic()-started,
                         'peak_rss_mib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024},
              'scientific_acceptance': False}
    dump(out/'RESULT.json', report)
    dump(out/'TRACE.json', {'convention': 'Only active species, separate HT/MT/LT dense solutions; no 100-to-10 MeV zero-fill.', 'eras': traces})
    print(json.dumps({'out':str(out),'YPBBN':result['YPBBN'],'DoH':result['DoH'], 'reference_pass':checks['author_reference_pass'], **report['timing']}), flush=True)


if __name__ == '__main__':
    main()
