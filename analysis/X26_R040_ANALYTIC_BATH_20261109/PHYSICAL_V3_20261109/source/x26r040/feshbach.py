"""Exact Schur/Feshbach reduction of (V,1,2) plus the bath on site 2."""
from __future__ import annotations
import numpy as np
from .model import R040Parameters


def q_denominator(z: complex, p: R040Parameters, sheet: str = "physical") -> complex:
    return complex(z) - p.E_2 - p.bath().self_energy(z, sheet=sheet)


def reduced_self_energy(z: complex, p: R040Parameters, sheet: str = "physical") -> np.ndarray:
    q = q_denominator(z, p, sheet=sheet)
    return np.outer(p.v_PQ, p.v_PQ.conj()) / q


def effective_hamiltonian(z: complex, p: R040Parameters, sheet: str = "physical") -> np.ndarray:
    return p.h_PP + reduced_self_energy(z, p, sheet=sheet)


def full_effective_matrix(z: complex, p: R040Parameters, sheet: str = "physical") -> np.ndarray:
    """zI-H3-s_b(z)|2><2|, whose determinant gives the full poles."""
    a = complex(z) * np.eye(3, dtype=complex) - p.H3
    a[2, 2] -= p.bath().self_energy(z, sheet=sheet)
    return a


def reduced_effective_matrix(z: complex, p: R040Parameters, sheet: str = "physical") -> np.ndarray:
    return complex(z) * np.eye(2, dtype=complex) - effective_hamiltonian(z, p, sheet=sheet)


def determinant_identity_residual(z: complex, p: R040Parameters, sheet: str = "physical") -> float:
    q = q_denominator(z, p, sheet=sheet)
    lhs = np.linalg.det(full_effective_matrix(z, p, sheet=sheet))
    rhs = q * np.linalg.det(reduced_effective_matrix(z, p, sheet=sheet))
    return float(abs(lhs - rhs) / max(1.0, abs(lhs), abs(rhs)))


def projected_resolvent_residual(z: complex, p: R040Parameters, sheet: str = "physical") -> float:
    full = np.linalg.inv(full_effective_matrix(z, p, sheet=sheet))[:2, :2]
    red = np.linalg.inv(reduced_effective_matrix(z, p, sheet=sheet))
    return float(np.linalg.norm(full - red, ord="fro") / max(1.0, np.linalg.norm(full, ord="fro")))


def bath_density_eff(energy: float, p: R040Parameters) -> np.ndarray:
    """Absolutely-continuous part J_eff(E) of the exact reduced measure.

    The point masses from real exterior roots of q(E)=0 are returned separately
    by `discrete_measure_atoms`; they are not included in this function.
    """
    bath = p.bath()
    jb = bath.j_density(energy)
    if jb == 0.0:
        return np.zeros((2, 2), dtype=complex)
    # Boundary value on the upper rim: Re s=0 for the centered 1-D chain.
    s_up = bath.self_energy(complex(float(energy), 1e-14), sheet="physical")
    q = complex(energy) - p.E_2 - s_up
    return (jb / (abs(q) ** 2)) * np.outer(p.v_PQ, p.v_PQ.conj())


def discrete_measure_atoms(p: R040Parameters) -> list[dict]:
    """Point masses of vv†/[z-E2-s_b(z)] outside the bath band."""
    bath = p.bath()
    atoms = []
    for energy in bath.bound_state_roots(p.E_2):
        derivative = bath.self_energy_derivative(complex(energy, 0.0)).real
        denom_derivative = 1.0 - derivative
        if denom_derivative <= 0.0:
            raise ArithmeticError("non-positive Feshbach point-mass residue")
        residue = np.outer(p.v_PQ, p.v_PQ.conj()) / denom_derivative
        atoms.append({"energy": float(energy), "residue": residue})
    return atoms


def reduced_measure_sum_rule(p: R040Parameters, epsabs: float = 1e-9,
                             epsrel: float = 1e-9) -> dict:
    """Check integral(J_eff dE)+sum(point residues)=v v^dagger.

    This is the total-mass sum rule for the scalar Q-block spectral measure
    lifted into the P subspace. The continuous and point parts are both included.
    """
    from scipy.integrate import quad_vec
    bath=p.bath()
    continuous, error=quad_vec(lambda e: bath_density_eff(float(e),p),
                               bath.lower_edge,bath.upper_edge,epsabs=epsabs,epsrel=epsrel)
    atoms=discrete_measure_atoms(p)
    point=sum((a["residue"] for a in atoms),np.zeros((2,2),dtype=complex))
    total=continuous+point
    target=np.outer(p.v_PQ,p.v_PQ.conj())
    residual=float(np.linalg.norm(total-target,ord="fro"))
    scaled=residual/max(1.0,float(np.linalg.norm(target,ord="fro")))
    return {
        "continuous_mass":np.asarray(continuous).tolist(),
        "point_mass":point.tolist(),
        "total_mass":np.asarray(total).tolist(),
        "expected_vv_dagger":target.tolist(),
        "quadrature_error_estimate":float(error),
        "absolute_residual":residual,
        "scaled_residual":scaled,
        "continuous_plus_point_sum_rule_pass":bool(scaled<=max(epsabs,epsrel)*10.0),
    }
