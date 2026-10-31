import json
from pathlib import Path
import numpy as np
from scipy.linalg import lu_factor, lu_solve

def main():
    nodes=np.array([(s//27).bit_count() for s in range(216)])
    idx=[];trace=[];offset=0;dims=[];offsets=[]
    for n in range(4):
        ids=np.flatnonzero(nodes==n);d=len(ids);dims.append(d);offsets.append(offset)
        idx.extend((ids[:,None]+216*ids[None,:]).ravel(order='F'))
        trace.extend(offset+np.arange(d)*(d+1));offset+=d*d
    idx=np.array(idx);trace=np.array(trace)
    assert dims==[27,81,81,27] and offsets==[0,729,7290,13851]
    allq=np.flatnonzero((nodes[:,None]==nodes[None,:]).ravel(order='F'))
    assert len(idx)==14580 and np.array_equal(np.sort(idx),allq)
    assert len(trace)==216 and set(idx[trace])==set(np.arange(216)*217)
    rng=np.random.default_rng(241031);v=rng.normal(size=14580)+1j*rng.normal(size=14580)
    full=np.zeros(216**2,complex);full[idx]=v
    assert np.array_equal(full[idx],v)
    assert abs(v[trace].sum()-np.trace(full.reshape(216,216,order='F')))<1e-12
    L=np.array([[-1.,2.],[1.,-2.]])
    border=np.zeros((3,3));border[:2,:2]=L;border[:2,2]=.5;border[2,:2]=1
    rhs=np.array([[0,2/3],[0,-2/3],[1,0.]])
    factors=lu_factor(border);out=lu_solve(factors,rhs)
    expected=np.array([[2/3,-2/9],[1/3,2/9],[0,0.]])
    error=float(abs(out-expected).max());residual=float(abs(border@out-rhs).max())
    assert error<1e-14 and residual<1e-14
    data={'passed':True,'scope':'index sets and toy bordered solve only; no physical model assembly/evolution','dimensions':dims,'offsets':offsets,'q0_size':len(idx),'trace_entries':len(trace),'border_max_error':error,'border_residual':residual,'baseline_workload':{'factorizations':6,'NESS_rhs':6,'response_rhs':18,'total_rhs':24},'optional_all_model_detuning_extension':{'extra_factorizations':6,'extra_rhs':18,'total_factorizations':12,'total_rhs':42}}
    Path(__file__).with_name('construction_checks.json').write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps(data))

if __name__=='__main__':main()
