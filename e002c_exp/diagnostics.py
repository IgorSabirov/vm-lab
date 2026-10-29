"""State diagnostics. No separability claim is inferred from a zero negativity."""
import numpy as np
from .model import ONE, TWO, operators

FLOOR = 1e-6

def partial_transpose(rho, dims, subsystems):
    n=len(dims); axes=list(range(2*n))
    for i in subsystems: axes[i],axes[n+i]=axes[n+i],axes[i]
    return rho.reshape(tuple(dims)*2).transpose(axes).reshape(rho.shape)

def negativity(rho, dims, subsystems):
    pt=partial_transpose(rho,dims,subsystems)
    ev=np.linalg.eigvalsh((pt+pt.conj().T)/2)
    return float(-ev[ev<0].sum()),float(ev[0])

def node_blocks(rho):
    # Trace only diagonal edge blocks; projection on a mask is not on excitation number.
    a=np.einsum('aebe->eab',rho.reshape(8,27,8,27))
    masks=operators()['mask_id']
    blocks=np.array([a[masks==m].sum(axis=0) for m in range(8)])
    return np.concatenate([blocks.sum(axis=0)[None],blocks])

def pair_reduction(rho, excluded):
    a=rho.reshape(2,2,2,2,2,2)
    return np.trace(a,axis1=excluded,axis2=excluded+3).reshape(4,4)

def phase_fix(v):
    i=np.flatnonzero(abs(v)>1e-12)
    return v if not len(i) else v*np.exp(-1j*np.angle(v[i[0]]))

def deterministic_eigh(a):
    vals,vecs=np.linalg.eigh((a+a.conj().T)/2)
    out=[];i=0
    while i<len(vals):
        j=i+1
        while j<len(vals) and abs(vals[j]-vals[i])<=1e-12*max(1.,np.max(abs(vals))):j+=1
        projector=vecs[:,i:j]@vecs[:,i:j].conj().T
        basis=[]
        for col in projector.T:
            v=col.astype(complex,copy=True)
            for _ in range(2):
                for u in basis:v-=u*np.vdot(u,v)
            norm=np.linalg.norm(v)
            if norm>1e-10:
                basis.append(phase_fix(v/norm))
            if len(basis)==j-i:break
        if len(basis)!=j-i:raise ValueError('Degenerate basis construction failed')
        out.extend(basis);i=j
    return np.array(out).T

def schmidt_alpha(psi):
    t=psi.reshape(2,2,2)
    return max(float(np.linalg.svd(np.moveaxis(t,i,0).reshape(2,4),compute_uv=False)[0]**2) for i in range(3))

def witnesses(rho):
    vs=[]
    for sector in (ONE,TWO):
        v=deterministic_eigh(rho[np.ix_(sector,sector)])
        for j in range(3):
            psi=np.zeros(8,complex);psi[sector]=v[:,j];vs.append(psi)
    vs=np.array(vs);alpha=np.array([schmidt_alpha(v) for v in vs])
    overlap=np.array([np.vdot(v,rho@v).real for v in vs])
    return vs,alpha,overlap

def conditional_fraction(numerator,weight):
    if weight<=FLOOR:return dict(value=None,reason='weight_le_1e-6',weight=float(weight))
    return dict(value=float(numerator/weight),reason=None,weight=float(weight))

def certificate(blocks):
    vectors=np.zeros((9,6,8),complex);alpha=np.zeros((9,6));overlap=np.zeros((9,6))
    valid=np.trace(blocks,axis1=1,axis2=2).real>FLOOR
    for s in np.flatnonzero(valid):
        rho=blocks[s]/np.trace(blocks[s]).real
        vectors[s],alpha[s],overlap[s]=witnesses(rho)
    return dict(blocks=blocks,vectors=vectors,alpha=alpha,overlap=overlap,valid=valid)

def coherence_values(blocks):
    """C01=<010|rho_m|100>, unnormalised; conditional values divide by mask trace."""
    names=[];values=[]
    for conditional in (False,True):
        for m in (7,6):
            weight=float(np.trace(blocks[m+1]).real);c=complex(blocks[m+1,2,4])
            if conditional:c=c/weight if weight>FLOOR else complex(np.nan,np.nan)
            for part,value in (('re',c.real),('im',c.imag)):
                names.append(f"{'c' if conditional else 'C'}01_m{m}_{part}");values.append(value)
    return names,np.array(values,dtype=float)

def coherence_quality(weight):
    return 'undefined' if weight<=FLOOR else ('low_weight' if weight<1e-5 else 'ok')

def expanded(rho,model):
    blocks=node_blocks(rho);cert=certificate(blocks)
    n=[];v=[]
    def add(name,value):n.append(name);v.append(value)
    # Conditional mask currents, unnormalised. They sum to the full currents.
    a=rho.reshape(8,27,8,27)
    for m in range(8):
        sel=operators()['mask_id']==m
        for e,op in enumerate(model['currents']):
            # An edge-diagonal current permits extraction of its fixed edge block.
            inds=np.flatnonzero(sel)
            current=0.
            for k in inds:
                on=op[k::27,k::27].toarray()
                current+=np.trace(on@a[:,k,:,k]).real
            add(f'I{("01","12","02")[e]}_m{m}',current)
    for tag in ('isolated','interference'):
        for m in range(8):add(f'd_{tag}_m{m}',np.trace(model['dark'][m][tag]@blocks[m+1]).real)
    for excluded in range(3):add(f'pair_N_exclude{excluded}',negativity(pair_reduction(blocks[0],excluded),[2,2],[0])[0])
    for s in range(9):
        valid=bool(cert['valid'][s]);weight=np.trace(blocks[s]).real
        for cut in range(3):
            add(f'N_s{s}_cut{cut}',negativity(blocks[s]/weight,[2,2,2],[cut])[0] if valid else np.nan)
        add(f'W_s{s}',float(np.min(cert['alpha'][s]-cert['overlap'][s])) if valid else np.nan)
        add(f'valid_s{s}',float(valid))
    cn,cv=coherence_values(blocks);n.extend(cn);v.extend(cv)
    return n,np.array(v,dtype=np.float64),cert

def quality(rho,L):
    trace=float(abs(np.trace(rho)-1));herm=float(np.max(abs(rho-rho.conj().T)))
    eigen=float(np.linalg.eigvalsh((rho+rho.conj().T)/2)[0])
    rhs=float(np.linalg.norm(L@rho.reshape(-1,order='F'))/np.linalg.norm(rho))
    values=dict(trace=trace,hermiticity=herm,min_eigen=eigen,rhs=rhs)
    if not np.isfinite(list(values.values())).all() or trace>1e-10 or herm>1e-10 or eigen < -1e-8:
        raise ValueError('Unphysical state: '+str(values))
    return values
