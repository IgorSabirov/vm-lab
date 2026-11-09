"""Fano zero diagnostic kept separate from BIC and pole classification."""
from __future__ import annotations
import math


def fano_profile(energy: float, resonance_energy: float, width: float,
                 asymmetry_q: float, background_scale: float = 1.0) -> dict:
    """Standard normalized Fano profile (epsilon+q)^2/(epsilon^2+1).

    This is an explicitly phenomenological scattering-line-shape control. It
    has no access to the R040 eigenproblem and therefore can never return a BIC.
    """
    vals = (energy, resonance_energy, width, asymmetry_q, background_scale)
    if not all(math.isfinite(float(x)) for x in vals) or width <= 0.0 or background_scale < 0.0:
        raise ValueError("finite parameters, width>0 and background_scale>=0 required")
    eps = 2.0 * (float(energy) - float(resonance_energy)) / float(width)
    value = float(background_scale * ((eps + asymmetry_q) ** 2 / (eps ** 2 + 1.0)))
    zero_energy = float(resonance_energy - 0.5 * asymmetry_q * width)
    return {
        "status": "FANO_LINE_SHAPE_ONLY_NOT_BIC_TEST",
        "reduced_energy": eps,
        "profile": value,
        "amplitude_zero_energy": zero_energy,
        "resonance_width": float(width),
        "width_remains_nonzero_at_fano_zero": True,
    }
