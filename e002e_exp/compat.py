"""Preserve explicit tolerances across the measured SciPy/NumPy versions."""
import inspect
import numpy as np
from scipy.sparse.linalg import gmres as scipy_gmres

def gmres(A, b, *, rtol, atol, **kwargs):
    relative_name = 'rtol' if 'rtol' in inspect.signature(scipy_gmres).parameters else 'tol'
    return scipy_gmres(A, b, **{relative_name: rtol, 'atol': atol}, **kwargs)

def trapezoid(y, x, axis=0):
    fn = np.trapezoid if hasattr(np, 'trapezoid') else np.trapz
    return fn(y, x, axis=axis)
