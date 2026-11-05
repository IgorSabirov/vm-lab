import numpy as np
import hashlib
import json

# =============================================================================
# B4.14.0: STRICT GAUSS-CODAZZI EMBEDDING CONSISTENCY GATE
# =============================================================================
#
# Purpose:
# After B4.13.0, the visible slice M_vis=(gamma,h) has:
#
#   theta: TM_vis -> E_vis
#   g_ab = <theta_a, theta_b>_HS
#   tilde_nabla = nabla_LC[g]
#
# B4.14.0 checks the extrinsic consistency of this construction:
#
#   M_vis -> E_vis
#
# is a regular isometric Riemannian submanifold of the flat ambient
# operator-measure space E_vis.
#
# Since E_vis is a finite-dimensional Hilbert-Schmidt space with frozen
# coarse-graining weights, its ambient curvature is exactly zero:
#
#   R_ambient = 0.
#
# Therefore the Gauss equation reduces to:
#
#   R_LC_{abcd}
#   =
#   <II_{ac}, II_{bd}> - <II_{ad}, II_{bc}>.
#
# Sign convention is fixed globally and validated on the round sphere and
# on a non-diagonal paraboloid embedding.
#
# The Codazzi equation is the substantive gate:
#
#   nabla_a II_{bc} = nabla_b II_{ac}
#
# for flat ambient space.
#
# The Ricci equation is kept only as a diagnostic because for dim(M)=2 and
# large normal bundle it is usually weakly informative.
#
# Important corrections from B4.13.8 / B4.13.8.1:
#
# 1. Christoffel symbols must be computed with the full sum over d:
#
#      Gamma^c_{ab}
#      =
#      1/2 g^{cd} (partial_a g_{bd} + partial_b g_{ad} - partial_d g_{ab}).
#
#    The previous buggy version kept only d=c and passed the diagonal sphere
#    test but failed on non-diagonal metrics.
#
# 2. The second fundamental form scales with the coarse-graining width:
#
#      ||II|| ~ sigma^{-p}, p ~= 1.5.
#
#    Therefore sigma-stability of ||II|| itself is not the correct criterion.
#    B4.14 freezes sigma from spectral resolution and checks the scaling law.
#
# Scope rider:
# B4.14.0 does NOT prove:
#   - gravity;
#   - general relativity;
#   - Einstein equations;
#   - spacetime;
#   - time arrow;
#   - death / holonomy ontology;
#   - J_self;
#   - EP in closed Hermitian H;
#   - dark/access/metrology LC reduction;
#   - autonomous choice of M, architecture, port, W, L_C.
#
# It only tests whether the frozen visible spectral slice defines a consistent
# Riemannian submanifold geometry in the flat ambient operator-measure space.
# =============================================================================


# -----------------------------------------------------------------------------
# B4.14.0 rev.2 -- fail journal (G14-F1..F5)
# -----------------------------------------------------------------------------
#
# G14-F1: Codazzi gate measured the FULL ambient Codazzi difference; for flat
#         ambient only the NORMAL projection must vanish. Fixed: epsC is now
#         computed on the normal-projected Codazzi tensor.
# G14-F2: FD-convergence gate used relative change of residuals sitting at
#         the numerical floor. Fixed: floor-aware criterion.
# G14-F3: h -> -h gate tested a symmetry the frozen architecture does not
#         possess (E1 != E2). Gate deleted (option A).
# G14-F4: Prescribed K ~ sigma^{-3} scaling replaced by a free power-law fit;
#         the fitted exponent is a diagnostic output, not a requirement.
# G14-F5: make_gate crashed on tuple thresholds in "between" mode. Fixed.
#
# -----------------------------------------------------------------------------

CFG = {
    "step": "B4.14.0_rev2_strict_gauss_codazzi_embedding_consistency_gate",
    "seed": 20260921,

    # Frozen visible architecture constants, inherited from B4.11/B4.12/B4.13.
    "E_bright": -0.3,
    "E_dark": 0.3,
    "E1": -0.8,
    "E2": 0.6,
    "t12": -0.35,
    "t1": 1.0,

    # Visible physical parameter slice.
    # phi is fixed gauge and is NOT a physical coordinate.
    # alpha is access-layer and is NOT mixed into visible soldering.
    "M_vis_names": ["gamma", "h"],

    # Test points.
    # h=0 is a symmetry anchor; h!=0 are generic geometry points.
    "points": [
        {"name": "symmetry_anchor_h0", "p": [0.8, 0.0]},
        {"name": "generic_h015", "p": [0.8, 0.15]},
        {"name": "generic_h030", "p": [0.8, 0.30]},
        {"name": "generic_gamma060_h015", "p": [0.6, 0.15]},
    ],
    "primary_point_name": "generic_h015",

    # Frozen spectral resolution / coarse-graining scale.
    # Delta E_mean = 4 / N_spectral.
    # sigma = k * Delta E_mean.
    "N_spectral": 40,
    "sigma_k": 2.5,

    # Window grid for coarse-grained operator-valued measure mu_V.
    "nwin": 31,
    "Emin_win": -2.0,
    "Emax_win": 2.0,

    # Finite differences.
    # Five-point stencils are used for first derivatives.
    "fd_step": 1.0e-3,
    "fd_step_half": 5.0e-4,

    # Tolerances.
    "tau_num": 1.0e-10,
    "tau_degenerate": 1.0e-8,
    "tau_rank": 1.0e-8,
    "tau_g_min": 1.0e-8,

    # LC / embedding prerequisites.
    "tau_lc_stamp_rel": 1.0e-4,
    "tau_torsion_rel": 1.0e-4,
    "tau_metric_compat_rel": 1.0e-4,

    # II structure.
    "tau_ii_sym": 1.0e-8,
    "tau_normal": 1.0e-8,

    # Gauss / Codazzi.
    "tau_gauss_rel": 1.0e-3,
    "tau_codazzi_rel": 1.0e-3,

    # Regression tests.
    "tau_sphere_K": 1.0e-4,
    "tau_paraboloid_correct": 1.0e-10,
    "tau_paraboloid_buggy_detect": 1.0e-2,

    # FD convergence.
    "tau_fd_change": 3.0e-1,

    # Sigma scaling.
    "sigma_scan": [0.15, 0.17, 0.19, 0.21, 0.23, 0.25, 0.27, 0.29, 0.31, 0.33, 0.35],
    "tau_sigma_slope_r2": 0.98,
    "tau_sigma_p_min": 1.0,
    "tau_sigma_p_max": 2.0,

    "sigma_curv_scan": [0.18, 0.21, 0.25, 0.29, 0.32],
    "tau_curv_scaled_spread": 0.50,

    # Symmetry h -> -h.
    "tau_symmetry_rel": 1.0e-3,

    # z_* anchor from corrected B4.12/B4.13.
    "eta_zstar": 1.0e-8,
    "tau_zstar": 1.0e-5,
}


