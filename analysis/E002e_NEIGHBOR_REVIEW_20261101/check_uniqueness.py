"""Sufficient algebra-generation certificate, without constructing a Liouvillian."""
import json,time,itertools,platform,sys
from pathlib import Path
import numpy as np
from scipy import sparse as sp
from scipy.sparse.csgraph import connected_components
from e002e_exp.model import make_full
from e002e_exp.plan import selected_work
from e002e_exp.runtime import environment,kernel_hash
from e002_exp.model import maxabs
D=Path(__file__).resolve().parent
def main():
    checks=[]
    for model in ('QS','RR_QS'):
        case=next(c for c in selected_work('F2')['full'] if c['model']==model and c['m6_v_over_J']==0 and c['epsilon']==0)
        m=make_full(case,assemble=False);assert 'L' not in m;J=dict(m['jumps']);I=sp.eye(216,format='csr')
        # Each of six dephasing jumps has nondegenerate LOCAL eigenvalues.
        # Spectral projectors are polynomials, hence products give all216 P_i.
        names=['node_dephase_'+str(i) for i in range(3)]+['edge_dephase_'+e for e in ('01','12','02')]
        projectors=[];diags=[];polynomial_error=0.
        for name in names:
            op=J[name];diag=op.diagonal();assert maxabs(op-sp.diags(diag))==0
            eig=np.unique(diag);assert len(eig)==(2 if name.startswith('node') else 3)
            qs=[]
            for a in eig:
                q=I.copy()
                for b in eig:
                    if a!=b:q=q@(op-b*I)/(a-b)
                polynomial_error=max(polynomial_error,maxabs(q-sp.diags((diag==a).astype(float))))
                qs.append(q.diagonal())
            projectors.append(qs);diags.append(diag)
        assert np.unique(np.array(diags).T,axis=0).shape==(216,6)
        picked=[]
        for factors in itertools.product(*projectors):
            q=np.prod(np.array(factors),axis=0);ix=np.flatnonzero(abs(q)>.5);assert len(ix)==1;picked.append(int(ix[0]));assert abs(q[ix[0]]-1)<1e-12
        assert sorted(picked)==list(range(216)) and polynomial_error<1e-12
        damping=sum((c.getH()@c for c in J.values()),sp.csr_matrix((216,216),dtype=complex))
        assert maxabs(damping-sp.diags(damping.diagonal()))==0
        Heff=m['H']-.5j*damping
        edges=set();minimum=None
        for op in [Heff,*J.values()]:
            x=op.tocoo()
            for i,j,z in zip(x.row,x.col,x.data):
                if i!=j and abs(z)>1e-12:
                    edges.add((int(j),int(i)));minimum=abs(z) if minimum is None else min(minimum,abs(z))
        graph=sp.csr_matrix((np.ones(len(edges)),tuple(np.array(sorted(edges)).T)),shape=(216,216))
        count,labels=connected_components(graph,directed=True,connection='strong');assert count==1
        checks.append(dict(model=model,dimension=216,diagonal_rank_one_projectors=len(picked),projector_error=polynomial_error,directed_support_edges=len(edges),strong_components=int(count),smallest_used_offdiagonal_magnitude=float(minimum),Heff_offdiagonal_equals_H=True,full_operator_algebra_dimension=216**2,condition='All P_i belong to algebra. For edge j->i, P_i A P_j=A_ij E_ij. Directed paths generate every E_ij.',conclusion='YOSHIDA_SUFFICIENT_CONDITION_PASSED_UNIQUE_FAITHFUL_NESS',extension='epsilon changes H by a diagonal operator only; same certificate holds for all real epsilon at v=0',new_liouvillians=0,new_NESS=0))
    out=dict(kernel_sha256=kernel_hash(),checks=checks,environment=environment(),scope='Exact support/algebra argument checked against numerical216x216 builders; not a spectral-gap or relaxation-time computation')
    (D/'uniqueness.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(dict(checks=checks,kernel=out['kernel_sha256'])))
if __name__=='__main__':main()
