"""Explicit Z2 exchange symmetry check for the R040 trimer."""
from __future__ import annotations
import numpy as np
from .model import R040Parameters


def z2_exchange_operator() -> np.ndarray:
    """Swap internal nodes V and 1, leaving node 2 and the bath port fixed."""
    return np.array([[0,1,0],[1,0,0],[0,0,1]],dtype=complex)


def check_z2_exchange(p: R040Parameters, tol: float = 1e-12) -> dict:
    r=z2_exchange_operator()
    residual=float(np.linalg.norm(r @ p.H3 @ r.conj().T - p.H3,ord="fro"))
    dark=p.dark_vector
    odd_residual=float(np.linalg.norm(r @ dark + dark))
    passed=residual<=tol and odd_residual<=tol
    return {
        "status":"EXACT_Z2_EXCHANGE_SYMMETRY" if passed else "Z2_SYMMETRY_NOT_PRESENT",
        "hamiltonian_commutator_residual":residual,
        "dark_state_odd_parity_residual":odd_residual,
        "conditions":{
            "E_V_equals_E_1":bool(abs(p.E_V-p.E_1)<=tol),
            "gamma_d_equals_t_2":bool(abs(p.gamma_d-p.t_2)<=tol),
        },
        "scope":"trimer exchange V<->1; bath port on node 2 remains invariant",
    }
