"""One-step transport test for a moving protected subspace.

The transport/isometry T_X is an input law.  It is never reconstructed from a
completed trajectory.  This module checks T_X^* P_{F(X)} T_X = P_X.
"""
from __future__ import annotations

import numpy as np


def validate_orthogonal_projector(projector: np.ndarray, tol: float = 1e-10) -> dict:
    if not np.isfinite(tol) or not 0 < tol <= 1e-3:
        raise ValueError('finite tolerance in (0,1e-3] required')
    p = np.asarray(projector, dtype=complex)
    if not np.all(np.isfinite(p)):
        raise ValueError('projector must be finite')
    if p.ndim != 2 or p.shape[0] != p.shape[1]:
        raise ValueError("projector must be square")
    herm = float(np.linalg.norm(p - p.conj().T, ord="fro"))
    idem = float(np.linalg.norm(p @ p - p, ord="fro"))
    if herm > tol or idem > tol:
        raise ValueError(f"invalid orthogonal projector (Hermitian={herm}, idempotence={idem})")
    return {"dimension": int(p.shape[0]), "rank": int(round(float(np.trace(p).real))),
            "hermiticity_residual": herm, "idempotence_residual": idem}


def check_moving_projector_transport(P_X: np.ndarray, P_FX: np.ndarray,
                                     T_X: np.ndarray, tol: float = 1e-9,
                                     source: str = "MODEL_ASSUMPTION") -> dict:
    """Check a declared isometry and the moving-projector intertwining identity.

    T_X shape is (dim(FX), dim(X)). It must be isometric: T^*T=I_X.
    No projector or transport operator is inferred from trajectory history.
    """
    p0 = np.asarray(P_X, dtype=complex)
    p1 = np.asarray(P_FX, dtype=complex)
    t = np.asarray(T_X, dtype=complex)
    meta0 = validate_orthogonal_projector(p0, tol=tol)
    meta1 = validate_orthogonal_projector(p1, tol=tol)
    if t.ndim != 2 or t.shape != (p1.shape[0], p0.shape[0]):
        raise ValueError("T_X dimensions must be (dim(FX), dim(X))")
    if not np.all(np.isfinite(t)):
        raise ValueError('T must be finite')
    iso_res = float(np.linalg.norm(t.conj().T @ t - np.eye(p0.shape[0]), ord="fro"))
    residual = float(np.linalg.norm(t.conj().T @ p1 @ t - p0, ord="fro"))
    pass_iso = iso_res <= tol
    pass_projector = residual <= tol
    return {
        "status": "MOVING_PROTECTED_SUBSPACE_TRANSPORT_PASS" if pass_iso and pass_projector
                  else "MOVING_PROTECTED_SUBSPACE_TRANSPORT_FAIL",
        "transport_source": source,
        "isometry_residual": iso_res,
        "projector_intertwining_residual": residual,
        "tolerance": float(tol),
        "isometry_pass": bool(pass_iso),
        "projector_intertwining_pass": bool(pass_projector),
        "source_projector": meta0,
        "target_projector": meta1,
        "future_history_used": False,
        "warning": "A passing algebraic identity is meaningful only if P_X, P_FX and T_X were fixed by a local prospective law before execution.",
    }


def role_following_identity_transport(dimension: int, accepted: bool = False) -> np.ndarray:
    """Return identity only under the explicit role-following transport postulate."""
    if accepted is not True:
        raise ValueError("identity role transport requires explicit MODEL_ASSUMPTION acceptance")
    if type(dimension) is not int or dimension <= 0:
        raise ValueError("dimension must be a positive integer")
    return np.eye(dimension, dtype=complex)


def projector_from_dark_vector(dark_vector: np.ndarray) -> np.ndarray:
    d = np.asarray(dark_vector, dtype=complex)
    if d.ndim != 1 or not np.isclose(np.linalg.norm(d), 1.0, atol=1e-10, rtol=0):
        raise ValueError("dark vector must be one-dimensional and normalized")
    return np.outer(d, d.conj())
