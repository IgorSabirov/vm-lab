"""Isolated scalar glueballs in kinetic equilibrium, with an out-of-equilibrium number density."""

import math

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq
from scipy.special import kve

MPL_REDUCED_GEV = 2.435e18  # (8 pi G)^(-1/2), as in FMS


def hubble(rho):
    return math.sqrt(rho / 3) / MPL_REDUCED_GEV


def moments(x, mass):
    """Classical relativistic gas. Return log n(mu=0), E/T, and dE/dT."""
    # The scaled Bessel functions avoid underflow in the late dilute gas.
    if x > 1000:
        # Controlled large-x expansion through O(x^-2); kve can return NaN at x>1e9.
        logk = 0.5 * math.log(math.pi / (2 * x)) + math.log1p(
            1.875 / x + 105 / (128 * x**2)
        )
        e = x + 1.5 + 1.875 / x - 1.875 / x**2
        return (
            3 * math.log(mass) - math.log(2 * math.pi**2 * x) + logk - x,
            e,
            1.5 + 3.75 / x - 5.625 / x**2,
        )
    k2 = kve(2, x)
    ratio = kve(1, x) / k2
    e = x * ratio + 3
    cv = 3 + x * x * (1 - ratio * ratio) - 3 * x * ratio
    return 3 * math.log(mass) - math.log(2 * math.pi**2 * x) + math.log(k2) - x, e, cv


def kinetic(sm, mass, entropy_ratio, xc, B=1.0, rtol=2e-7):
    """Integrate number and energy conservation vs log(a/a_c), MB closure, FMS eq. (8)."""
    if not B > 0:
        raise ValueError("3->2 coefficient must be positive")
    cross = B * (4 * math.pi / 3) ** 6 / ((4 * math.pi) ** 3 * mass**5)
    logn0, e0, _ = moments(xc, mass)
    logs0 = logn0 + math.log((e0 + 1) / entropy_ratio)
    s_axis = np.log(2 * math.pi**2 / 45 * sm.s) + 3 * sm.t

    def background(logs):
        if not s_axis[0] <= logs <= s_axis[-1]:
            raise ValueError("Outside visible EOS")
        tg = math.exp(np.interp(logs, s_axis, sm.t))
        _, grho = sm.degrees(tg)
        return tg, math.pi**2 / 30 * grho * tg**4

    def equilibrium(x, full_h):
        logn, e, _ = moments(x, mass)
        tg, rv = background(logn + math.log((e + 1) / entropy_ratio))
        n = math.exp(logn)
        h = hubble(rv + (n * mass * e / x if full_h else 0))
        return math.log(x * cross * n * n / (3 * h)), tg

    def rhs(u, state):
        logs = logs0 - 3 * u
        ln_y, ln_x = state
        x = math.exp(ln_x)
        logeq, e, cv = moments(x, mass)
        logn = ln_y + logs
        n = math.exp(logn)
        _, rv = background(logs)
        h = hubble(rv + n * mass * e / x)
        delta = logeq - logn
        if delta > 0:
            loss = (cross / h) * math.exp(logn + logeq) * math.expm1(-delta)
        else:
            loss = -(cross * n * n / h) * math.expm1(delta)
        return [-loss, (3 - e * loss) / cv]

    # Stop after comoving abundance stabilizes; check it over a full e-fold.
    y0 = [logn0 - logs0, math.log(xc)]
    end = min(12.0, (logs0 - s_axis[0]) / 3 - 1e-5)
    sol = solve_ivp(
        rhs,
        (0, end),
        y0,
        method="Radau",
        rtol=rtol,
        atol=rtol * 0.003,
        max_step=0.18,
        dense_output=True,
    )
    if not sol.success:
        raise ValueError(sol.message)
    drift = abs(math.expm1(sol.y[0, -1] - sol.sol(end - 1)[0]))
    if drift > 1e-4:
        raise ValueError(f"Relic yield still evolving: {drift}")
    # Same sudden rate criterion as the LO control; the integrated yield above
    # does not depend on the choice of a freeze-out crossing.
    checks = {}
    for name, full_h in [("visible", False), ("total", True)]:
        root = brentq(lambda x: equilibrium(x, full_h)[0], xc, 35)
        checks[name] = dict(x=root, T_gamma_GeV=equilibrium(root, full_h)[1])
    y = math.exp(sol.y[0, -1])
    return dict(
        B=B,
        MB_sudden=checks,
        Y_final=y,
        Omega_h2=0.1186 * mass * y / 4.322e-10,
        final_yield_fractional_drift=drift,
        log_a_end=end,
    )
