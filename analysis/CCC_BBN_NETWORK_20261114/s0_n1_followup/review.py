"""Reproduce the referee-claim checks using archived data; never run PRIMAT."""
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
import common as c

def array_hash(a):
    a = np.ascontiguousarray(a, dtype='<f8')
    return hashlib.sha256(a.tobytes()).hexdigest()

def analyze(destination):
    root = c.PARENT_ROOT
    count = c.verify_artifacts(root)
    c.verify_freeze(root)
    with np.load(root/'runs/CACHE_BG2000/GENERATED_WEAK.npz', allow_pickle=False) as f:
        generated, shipped = f['table'], f['shipped']
    reloaded = np.loadtxt(root/'caches/BG8000/weak/nTOp_dc55a0b9270e3e3d.txt')
    generated_reload = np.loadtxt(root/'caches/BG2000_GEN/weak/nTOp_7e3af87bd0404e0a.txt')
    serialization = {
        'shape': list(generated.shape), 'dtype': str(generated.dtype),
        'generated_binary_sha256': array_hash(generated),
        'reloaded_binary_sha256': array_hash(generated_reload),
        'bitwise_equal': generated.tobytes() == generated_reload.tobytes(),
        'max_absolute_difference': float(np.max(abs(generated-generated_reload))),
        'format': 'upstream np.savetxt default %.18e; np.loadtxt float64',
        'scope': 'Actual archived BG2000 generation before writing versus loaded text; not just text-file hashes',
    }
    env = {}
    with np.load(c.BASE/'RAW_SOLVER.npz', allow_pickle=False) as a, np.load(root/'runs/R_ENV/RAW_SOLVER.npz', allow_pickle=False) as b:
        for era in ('HT','MT','LT'):
            env[era] = all(np.array_equal(a[era+k],b[era+k]) for k in ('_Y','_t_seconds','_species'))
    old = c.read(root/'CONVERGENCE_SUMMARY.json')
    failures = [{'pair':pair,'observable':key,**g} for pair,gs in old['gates'].items() for key,g in gs.items() if not g['pass']]
    n = old['axes']['rate']['Y_n']
    tail = abs(n['signed_increments'][1])/(2**n['p_observed']-1)
    out = {
        'parent_commit':c.read(c.PKG/'PLAN.json')['parent_result_commit'],
        'archived_hashes_verified': count,
        'cold_reset': {'implemented_in_original_series':True,
            'evidence':'s0_n1/launch.py process(): subprocess.Popen of a fresh Python worker, serial wait, cache snapshots and frozen load hashes',
            'environment_reproduction_raw_arrays':env,
            'limit':'Process isolation excludes persistence of Python globals. A dedicated same-machine before/after replay is newly scheduled; OS effects are not ruled out by process isolation alone.'},
        'serialization':serialization,
        'generation_difference': {
            'max_normalized_difference': float(np.max(abs(generated-shipped)/np.maximum(np.maximum(abs(generated),abs(shipped)),1e-28))),
            'arises_before_serialization':True,
            'origin':'Upstream shipped table versus current pinned generator/background realization; original generation environment is not reconstructed',
            'not_a_precision_loss_claim':True},
        'original_failures':failures,
        'fine_level_increment_gates_all_pass':all(g['pass'] for p,gs in old['gates'].items() if p in ('R2_vs_R1','R4_vs_R3','R6_vs_R5','R8_vs_R7') for g in gs.values()),
        'rate_grid_neutron_tail_diagnostic':{'observed_order':n['p_observed'],'estimated_absolute_tail_at_16000':tail,'estimated_relative_tail_at_16000':tail/old['observables']['R4']['Y_n'],'conditional':'Three-point Richardson diagnostic only; requires asymptotic power law and fixed other errors. Not a certified bound.'},
        'Neff':{'value':old['observables']['R0']['Neff'],'dependency':'PRIMAT.main._build_results reads background.rho_nu_total_final; standard background uses fixed NEVO temperature tables at fixed T_end. Nuclear-network convergence cannot independently validate neutrino decoupling.','source_pin':c.PIN,'benchmark_source':'https://arxiv.org/abs/2012.02726','published_benchmark':'3.0440 +/- 0.0002 in this cited paper, not a universal certification'},
        'D_over_H':{'R8_minus_R_CACHE':old['differences_from_anchor']['R8']['DoH']['signed'],'interpretation':'Deterministic difference between controlled numerical configurations, not a measured stochastic noise floor. Run index is not physical time. No requirement for different discretizations to collapse onto coarse R0.','literature':'https://arxiv.org/abs/2604.16600','literature_limit':'That paper obtains 2.442 +/- 0.040 times 1e-5 with Planck and 1.70 sigma versus Cooke; significance is dataset/rate dependent and is not calculated for our run.'},
        'historical_status_unchanged':old['status'],'scientific_acceptance':False,
    }
    if not serialization['bitwise_equal']:
        raise ValueError('Observed serialization loss: stop and investigate before a new solve')
    c.write(Path(destination)/'REVIEW.json',out)
    return out

if __name__=='__main__':
    result=analyze(Path(sys.argv[1]) if len(sys.argv)>1 else c.PKG)
    print(json.dumps({'serialization_loss':not result['serialization']['bitwise_equal'],'historical_failures':len(result['original_failures']),'fine_increment_gates_pass':result['fine_level_increment_gates_all_pass']}))
