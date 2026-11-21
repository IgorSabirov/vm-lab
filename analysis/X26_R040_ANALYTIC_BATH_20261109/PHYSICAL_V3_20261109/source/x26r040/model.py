"""Conditional R040 three-mode model; no ADD-to-Hamiltonian map is assumed."""
from __future__ import annotations
from dataclasses import dataclass, replace
import math
import numpy as np


@dataclass(frozen=True)
class R040Parameters:
    E_V: float
    E_1: float
    E_2: float
    t_1: float
    t_2: float
    gamma_d: float
    kappa: float
    g: float
    bath_onsite: float = 0.0

    def __post_init__(self) -> None:
        for name, value in self.__dict__.items():
            if not math.isfinite(float(value)):
                raise ValueError(f"{name} must be finite")
        if self.kappa <= 0.0 or self.g <= 0.0:
            raise ValueError("kappa and g must be positive")
        if abs(self.t_2) < 1e-14 or abs(self.gamma_d) < 1e-14:
            raise ValueError("R040 dark-state formula requires nonzero t_2 and gamma_d")

    @property
    def H3(self) -> np.ndarray:
        return np.array([
            [self.E_V, self.t_1, self.gamma_d],
            [self.t_1, self.E_1, self.t_2],
            [self.gamma_d, self.t_2, self.E_2],
        ], dtype=complex)

    @property
    def h_PP(self) -> np.ndarray:
        return self.H3[:2, :2].copy()

    @property
    def v_PQ(self) -> np.ndarray:
        return np.array([self.gamma_d, self.t_2], dtype=complex)

    @property
    def dark_energy(self) -> float:
        return self.E_1 - self.t_1 * self.t_2 / self.gamma_d

    @property
    def dark_vector(self) -> np.ndarray:
        d = np.array([self.t_2, -self.gamma_d, 0.0], dtype=complex)
        return d / np.linalg.norm(d)

    @property
    def bright_vector(self) -> np.ndarray:
        b = np.array([self.gamma_d, self.t_2, 0.0], dtype=complex)
        return b / np.linalg.norm(b)

    @property
    def tuned_E_V(self) -> float:
        return (self.E_1 + self.t_1 * self.gamma_d / self.t_2
                - self.t_1 * self.t_2 / self.gamma_d)

    def with_dark_tuning(self) -> "R040Parameters":
        return replace(self, E_V=self.tuned_E_V)

    def with_Z2_tuning(self) -> "R040Parameters":
        """Subfamily E_V=E_1 and gamma_d=t_2 (requires compatible input)."""
        return replace(self, E_V=self.E_1, gamma_d=self.t_2)

    def bath(self):
        from .bath import TightBindingBath
        return TightBindingBath(self.kappa, self.g, self.bath_onsite)


def validate_hermitian(matrix: np.ndarray, tol: float = 1e-12) -> float:
    a = np.asarray(matrix, dtype=complex)
    if a.ndim != 2 or a.shape[0] != a.shape[1]:
        raise ValueError("matrix must be square")
    err = float(np.linalg.norm(a - a.conj().T, ord="fro"))
    if err > tol:
        raise ValueError(f"matrix is not Hermitian: residual={err:.6g}")
    return err