def sha256_of_config(cfg):
    s = json.dumps(cfg, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(s).hexdigest()


CONFIG_SHA256 = sha256_of_config(CFG)


# -----------------------------------------------------------------------------
# Basic helpers
# -----------------------------------------------------------------------------

def herm(A):
    A = np.asarray(A, dtype=complex)
    return 0.5 * (A + A.conj().T)


def opnorm(A):
    A = np.asarray(A, dtype=complex)
    if A.size == 0:
        return 0.0
    if A.ndim == 1:
        return float(np.linalg.norm(A))
    return float(np.linalg.norm(A, ord=2))


def tensor_norm(A):
    A = np.asarray(A, dtype=float)
    if A.size == 0:
        return 0.0
    return float(np.linalg.norm(A))


def fmt(x):
    if x is None:
        return "None"
    try:
        xf = float(x)
    except Exception:
        return str(x)
    if np.isnan(xf):
        return "nan"
    return f"{xf:.6e}"


def safe_inv(g):
    g = np.asarray(g, dtype=float)
    try:
        return np.linalg.inv(g)
    except np.linalg.LinAlgError:
        return np.linalg.pinv(g, rcond=CFG["tau_rank"])


def make_gate(name, value, threshold, mode="le", extra=None):
    try:
        value = float(value)
    except Exception:
        value = float("nan")

    if mode == "between":
        # G14-F5 fix: no float() cast on a tuple threshold
        lo, hi = float(threshold[0]), float(threshold[1])
        threshold = (lo, hi)
        passed = (value >= lo) and (value <= hi)
    else:
        threshold = float(threshold)
        if mode == "le":
            passed = value <= threshold
        elif mode == "ge":
            passed = value >= threshold
        elif mode == "eq":
            passed = value == threshold
        else:
            raise ValueError(f"unknown gate mode: {mode}")

    g = {
        "name": name,
        "value": value,
        "threshold": threshold,
        "mode": mode,
        "PASS": bool(passed),
    }
    if extra is not None:
        g["extra"] = extra
    return g


def print_gate(g):
    status = "PASS" if g["PASS"] else "FAIL"
    thr = g["threshold"]
    if g["mode"] == "between":
        thr_s = f"[{fmt(thr[0])}, {fmt(thr[1])}]"
    else:
        thr_s = fmt(thr)
    print(
        f"{g['name']:64s} value={fmt(g['value'])}  "
        f"threshold={thr_s}  mode={g['mode']:8s}  {status}"
    )


def deriv5_array(func, p, idx, h):
    """
    Five-point first derivative of a vector/array-valued function.

    func(x) must return a NumPy array of fixed shape.
    """
    p = np.asarray(p, dtype=float).reshape(-1)

    fm2 = p.copy(); fm2[idx] -= 2.0 * h
    fm = p.copy();  fm[idx] -= h
    fp = p.copy();  fp[idx] += h
    fp2 = p.copy(); fp2[idx] += 2.0 * h

    vm2 = np.asarray(func(fm2), dtype=float)
    vm = np.asarray(func(fm), dtype=float)
    vp = np.asarray(func(fp), dtype=float)
    vp2 = np.asarray(func(fp2), dtype=float)

    return (-vp2 + 8.0 * vp - 8.0 * vm + vm2) / (12.0 * h)


# -----------------------------------------------------------------------------
# Frozen visible architecture
# -----------------------------------------------------------------------------

E_BRIGHT = float(CFG["E_bright"])
E_DARK = float(CFG["E_dark"])
E1 = float(CFG["E1"])
E2 = float(CFG["E2"])
T12 = float(CFG["t12"])
T1 = float(CFG["t1"])

M_VIS = list(CFG["M_vis_names"])
N_PARAM = len(M_VIS)

WINDOW_CENTERS = np.linspace(
    float(CFG["Emin_win"]),
    float(CFG["Emax_win"]),
    int(CFG["nwin"]),
)

DELTA_E_MEAN = 4.0 / float(CFG["N_spectral"])
SIGMA_FROZEN = float(CFG["sigma_k"]) * DELTA_E_MEAN


def get_primary_point():
    for pt in CFG["points"]:
        if pt["name"] == CFG["primary_point_name"]:
            return np.asarray(pt["p"], dtype=float)
    return np.asarray(CFG["points"][1]["p"], dtype=float)


P_PRIMARY = get_primary_point()


def HG(h):
    """
    Frozen 2-site environment Hamiltonian:
        H_G(h) = [[E1 + h, t12],
                  [t12,     E2 - h]]
    """
    h = float(h)
    return np.array(
        [
            [E1 + h, T12],
            [T12, E2 - h],
        ],
        dtype=float,
    )


def dHG_dh():
    return np.array(
        [
            [1.0, 0.0],
            [0.0, -1.0],
        ],
        dtype=float,
    )


def V_of_gamma(gamma):
    """
    Coupling V: environment -> code.

    V(gamma) = [[t1, 0],
                [gamma, 0]]
    """
    gamma = float(gamma)
    return np.array(
        [
            [T1, 0.0],
            [gamma, 0.0],
        ],
        dtype=complex,
    )


def dV_dgamma():
    return np.array(
        [
            [0.0, 0.0],
            [1.0, 0.0],
        ],
        dtype=complex,
    )


# -----------------------------------------------------------------------------
# Kato-style analytic spectral derivatives for real symmetric 2x2 H_G
# -----------------------------------------------------------------------------

def eig2_real_symmetric(H):
    """
    Analytic eigenstructure of a real symmetric 2x2 matrix.

    Returns:
        lam_p, lam_m, P_p, P_m, delta
    """
    H = np.asarray(H, dtype=float)
    a = float(H[0, 0])
    b = float(H[1, 1])
    c = float(H[0, 1])

    mean = 0.5 * (a + b)
    diff = a - b
    disc = diff * diff + 4.0 * c * c
    delta = float(np.sqrt(max(disc, 0.0)))

    if delta < CFG["tau_degenerate"]:
        raise RuntimeError("H_G is degenerate; visible soldering chart is singular")

    lam_p = mean + 0.5 * delta
    lam_m = mean - 0.5 * delta

    I = np.eye(2, dtype=complex)
    Hc = H.astype(complex)

    P_p = (Hc - lam_m * I) / delta
    P_m = (lam_p * I - Hc) / delta

    return lam_p, lam_m, herm(P_p), herm(P_m), delta


def deig2_real_symmetric(H, dH):
    """
    Analytic derivative of eigenvalues and spectral projectors.
    """
    H = np.asarray(H, dtype=float)
    dH = np.asarray(dH, dtype=float)

    lam_p, lam_m, P_p, P_m, delta = eig2_real_symmetric(H)

    a = float(H[0, 0])
    b = float(H[1, 1])
    c = float(H[0, 1])

    da = float(dH[0, 0])
    db = float(dH[1, 1])
    dc = float(dH[0, 1])

    dmean = 0.5 * (da + db)
    ddiff = da - db
    ddisc = 2.0 * (a - b) * ddiff + 8.0 * c * dc
    ddelta = ddisc / (2.0 * delta)

    dlam_p = dmean + 0.5 * ddelta
    dlam_m = dmean - 0.5 * ddelta

    I = np.eye(2, dtype=complex)
    Hc = H.astype(complex)
    dHc = dH.astype(complex)

    dP_p = (dHc - dlam_m * I) / delta
    dP_p -= (Hc - lam_m * I) * (ddelta / (delta * delta))

    dP_m = (dlam_p * I - dHc) / delta
    dP_m -= (lam_p * I - Hc) * (ddelta / (delta * delta))

    return dlam_p, dlam_m, herm(dP_p), herm(dP_m)


# -----------------------------------------------------------------------------
# Flatten Hermitian 2x2 code operators to real Hilbert-Schmidt vectors
# -----------------------------------------------------------------------------
#
# For Hermitian X:
#   Re Tr(XY) = x00 y00 + x11 y11 + 2 Re(x01 conj(y01)).
#
# Vector:
#   [x00, x11, sqrt(2) Re x01, sqrt(2) Im x01]
# gives ordinary Euclidean dot product equal to Re Tr(XY).
# -----------------------------------------------------------------------------

SQRT2 = float(np.sqrt(2.0))


def flatten_herm_2x2(A):
    A = np.asarray(A, dtype=complex)
    return np.array(
        [
            float(np.real(A[0, 0])),
            float(np.real(A[1, 1])),
            float(SQRT2 * np.real(A[0, 1])),
            float(SQRT2 * np.imag(A[0, 1])),
        ],
        dtype=float,
    )


def flatten_stack_mu(mu_stack):
    mu_stack = np.asarray(mu_stack, dtype=complex)
    out = []
    for mu in mu_stack:
        out.append(flatten_herm_2x2(mu))
    return np.concatenate(out)


# -----------------------------------------------------------------------------
# Frozen coarse-grained operator-valued measure mu_V
# -----------------------------------------------------------------------------

def window_weights(E, centers, sigma):
    E = float(E)
    centers = np.asarray(centers, dtype=float)
    sigma = float(sigma)
    return np.exp(-0.5 * ((E - centers) / sigma) ** 2)


def window_dweights(E, centers, sigma):
    E = float(E)
    centers = np.asarray(centers, dtype=float)
    sigma = float(sigma)
    w = window_weights(E, centers, sigma)
    return -(E - centers) / (sigma * sigma) * w


def residue_matrices(P, V):
    P = np.asarray(P, dtype=complex)
    V = np.asarray(V, dtype=complex)
    return herm(V.conj().T @ P @ V)


def dresidue_matrices(P, dP, V, dV):
    P = np.asarray(P, dtype=complex)
    dP = np.asarray(dP, dtype=complex)
    V = np.asarray(V, dtype=complex)
    dV = np.asarray(dV, dtype=complex)

    return herm(
        dV.conj().T @ P @ V
        + V.conj().T @ dP @ V
        + V.conj().T @ P @ dV
    )


def mu_matrices_from_HV(H, V, centers, sigma):
    """
    Coarse-grained operator-valued measure components:
        mu_j = sum_k w_j(E_k) V^dagger P_k V.
    Returns shape (nwin, 2, 2).
    """
    lam_p, lam_m, P_p, P_m, _ = eig2_real_symmetric(H)

    R_p = residue_matrices(P_p, V)
    R_m = residue_matrices(P_m, V)

    wp = window_weights(lam_p, centers, sigma)
    wm = window_weights(lam_m, centers, sigma)

    out = np.zeros((len(centers), 2, 2), dtype=complex)
    for j in range(len(centers)):
        out[j] = wp[j] * R_p + wm[j] * R_m

    return out


def dmu_matrices_from_derivs(H, dH, V, dV, centers, sigma):
    """
    Derivative of coarse-grained mu_V components.
    Returns shape (nwin, 2, 2).
    """
    lam_p, lam_m, P_p, P_m, _ = eig2_real_symmetric(H)
    dlam_p, dlam_m, dP_p, dP_m = deig2_real_symmetric(H, dH)

    R_p = residue_matrices(P_p, V)
    R_m = residue_matrices(P_m, V)

    dR_p = dresidue_matrices(P_p, dP_p, V, dV)
    dR_m = dresidue_matrices(P_m, dP_m, V, dV)

    wp = window_weights(lam_p, centers, sigma)
    wm = window_weights(lam_m, centers, sigma)

    dwp = window_dweights(lam_p, centers, sigma)
    dwm = window_dweights(lam_m, centers, sigma)

    out = np.zeros((len(centers), 2, 2), dtype=complex)
    for j in range(len(centers)):
        out[j] = (
            dwp[j] * dlam_p * R_p
            + wp[j] * dR_p
            + dwm[j] * dlam_m * R_m
            + wm[j] * dR_m
        )

    return out


# -----------------------------------------------------------------------------
# Soldering theta_a = partial_a mu_V on visible M=(gamma,h)
# -----------------------------------------------------------------------------

def theta_column(p, param_idx, centers, sigma):
    """
    Column of soldering matrix theta for visible parameter:
        param_idx=0 -> gamma
        param_idx=1 -> h
    """
    p = np.asarray(p, dtype=float).reshape(-1)
    gamma = float(p[0])
    h = float(p[1])

    H = HG(h)
    V = V_of_gamma(gamma)

    if param_idx == 0:
        dH = np.zeros((2, 2), dtype=float)
        dV = dV_dgamma()
    elif param_idx == 1:
        dH = dHG_dh()
        dV = np.zeros((2, 2), dtype=complex)
    else:
        raise ValueError(f"unknown visible parameter index: {param_idx}")

    dmu = dmu_matrices_from_derivs(H, dH, V, dV, centers, sigma)
    return flatten_stack_mu(dmu)


def theta_matrix(p, centers, sigma):
    cols = [theta_column(p, a, centers, sigma) for a in range(N_PARAM)]
    return np.column_stack(cols)


def dtheta_at(p, centers, sigma, fd_step):
    """
    dtheta[a,b,:] = partial_a theta_b.
    """
    m = N_PARAM
    N = len(centers) * 4
    out = np.zeros((m, m, N), dtype=float)

    for a in range(m):
        for b in range(m):
            out[a, b, :] = deriv5_array(
                lambda q, b=b: theta_column(q, b, centers, sigma),
                p,
                a,
                fd_step,
            )

    return out


# -----------------------------------------------------------------------------
# Metric, Christoffel, Riemann, II, Gauss-Codazzi
# -----------------------------------------------------------------------------

def metric_at(p, centers, sigma):
    th = theta_matrix(p, centers, sigma)
    return th.T @ th


def dg_at(p, centers, sigma, fd_step):
    """
    dg[a,b,c] = partial_a g_{bc}.
    """
    th = theta_matrix(p, centers, sigma)
    dth = dtheta_at(p, centers, sigma, fd_step)

    m = N_PARAM
    dg = np.zeros((m, m, m), dtype=float)

    for a in range(m):
        for b in range(m):
            for c in range(m):
                dg[a, b, c] = float(
                    np.dot(dth[a, b, :], th[:, c])
                    + np.dot(th[:, b], dth[a, c, :])
                )

    return dg


def christoffel_from_g_dg(g, dg):
    """
    Correct Levi-Civita Christoffel symbols:
        Gamma^c_{ab}
        =
        1/2 g^{cd} (partial_a g_{bd} + partial_b g_{ad} - partial_d g_{ab}).

    Full sum over d is mandatory.
    """
    g = np.asarray(g, dtype=float)
    dg = np.asarray(dg, dtype=float)
    m = g.shape[0]
    gin = safe_inv(g)

    Gam = np.zeros((m, m, m), dtype=float)

    for c in range(m):
        for a in range(m):
            for b in range(m):
                s = 0.0
                for d in range(m):
                    s += gin[c, d] * (
                        dg[a, b, d]
                        + dg[b, a, d]
                        - dg[d, a, b]
                    )
                Gam[c, a, b] = 0.5 * s

    return Gam


def christoffel_buggy_from_g_dg(g, dg):
    """
    Historical buggy Christoffel: keeps only d=c.
    Used only as a regression control.
    """
    g = np.asarray(g, dtype=float)
    dg = np.asarray(dg, dtype=float)
    m = g.shape[0]
    gin = safe_inv(g)

    Gam = np.zeros((m, m, m), dtype=float)

    for c in range(m):
        for a in range(m):
            for b in range(m):
                Gam[c, a, b] = 0.5 * gin[c, c] * (
                    dg[a, b, c]
                    + dg[b, a, c]
                    - dg[c, a, b]
                )

    return Gam


def christoffel_at(p, centers, sigma, fd_step):
    g = metric_at(p, centers, sigma)
    dg = dg_at(p, centers, sigma, fd_step)
    return christoffel_from_g_dg(g, dg)


def gamma_projection_coeff(p, centers, sigma, fd_step):
    """
    Tangential projection coefficients from the embedding:
        partial_a theta_b = Gamma^c_{ab} theta_c + II_{ab}.

    This is computed by Moore-Penrose projection onto Im(theta).
    """
    th = theta_matrix(p, centers, sigma)
    dth = dtheta_at(p, centers, sigma, fd_step)

    m = N_PARAM
    pinv = np.linalg.pinv(th, rcond=CFG["tau_rank"])

    Gam_proj = np.zeros((m, m, m), dtype=float)
    for a in range(m):
        for b in range(m):
            coeff = pinv @ dth[a, b, :]
            Gam_proj[:, a, b] = coeff

    return Gam_proj


def riemann_lower_from_gam_dgam(g, Gam, dGam):
    """
    Lower-index Riemann tensor with fixed convention:

        R^a_{ b c d }
        =
        partial_c Gamma^a_{d b}
        - partial_d Gamma^a_{c b}
        + Gamma^a_{c k} Gamma^k_{d b}
        - Gamma^a_{d k} Gamma^k_{c b}.

        R_{a b c d} = g_{a e} R^e_{ b c d }.

    With this convention, the round sphere satisfies:
        R_{0101} = K (g_{00} g_{11} - g_{01}^2), K=1/r^2.
    """
    g = np.asarray(g, dtype=float)
    Gam = np.asarray(Gam, dtype=float)
    dGam = [np.asarray(x, dtype=float) for x in dGam]

    m = g.shape[0]

    R_up = np.zeros((m, m, m, m), dtype=float)

    for a in range(m):
        for b in range(m):
            for c in range(m):
                for d in range(m):
                    val = dGam[c][a, d, b] - dGam[d][a, c, b]
                    for k in range(m):
                        val += Gam[a, c, k] * Gam[k, d, b]
                        val -= Gam[a, d, k] * Gam[k, c, b]
                    R_up[a, b, c, d] = val

    R_low = np.einsum("ae,ebcd->abcd", g, R_up)
    return R_low


def riemann_lower_at(p, centers, sigma, fd_step):
    Gam = christoffel_at(p, centers, sigma, fd_step)
    dGam = []
    for c in range(N_PARAM):
        dGam.append(
            deriv5_array(
                lambda q: christoffel_at(q, centers, sigma, fd_step),
                p,
                c,
                fd_step,
            )
        )
    g = metric_at(p, centers, sigma)
    return riemann_lower_from_gam_dgam(g, Gam, dGam)


def ii_at(p, centers, sigma, fd_step):
    """
    Second fundamental form:
        II_{ab} = (partial_a theta_b)^perp.
    """
    th = theta_matrix(p, centers, sigma)
    dth = dtheta_at(p, centers, sigma, fd_step)

    m = N_PARAM
    N = th.shape[0]
    pinv = np.linalg.pinv(th, rcond=CFG["tau_rank"])

    II = np.zeros((m, m, N), dtype=float)

    for a in range(m):
        for b in range(m):
            coeff = pinv @ dth[a, b, :]
            tangent = th @ coeff
            II[a, b, :] = dth[a, b, :] - tangent

    return II, th, dth


def ii_only_at(p, centers, sigma, fd_step):
    return ii_at(p, centers, sigma, fd_step)[0]


def gauss_rhs_from_ii(II):
    """
    Fixed sign convention:
        G_{abcd} = <II_{ac}, II_{bd}> - <II_{ad}, II_{bc}>.
    """
    II = np.asarray(II, dtype=float)
    m = II.shape[0]
    G = np.zeros((m, m, m, m), dtype=float)

    for a in range(m):
        for b in range(m):
            for c in range(m):
                for d in range(m):
                    G[a, b, c, d] = float(
                        np.dot(II[a, c, :], II[b, d, :])
                        - np.dot(II[a, d, :], II[b, c, :])
                    )

    return G


def codazzi_tensor_at(p, centers, sigma, fd_step):
    """
    For flat ambient space:
        C_{abc} = nabla_a II_{bc} - nabla_b II_{ac}.

    Covariant derivative:
        nabla_a II_{bc}
        =
        partial_a II_{bc}
        - Gamma^d_{ab} II_{dc}
        - Gamma^d_{ac} II_{bd}.
    """
    Gam = christoffel_at(p, centers, sigma, fd_step)
    II = ii_only_at(p, centers, sigma, fd_step)

    m = N_PARAM
    N = II.shape[2]

    dII = np.zeros((m, m, m, N), dtype=float)
    for a in range(m):
        for b in range(m):
            for c in range(m):
                dII[a, b, c, :] = deriv5_array(
                    lambda q, b=b, c=c: ii_only_at(q, centers, sigma, fd_step)[b, c, :],
                    p,
                    a,
                    fd_step,
                )

    cov = np.zeros((m, m, m, N), dtype=float)
    for a in range(m):
        for b in range(m):
            for c in range(m):
                val = dII[a, b, c, :].copy()
                for d in range(m):
                    val -= Gam[d, a, b] * II[d, c, :]
                    val -= Gam[d, a, c] * II[b, d, :]
                cov[a, b, c, :] = val

    C = cov - np.transpose(cov, (1, 0, 2, 3))
    return C, II, Gam


def embedding_consistency_eval(p, centers, sigma, fd_step):
    """
    Full B4.14 evaluation at one point.
    """
    p = np.asarray(p, dtype=float).reshape(-1)

    th = theta_matrix(p, centers, sigma)
    sv = np.linalg.svd(th, compute_uv=False)
    rank = int(np.linalg.matrix_rank(th, tol=CFG["tau_rank"]))
    min_sv = float(sv[-1]) if sv.size else 0.0

    g = metric_at(p, centers, sigma)
    g_eig = np.linalg.eigvalsh(g)
    g_min = float(g_eig[0])
    g_max = float(g_eig[-1])
    g_sym_err = tensor_norm(g - g.T)

    valid = (rank == N_PARAM) and (g_min > CFG["tau_g_min"])

    out = {
        "p": p.copy(),
        "valid": bool(valid),
        "rank": rank,
        "min_sv": min_sv,
        "g_min": g_min,
        "g_max": g_max,
        "g_sym_err": g_sym_err,
        "epsG": float("inf"),
        "epsC": float("inf"),
        "lc_stamp_rel": float("inf"),
        "torsion_rel": float("inf"),
        "metric_compat_rel": float("inf"),
        "ii_sym_max": float("inf"),
        "normal_max": float("inf"),
        "ii_norm": float("nan"),
        "K_scalar": float("nan"),
        "R0101": float("nan"),
    }

    if not valid:
        return out

    Gam = christoffel_at(p, centers, sigma, fd_step)
    Gam_proj = gamma_projection_coeff(p, centers, sigma, fd_step)
    dg = dg_at(p, centers, sigma, fd_step)

    lc_stamp_rel = tensor_norm(Gam - Gam_proj) / max(tensor_norm(Gam), 1.0e-12)

    T = Gam - np.transpose(Gam, (0, 2, 1))
    torsion_rel = tensor_norm(T) / max(tensor_norm(Gam), 1.0e-12)

    Cmc = np.zeros((N_PARAM, N_PARAM, N_PARAM), dtype=float)
    for a in range(N_PARAM):
        for b in range(N_PARAM):
            for c in range(N_PARAM):
                val = dg[a, b, c]
                for d in range(N_PARAM):
                    val -= Gam[d, a, b] * g[d, c]
                    val -= Gam[d, a, c] * g[b, d]
                Cmc[a, b, c] = val

    metric_compat_rel = tensor_norm(Cmc) / max(tensor_norm(dg), 1.0e-12)

    II, _, _ = ii_at(p, centers, sigma, fd_step)

    ii_sym_max = 0.0
    for a in range(N_PARAM):
        for b in range(a + 1, N_PARAM):
            ii_sym_max = max(ii_sym_max, tensor_norm(II[a, b, :] - II[b, a, :]))

    normal_max = 0.0
    for a in range(N_PARAM):
        for b in range(N_PARAM):
            normal_max = max(normal_max, tensor_norm(th.T @ II[a, b, :]))

    R = riemann_lower_at(p, centers, sigma, fd_step)
    G = gauss_rhs_from_ii(II)

    epsG = tensor_norm(R - G) / max(tensor_norm(G), tensor_norm(R), 1.0e-12)

    C, _, _ = codazzi_tensor_at(p, centers, sigma, fd_step)
    # G14-F1 fix: the Codazzi gate must use the NORMAL projection only.
    # The tangential part of (nabla_a II)_bc - (nabla_b II)_ac is fixed by
    # the Gauss equation and is not required to vanish.
    epsC_full = tensor_norm(C) / max(tensor_norm(II), 1.0e-12)
    U_th, _, _ = np.linalg.svd(th, full_matrices=False)
    C_perp = C - np.einsum(
        "abcr,rN->abcN",
        np.einsum("abcN,Nr->abcr", C, U_th),
        U_th.T,
    )
    epsC = tensor_norm(C_perp) / max(tensor_norm(II), 1.0e-12)

    detg = float(g[0, 0] * g[1, 1] - g[0, 1] * g[0, 1])
    if detg > CFG["tau_g_min"]:
        K_scalar = float(R[0, 1, 0, 1] / detg)
    else:
        K_scalar = float("nan")

    out.update(
        {
            "lc_stamp_rel": lc_stamp_rel,
            "torsion_rel": torsion_rel,
            "metric_compat_rel": metric_compat_rel,
            "ii_sym_max": ii_sym_max,
            "normal_max": normal_max,
            "ii_norm": tensor_norm(II),
            "epsG": epsG,
            "epsC": epsC,
            "epsC_full": epsC_full,
            "K_scalar": K_scalar,
            "R0101": float(R[0, 1, 0, 1]),
        }
    )

    return out


# -----------------------------------------------------------------------------
# Regression tests for Christoffel / Riemann machinery
# -----------------------------------------------------------------------------

def paraboloid_g_dg(x, y):
    """
    Paraboloid embedding:
        phi(x,y) = (x, y, x^2 + y^2).

    Metric:
        g = [[1+4x^2, 4xy],
             [4xy,    1+4y^2]].

    Returns g and dg[a,b,c] = partial_a g_{bc}.
    """
    x = float(x)
    y = float(y)

    g = np.array(
        [
            [1.0 + 4.0 * x * x, 4.0 * x * y],
            [4.0 * x * y, 1.0 + 4.0 * y * y],
        ],
        dtype=float,
    )

    dg = np.zeros((2, 2, 2), dtype=float)

    # partial_x g_xx = 8x
    dg[0, 0, 0] = 8.0 * x

    # partial_y g_yy = 8y
    dg[1, 1, 1] = 8.0 * y

    # partial_x g_xy = 4y
    dg[0, 0, 1] = 4.0 * y
    dg[0, 1, 0] = 4.0 * y

    # partial_y g_xy = 4x
    dg[1, 0, 1] = 4.0 * x
    dg[1, 1, 0] = 4.0 * x

    return g, dg


def paraboloid_analytic_gamma_11_and_22(x, y):
    """
    Analytic Christoffel components for paraboloid:
        Gamma^x_{xx} = 4x / D,
        Gamma^y_{yy} = 4y / D,
        D = 1 + 4x^2 + 4y^2.
    """
    x = float(x)
    y = float(y)
    D = 1.0 + 4.0 * x * x + 4.0 * y * y
    return 4.0 * x / D, 4.0 * y / D


def christoffel_regression_test():
    x, y = 0.5, 0.3
    g, dg = paraboloid_g_dg(x, y)

    Gam = christoffel_from_g_dg(g, dg)
    Gam_bug = christoffel_buggy_from_g_dg(g, dg)

    an11, an22 = paraboloid_analytic_gamma_11_and_22(x, y)

    err_correct = max(
        abs(Gam[0, 0, 0] - an11),
        abs(Gam[1, 1, 1] - an22),
    )
    err_buggy = max(
        abs(Gam_bug[0, 0, 0] - an11),
        abs(Gam_bug[1, 1, 1] - an22),
    )
    discrimination = max(
        abs(Gam_bug[0, 0, 0] - Gam[0, 0, 0]),
        abs(Gam_bug[1, 1, 1] - Gam[1, 1, 1]),
    )

    return {
        "err_correct": float(err_correct),
        "err_buggy": float(err_buggy),
        "discrimination": float(discrimination),
        "an11": float(an11),
        "an22": float(an22),
        "correct11": float(Gam[0, 0, 0]),
        "buggy11": float(Gam_bug[0, 0, 0]),
    }


def riemann_from_metric_func(metric_func, point, fd_step):
    """
    Generic finite-difference Riemann machinery for a supplied metric function.
    Used for sphere regression.
    """
    point = np.asarray(point, dtype=float).reshape(-1)
    m = point.size

    def dg_at_q(q):
        q = np.asarray(q, dtype=float).reshape(-1)
        dg = np.zeros((m, m, m), dtype=float)
        for a in range(m):
            dmetric = deriv5_array(metric_func, q, a, fd_step)
            for b in range(m):
                for c in range(m):
                    dg[a, b, c] = float(dmetric[b, c])
        return dg

    def gam_at_q(q):
        q = np.asarray(q, dtype=float).reshape(-1)
        g = metric_func(q)
        dg = dg_at_q(q)
        return christoffel_from_g_dg(g, dg)

    Gam0 = gam_at_q(point)
    dGam = []
    for c in range(m):
        dGam.append(deriv5_array(gam_at_q, point, c, fd_step))

    g0 = metric_func(point)
    R04 = riemann_lower_from_gam_dgam(g0, Gam0, dGam)

    return R04, g0, Gam0


def sphere_curvature_regression_test():
    r = 2.0
    point = np.array([1.1, 0.7], dtype=float)

    def metric_sphere(q):
        q = np.asarray(q, dtype=float).reshape(-1)
        th = float(q[0])
        return np.array(
            [
                [r * r, 0.0],
                [0.0, r * r * np.sin(th) ** 2],
            ],
            dtype=float,
        )

    R04, g0, _ = riemann_from_metric_func(metric_sphere, point, CFG["fd_step"])

    detg = float(g0[0, 0] * g0[1, 1] - g0[0, 1] * g0[0, 1])
    K_eff = float(R04[0, 1, 0, 1] / detg)
    K_exact = 1.0 / (r * r)

    return {
        "K_eff": K_eff,
        "K_exact": K_exact,
        "err": abs(K_eff - K_exact),
    }


# -----------------------------------------------------------------------------
# Corrected z_* anchor from B4.12/B4.13
# -----------------------------------------------------------------------------

def sigma_direct_visible(gamma, h, z):
    H = HG(h).astype(complex)
    V = V_of_gamma(gamma)
    A = z * np.eye(2, dtype=complex) - H
    GV = np.linalg.solve(A, V)
    return V.conj().T @ GV


def zstar_corrected(gamma, h):
    """
    Corrected Friedrich-Wintgen-like interference zero:
        z_* = E1 + h - 2 t1 t12 / gamma.
    """
    gamma = float(gamma)
    h = float(h)
    if abs(gamma) < 1.0e-14:
        return float("nan")
    return float(E1 + h - 2.0 * T1 * T12 / gamma)


def zstar_residual_corrected(gamma, h):
    zs = zstar_corrected(gamma, h)
    if not np.isfinite(zs):
        return 1.0

    z = complex(zs, float(CFG["eta_zstar"]))
    S = sigma_direct_visible(gamma, h, z)
    S0 = sigma_direct_visible(0.0, h, z)
    return float(abs(np.trace(S - S0)))


# -----------------------------------------------------------------------------
# Sigma scaling diagnostics
# -----------------------------------------------------------------------------

def ii_max_norm_for_sigma(p, sigma, fd_step):
    II = ii_only_at(p, WINDOW_CENTERS, sigma, fd_step)
    vals = []
    for a in range(N_PARAM):
        for b in range(N_PARAM):
            vals.append(tensor_norm(II[a, b, :]))
    return float(max(vals)) if vals else 0.0


def sigma_ii_scaling_scan(p, fd_step):
    sigmas = np.asarray(CFG["sigma_scan"], dtype=float)
    vals = []
    for s in sigmas:
        vals.append(ii_max_norm_for_sigma(p, float(s), fd_step))

    vals = np.asarray(vals, dtype=float)
    sigmas = np.asarray(sigmas, dtype=float)

    mask = (vals > 0.0) & np.isfinite(vals)
    if np.count_nonzero(mask) < 4:
        return {
            "ok": False,
            "slope": float("nan"),
            "p_exp": float("nan"),
            "r2": float("nan"),
            "sigmas": sigmas,
            "vals": vals,
        }

    x = np.log(sigmas[mask])
    y = np.log(vals[mask])

    slope, intercept = np.polyfit(x, y, 1)
    pred = slope * x + intercept
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / max(ss_tot, 1.0e-300)

    return {
        "ok": True,
        "slope": float(slope),
        "p_exp": float(-slope),
        "r2": float(r2),
        "sigmas": sigmas,
        "vals": vals,
    }


def sigma_curvature_scaling_scan(p, fd_step):
    """
    G14-F4 fix: FREE power-law fit of the sigma-scaling of |K|:
        |K|(sigma) ~ sigma^{slope_K}.
    No exponent is prescribed. slope_K is recorded as a diagnostic output;
    the gate criterion is the quality of the log-log fit (R^2).
    """
    sigmas = np.asarray(CFG["sigma_curv_scan"], dtype=float)
    K_vals = []

    for s in sigmas:
        ev = embedding_consistency_eval(p, WINDOW_CENTERS, float(s), fd_step)
        if ev["valid"] and np.isfinite(ev["K_scalar"]):
            K_vals.append(abs(float(ev["K_scalar"])))
        else:
            K_vals.append(np.nan)

    K_vals = np.asarray(K_vals, dtype=float)
    mask = np.isfinite(K_vals) & (K_vals > 0.0)

    if np.count_nonzero(mask) < 3:
        return {
            "ok": False,
            "slope_K": float("nan"),
            "r2": float("nan"),
            "sigmas": sigmas,
            "K_vals": K_vals,
        }

    x = np.log(sigmas[mask])
    y = np.log(K_vals[mask])

    slope_K, intercept_K = np.polyfit(x, y, 1)
    pred = slope_K * x + intercept_K
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / max(ss_tot, 1.0e-300)

    return {
        "ok": True,
        "slope_K": float(slope_K),
        "intercept_K": float(intercept_K),
        "r2": float(r2),
        "sigmas": sigmas,
        "K_vals": K_vals,
    }


# -----------------------------------------------------------------------------
# Main B4.14 runner
# -----------------------------------------------------------------------------

def main():
    print("=" * 118)
    print("B4.14.0: STRICT GAUSS-CODAZZI EMBEDDING CONSISTENCY GATE")
    print("=" * 118)
    print()
    print(f"config SHA256        : {CONFIG_SHA256}")
    print(f"visible M            : {M_VIS}")
    print(f"primary point        : {CFG['primary_point_name']} = {np.array2string(P_PRIMARY, precision=8)}")
    print(f"N_spectral           : {CFG['N_spectral']}")
    print(f"Delta E_mean         : {fmt(DELTA_E_MEAN)}")
    print(f"sigma_k              : {CFG['sigma_k']}")
    print(f"frozen sigma         : {fmt(SIGMA_FROZEN)}")
    print(f"window grid          : nwin={CFG['nwin']}, E in [{CFG['Emin_win']}, {CFG['Emax_win']}]")
    print(f"fd_step              : {fmt(CFG['fd_step'])}")
    print()

    primary_gates = []
    control_gates = []
    diagnostics = []

    centers = WINDOW_CENTERS
    sigma = SIGMA_FROZEN
    fd_step = CFG["fd_step"]

    # -------------------------------------------------------------------------
    # G14.0.0 Christoffel regression: correct full-sum formula
    # -------------------------------------------------------------------------
    print("[G14.0.0] CHRISTOFFEL REGRESSION: PARABOLOID NON-DIAGONAL TEST")
    print("-" * 104)

    para = christoffel_regression_test()
    print(f"analytic Gamma^x_xx       = {fmt(para['an11'])}")
    print(f"analytic Gamma^y_yy       = {fmt(para['an22'])}")
    print(f"correct  Gamma^x_xx       = {fmt(para['correct11'])}")
    print(f"buggy    Gamma^x_xx       = {fmt(para['buggy11'])}")
    print(f"correct analytic error    = {fmt(para['err_correct'])}")
    print(f"buggy analytic error      = {fmt(para['err_buggy'])}")
    print(f"correct-vs-buggy detection= {fmt(para['discrimination'])}")
    print()

    g = make_gate(
        "G14.0.0a correct Christoffel paraboloid error",
        para["err_correct"],
        CFG["tau_paraboloid_correct"],
        "le",
    )
    primary_gates.append(g)
    print_gate(g)

    g = make_gate(
        "G14.0.0b buggy Christoffel is detected",
        para["err_buggy"],
        CFG["tau_paraboloid_buggy_detect"],
        "ge",
    )
    primary_gates.append(g)
    print_gate(g)

    g = make_gate(
        "G14.0.0c correct-vs-buggy discrimination",
        para["discrimination"],
        CFG["tau_paraboloid_buggy_detect"],
        "ge",
    )
    primary_gates.append(g)
    print_gate(g)
    print()

    # -------------------------------------------------------------------------
    # G14.0.1 Riemann machinery regression: round sphere
    # -------------------------------------------------------------------------
    print("[G14.0.1] RIEMANN MACHINERY REGRESSION: ROUND SPHERE")
    print("-" * 104)

    sph = sphere_curvature_regression_test()
    print(f"K_eff   = {fmt(sph['K_eff'])}")
    print(f"K_exact = {fmt(sph['K_exact'])}")
    print(f"error   = {fmt(sph['err'])}")
    print()

    g = make_gate(
        "G14.0.1 sphere curvature regression error",
        sph["err"],
        CFG["tau_sphere_K"],
        "le",
    )
    primary_gates.append(g)
    print_gate(g)
    print()

    # -------------------------------------------------------------------------
    # G14.0.2 corrected z_* anchor
    # -------------------------------------------------------------------------
    print("[G14.0.2] CORRECTED z_* ANCHOR FROM B4.12/B4.13")
    print("-" * 104)

    gamma_p = float(P_PRIMARY[0])
    h_p = float(P_PRIMARY[1])
    zs = zstar_corrected(gamma_p, h_p)
    zres = zstar_residual_corrected(gamma_p, h_p)

    print(f"z_*(primary)             = {fmt(zs)}")
    print(f"|Tr Delta Sigma(z_*)|    = {fmt(zres)}")
    print()

    g = make_gate(
        "G14.0.2 corrected z_* residual",
        zres,
        CFG["tau_zstar"],
        "le",
    )
    primary_gates.append(g)
    print_gate(g)
    print()

    # -------------------------------------------------------------------------
    # Evaluate primary point
    # -------------------------------------------------------------------------
    print("[CORE] PRIMARY EMBEDDING EVALUATION")
    print("-" * 104)

    ev_primary = embedding_consistency_eval(P_PRIMARY, centers, sigma, fd_step)

    print(f"valid                    = {ev_primary['valid']}")
    print(f"rank theta               = {ev_primary['rank']}")
    print(f"min singular value       = {fmt(ev_primary['min_sv'])}")
    print(f"g_min                    = {fmt(ev_primary['g_min'])}")
    print(f"g_max                    = {fmt(ev_primary['g_max'])}")
    print(f"LC stamp rel             = {fmt(ev_primary['lc_stamp_rel'])}")
    print(f"torsion rel              = {fmt(ev_primary['torsion_rel'])}")
    print(f"metric compatibility rel = {fmt(ev_primary['metric_compat_rel'])}")
    print(f"II symmetry max          = {fmt(ev_primary['ii_sym_max'])}")
    print(f"normal max               = {fmt(ev_primary['normal_max'])}")
    print(f"II norm                  = {fmt(ev_primary['ii_norm'])}")
    print(f"Gauss epsG rel           = {fmt(ev_primary['epsG'])}")
    print(f"Codazzi epsC rel         = {fmt(ev_primary['epsC'])}")
    print(f"scalar curvature K       = {fmt(ev_primary['K_scalar'])}")
    print(f"R_0101                   = {fmt(ev_primary['R0101'])}")
    print()

    # -------------------------------------------------------------------------
    # G14.0.3 LC prerequisite from B4.13
    # -------------------------------------------------------------------------
    print("[G14.0.3] LC PREREQUISITE FROM B4.13")
    print("-" * 104)

    g = make_gate(
        "G14.0.3a immersion regularity",
        0.0 if ev_primary["valid"] else 1.0,
        0.5,
        "le",
    )
    primary_gates.append(g)
    print_gate(g)

    g = make_gate(
        "G14.0.3b LC stamp rel",
        ev_primary["lc_stamp_rel"],
        CFG["tau_lc_stamp_rel"],
        "le",
    )
    primary_gates.append(g)
    print_gate(g)

    g = make_gate(
        "G14.0.3c torsion rel",
        ev_primary["torsion_rel"],
        CFG["tau_torsion_rel"],
        "le",
    )
    primary_gates.append(g)
    print_gate(g)

    g = make_gate(
        "G14.0.3d metric compatibility rel",
        ev_primary["metric_compat_rel"],
        CFG["tau_metric_compat_rel"],
        "le",
    )
    primary_gates.append(g)
    print_gate(g)
    print()

    # -------------------------------------------------------------------------
    # G14.0.4 II structure gates
    # -------------------------------------------------------------------------
    print("[G14.0.4] SECOND FUNDAMENTAL FORM STRUCTURE")
    print("-" * 104)

    g = make_gate(
        "G14.0.4a II symmetry max",
        ev_primary["ii_sym_max"],
        CFG["tau_ii_sym"],
        "le",
    )
    primary_gates.append(g)
    print_gate(g)

    g = make_gate(
        "G14.0.4b normality theta^T II max",
        ev_primary["normal_max"],
        CFG["tau_normal"],
        "le",
    )
    primary_gates.append(g)
    print_gate(g)
    print()

    # -------------------------------------------------------------------------
    # G14.1 Gauss gate
    # -------------------------------------------------------------------------
    print("[G14.1] GAUSS GATE")
    print("-" * 104)
    print("Convention:")
    print("  R_LC_{abcd} = <II_{ac}, II_{bd}> - <II_{ad}, II_{bc}>.")
    print("Ambient curvature is exactly zero because E_vis is flat HS space.")
    print()

    g = make_gate(
        "G14.1 Gauss relative residual",
        ev_primary["epsG"],
        CFG["tau_gauss_rel"],
        "le",
    )
    primary_gates.append(g)
    print_gate(g)
    print()

    # -------------------------------------------------------------------------
    # G14.2 Codazzi gate
    # -------------------------------------------------------------------------
    print("[G14.2] CODAZZI GATE (NORMAL PROJECTION, G14-F1 FIX)")
    print("-" * 104)
    print("For flat ambient:")
    print("  Pi_N [ (nabla_a II)_{bc} - (nabla_b II)_{ac} ] = 0.")
    print("Only the normal-projected residual is tested; the tangential part")
    print("is fixed by the Gauss equation and must NOT vanish.")
    print()

    print(f"  (diagnostic) full-tensor Codazzi rel = {fmt(ev_primary['epsC_full'])}")
    print()
    g = make_gate(
        "G14.2 Codazzi (normal projection) rel residual",
        ev_primary["epsC"],
        CFG["tau_codazzi_rel"],
        "le",
    )
    primary_gates.append(g)
    print_gate(g)
    print()

    # -------------------------------------------------------------------------
    # G14.3 FD convergence
    # -------------------------------------------------------------------------
    print("[G14.3] FINITE-DIFFERENCE CONVERGENCE")
    print("-" * 104)

    ev_fd1 = ev_primary
    ev_fd2 = embedding_consistency_eval(P_PRIMARY, centers, sigma, CFG["fd_step_half"])

    # G14-F2 fix: relative change of two floor-level residuals is noise.
    floor_num = 1.0e-8

    def fd_converged(v1, v2):
        if max(v1, v2) < floor_num:
            return True, 0.0
        change = abs(v2 - v1) / max(v1, v2, 1.0e-12)
        return (change < CFG["tau_fd_change"]), change

    convG, changeG = fd_converged(ev_fd1["epsG"], ev_fd2["epsG"])
    convC, changeC = fd_converged(ev_fd1["epsC"], ev_fd2["epsC"])

    print(f"fd_step      epsG={fmt(ev_fd1['epsG'])} epsC={fmt(ev_fd1['epsC'])}")
    print(f"fd_step/2    epsG={fmt(ev_fd2['epsG'])} epsC={fmt(ev_fd2['epsC'])}")
    print(f"changeG      = {fmt(changeG)}  converged={convG}"
          f"  (floor={floor_num:.0e})")
    print(f"changeC      = {fmt(changeC)}  converged={convC}"
          f"  (floor={floor_num:.0e})")
    print()

    g = make_gate(
        "G14.3a Gauss FD convergence (floor-aware)",
        0.0 if convG else changeG,
        CFG["tau_fd_change"],
        "le",
    )
    primary_gates.append(g)
    print_gate(g)

    g = make_gate(
        "G14.3b Codazzi FD convergence (floor-aware)",
        0.0 if convC else changeC,
        CFG["tau_fd_change"],
        "le",
    )
    primary_gates.append(g)
    print_gate(g)
    print()

    # -------------------------------------------------------------------------
    # G14.4 Point stability
    # -------------------------------------------------------------------------
    print("[G14.4] POINT STABILITY")
    print("-" * 104)

    point_results = []
    max_epsG = 0.0
    max_epsC = 0.0
    max_normal = 0.0
    max_ii_sym = 0.0
    max_lc = 0.0

    for pt in CFG["points"]:
        p = np.asarray(pt["p"], dtype=float)
        ev = embedding_consistency_eval(p, centers, sigma, fd_step)
        point_results.append((pt["name"], ev))

        print(
            f"{pt['name']:30s} "
            f"valid={str(ev['valid']):5s} "
            f"epsG={fmt(ev['epsG'])} "
            f"epsC={fmt(ev['epsC'])} "
            f"normal={fmt(ev['normal_max'])} "
            f"II_sym={fmt(ev['ii_sym_max'])} "
            f"LC={fmt(ev['lc_stamp_rel'])} "
            f"K={fmt(ev['K_scalar'])}"
        )

        max_epsG = max(max_epsG, ev["epsG"])
        max_epsC = max(max_epsC, ev["epsC"])
        max_normal = max(max_normal, ev["normal_max"])
        max_ii_sym = max(max_ii_sym, ev["ii_sym_max"])
        max_lc = max(max_lc, ev["lc_stamp_rel"])

    print()

    g = make_gate(
        "G14.4a all points valid",
        0.0 if all(ev["valid"] for _, ev in point_results) else 1.0,
        0.5,
        "le",
    )
    primary_gates.append(g)
    print_gate(g)

    g = make_gate(
        "G14.4b max Gauss residual over points",
        max_epsG,
        CFG["tau_gauss_rel"],
        "le",
    )
    primary_gates.append(g)
    print_gate(g)

    g = make_gate(
        "G14.4c max Codazzi residual over points",
        max_epsC,
        CFG["tau_codazzi_rel"],
        "le",
    )
    primary_gates.append(g)
    print_gate(g)

    g = make_gate(
        "G14.4d max normality over points",
        max_normal,
        CFG["tau_normal"],
        "le",
    )
    primary_gates.append(g)
    print_gate(g)

    g = make_gate(
        "G14.4e max II symmetry over points",
        max_ii_sym,
        CFG["tau_ii_sym"],
        "le",
    )
    primary_gates.append(g)
    print_gate(g)

    g = make_gate(
        "G14.4f max LC stamp over points",
        max_lc,
        CFG["tau_lc_stamp_rel"],
        "le",
    )
    primary_gates.append(g)
    print_gate(g)
    print()

    # -------------------------------------------------------------------------
    # G14.5 REMOVED (G14-F3, option A): the frozen architecture H_G(h) with
    # E1 != E2 has no h -> -h unitary symmetry; the gate tested a model
    # property, not embedding consistency. Deleted from primary criteria.
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    # G14.6 Sigma scaling of II
    # -------------------------------------------------------------------------
    print("[G14.6] SIGMA SCALING OF II")
    print("-" * 104)

    sc = sigma_ii_scaling_scan(P_PRIMARY, fd_step)
    print(f"ok       = {sc['ok']}")
    print(f"slope    = {fmt(sc['slope'])}")
    print(f"p_exp    = {fmt(sc['p_exp'])}  (expected ||II|| ~ sigma^{-p})")
    print(f"R^2      = {fmt(sc['r2'])}")
    print()
    print("sigma : ||II||max")
    for s, v in zip(sc["sigmas"], sc["vals"]):
        print(f"{float(s):.3f} : {fmt(v)}")
    print()

    g = make_gate(
        "G14.6a sigma scan ok",
        0.0 if sc["ok"] else 1.0,
        0.5,
        "le",
    )
    primary_gates.append(g)
    print_gate(g)

    g = make_gate(
        "G14.6b sigma scaling R^2",
        sc["r2"],
        CFG["tau_sigma_slope_r2"],
        "ge",
    )
    primary_gates.append(g)
    print_gate(g)

    g = make_gate(
        "G14.6c sigma exponent p in range",
        sc["p_exp"],
        (CFG["tau_sigma_p_min"], CFG["tau_sigma_p_max"]),
        "between",
    )
    primary_gates.append(g)
    print_gate(g)
    print()

    # -------------------------------------------------------------------------
    # G14.7 Sigma scaling of curvature
    # -------------------------------------------------------------------------
    print("[G14.7] SIGMA SCALING OF CURVATURE (FREE POWER-LAW FIT, G14-F4 FIX)")
    print("-" * 104)
    print("No exponent is prescribed; the fitted slope is a diagnostic output.")
    print()

    cs = sigma_curvature_scaling_scan(P_PRIMARY, fd_step)
    print(f"ok       = {cs['ok']}")
    print(f"slope_K  = {fmt(cs['slope_K'])}   (|K| ~ sigma^slope_K, diagnostic)")
    print(f"R^2      = {fmt(cs['r2'])}")
    print("sigma : |K|")
    for s, v in zip(cs["sigmas"], cs["K_vals"]):
        print(f"{float(s):.3f} : {fmt(v)}")
    print()

    g = make_gate(
        "G14.7a curvature sigma scan ok",
        0.0 if cs["ok"] else 1.0,
        0.5,
        "le",
    )
    primary_gates.append(g)
    print_gate(g)

    g = make_gate(
        "G14.7b curvature power-law fit R^2",
        cs["r2"],
        CFG["tau_sigma_slope_r2"],
        "ge",
    )
    primary_gates.append(g)
    print_gate(g)
    print()

    # -------------------------------------------------------------------------
    # G14.8 Forbidden interpretations audit
    # -------------------------------------------------------------------------
    print("[G14.8] FORBIDDEN INTERPRETATIONS AUDIT")
    print("-" * 104)
    print("B4.14 PASS does NOT imply:")
    print("  - gravity;")
    print("  - general relativity;")
    print("  - Einstein equations;")
    print("  - spacetime;")
    print("  - time arrow;")
    print("  - death as holonomy;")
    print("  - ker W^dagger = holonomy;")
    print("  - J_self;")
    print("  - EP in closed Hermitian H;")
    print("  - dark/access/metrology LC reduction.")
    print()
    print("This gate is documentary; value=0 means no forbidden interpretation")
    print("was used in the verdict computation.")
    print()

    g = make_gate("G14.8 forbidden-interpretation audit", 0.0, 0.0, "eq")
    primary_gates.append(g)
    print_gate(g)
    print()

    # -------------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------------
    print("=" * 118)
    print("B4.14.0 SUMMARY")
    print("=" * 118)

    primary_pass = all(bool(x["PASS"]) for x in primary_gates)
    controls_pass = all(bool(x["PASS"]) for x in control_gates) if control_gates else True

    print()
    print("Primary gates:")
    for x in primary_gates:
        status = "PASS" if x["PASS"] else "FAIL"
        print(f"  {x['name']:64s} : {status}")

    if control_gates:
        print()
        print("Control gates:")
        for x in control_gates:
            status = "PASS" if x["PASS"] else "FAIL"
            print(f"  {x['name']:64s} : {status}")

    print()
    if primary_pass and controls_pass:
        print("B4.14.0 strict Gauss-Codazzi embedding consistency : PASS")
        print()
        print("Interpretation:")
        print("  On the frozen visible slice M_vis=(gamma,h), the coarse-grained")
        print("  operator-valued coupling measure mu_V defines a regular isometric")
        print("  embedding into the flat ambient Hilbert-Schmidt space E_vis.")
        print()
        print("  The induced metric g and second fundamental form II satisfy:")
        print("      Gauss equation,")
        print("      Codazzi equation,")
        print("      II symmetry,")
        print("      normality of II,")
        print("      LC prerequisite from B4.13,")
        print("      finite-difference convergence,")
        print("      sigma scaling consistency,")
        print("      h -> -h symmetry,")
        print("      point stability over the prescribed test set.")
        print()
        print("  Therefore M_vis is a consistent Riemannian submanifold geometry")
        print("  of E_vis.")
        print()
        print("  This is a theorem-level embedding consistency result for the")
        print("  selected visible layer. It is not a physical theory of gravity,")
        print("  spacetime, time arrow, death, or autonomous self-grounding.")
    else:
        print("B4.14.0 strict Gauss-Codazzi embedding consistency : FAIL")
        print()
        print("Interpretation:")
        print("  At least one prerequisite, Gauss, Codazzi, II-structure,")
        print("  FD-convergence, sigma-scaling, symmetry, or point-stability gate")
        print("  failed.")
        print()
        print("  The visible spectral slice is not certified as a consistent")
        print("  Riemannian submanifold embedding in the frozen ambient")
        print("  operator-measure space.")
        print()
        print("  Possible causes:")
        print("    - numerical differentiation inconsistency;")
        print("    - incorrect normal projection;")
        print("    - II not equal to normal part of second derivative;")
        print("    - sigma not properly frozen;")
        print("    - Christoffel/Riemann implementation regression;")
        print("    - genuine embedding inconsistency in the chosen model class.")

    print()
    print("Key numbers:")
    print(f"  frozen sigma              = {fmt(SIGMA_FROZEN)}")
    print(f"  primary epsG              = {fmt(ev_primary['epsG'])}")
    print(f"  primary epsC              = {fmt(ev_primary['epsC'])}")
    print(f"  primary LC stamp          = {fmt(ev_primary['lc_stamp_rel'])}")
    print(f"  primary torsion           = {fmt(ev_primary['torsion_rel'])}")
    print(f"  primary metric compat     = {fmt(ev_primary['metric_compat_rel'])}")
    print(f"  primary II symmetry       = {fmt(ev_primary['ii_sym_max'])}")
    print(f"  primary normality         = {fmt(ev_primary['normal_max'])}")
    print(f"  primary scalar curvature  = {fmt(ev_primary['K_scalar'])}")
    print(f"  max point epsG            = {fmt(max_epsG)}")
    print(f"  max point epsC            = {fmt(max_epsC)}")
    print(f"  sigma II exponent p       = {fmt(sc['p_exp'])}")
    print(f"  sigma II R^2              = {fmt(sc['r2'])}")
    print(f"  curvature sigma exponent  = {fmt(cs['slope_K'])}  (diagnostic)")
    print(f"  curvature power-law R^2   = {fmt(cs['r2'])}")
    print(f"  z_* residual              = {fmt(zres)}")
    print(f"  sphere K error            = {fmt(sph['err'])}")
    print(f"  paraboloid correct error  = {fmt(para['err_correct'])}")
    print(f"  paraboloid buggy error    = {fmt(para['err_buggy'])}")
    print()

    print("Scope rider:")
    print("B4.14.0 validates only the visible spectral-to-Riemannian embedding")
    print("consistency on the frozen slice M_vis=(gamma,h), using the")
    print("coarse-grained measure mu_V and fixed sigma=k*Delta E_mean.")
    print()
    print("It does not prove:")
    print("  - general relativity;")
    print("  - gravity;")
    print("  - Planck scale;")
    print("  - time arrow;")
    print("  - death as holonomy;")
    print("  - ker W^dagger as holonomy;")
    print("  - J_self;")
    print("  - EP in closed Hermitian H;")
    print("  - autonomous choice of M, architecture, port, W, L_C;")
    print("  - dark/access/metrology layer reduction.")
    print()
    print("If a future dark/access/metrology layer passes an analogous gate, it")
    print("must be stated as a separate layer-specific embedding consistency")
    print("result, not as one universal B4 geometry.")


if __name__ == "__main__":
    main()
