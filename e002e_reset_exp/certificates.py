"""Operator-premise checks for the published algebraic uniqueness argument."""
import itertools
import numpy as np
from scipy import sparse as sp
from scipy.sparse.csgraph import connected_components
from e002_exp.model import maxabs,adjoint_jump
from e002e_exp.model import make_full
from e002e_corr_exp.core import physicality,marginals,sector_check,array_hash
from .core import matrix_hash,entropy


def support_graph(H,jumps):
    loss=sum((c.getH()@c for _,c in jumps),sp.csr_matrix(H.shape,dtype=complex))
    if maxabs(loss-sp.diags(loss.diagonal()))>1e-12:raise ArithmeticError('Original loss is not diagonal')
    effective=H-.5j*loss;edges=set()
    for A in [effective,*[c for _,c in jumps]]:
        a=A.tocoo()
        edges.update((int(j),int(i)) for i,j,v in zip(a.row,a.col,a.data) if i!=j and abs(v)>1e-12)
    ij=np.array(sorted(edges),int).T
    graph=sp.csr_matrix((np.ones(len(edges)),ij),shape=H.shape)
    count,_=connected_components(graph,directed=True,connection='strong')
    return edges,int(count),effective


def uniqueness(model):
    if model['space'].d!=216:raise ValueError('Production certificate requires 216 Hilbert states')
    old=make_full(dict(model['case'],m6_v_over_J=0.),assemble=False)
    names=['node_dephase_'+str(i) for i in range(3)]+['edge_dephase_'+s for s in ('01','12','02')]
    jumps=dict(model['jumps']);diags=[];projector_error=0.
    for name in names:
        op=jumps[name];diag=op.diagonal();spectrum=np.unique(diag)
        if maxabs(op-sp.diags(diag))>1e-12 or len(spectrum)!=(2 if name.startswith('node') else 3):
            raise ArithmeticError('Dephasing premise failed')
        diags.append(diag)
        for value in spectrum:
            p=np.ones(len(diag),complex)
            for other in spectrum:
                if other!=value:p*=((diag-other)/(value-other))
            projector_error=max(projector_error,maxabs(p-(diag==value)))
    if np.unique(np.array(diags).T,axis=0).shape[0]!=216 or projector_error>1e-12:
        raise ArithmeticError('Joint rank-one projectors not complete')
    if set(dict(old['jumps']))!=set(jumps) or any(matrix_hash(c)!=matrix_hash(jumps[n]) for n,c in old['jumps']):
        raise ArithmeticError('v change altered jumps')
    e0,c0,h0=support_graph(old['H'],old['jumps']);e1,c1,h1=support_graph(model['H'],model['jumps'])
    if c0!=1 or c1!=1 or not e0<=e1:raise ArithmeticError('Connectivity extension premise failed')
    return dict(status='OPERATOR_PREMISES_VERIFIED',model=model['case']['model'],dimension=216,
        projectors=216,projector_error=projector_error,strong_components_v0=c0,strong_components_v1=c1,
        original_edges=len(e0),v1_edges=len(e1),lost_edges=len(e0-e1),
        H_effective_v0_sha256=matrix_hash(h0),H_effective_v1_sha256=matrix_hash(h1),
        jump_sha256={n:matrix_hash(c) for n,c in model['jumps']},
        gamma_extension='All double-index Kraus jumps: sum KdagK=I, Heff_gamma=Heff_v1-i*gamma*I/2',
        result='UNIQUE_FAITHFUL_RELAXING_NESS',numerical_gap='NOT_MEASURED')


def state_record(model,x,reset,gamma):
    space=model['space'];rho=space.unpack(x)
    quality=physicality(space,x,1e-9);sector=sector_check(space,rho,rho,1e-10)
    action=reset.certify_action(x);rx=reset.apply(x);rr=space.unpack(rx)
    raw={}
    for n,op in model['observables'].items():
        value=complex(space.row(op)@x)
        if n.startswith('C_'):raw[n]=dict(re=float(value.real),im=float(value.imag))
        else:
            if abs(value.imag)>1e-9:raise ArithmeticError('Complex Hermitian observable '+n)
            raw[n]=float(value.real)
    if max(abs(raw['F']-raw['J_h']),abs(raw['F']-raw['source']))>1e-9:
        raise ArithmeticError('Stationary output balance failed')
    nodes,edges=marginals(rho,reset.dimensions)
    e=[entropy(a) for a in (nodes,edges,rho)]
    delta=rr-rho
    energy=float(np.trace(model['H']@delta).real)
    inv=model['observables']['inventory']
    inv_event=float(np.trace(inv@delta).real)
    base_resource=1j*(model['H']@inv-inv@model['H'])+sum(adjoint_jump(c,inv) for _,c in model['jumps'])
    resource=float(np.trace(base_resource@rho).real)
    if abs(resource+gamma*inv_event)>1e-9:raise ArithmeticError('Inventory balance failed')
    dissipation={name:float(np.trace(adjoint_jump(c,model['H'])@rho).real) for name,c in model['jumps']}
    power=gamma*energy
    if abs(sum(dissipation.values())+power)>1e-9:raise ArithmeticError('Energy balance failed')
    distance=float(np.abs(np.linalg.eigvalsh(((edges-reset.tau)+(edges-reset.tau).conj().T)/2)).sum()/2)
    return dict(gamma=gamma,state_sha256=array_hash(x),raw=raw,physicality=quality,sector=sector,reset_action=action,
        correlations=dict(mutual_information=e[0]['value']+e[1]['value']-e[2]['value'],entropy_diagnostics=e,
                          edge_trace_distance_to_target=distance),
        energy=dict(delta_E_event=energy,P_reset=power,dissipator_power=dissipation,
                    balance_residual=abs(sum(dissipation.values())+power),full_external_cost='NOT_MEASURED'),
        resource=dict(delta_inventory_event=inv_event,reset_rate=gamma*inv_event,original_rate=resource,
                      balance_residual=abs(resource+gamma*inv_event)))
