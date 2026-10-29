"""Local instrumented replay of pinned code; no VM access or new VM calibration."""
import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-cache',type=Path,required=True)
    p.add_argument('--github-cache',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[key]='1'
    assert not os.environ.get('VM_SOURCE_COMMIT'), 'This audit is local only'
    report=json.loads((args.github_cache/'run.json').read_text())
    assert report['source_commit']=='ca15a197834bc3193f3da87d1bbd9ab1a538bf90'
    for name,sha in report['input_sha256'].items():
        assert hashlib.sha256((args.source_cache/name).read_bytes()).hexdigest()==sha,name
    sys.path.insert(0,str(args.source_cache))
    import numpy as np
    from e002c_exp import engine,task
    records={};active=None
    build_original=engine.build
    def counted_build(case,alpha=None):
        nonlocal active
        active=case['id'];model=build_original(case,alpha)
        records[active]=dict(rk4_calls=0,rhs_calls=0,expanded_calls=0,quality_calls=0,
            sample_calls=0,snapshot_writes=0,liouvillian_shape=list(model['L'].shape),
            liouvillian_nnz=int(model['L'].nnz))
        return model
    rk4_original=engine.rk4
    def counted_rk4(rhs,v,dt):
        rec=records[active];rec['rk4_calls']+=1;calls=0
        assert v.shape==(46656,)
        def counted_rhs(x):
            nonlocal calls
            calls+=1;rec['rhs_calls']+=1
            return rhs(x)
        result=rk4_original(counted_rhs,v,dt)
        assert calls==4
        return result
    expanded_original=engine.expanded
    def counted_expanded(*a,**kw):
        records[active]['expanded_calls']+=1
        return expanded_original(*a,**kw)
    quality_original=engine.quality
    def counted_quality(*a,**kw):
        records[active]['quality_calls']+=1
        return quality_original(*a,**kw)
    sample_original=engine.Trajectory.sample
    def counted_sample(self,step):
        records[self.case['id']]['sample_calls']+=1
        return sample_original(self,step)
    savez_original=np.savez
    def counted_savez(file,*a,**kw):
        if Path(file).name.startswith('rho_'):
            assert kw['rho'].shape==(216,216)
            records[active]['snapshot_writes']+=1
        return savez_original(file,*a,**kw)
    engine.build=counted_build;engine.rk4=counted_rk4
    engine.expanded=counted_expanded;engine.quality=counted_quality
    engine.Trajectory.sample=counted_sample;np.savez=counted_savez
    config=json.loads((args.source_cache/'config.json').read_text())
    config['local_source_commit']=report['source_commit']
    prior_local_seconds=194.6643578229996
    with tempfile.TemporaryDirectory() as tmp:
        started=time.monotonic();metrics,checks=task.run(config,tmp)
        elapsed=time.monotonic()-started
        assert checks['failures']==[]
        differences={}
        for s in metrics['cases']:
            cid=s['case']['id'];rec=records[cid]
            assert rec['rk4_calls']==s['steps'] and rec['rhs_calls']==s['rhs_calls']
            assert rec['sample_calls']==s['steps']+1
            assert rec['quality_calls']==rec['expanded_calls']==s['diagnostic_records']
            assert rec['snapshot_writes']==s['snapshots']
            assert rec['liouvillian_shape']==[46656,46656]
            differences[cid]={}
            for section in ('series','diagnostics'):
                with np.load(Path(tmp)/'report'/section/(cid+'.npz'),allow_pickle=False) as z:a=z['values']
                with np.load(args.github_cache/'files'/section/(cid+'.npz'),allow_pickle=False) as z:b=z['values']
                assert a.shape==b.shape and np.array_equal(np.isnan(a),np.isnan(b))
                finite=np.isfinite(a)&np.isfinite(b)
                error=float(np.max(abs(a[finite]-b[finite])))
                assert np.allclose(a,b,atol=1e-9,rtol=1e-9,equal_nan=True),(cid,section,error)
                differences[cid][section+'_max_abs_error']=error
    totals={k:sum(r[k] for r in records.values()) for k in
        ('rk4_calls','rhs_calls','expanded_calls','quality_calls','sample_calls','snapshot_writes')}
    assert totals==dict(rk4_calls=25000,rhs_calls=100000,expanded_calls=136,
                        quality_calls=136,sample_calls=25012,snapshot_writes=80)
    result=dict(status='INSTRUMENTED_LOCAL_REPLAY_MATCHES_VM_EXPORT',local_only=True,
        source_commit=report['source_commit'],report_commit='26ddea1e48f1c48d8ae767d389452297376a5b1f',
        local_time=dict(prior_local_seconds=prior_local_seconds,actual_seconds=elapsed,
                        purpose='audit execution cost only; not a VM forecast or calibration'),
        counters=totals,per_case=records,export_comparison=differences,
        environment=metrics['environment'],
        limitations=['Actual callback calls counted in this local replay, not retroactively inside the finished VM process.',
          'VM rhs_calls is derived as four times steps. Pinned RK4 code, independent replay counts and matching exported trajectories support execution completeness.',
          'The local environment differs from the VM; local runtime is not used for the production forecast.'])
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(status=result['status'],local_time=result['local_time'],counters=totals)))

if __name__=='__main__':main()
