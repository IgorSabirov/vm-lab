"""Unconditional local CPTP edge maps. Never postselect or renormalize."""
import numpy as np
from scipy import sparse as sp
from .model import ketbra,tensor,maxabs
DIMS=(2,2,2,3,3,3)

def kraus(kind):
    p=[ketbra(3,i,i) for i in range(3)]
    if kind=='none':return [sp.eye(3,format='csr')]
    if kind=='link':return [p[0]+p[1],ketbra(3,0,2)]
    if kind=='feed':return [p[0]+p[1],ketbra(3,1,2)]
    if kind=='resource':return [p[0]+p[2],ketbra(3,0,1)]
    if kind=='hard':return [ketbra(3,0,i) for i in range(3)]
    raise ValueError(kind)

def complete(ks):
    err=maxabs(sum(k.getH()@k for k in ks)-sp.eye(3))
    if err>1e-12:raise ValueError('Incomplete Kraus map')
    return err

def apply(v,kind,edges=(0,1,2)):
    ks=kraus(kind);complete(ks)
    rho=v.reshape(216,216,order='F').copy()
    for e in edges:
        if e not in (0,1,2):raise ValueError('Invalid edge')
        out=np.zeros_like(rho)
        for k in ks:
            factors=[sp.eye(d,format='csr') for d in DIMS];factors[e+3]=k
            op=tensor(factors);left=op@rho;out+=(op.conj()@left.T).T
        rho=out
    return rho.reshape(-1,order='F')
