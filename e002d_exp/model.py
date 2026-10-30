"""Add only independent diagonal Lindblad jumps to the pinned E002c model."""
import numpy as np
from scipy import sparse as sp
from e002_exp.model import clean,maxabs
from e002c_exp.model import build as base_build,operators

TARGETS={'A':(2,5,6),'B':(4,3,6)}
MONITORS={**TARGETS,'N1_A':(2,1,2),'N1_B':(4,1,4)}
NUMBERS=np.array([i.bit_count() for i in range(8)])

def jump_diagonals(target,kind,gamma):
    if target=='base':
        if kind!='base' or gamma!=0:raise ValueError('Invalid baseline')
        return []
    if target not in ('A','B','AB') or kind not in ('T','C') or not np.isfinite(gamma) or gamma<0:
        raise ValueError('Invalid intervention')
    result=[]
    for key in (('A','B') if target=='AB' else (target,)):
        mask,a,b=TARGETS[key];node=np.zeros(8);node[a]=1;node[b]=-1 if kind=='T' else 1
        edge=(operators()['mask_id']==mask).astype(float)
        result.append((key,np.sqrt(gamma)*np.kron(node,edge)))
    return result

def damping(diagonals):
    result=np.zeros((216,216))
    for _,d in diagonals:result+=.5*(d[:,None]-d[None,:])**2
    return result

def consequence_map():
    result={}
    for target in ('A','B','AB'):
        t=damping(jump_diagonals(target,'T',1.));c=damping(jump_diagonals(target,'C',1.))
        expected=np.zeros_like(t)
        for key in (('A','B') if target=='AB' else (target,)):
            mask,a,b=TARGETS[key];edge=np.flatnonzero(operators()['mask_id']==mask)
            ia=a*27+edge;ib=b*27+edge
            expected[np.ix_(ia,ib)]=2.;expected[np.ix_(ib,ia)]=2.
        error=float(np.max(abs(t-c-expected)))
        result[target]=dict(gamma=1.,difference_error=error,
            target_control_difference_values=np.unique(t-c).tolist(),
            changed_matrix_entries=int(np.count_nonzero(expected)),
            target_rates=np.unique(t).tolist(),control_rates=np.unique(c).tolist(),
            population_damping=float(max(np.max(abs(t.diagonal())),np.max(abs(c.diagonal())))),
            independent_jump_count=2 if target=='AB' else 1)
        if error>1e-12:raise ValueError('Unmatched collateral')
    return result

def extra_observables(model):
    names=[];ops=[];o=operators();h=model['currents'][1]+model['currents'][2]
    for m in range(8):
        for n in range(4):
            p=sp.kron(sp.diags((NUMBERS==n).astype(float)),o['masks'][m],format='csr')
            names.extend([f'p_m{m}_N{n}',f'h_m{m}_N{n}']);ops.extend([p,clean(p@h)])
    for key,(m,a,b) in MONITORS.items():
        node=np.zeros((8,8),complex);node[b,a]=1
        op=sp.kron(node,o['masks'][m],format='csr')
        names.extend([f'C_{key}_re',f'C_{key}_im'])
        ops.extend([clean((op+op.getH())/2),clean((op-op.getH())/(2j))])
    rows=sp.vstack([sp.csr_matrix(op.T.toarray().reshape(1,-1,order='F')) for op in ops],format='csr')
    return names,rows

def build(case,alpha=None):
    if alpha is not None or case['model'] not in ('QS','RR_QS'):raise ValueError('E002d scope is QS/RR only')
    model=base_build(case)
    ds=jump_diagonals(case['target'],case['kind'],float(case['gamma']))
    rates=damping(ds);addition=-sp.diags(rates.reshape(-1,order='F'),format='csr')
    model['L']=clean(model['L']+addition)
    model['jumps'] += [(f'selective_{key}_{case["kind"]}',sp.diags(d,format='csr')) for key,d in ds]
    names,rows=extra_observables(model)
    model['rows']=sp.vstack([model['rows'],rows],format='csr');model['names']+=names
    model['checks'].update(selective_population_damping=float(np.max(abs(rates.diagonal()))),
        selective_trace=float(maxabs(sp.csr_matrix(np.eye(216).reshape(1,-1,order='F'))@addition)),
        selective_H_change=0.)
    if max(model['checks'].values())>1e-10:raise ValueError('Operator identity failed')
    return model
