"""Replicate the supplied code unchanged, then audit its checkpoint statistics."""
import argparse, contextlib, hashlib, json, os, platform, sys, time
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE/'inputs'))
import g8_subcase as g
import g8_compacted_toy as c

SCENARIOS = [
    ('S1_initiator_off_RW_on', 0, False, False, False, 20261106),
    ('S2_reader_writer_off', 1, False, False, False, 20361106),
    ('S3_partial_50pct_mark_loss', 2, False, False, False, 20461106),
    ('S4_full_mark_loss', 3, False, False, False, 20561106),
    ('S5_apparatus_renewal_A_preloaded', 0, True, True, False, 20661106),
    ('S5_control_apparatus_source_off', 0, True, False, False, 20761106),
    ('C1_compact_core_RW_on', 0, False, False, True, 20761106),
    ('C5_compact_core_apparatus_A_on', 0, True, True, True, 20861106),
    ('C5_control_compact_core_A_off', 0, True, False, True, 20961106),
]

def once(s):
    name, mode, dynamic, app, compact, seed = s
    ker = c.make_compact_kernel() if compact else g.make_kernel(g.N, g.GAMMA)
    return g.run_one(seed, mode, dynamic, app, ker, g.N, g.CENTER, g.CORE,
                     g.K0,g.K,g.EPS,g.NE0,g.KB_OVER_KU,g.TCYC,g.NCYCLES,
                     g.PARTIAL_KEEP_PROB,g.B0,g.KSYN,g.KDEG,g.THRESHOLD)

