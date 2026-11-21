"""Self-consistent complex poles on the explicitly defined second sheet."""
from __future__ import annotations
import numpy as np
from scipy.optimize import root
from .model import R040Parameters
from .feshbach import full_effective_matrix


def pole_equation(z: complex, p: R040Parameters, sheet: str = "II") -> complex:
    return complex(np.linalg.det(full_effective_matrix(z, p, sheet=sheet)))


def classify_pole(z: complex, p: R040Parameters, tol: float = 1e-9) -> dict:
    z = complex(z)
    bath = p.bath()
    if z.imag >= -tol:
        return {"status": "WRONG_SIGN_OR_NOT_DECAYING_POLE", "z": [z.real, z.imag],
                "width": None}
    width = -2.0 * z.imag
    if bath.lower_edge < z.real < bath.upper_edge:
        status = "SECOND_SHEET_RESONANCE"
    else:
        status = "SECOND_SHEET_POLE_OUTSIDE_BAND_CLASSIFY_SEPARATELY"
    return {"status": status, "z": [float(z.real), float(z.imag)],
            "width": float(width)}


def solve_second_sheet_pole(p: R040Parameters, seed: complex,
                            residual_tol: float = 1e-8,
                            maxfev: int = 4000) -> dict:
    """Solve det[z-H3-s_II(z)|2><2|]=0 from one explicit complex seed."""
    seed = complex(seed)

    def fun(xy: np.ndarray) -> np.ndarray:
        z = complex(float(xy[0]), float(xy[1]))
        value = pole_equation(z, p, sheet="II")
        return np.array([value.real, value.imag], dtype=float)

    result = root(fun, np.array([seed.real, seed.imag]), method="hybr",
                  options={"maxfev": int(maxfev), "xtol": 1e-11})
    z = complex(result.x[0], result.x[1])
    residual = abs(pole_equation(z, p, sheet="II"))
    scale = max(1.0, np.linalg.norm(z * np.eye(3) - p.H3, ord="fro") ** 3)
    converged = bool(result.success and np.isfinite(residual)
                     and residual / scale <= residual_tol)
    classified = classify_pole(z, p)
    if not converged:
        status = "ROOT_NOT_CONVERGED"
    elif classified["status"] == "WRONG_SIGN_OR_NOT_DECAYING_POLE":
        status = "WRONG_SHEET_POLE_REJECTED"
    else:
        status = classified["status"]
    return {
        "status": status,
        "z": [float(z.real), float(z.imag)],
        "width": classified["width"] if status not in {"ROOT_NOT_CONVERGED", "WRONG_SHEET_POLE_REJECTED"} else None,
        "determinant_residual": float(residual),
        "scaled_residual": float(residual / scale),
        "solver_success": bool(result.success),
        "solver_message": str(result.message),
        "sheet": "II",
        "seed": [seed.real, seed.imag],
    }
