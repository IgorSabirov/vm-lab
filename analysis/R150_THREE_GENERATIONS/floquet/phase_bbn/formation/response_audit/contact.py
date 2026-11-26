"""Mixed thermodynamic response for the split/merge detector of R150."""
import math
import numpy as np
from scipy.special import logsumexp


def detector_contact(length, x, strength):
    """strength=lambda/T. r=1 is the periodic seam. d=1 adds -lambda*C."""
    cycle = [0, *range(2, length)]
    n = len(cycle)
    detector = np.diag(np.isin(np.arange(length), [0, 1]).astype(float))
    def block(phi):
        step = np.zeros((length, length), dtype=complex)
        step[1, 1] = 1
        for j, vertex in enumerate(cycle):
            step[cycle[(j + 1) % n], vertex] = np.exp(1j * phi) if j==n-1 else 1
        log_weight = x * (step + step.conj().T) / 2
        free = float(logsumexp(np.linalg.eigvalsh(log_weight)))
        bound = float(logsumexp(np.linalg.eigvalsh(log_weight + strength * detector)))
        detector_mean = 1/n + (1-1/n) * math.exp(x-free)
        return bound-free, detector_mean
    shift_0, mean_0 = block(0)
    shift_pi, mean_pi = block(math.pi)
    return dict(g_eff=shift_0-shift_pi, slope_at_zero=mean_0-mean_pi,
                mean_periodic=mean_0, mean_antiperiodic=mean_pi,
                nuclear_bias_shift_at_r0=shift_pi)


def trials():
    results = {}
    for length, x in [(3,4),(7,4),(7,2*.15/.07251310823341744),(9,4),(15,4)]:
        key = f"L{length}_x{x:.6f}"
        plus = detector_contact(length, x, .1)
        minus = detector_contact(length, x, -.1)
        delta = 1e-4
        finite = (detector_contact(length,x,delta)["g_eff"]
                  - detector_contact(length,x,-delta)["g_eff"]) / (2*delta)
        assert abs(plus["slope_at_zero"] - finite) < 1e-8
        assert detector_contact(length,x,0)["g_eff"] == 0
        results[key] = {**plus,"g_eff_at_minus_0p1":minus["g_eff"]}
    return results
