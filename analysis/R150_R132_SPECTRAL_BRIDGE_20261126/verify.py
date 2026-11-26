#!/usr/bin/env python3
"""Reproduce the R150--R132 spectral bridge checks (standard library only)."""
from __future__ import annotations
import json
import math


def matmul(a, b):
    n, m, p = len(a), len(b), len(b[0])
    return [[sum(a[i][k] * b[k][j] for k in range(m))
             for j in range(p)] for i in range(n)]


def transpose(a):
    return [list(row) for row in zip(*a)]


def matrix_max_abs(a):
    return max(abs(x) for row in a for x in row)


def make_active_F(L):
    """One fixed port plus an (L-1)-cycle, in a convenient basis."""
    n = L - 1
    F = [[0.0] * L for _ in range(L)]
    F[0][0] = 1.0
    for j in range(n):
        source = 1 + j
        target = 1 + ((j + 1) % n)
        F[target][source] = 1.0
    return F


def matrix_add(a, b, scale=1.0):
    return [[a[i][j] + scale * b[i][j]
             for j in range(len(a[0]))] for i in range(len(a))]


def identity(n):
    return [[1.0 if i == j else 0.0 for j in range(n)]
            for i in range(n)]


def matrix_scale(a, scale):
    return [[scale * x for x in row] for row in a]


def operator_checks():
    max_unitarity = 0.0
    max_identity = 0.0
    max_hop = 0.0
    cases = 0
    for L in range(3, 32):
        F = make_active_F(L)
        Ft = transpose(F)
        I = identity(L)
        d = matrix_add(F, I, -1.0)
        dt = transpose(d)
        unitarity = matrix_add(matmul(Ft, F), I, -1.0)
        lhs = matmul(dt, d)
        rhs = matrix_add(matrix_add(matrix_scale(I, 2.0), F, -1.0), Ft, -1.0)
        hop = matrix_scale(matrix_add(F, Ft), -0.37)
        hop_residual = matrix_add(matrix_add(hop, matrix_scale(I, 0.74)),
                                  matrix_scale(lhs, -0.37))
        max_unitarity = max(max_unitarity, matrix_max_abs(unitarity))
        max_identity = max(max_identity,
                           matrix_max_abs(matrix_add(lhs, rhs, -1.0)))
        max_hop = max(max_hop, matrix_max_abs(hop_residual))
        cases += 1
    return {
        "fixed_layer_sizes_checked": cases,
        "L_range": [3, 31],
        "max_unitarity_residual": max_unitarity,
        "max_dagger_d_residual": max_identity,
        "max_hop_shift_residual": max_hop,
    }


def singular_values_cycle(N, alpha):
    return [2.0 * abs(math.sin(math.pi * (k + alpha) / N))
            for k in range(N)]


def z_quadratic(N, y, alpha):
    # y=N^2 T/J, hence J/T=N^2/y.
    return 1.0 + sum(math.exp(-(N * N) * s * s / y)
                     for s in singular_values_cycle(N, alpha))


def golden_max(fn, lo, hi, iterations=180):
    gr = (math.sqrt(5.0) - 1.0) / 2.0
    c = hi - gr * (hi - lo)
    d = lo + gr * (hi - lo)
    fc, fd = fn(c), fn(d)
    for _ in range(iterations):
        if fc > fd:
            hi, d, fd = d, c, fc
            c = hi - gr * (hi - lo)
            fc = fn(c)
        else:
            lo, c, fc = c, d, fd
            d = lo + gr * (hi - lo)
            fd = fn(d)
    x = 0.5 * (lo + hi)
    return x, fn(x)


def finite_cycle_max(N):
    y, coeff = golden_max(
        lambda y: y * math.log(z_quadratic(N, y, 0.0)
                               / z_quadratic(N, y, 0.5)),
        0.2, 30.0)
    return {
        "N": N,
        "N2_Tmax_over_J": y,
        "N2_DFmax_over_J": coeff,
    }


def theta0(y):
    return sum(math.exp(-4.0 * math.pi**2 * k*k / y)
               for k in range(-30, 31))


def thetah(y):
    return sum(math.exp(-4.0 * math.pi**2 * (k+0.5)**2 / y)
               for k in range(-30, 31))


def asymptotic_coefficients():
    def isolated(y):
        return y * math.log((1.0 + theta0(y)) / (1.0 + thetah(y)))

    def all_active(y):
        t0, th = theta0(y), thetah(y)
        return y * math.log((3.0*t0 + 1.0) / (2.0*t0 + 1.0 + th))

    def one_active(y):
        t0, th = theta0(y), thetah(y)
        return y * (t0 - th) / (3.0*t0 + 1.0)

    results = {}
    for name, fn in (("isolated", isolated),
                     ("all_active", all_active),
                     ("one_active", one_active)):
        y, coeff = golden_max(fn, 0.1, 60.0, 220)
        results[name] = {"y_at_max": y, "coefficient": coeff}
    return results


def cycle_sum(m, T_over_J, alpha):
    return sum(math.exp(-(s*s) / T_over_J)
               for s in singular_values_cycle(m, alpha))


def carrier_partition(L, T_over_J, preparation):
    N = L - 1
    passive = (2*L - 1) * cycle_sum(L, T_over_J, 0.0)
    active0 = (L - 2) * (1.0 + cycle_sum(N, T_over_J, 0.0))
    Z0 = passive + active0
    if preparation == "isolated":
        return (1.0 + cycle_sum(N, T_over_J, 0.0),
                1.0 + cycle_sum(N, T_over_J, 0.5))
    if preparation == "all_active":
        Z1 = passive + (L - 2) * (1.0 + cycle_sum(N, T_over_J, 0.5))
        return Z0, Z1
    if preparation == "one_active":
        Z1 = (passive
              + (L - 3) * (1.0 + cycle_sum(N, T_over_J, 0.0))
              + (1.0 + cycle_sum(N, T_over_J, 0.5)))
        return Z0, Z1
    raise ValueError("unknown preparation")


