"""Exact invariant-coordinate CSR restriction, with explicit input validation."""
import numpy as np
from scipy import sparse as sp

class NumberDiagonalRHS:
    def __init__(self, generator, charges):
        charges = np.asarray(charges)
        self.n = len(charges)
        if generator.shape != (self.n**2, self.n**2):
            raise ValueError('generator dimension mismatch')
        supported = (charges[:, None] == charges[None, :]).reshape(-1, order='F')
        self.keep = np.flatnonzero(supported)
        self.drop = np.flatnonzero(~supported)
        leak = generator[self.drop, :][:, self.keep]
        leak.eliminate_zeros()
        self.leakage_nnz = leak.nnz
        if leak.nnz:
            raise ValueError('subspace is not invariant: generator leaks outside')
        self.matrix = generator[self.keep, :][:, self.keep].tocsr()
        self.matrix.sum_duplicates(); self.matrix.eliminate_zeros(); self.matrix.sort_indices()

    def pack(self, full):
        full = np.asarray(full)
        if full.shape != (self.n**2,) or not np.isfinite(full).all():
            raise ValueError('invalid full state')
        if np.any(full[self.drop] != 0):
            raise ValueError('unsupported coherences: use full-space path')
        return full[self.keep].copy()

    def unpack(self, reduced):
        if np.shape(reduced) != (len(self.keep),):
            raise ValueError('reduced state dimension mismatch')
        full = np.zeros(self.n**2, dtype=np.complex128)
        full[self.keep] = reduced
        return full

    def dot(self, reduced):
        return self.matrix.dot(reduced)

    def full_rhs(self, full):
        return self.unpack(self.dot(self.pack(full)))

def compiled_direct_rhs(h, jumps):
    """Copilot's proposal: general direct Lindblad, declared diagonal channels compiled."""
    n = h.shape[0]
    damping = np.zeros((n, n), float)
    general = []
    def right(rho, a):
        return (a.T @ rho.T).T
    for name, c in jumps:
        diagonal = name.startswith(('node_dephase_', 'edge_dephase_', 'probe_'))
        if diagonal:
            lam = c.diagonal()
            other = c-sp.diags(lam, format='csr')
            other.eliminate_zeros()
            if other.nnz or np.any(lam.imag != 0):
                raise ValueError('declared Hermitian diagonal jump is not diagonal/Hermitian')
            damping -= .5*(lam.real[:, None]-lam.real[None, :])**2
        else:
            general.append((c, c.getH().tocsr(), (c.getH()@c).tocsr()))
    def rhs(v):
        rho = v.reshape((n, n), order='F')
        out = -1j*(h@rho-right(rho,h)) + damping*rho
        for c, ch, a in general:
            out += right(c@rho,ch)-.5*(a@rho+right(rho,a))
        return out.reshape(-1,order='F')
    return rhs
