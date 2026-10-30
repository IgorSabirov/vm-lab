"""Fixed ten-unit reference windows on the even-time grid; no dynamics imports."""
import numpy as np
from scipy.integrate import simpson


def integral_mean(series, names, horizon):
    take = ((series[:, 0] >= horizon - 10 - 1e-8) &
            (series[:, 0] <= horizon + 1e-8) &
            np.isclose(series[:, 0] / 2, np.round(series[:, 0] / 2), atol=1e-8))
    a = series[take]
    expected = horizon - 10 + 2 * np.arange(6)
    if len(a) != 6 or not np.allclose(a[:, 0], expected, atol=1e-8, rtol=0):
        return None
    return dict(zip(names, (simpson(a[:, 1:], x=a[:, 0], axis=0) / 10).tolist()))
