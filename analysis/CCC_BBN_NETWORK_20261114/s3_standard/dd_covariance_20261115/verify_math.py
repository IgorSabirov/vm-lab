"""Dependency-free algebra checks for the preregistered two-channel delta method."""
import math


def kappa(a1, a2):
    den = a1*a1 + a2*a2
    return None if den == 0 else 2*a1*a2/den


def ratio(a1, a2, rho):
    k = kappa(a1, a2)
    if k is None:
        return None
    if not -1 <= rho <= 1:
        raise ValueError('rho outside PSD correlation interval')
    return math.sqrt(1 + k*rho)


def main():
    for a1 in (-3.1, -0.2, 0.0, 0.7, 2.5):
        for a2 in (-2.0, 0.0, 0.3, 1.8):
            k = kappa(a1, a2)
            if k is None:
                assert ratio(a1, a2, 0.5) is None
                continue
            assert -1 - 1e-14 <= k <= 1 + 1e-14
            assert math.isclose(kappa(1e-6*a1, 1e-6*a2), k, rel_tol=1e-12, abs_tol=1e-12)
            for rho in (-1.0, -0.8, -0.5, 0.0, 0.5, 0.8, 1.0):
                x = ratio(a1, a2, rho)
                assert x is not None and math.isfinite(x) and x >= 0
    assert math.isclose(kappa(1.0, 1.0), 1.0)
    assert math.isclose(kappa(1.0, -1.0), -1.0)
    assert math.isclose(ratio(1.0, 1.0, 1.0), math.sqrt(2.0))
    assert math.isclose(ratio(1.0, -1.0, 1.0), 0.0)
    print('PASS: kappa bounds, scale invariance, PSD rho domain, extrema')


if __name__ == '__main__':
    main()
