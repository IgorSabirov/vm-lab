"""Analytic one-dimensional tight-binding bath.

Convention: s(z) = |g|^2 <0|(z-H_b)^(-1)|0>, so Im s(E+i0) <= 0.
The physical square-root branch is fixed by G_00(z) ~ 1/z at infinity.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np


@dataclass(frozen=True)
class TightBindingBath:
    kappa: float
    coupling: float
    onsite: float = 0.0

    def __post_init__(self) -> None:
        vals = (self.kappa, self.coupling, self.onsite)
        if not all(math.isfinite(float(x)) for x in vals):
            raise ValueError("bath parameters must be finite")
        if self.kappa <= 0.0:
            raise ValueError("kappa must be positive")
        if self.coupling <= 0.0:
            raise ValueError("coupling must be positive")

    @property
    def lower_edge(self) -> float:
        return self.onsite - 2.0 * self.kappa

    @property
    def upper_edge(self) -> float:
        return self.onsite + 2.0 * self.kappa

    def _root_physical(self, z: complex) -> complex:
        """sqrt(z-onsite-2kappa)*sqrt(z-onsite+2kappa), principal factors.

        The product, unlike a naive principal sqrt(z**2-4*kappa**2), has the
        required sign on both exterior real intervals and is asymptotic to z.
        """
        zc = complex(z) - self.onsite
        return complex(np.sqrt(zc - 2.0 * self.kappa + 0j)
                       * np.sqrt(zc + 2.0 * self.kappa + 0j))

    def green(self, z: complex, sheet: str = "physical") -> complex:
        """Local Green function on the physical sheet or its adjacent second sheet.

        On sheet='II' the analytic continuation across the band cut is represented
        by -G_I in the lower-half-plane resonance chart. The same analytic chart
        formula is evaluated during root iterations; accepted decaying poles must
        end in Im(z)<0.
        """
        if sheet not in {"physical", "II"}:
            raise ValueError("sheet must be 'physical' or 'II'")
        root = self._root_physical(z)
        if abs(root) == 0.0:
            raise ZeroDivisionError("Green function evaluated at a band edge")
        value = 1.0 / root
        return -value if sheet == "II" else value

    def self_energy(self, z: complex, sheet: str = "physical") -> complex:
        return (self.coupling ** 2) * self.green(z, sheet=sheet)

    def density(self, energy: float) -> float:
        x = float(energy) - self.onsite
        rad = 4.0 * self.kappa ** 2 - x ** 2
        if rad <= 0.0:
            return 0.0
        return 1.0 / (math.pi * math.sqrt(rad))

    def j_density(self, energy: float) -> float:
        """j_b(E) in s(E+i0)=PV integral j_b/(E-E') - i*pi*j_b."""
        return self.coupling ** 2 * self.density(energy)

    def finite_ring_green(self, z: complex, n_sites: int) -> complex:
        """Finite periodic ring local resolvent; finite N is not a continuum."""
        if type(n_sites) is not int or n_sites < 3:
            raise ValueError("n_sites must be an integer >= 3")
        k = np.arange(n_sites, dtype=float)
        energies = self.onsite + 2.0 * self.kappa * np.cos(2.0 * np.pi * k / n_sites)
        return complex(np.mean(1.0 / (complex(z) - energies)))

    def ring_energies(self, n_sites: int) -> np.ndarray:
        if type(n_sites) is not int or n_sites < 3:
            raise ValueError("n_sites must be an integer >= 3")
        k = np.arange(n_sites, dtype=float)
        return self.onsite + 2.0 * self.kappa * np.cos(2.0 * np.pi * k / n_sites)

    def bound_state_roots(self, q_energy: float, edge_eps: float = 1e-8) -> list[float]:
        """Roots of E-E2-s_b(E)=0 outside the band (Q-block bound states).

        Returns the lower- and upper-exterior roots. These are point masses in
        the Feshbach spectral measure and must not be discarded with J_eff(E).
        """
        from scipy.optimize import brentq

        if not math.isfinite(q_energy):
            raise ValueError("q_energy must be finite")
        eps = max(float(edge_eps), 1e-12 * self.kappa)

        def q(e: float) -> float:
            return float(e - q_energy - self.self_energy(complex(e, 0.0)).real)

        scale = max(abs(q_energy), self.kappa, 1.0)
        lo = self.lower_edge - eps
        hi = self.upper_edge + eps
        left_far = self.lower_edge - 2.0 * scale
        right_far = self.upper_edge + 2.0 * scale
        for _ in range(80):
            if q(left_far) < 0.0 and q(lo) > 0.0:
                break
            left_far = self.onsite - 2.0 * (self.onsite - left_far + scale)
        else:
            raise RuntimeError("failed to bracket lower Q-block bound state")
        for _ in range(80):
            if q(hi) < 0.0 and q(right_far) > 0.0:
                break
            right_far = self.onsite + 2.0 * (right_far - self.onsite + scale)
        else:
            raise RuntimeError("failed to bracket upper Q-block bound state")
        return [
            float(brentq(q, left_far, lo, xtol=1e-13, rtol=1e-12)),
            float(brentq(q, hi, right_far, xtol=1e-13, rtol=1e-12)),
        ]

    def self_energy_derivative(self, z: complex, sheet: str = "physical") -> complex:
        root = self._root_physical(z)
        if abs(root) == 0.0:
            raise ZeroDivisionError("derivative evaluated at a band edge")
        derivative = -(complex(z) - self.onsite) / (root ** 3)
        if sheet == "II":
            derivative = -derivative
        elif sheet != "physical":
            raise ValueError("sheet must be 'physical' or 'II'")
        return self.coupling ** 2 * derivative
