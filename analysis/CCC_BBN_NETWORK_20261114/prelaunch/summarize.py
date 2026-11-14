"""Aggregate evidence; exit zero requires every scoped engineering gate."""
from pathlib import Path
import json
import math
import subprocess
from run import dump, digest

root=Path(__file__).resolve().parent
r=root/'results'
positive=['P0_cold_repaired','P1_cold','P1_warm','P1_refined','S1_exponential_repaired']
negative='cooling_only'
rows=[]
for name in positive+[negative]:
    report=json.loads((r/name/'RESULT.json').read_text())
    receipt=json.loads((r/(name+'_PROCESS.after.json')).read_text())
    ch=report['checks']
    gates={k:bool(ch[k]) for k in ('finite_outputs','solver_success','final_baryon_pass','raw_positivity_with_1e-12_roundoff_floor')}
    gates['raw_baryon']=all(e['max_baryon_residual']<=1e-10 for e in report['eras'])
    gates['Y_final_finite']=all(math.isfinite(y) for y in report['result']['Y_final'].values())
    gates['all_eras_present']=[e['era'] for e in report['eras']]==['HT','MT','LT']
    gates['process_exit_zero']=receipt['exit_code']==0
    if name in positive: gates['author_reference']=ch['author_reference_pass']
    rows.append({'run':name,'gates':gates,'engineering_pass':all(gates.values()),'YPBBN':report['result']['YPBBN'],
                 'DoH':report['result']['DoH'],'Neff':report['result']['Neff'],
                 'max_baryon_residual':max(e['max_baryon_residual'] for e in report['eras']),
                 'raw_min':min(e['raw_min'] for e in report['eras']),
                 'wall_seconds':receipt['wall_seconds'],'cpu_seconds':receipt['cpu_seconds'],
                 'peak_rss_mib':report['timing']['peak_rss_mib'],'new_cache_files':report['new_cache_files']})
comparisons={name:json.loads((r/name).read_text()) for name in ('S1_COMPARISON.json','NEGATIVE_COMPARISON.json','REPEATABILITY.json')}
ledger=json.loads((r/'LEDGER.json').read_text())
source_rows=[]
repo=root.parents[2]
for manifest_path in sorted(r.glob('*/S0_EXECUTION_MANIFEST.json')):
    manifest=json.loads(manifest_path.read_text());name=manifest_path.parent.name
    before=json.loads((r/(name+'_PROCESS.before.json')).read_text());sha=before['source_commit']
    checks={}
    for filename in ('run.py','s1_adapter.py','launch.py'):
        path=str((root/filename).relative_to(repo))
        frozen=subprocess.check_output(['git','-C',str(repo),'show',sha+':'+path])
        import hashlib
        checks[filename]=hashlib.sha256(frozen).hexdigest()==manifest['scripts'][filename]['sha256']
    config_path=before['command'][before['command'].index('--config')+1]
    config=json.loads(subprocess.check_output(['git','-C',str(repo),'show',sha+':'+config_path]))
    checks['config']=all(manifest['params'][k]==v for k,v in config.items())
    source_rows.append({'run':name,'source_commit':sha,'checks':checks,'pass':all(checks.values())})
source_pass=all(x['pass'] for x in source_rows)
dump(r/'SOURCE_RECONCILIATION.json',{'runs':source_rows,'pass':source_pass})
repeat=comparisons['REPEATABILITY.json']
checks={'all_completed_run_gates':all(x['engineering_pass'] for x in rows),'S1_invariant':comparisons['S1_COMPARISON.json']['invariance_pass'],
        'negative_control_detected':not comparisons['NEGATIVE_COMPARISON.json']['invariance_pass'],
        'repeatability':repeat['final_results_exactly_equal'] and repeat['all_dense_samples_exactly_equal'],
        'source_identity':source_pass,'package_wall_within_600s':sum(x['wall_seconds'] for x in ledger)<=600}
summary={'status':'PASS' if all(checks.values()) else 'FAIL','scope':'P0/P1 S0 and conditional P1 S1, fixed weak/plasma caches and background grid',
         'checks':checks,'runs':rows,'process_attempts':len(ledger),'completed_runs':len(rows),
         'total_wall_seconds':sum(x['wall_seconds'] for x in ledger),'total_cpu_seconds':sum(x['cpu_seconds'] for x in ledger),
         'failed_attempts':[x for x in ledger if x['exit_code']!=0],
         'S1_max_tolerance_ratio':comparisons['S1_COMPARISON.json']['max_trajectory_tolerance_ratio'],
         'negative_max_tolerance_ratio':comparisons['NEGATIVE_COMPARISON.json']['max_trajectory_tolerance_ratio'],
         'scientific_acceptance':False,'vm_jobs_submitted':0,'P2_solve_performed':False,'independent_solver_validation':False}
dump(r/'SUMMARY.json',summary)
print(json.dumps({'status':summary['status'],'checks':checks,'wall':summary['total_wall_seconds'],'S1_ratio':summary['S1_max_tolerance_ratio'],'negative_ratio':summary['negative_max_tolerance_ratio']},indent=2))
if summary['status']!='PASS': raise SystemExit(1)
