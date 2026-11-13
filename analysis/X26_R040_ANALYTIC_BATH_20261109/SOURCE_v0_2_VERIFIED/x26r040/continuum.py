"""Finite-ring approximation diagnostics against the exact infinite-chain bath."""
from __future__ import annotations
import numpy as np
from .bath import TightBindingBath


def ring_limit_scan(bath: TightBindingBath, sizes: list[int], z_points: list[complex],
                    reference_energy: float | None = None,
                    gamma_infinite_chain: float | None = None) -> list[dict]:
    """Compare finite-ring Cauchy transforms with the exact infinite-chain value.

    A finite ring is a closed Hermitian bath: it has no irreversible decay width.
    Thus Gamma_N is deliberately null. If a separately computed infinite-chain
    resonance width is supplied, report Gamma_infinity/delta_N only as a
    resolution diagnostic, not as a finite-box width.
    """
    outputs = []
    for n in sizes:
        if type(n) is not int or n < 3:
            raise ValueError("all ring sizes must be integers >= 3")
        errors = []
        for z in z_points:
            exact = bath.green(complex(z), sheet="physical")
            approx = bath.finite_ring_green(complex(z), n)
            errors.append(float(abs(approx - exact)))
        band_span_over_n = (bath.upper_edge - bath.lower_edge) / n
        local_spacing = None
        if reference_energy is not None:
            rho = bath.density(float(reference_energy))
            if rho > 0.0:
                local_spacing = float(1.0 / (n * rho))
        ratio = None
        if gamma_infinite_chain is not None and local_spacing is not None:
            ratio = float(gamma_infinite_chain / local_spacing)
        outputs.append({
            "N": n,
            "green_abs_errors_by_test_point": errors,
            "max_abs_green_error_off_real_axis": max(errors, default=0.0),
            "delta_N_local_from_infinite_DOS": local_spacing,
            "band_span_over_N": float(band_span_over_n),
            "Gamma_N_finite_ring": None,
            "Gamma_infinite_chain_reference": gamma_infinite_chain,
            "Gamma_infinite_over_delta_N": ratio,
            "interpretation": "finite closed ring; no irreversible width at finite N",
        })
    return outputs


def moment_checks(bath: TightBindingBath, n_sites: int) -> dict:
    """First local moments of finite ring vs infinite nearest-neighbour chain.

    For N>=3: m0=1, m1=onsite, m2=onsite^2+2*kappa^2.
    """
    e = bath.ring_energies(n_sites)
    moments = [float(np.mean(e ** k)) for k in range(3)]
    expected = [1.0, bath.onsite, bath.onsite ** 2 + 2.0 * bath.kappa ** 2]
    return {"finite_ring_moments_0_2": moments,
            "infinite_chain_moments_0_2": expected,
            "absolute_errors": [abs(a-b) for a,b in zip(moments, expected)]}
