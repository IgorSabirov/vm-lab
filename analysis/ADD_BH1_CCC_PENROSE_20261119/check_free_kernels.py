"""Reproduce the free S³ field counts and test the thermal winding kernels.

Run with Python 3 and SymPy: python check_free_kernels.py
Equations (3.19), (3.20), (5.58), (5.60), (5.61) and note 42, hep-th/0310285v6.
"""
import json

import mpmath as mp
import sympy as sp


def fields(x):
    denominator = (1 - x) ** 3
    scalar = x * (1 + x) / denominator
    fermion = 4 * x ** sp.Rational(3, 2) / denominator
    vector = (6 * x**2 - 2 * x**3) / denominator
    return scalar, fermion, vector


def require_zero(expr):
    difference = sp.factor(expr)
    if difference != 0:
        raise ValueError(f"Unexpected symbolic residual: {difference}")
    return str(difference)


def critical_jump(z, x):
    count = sp.lambdify(x, z, "mpmath")
    slope = sp.lambdify(x, x * sp.diff(z, x), "mpmath")
    lo, hi = mp.mpf(0), mp.mpf(1)
    for _ in range(170):
        mid = (hi + lo) / 2
        if count(mid) < 1:
            lo = mid
        else:
            hi = mid
    root = (lo + hi) / 2
    return mp.nstr(-mp.log(root) * slope(root) / 4, 20)


def main():
    mp.mp.dps = 55
    x = sp.symbols("x", positive=True)
    scalar, fermion, vector = fields(x)
    bosons = vector + 6 * scalar
    fermions = 4 * fermion
    total = bosons + fermions
    rescaled = total.subs(x, x**2)
    # For y=x**n the two signs cover all positive winding numbers n.
    defects = {}
    for parity, sign in (("odd", 1), ("even", -1)):
        kernel = (bosons + sign * fermions).subs(x, x**2)
        expected = 0 if parity == "odd" else -32 * x**3 / (1 - x**2) ** 3
        require_zero(kernel - vector - expected)
        defects[parity] = str(expected)
    root = 2 - sp.sqrt(3)
    require_zero(vector.subs(x, root) - 1)
    vector_slope = sp.factor(x * sp.diff(vector, x))
    require_zero(vector_slope.subs(x, root) - 3)
    d_log = x * sp.diff(rescaled - vector, x)
    jump = 3 * sp.log(2 + sp.sqrt(3)) / 4
    spectra = {"YM": vector, "N=4": total, "N=1": vector + fermion,
               "V+4F": vector + 4*fermion, "6S": 6*scalar, "V+6S": bosons}
    jumps = {name: critical_jump(z, x) for name, z in spectra.items()}
    for name in ("YM", "N=4"):
        if abs(mp.mpf(jumps[name]) - mp.mpf(str(jump.evalf(45)))) > mp.mpf("1e-19"):
            raise ValueError(f"Unexpected entropy jump for {name}")
    if any(abs(mp.mpf(jumps[name]) - mp.mpf(jumps["YM"])) < mp.mpf("1e-5")
           for name in ("N=1", "V+4F", "6S", "V+6S")):
        raise ValueError("Field-content control did not distinguish entropy jumps")
    print(json.dumps({
        "reference": "hep-th/0310285v6, note 42 and equations (3.19)-(3.20), (5.58)-(5.61)",
        "regime": "free adjoint fields, round S3, leading large N entropy jump, k_B=1",
        "single_particle_residual": require_zero(rescaled - vector),
        "log_derivative_residual": require_zero(d_log),
        "winding_variable": "x in the following residual stands for q**n, q=exp(-1/(TR))",
        "winding_kernel_N4_rescaled_minus_vector": defects,
        "x_H_pure": str(root),
        "x_H_N4": str(sp.expand(root**2)),
        "entropy_jump_per_N_squared": str(jump),
        "numerical_jumps": jumps,
    }, indent=2))


if __name__ == "__main__":
    main()
