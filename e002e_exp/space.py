"""Charge-covariant q=0 Liouvillian, without a dense Liouville matrix."""
from dataclasses import dataclass
import numpy as np
from scipy import sparse as sp
from e002_exp.model import clean, maxabs


@dataclass
class Space:
    charges: np.ndarray

    def __post_init__(self):
        self.charges = np.asarray(self.charges, dtype=int)
        self.d = len(self.charges)
        self.groups = [np.flatnonzero(self.charges == n) for n in np.unique(self.charges)]
        self.sizes = [len(g) ** 2 for g in self.groups]
        self.offsets = np.r_[0, np.cumsum(self.sizes)]
        self.indices = np.concatenate([(g[:, None] + self.d*g[None, :]).ravel(order='F') for g in self.groups])
        self.trace_indices = np.concatenate([off + np.arange(len(g))*(len(g)+1)
                                            for off, g in zip(self.offsets, self.groups)])
        self.size = len(self.indices)
        self.trace_row = sp.csr_matrix((np.ones(self.d), (np.zeros(self.d, int), self.trace_indices)), shape=(1, self.size))

    def pack(self, matrix, tolerance=1e-12):
        a = matrix.toarray() if sp.issparse(matrix) else np.asarray(matrix)
        if a.shape != (self.d, self.d):
            raise ValueError('Hilbert dimensions disagree')
        if maxabs(np.where(self.charges[:, None] != self.charges[None, :], a, 0)) > tolerance:
            raise ValueError('Input has components outside q=0')
        return a.ravel(order='F')[self.indices].copy()

    def unpack(self, vector):
        v = np.asarray(vector)
        if v.shape != (self.size,):
            raise ValueError('Reduced vector shape mismatch')
        a = np.zeros(self.d*self.d, complex)
        a[self.indices] = v
        return a.reshape(self.d, self.d, order='F')

    def row(self, operator):
        # trace(O rho), without conjugation of O: vec(O.T)^T vec(rho).
        a = operator.toarray() if sp.issparse(operator) else np.asarray(operator)
        return a.T.ravel(order='F')[self.indices]

    def trace(self, vector):
        return np.asarray(vector)[self.trace_indices].sum(axis=0)


def charge_checks(H, jumps, space, tolerance=1e-12):
    h = sp.coo_matrix(H)
    hbad = maxabs(h.data[space.charges[h.row] != space.charges[h.col]])
    deltas = {}
    for name, C in jumps:
        c = sp.coo_matrix(C)
        nz = abs(c.data) > tolerance
        ds = np.unique(space.charges[c.row[nz]] - space.charges[c.col[nz]])
        if len(ds) > 1:
            raise ValueError('Jump lacks definite charge: ' + name)
        deltas[name] = int(ds[0]) if len(ds) else None
    if hbad > tolerance:
        raise ValueError('Hamiltonian violates charge covariance')
    return dict(H_charge_residual=hbad, jump_charge_changes=deltas)


def liouvillian(H, jumps, space):
    """Exact block construction; every within-charge coherence is retained."""
    charge_checks(H, jumps, space)
    H = sp.csr_matrix(H)
    count = len(space.groups)
    blocks = [[sp.csr_matrix((space.sizes[a], space.sizes[b]), dtype=complex)
               for b in range(count)] for a in range(count)]
    for a, g in enumerate(space.groups):
        h = H[g][:, g]; eye = sp.eye(len(g), format='csr')
        blocks[a][a] += -1j*(sp.kron(eye, h) - sp.kron(h.T, eye))
    for _, C in jumps:
        C = sp.csr_matrix(C); loss = clean(C.getH() @ C)
        for a, ga in enumerate(space.groups):
            eye = sp.eye(len(ga), format='csr'); m = loss[ga][:, ga]
            blocks[a][a] -= .5*(sp.kron(eye, m) + sp.kron(m.T, eye))
            for b, gb in enumerate(space.groups):
                c = C[ga][:, gb]
                if c.nnz:
                    blocks[a][b] += sp.kron(c.conjugate(), c)
    L = clean(sp.bmat(blocks, format='csr'))
    if maxabs(space.trace_row @ L) > 1e-11:
        raise ValueError('Reduced generator is not trace preserving')
    return L


def dissipator_action(C, rho):
    C = sp.csr_matrix(C); m = C.getH() @ C
    right = lambda a, b: (b.T @ a.T).T
    return right(C @ rho, C.getH()) - .5*(m @ rho + right(rho, m))