def env():
    cpu = next((l.split(':',1)[1].strip() for l in Path('/proc/cpuinfo').read_text().splitlines() if l.startswith('model name')), None)
    def read(p):
        try: return Path(p).read_text().strip()
        except OSError: return None
    return {'python':platform.python_version(),'numpy':np.__version__,
      'pandas':pd.__version__,'numba':__import__('numba').__version__,
      'llvmlite':__import__('llvmlite').__version__,'platform':platform.platform(),
      'cpu_model':cpu,'affinity':sorted(os.sched_getaffinity(0)),
      'cpu_quota':read('/sys/fs/cgroup/cpu.max'), 'memory_limit':read('/sys/fs/cgroup/memory.max'),
      'numba_threads':__import__('numba').get_num_threads(),'algorithm':'single-thread njit Gillespie; no parallel=True',
      'input_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (HERE/'inputs').iterdir() if p.is_file()}}

def calibrate():
    start=time.perf_counter()
    t=time.perf_counter();once(SCENARIOS[0]);cold=time.perf_counter()-t
    rows=[]
    for s in SCENARIOS:
        t=time.perf_counter();once(s);rows.append({'scenario':s[0],'seconds':time.perf_counter()-t})
    result={'environment':env(),'cold_first_trajectory_seconds':cold,'warm_scenarios':rows,
            'trajectory_calls':10,'wall_seconds':time.perf_counter()-start,
            'scope':'one cold first trajectory plus 9 warm scenario trajectories; Python imports excluded'}
    (HERE/'CALIBRATION.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

def run():
    start=time.perf_counter();out=HERE/'replication';out.mkdir(exist_ok=True)
    timings={}
    with (out/'run.log').open('w') as log,contextlib.redirect_stdout(log):
        t=time.perf_counter();g.main(str(out/'line'),100,20261106);timings['line_seconds']=time.perf_counter()-t
        t=time.perf_counter();c.main(str(out/'compact'));timings['compact_seconds']=time.perf_counter()-t
    checks=[]
    for folder,name in [('line','G8_SUBCASE_SUMMARY.csv'),('compact','G8_COMPACTED_TOY_SUMMARY.csv')]:
        a=pd.read_csv(HERE/'inputs'/name);b=pd.read_csv(out/folder/name)
        pd.testing.assert_frame_equal(a,b,check_exact=False,atol=1e-12,rtol=1e-12)
        checks.append({'file':name,'rows':len(a),'numeric_match_atol_rtol':1e-12})
    records=[];cum=[];extra=[]
    for folder,name in [('line','G8_SUBCASE_RAW.npz'),('compact','G8_COMPACTED_TOY_RAW.npz')]:
        with np.load(out/folder/name) as raw:
            scenarios=sorted({k.split('__')[0] for k in raw.files})
            for s in scenarios:
                arrays={k.split('__')[1]:raw[k] for k in raw.files if k.startswith(s+'__')}
                pc=arrays['pre_core'];post=arrays['post_core'];n=pc.shape[0]
                assert pc.shape==(100,7)
                assert np.all(arrays['pre_total']==pc+arrays['pre_leak'])
                assert np.all(arrays['post_total']==post+arrays['post_leak'])
                assert np.all(np.diff(arrays['pre_budget'],axis=1)<=0)
                for gen in range(7):
                    maj=(pc[:,:gen+1]>=5).all(axis=1);seed=(pc[:,:gen+1]>=1).all(axis=1)
                    lm,hm=g.wilson(int(maj.sum()),n);ls,hs=g.wilson(int(seed.sum()),n)
                    cum.append({'kernel_class':'generic_1D' if folder=='line' else 'schematic_compaction',
                       'scenario':s,'generation_inclusive':gen,'q_line_cumulative_majority':maj.mean(),
                       'majority_successes':int(maj.sum()),'majority_ci95_low':lm,'majority_ci95_high':hm,
                       'q_line_cumulative_seed':seed.mean(),'seed_successes':int(seed.sum()),
                       'seed_ci95_low':ls,'seed_ci95_high':hs,'n_trajectories':n})
                for rep in range(n):
                    for gen in range(7):records.append({'scenario':s,'trajectory':rep,'checkpoint':gen,**{k:int(v[rep,gen]) for k,v in arrays.items()}})
                extra.append({'scenario':s,'initial_majority':int((pc[:,0]>=5).sum()),
                  'initial_seed':int((pc[:,0]>=1).sum()),'endpoint_majority_n6':int((pc[:,6]>=5).sum()),
                  'every_pre_checkpoint_majority':int((pc>=5).all(axis=1).sum()),
                  'every_pre_checkpoint_seed':int((pc>=1).all(axis=1).sum()),
                  'all_post_dilutions_seed':int((post[:,1:]>=1).all(axis=1).sum()),
                  'total_zero_post_boundary_count':int((arrays['post_total'][:,1:]==0).sum()),
                  'core_zero_then_positive_next_pre_count':int(((post[:,1:6]==0)&(pc[:,2:]>0)).sum()),
                  'mean_precursor_used':float((45-arrays['pre_budget'][:,-1]).mean())})
    generated=pd.DataFrame(cum);supplied=pd.read_csv(HERE/'inputs/G8_LINE_CUMULATIVE.csv')
    order=['scenario','generation_inclusive']
    # Kernel class strings are presentation labels; all statistical fields are compared.
    cols=[x for x in supplied.columns if x!='kernel_class']
    pd.testing.assert_frame_equal(supplied[cols].sort_values(order).reset_index(drop=True),generated[cols].sort_values(order).reset_index(drop=True),check_exact=False,atol=1e-12,rtol=1e-12)
    generated.to_csv(out/'G8_LINE_CUMULATIVE_RECOMPUTED.csv',index=False)
    pd.DataFrame(records).to_csv(out/'RAW_TRAJECTORIES.csv',index=False)
    pd.DataFrame(extra).to_csv(out/'CHECKPOINT_DIAGNOSTICS.csv',index=False)
    plan=json.loads((HERE/'RUNTIME_PLAN.json').read_text())
    timings['main_and_audit_seconds']=time.perf_counter()-start
    result={'environment':env(),'summary_checks':checks,'cumulative_rows_match':63,
      'trajectory_count':900,'checkpoint_rows':len(records),'raw_integer_fields':10,
      'scientific_scope':'same supplied dynamics and seeds; no parameter search',
      'timings':timings,'runtime_plan':plan,
      'runtime_status':'PASS' if plan['lower_seconds']<=timings['main_and_audit_seconds']<=plan['upper_seconds'] else 'REVIEW_REQUIRED',
      'clock_scope':'after imports, before final result JSON write; startup/JIT are separately identified',
      'numerical_checks_pass':True}
    (out/'CHECKS.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--calibrate',action='store_true');args=parser.parse_args()
    calibrate() if args.calibrate else run()
