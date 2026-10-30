"""Bounded local equivalence/CPU benchmark, no production trajectories."""
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import numpy as np
import scipy
from scipy import sparse as sp

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'source'))
from e002_exp.model import rk4
from e002c_exp.model import build, initial, operators
from e002c_exp.diagnostics import expanded, quality
from invariant_rhs import NumberDiagonalRHS, compiled_direct_rhs

def seconds(call, count=100):
    # Five interleaved batches, each 20 RHS calls; warmup counted separately.
    values=[]
    for _ in range(5):
        start=time.perf_counter()
        for __ in range(count//5): call()
        values.append((time.perf_counter()-start)/(count//5))
    return float(np.median(values))

def csr_bytes(a):
    return a.data.nbytes+a.indices.nbytes+a.indptr.nbytes

class Adapter:
    def __init__(self, rhs): self.rhs=rhs
    def __matmul__(self, v): return self.rhs(v)

def main():
    started=time.perf_counter()
    manifest=json.loads((ROOT/'source_manifest.json').read_text())
    for name, meta in manifest['files'].items():
        assert hashlib.sha256((ROOT/'source'/name).read_bytes()).hexdigest()==meta['sha256']
    charges=np.repeat([n.bit_count() for n in range(8)],27)
    rng=np.random.default_rng(20261030)
    rho=np.zeros((216,216),complex)
    for number in range(4):
        idx=np.flatnonzero(charges==number)
        a=rng.normal(size=(len(idx),len(idx)))+1j*rng.normal(size=(len(idx),len(idx)))
        rho[np.ix_(idx,idx)]=a@a.conj().T
    rho/=np.trace(rho)
    random_state=rho.reshape(-1,order='F')
    rows=[]
    for variant in ['QS','RR_QS']:
        for probe in ['baseline','target','control']:
            case=dict(model=variant,dephasing=.05,phi_over_pi=0.,detuning=0.)
            start=time.perf_counter();model=build(case);base_build=time.perf_counter()-start
            h,jumps=model['H'],list(model['jumps'])
            generator=model['L'].copy()
            for m,a,b in ([] if probe=='baseline' else [(2,5,6),(4,3,6)]):
                node=np.zeros(8);node[a]=1;node[b]=-1 if probe=='target' else 1
                lam=np.sqrt(.1)*np.kron(node,(operators()['mask_id']==m).astype(float))
                jumps.append((f'probe_{m}',sp.diags(lam,format='csr')))
                generator+=sp.diags((-.5*(lam[:,None]-lam[None,:])**2).reshape(-1,order='F'),format='csr')
            generator=generator.tocsr();generator.eliminate_zeros()
            start=time.perf_counter();direct=compiled_direct_rhs(h,jumps);direct_compile=time.perf_counter()-start
            start=time.perf_counter();reduced=NumberDiagonalRHS(generator,charges);reduce_compile=time.perf_counter()-start
            model['L']=generator
            tests=[initial(),random_state]
            rhs_errors={'direct':0.,'reduced':0.}
            for full in tests:
                reference=generator@full
                rhs_errors['direct']=max(rhs_errors['direct'],float(np.max(abs(direct(full)-reference))))
                rhs_errors['reduced']=max(rhs_errors['reduced'],float(np.max(abs(reduced.full_rhs(full)-reference))))
            assert max(rhs_errors.values())<=1e-12
            packed=reduced.pack(random_state)
            for call in [lambda:generator@random_state,lambda:direct(random_state),lambda:reduced.dot(packed)]:call()
            timings={}
            # Alternate order across cases; timing ratios are local, not production predictions.
            calls={'csr':lambda:generator@random_state,'direct':lambda:direct(random_state),'reduced':lambda:reduced.dot(packed)}
            for key in (list(calls) if len(rows)%2==0 else list(reversed(calls))):timings[key]=seconds(calls[key])
            paths={'csr':generator.dot,'direct':direct,'reduced':reduced.dot}
            final={};step_times={};diag_times={};diagnostics={};qualities={};scalars={}
            for key, rhs in paths.items():
                v=reduced.pack(initial()) if key=='reduced' else initial()
                start=time.perf_counter()
                for _ in range(20):v=rk4(rhs,v,.01)
                step_times[key]=time.perf_counter()-start
                v=reduced.unpack(v) if key=='reduced' else v
                final[key]=v
                start=time.perf_counter()
                mat=v.reshape(216,216,order='F')
                _,values,_=expanded(mat,model)
                quality_rhs=reduced.full_rhs if key=='reduced' else rhs
                q=quality(mat,Adapter(quality_rhs))
                diag_times[key]=time.perf_counter()-start
                diagnostics[key]=values;qualities[key]=q
                scalars[key]=model['rows']@v
            state_errors={k:float(np.max(abs(v-final['csr']))) for k,v in final.items()}
            scalar_errors={k:float(np.max(abs(v-scalars['csr']))) for k,v in scalars.items()}
            diagnostic_errors={}
            for k,v in diagnostics.items():
                assert np.array_equal(np.isnan(v),np.isnan(diagnostics['csr']))
                diagnostic_errors[k]=float(np.max(abs(v-diagnostics['csr'])[np.isfinite(v)],initial=0))
            assert max(state_errors.values())<1e-10
            assert max(scalar_errors.values())<1e-10
            assert max(diagnostic_errors.values())<1e-10
            unsupported=initial();unsupported[27]=1e-8
            refused=False
            try:reduced.pack(unsupported)
            except ValueError:refused=True
            assert refused
            source_sink_cross=0
            # Count coupling between different diagonal-N sectors inside the retained coordinates.
            reduced_charge=charges[reduced.keep%216]
            coo=reduced.matrix.tocoo()
            source_sink_cross=int(np.count_nonzero(reduced_charge[coo.row]!=reduced_charge[coo.col]))
            assert source_sink_cross>0
            rows.append(dict(model=variant,probe=probe,dimension_full=46656,dimension_reduced=len(reduced.keep),
                full_nnz=generator.nnz,reduced_nnz=reduced.matrix.nnz,leakage_nnz=reduced.leakage_nnz,
                cross_number_population_couplings=source_sink_cross,unsupported_state_refused=refused,
                csr_bytes_full=csr_bytes(generator),csr_bytes_reduced=csr_bytes(reduced.matrix),
                base_build_seconds=base_build,direct_compile_seconds=direct_compile,restriction_compile_seconds=reduce_compile,
                rhs_max_errors=rhs_errors,rhs_median_seconds=timings,
                direct_rhs_speedup=timings['csr']/timings['direct'],reduced_rhs_speedup=timings['csr']/timings['reduced'],
                rk4_20_steps_seconds=step_times,diagnostics_once_seconds=diag_times,
                short_state_max_errors=state_errors,scalar_max_errors=scalar_errors,diagnostic_max_errors=diagnostic_errors,
                endpoint_quality=qualities))
    # Reject a deliberately non-invariant generator, rather than silently discard new dynamics.
    bad=generator.tolil();bad[27,reduced.keep[0]]=1e-4
    invariant_guard=False
    try:NumberDiagonalRHS(bad.tocsr(),charges)
    except ValueError:invariant_guard=True
    assert invariant_guard
    result=dict(status='PASS',elapsed_seconds=time.perf_counter()-started,source_commit=manifest['commit'],
        numpy=np.__version__,scipy=scipy.__version__,blas_threads=os.environ.get('OPENBLAS_NUM_THREADS'),
        rk4_steps_per_path_case=20,dt=.01,horizon=.2,rhs_timed_calls_per_path_case=100,
        leaking_generator_refused=invariant_guard,results=rows,
        limitations=['CPU microbenchmark, not VM production speedup','No peak RSS measured','Diagnostics measured once per path; not production frequency',
        'All paths use the reference full-L builder in this harness; construction cost retained','No long-run stationarity/dt convergence or production engine integration'])
    (ROOT/'benchmark_results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(status=result['status'],seconds=result['elapsed_seconds'],cases=[dict(model=r['model'],probe=r['probe'],
        direct_speedup=r['direct_rhs_speedup'],reduced_speedup=r['reduced_rhs_speedup'],max_rhs_error=max(r['rhs_max_errors'].values()),
        max_state_error=max(r['short_state_max_errors'].values()),max_diagnostic_error=max(r['diagnostic_max_errors'].values())) for r in rows]),indent=2))

if __name__=='__main__':main()
