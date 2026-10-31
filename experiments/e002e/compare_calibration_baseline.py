"""Compare pinned exported E002d endpoints with stationary calibration outputs."""
import argparse,json,time
from pathlib import Path
import numpy as np

def main():
    p=argparse.ArgumentParser();p.add_argument('report');p.add_argument('case');p.add_argument('output');a=p.parse_args()
    start=time.perf_counter();folder=Path(a.report)
    new=json.loads((folder/(a.case+'.json')).read_text());model=new['case']['model']
    source=json.loads(Path('experiments/e002e/baseline_reference_v001.json').read_text());old=source['cases'][model]
    assert new['case']['phi_over_pi']==.5 and new['case']['epsilon']==0 and new['case']['node_noise']==.05 and new['case']['m6_v_over_J']==1
    raw=new['raw'];ref=old['scalar_endpoint'];diff={}
    for k,v in raw.items():
        name='h' if k=='J_h' else k
        if name in ref and isinstance(v,(int,float)):diff[k]=abs(v-ref[name])
    blocks=json.loads((folder/(a.case+'_nodes.json')).read_text())
    n=np.array(blocks['real'])+1j*np.array(blocks['imag']);o=np.array(old['nodes_real'])+1j*np.array(old['nodes_imag'])
    error=float(abs(n-o).max());tol={'QS':1e-8,'RR_QS':5e-6}[model]
    out=dict(model=model,old_source=old['path'],old_sha256=old['sha256'],old_report_commit=source['report_commit'],
        old_time=200.,old_dt=.005,new_case=a.case,new_equation_residual=new['quality']['Lrho_inf'],
        primitive_count=len(diff),primitive_differences=diff,max_primitive_difference=max(diff.values()),
        node_block_max_difference=error,tolerance=tol,status='PASS' if error<=tol and max(diff.values())<=tol else 'FAIL',
        scope='Numerical baseline equivalence only; no mixed-horizon physical gap inference',internal_seconds=time.perf_counter()-start)
    Path(a.output).write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
    return 0 if out['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