def finite_carrier_max(L, preparation):
    log_t, coeff = golden_max(
        lambda log_t: math.exp(log_t) * math.log(
            carrier_partition(L, math.exp(log_t), preparation)[0]
            / carrier_partition(L, math.exp(log_t), preparation)[1]),
        -12.0, 4.0)
    return {"L": L, "preparation": preparation,
            "Tmax_over_J": math.exp(log_t), "DFmax_over_J": coeff}


def z_relativistic(N, T, M, epsilon, alpha):
    return 1.0 + sum(
        math.exp(-(math.sqrt(M*M + (epsilon*s)**2) - M) / T)
        for s in singular_values_cycle(N, alpha)
    )


def rel_contrast(N, T, M, epsilon):
    z0 = z_relativistic(N, T, M, epsilon, 0.0)
    zpi = z_relativistic(N, T, M, epsilon, 0.5)
    return 1.0 - zpi / z0


def bisect_root(fn, lo, hi, iterations=180):
    flo, fhi = fn(lo), fn(hi)
    if flo * fhi > 0.0:
        raise ValueError("root is not bracketed")
    for _ in range(iterations):
        mid = 0.5 * (lo + hi)
        fm = fn(mid)
        if flo * fm <= 0.0:
            hi, fhi = mid, fm
        else:
            lo, flo = mid, fm
    return 0.5 * (lo + hi)


def quadratic_contrast(N, T, J):
    y = N*N*T/J
    return 1.0 - z_quadratic(N, y, 0.5) / z_quadratic(N, y, 0.0)


def run():
    hbar_c = 197.3269804  # MeV fm
    M = 0.01585           # MeV
    ell = 1.995e4         # fm
    Tref = 0.080          # MeV
    epsilon = hbar_c / ell
    J = epsilon*epsilon / (2.0*M)

    dimensional = {
        "M_MeV": M, "ell_fm": ell,
        "epsilon_MeV": epsilon, "J_MeV": J,
        "Tref_MeV": Tref,
    }

    relativistic = {}
    inverse_one_percent = {}
    ultra_relativistic = {}
    for N in (6, 8):
        relativistic[str(N)] = rel_contrast(N, Tref, M, epsilon)
        eps_req = bisect_root(
            lambda e: rel_contrast(N, Tref, M, e) - 0.01,
            1.0e-8, 1.0)
        inverse_one_percent[str(N)] = {
            "epsilon_MeV": eps_req,
            "J_MeV": eps_req*eps_req/(2.0*M),
            "ell_fm": hbar_c/eps_req,
            "contrast": rel_contrast(N, Tref, M, eps_req),
        }
        r = epsilon / Tref
        z0 = 1.0 + sum(math.exp(-r*s)
                       for s in singular_values_cycle(N, 0.0))
        zpi = 1.0 + sum(math.exp(-r*s)
                        for s in singular_values_cycle(N, 0.5))
        ultra_relativistic[str(N)] = 1.0 - zpi/z0

    # The E2 value 4J=0.474 MeV belongs to the quadratic R150 calibration.
    J_E2 = 0.474 / 4.0
    epsilon_E2 = math.sqrt(2.0*M*J_E2)

    checks = {
        "schema": "r150-r132-spectral-bridge-checks-v1",
        "status": "PASS_NUMERICAL_IDENTITIES_AND_REPRODUCIBILITY_ONLY",
        "operator": operator_checks(),
        "finite_cycle_scaling": [
            finite_cycle_max(N) for N in (2, 6, 14, 60, 240, 1920)
        ],
        "asymptotic_coefficients": asymptotic_coefficients(),
        "L7_full_carrier": [
            finite_carrier_max(7, p)
            for p in ("isolated", "all_active", "one_active")
        ],
        "dimensional_example": dimensional,
        "relativistic_contrast_at_80keV": relativistic,
        "one_percent_inverse_calibration": inverse_one_percent,
        "ultra_relativistic_limit_fixed_epsilon_over_T": ultra_relativistic,
        "E2_quadratic_crosscheck": {
            "fourJ_MeV": 0.474,
            "J_MeV": J_E2,
            "N6_quadratic_contrast_at_80keV": quadratic_contrast(6, Tref, J_E2),
            "same_M_relativistic_epsilon_MeV": epsilon_E2,
            "N6_relativistic_contrast_at_80keV":
                rel_contrast(6, Tref, M, epsilon_E2),
        },
    }

    assert checks["operator"]["max_unitarity_residual"] < 1e-12
    assert checks["operator"]["max_dagger_d_residual"] < 1e-12
    assert checks["operator"]["max_hop_shift_residual"] < 1e-12
    assert abs(checks["finite_cycle_scaling"][-1]["N2_Tmax_over_J"]
               - 5.1797551667) < 2e-7
    assert abs(checks["finite_cycle_scaling"][-1]["N2_DFmax_over_J"]
               - 2.2437743021) < 2e-7
    assert abs(checks["asymptotic_coefficients"]["all_active"]["coefficient"]
               - 1.0058352789) < 2e-8
    assert abs(checks["asymptotic_coefficients"]["one_active"]["coefficient"]
               - 0.9232208940) < 2e-8
    assert abs(relativistic["6"] - 3.40919974e-6) < 2e-12
    assert abs(relativistic["8"] - 1.20192925e-7) < 2e-13
    return checks


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2, sort_keys=True))
