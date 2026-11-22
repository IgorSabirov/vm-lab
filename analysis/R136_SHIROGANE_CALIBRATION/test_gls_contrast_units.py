"""Regression test for R136.1 GLS contrast and covariance units.

Run:
    python test_gls_contrast_units.py

The plotted J variances (vJ) are already in J^2. Do not multiply them
by slope^2 when constructing the covariance in J-space.
"""
import numpy as np

S = np.array([68.96, 106.78])
R = np.array([0.024438471, -0.029300048])
EH = np.array([0.021046414, 0.016605519])
EC = np.array([0.0092617872, 0.0071178013])
E3 = np.array([0.022559457, 0.014992044])
EBC = np.array([0.00018, 0.00014])
E_INF = 0.00028
D_EXACT = 0.0006229000000006479
BETA0 = np.array([6.0636007, 6.0629778])
EXACT_ANCHOR = 6.0632464
R_EXACT = S * (BETA0 - EXACT_ANCHOR)
D_RESID = R[0] / S[0] - R[1] / S[1]
W = np.array([1.0 / S[0], -1.0 / S[1]])


def build_covariance(rho):
    v15 = EH**2 + EC**2 - 2.0 * rho * EH * EC
    vj = v15 + E3**2 - 2.0 * rho * np.sqrt(v15) * E3
    # vj is already in J^2. EBC*S converts beta_c uncertainty to J.
    return np.diag(vj + (EBC * S) ** 2) + E_INF**2 * np.outer(S, S)


def variance_of_contrast(rho):
    v15 = EH**2 + EC**2 - 2.0 * rho * EH * EC
    vj = v15 + E3**2 - 2.0 * rho * np.sqrt(v15) * E3
    j_sigma = np.sqrt(vj) / S
    return (
        j_sigma[0] ** 2 + j_sigma[1] ** 2
        + EBC[0] ** 2 + EBC[1] ** 2
    )


def gls_chi2_min(residuals, covariance):
    ci = np.linalg.inv(covariance)
    return (
        residuals @ ci @ residuals
        - (S @ ci @ residuals) ** 2 / (S @ ci @ S)
    )


def main():
    print(f"D_exact = {D_EXACT:.16g}")
    print(f"D_resid = {D_RESID:.16g}")
    print(f"relative difference = {(D_RESID / D_EXACT - 1) * 100:.9f}%")
    assert abs(W @ S) < 1e-14

    for rho in (0.0, 0.9):
        covariance = build_covariance(rho)
        var_d = variance_of_contrast(rho)
        chi2_gls = gls_chi2_min(R, covariance)
        chi2_exact_anchor = gls_chi2_min(R_EXACT, covariance)
        z2_resid = D_RESID**2 / var_d
        z2_exact = D_EXACT**2 / var_d
        print(f"rho={rho:.1f}: varD={var_d:.12e}")
        print(f"  GLS chi2_min       = {chi2_gls:.10f}")
        print(f"  z2(D_resid)        = {z2_resid:.10f}")
        print(f"  z2(D_exact)        = {z2_exact:.10f}")
        print(f"  GLS exact-anchor   = {chi2_exact_anchor:.10f}")
        assert np.isclose(chi2_gls, z2_resid, rtol=1e-9, atol=1e-12)
        assert np.isclose(chi2_exact_anchor, z2_exact, rtol=1e-9, atol=1e-12)
        assert np.isclose(W @ covariance @ W, var_d, rtol=1e-12)
        print("  GLS archived-r == z2(D_resid): PASS")
        print("  GLS exact-anchor == z2(D_exact): PASS")
        print("  w.T C w == varD:              PASS")

    sigma0 = np.sqrt(variance_of_contrast(0.0))
    print("Hierarchy (beta units):")
    print(f"  0.94% linearization scale = {0.0094 * D_EXACT:.12e}")
    print(f"  sigma_D(rho=0) = {sigma0:.12e}")
    print(f"  linearization / sigma_D = {0.0094 * D_EXACT / sigma0 * 100:.6f}%")
    print(f"  method deltaD range = {0.02 / 68.96:.12e} .. {0.05 / 68.96:.12e}")
    print(f"  sigma compression to 1.96 sigma = {(1 - (D_EXACT / 1.96) / sigma0) * 100:.6f}%")

    # Guard against the unit error: multiplying vJ by S^2 a second time.
    rho = 0.0
    v15 = EH**2 + EC**2 - 2.0 * rho * EH * EC
    vj = v15 + E3**2 - 2.0 * rho * np.sqrt(v15) * E3
    wrong_c = np.diag(vj * S**2 + (EBC * S) ** 2) + E_INF**2 * np.outer(S, S)
    wrong_chi2 = gls_chi2_min(R, wrong_c)
    correct_chi2 = gls_chi2_min(R, build_covariance(rho))
    assert not np.isclose(wrong_chi2, correct_chi2, rtol=1e-6)
    print(f"  double-scaled variance negative control = {wrong_chi2:.10f} (must differ)")
    print("ALL REGRESSION CHECKS PASS")


if __name__ == "__main__":
    main()
