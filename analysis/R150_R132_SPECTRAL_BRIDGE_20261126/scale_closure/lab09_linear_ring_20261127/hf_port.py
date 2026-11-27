"""Synthetic spectral response and negative controls for the locked LAB09 ring."""
from functools import lru_cache
from itertools import permutations

import numpy as np

import lab09
from hf_recovery import recover

PORT = 6
HF_LIMITS = {
    "hf_trace_detuned": None, "hf_calibrated_detuned": None, "hf_both_detuned": None,
    "hf_impure_declared": "PURE_RANK_ONE_CONTROL", "hf_impure_hidden": "FORWARD_SPECTRUM",
    "hf_frequency_sort": "BRANCH_TRACKING", "hf_missing_branch": "SPECTRUM_COMPLETE",
    "hf_false_independence": "FALSE_INDEPENDENCE", "hf_slope_from_sum": "FALSE_INDEPENDENCE",
    "hf_trace_sum_claimed": "TRACE_SUM_NOT_INDEPENDENT",
}


def ring_matrix():
    c = lab09.circulant_coefficients()
    return lab09.circulant(c), c


@lru_cache(maxsize=4)
def _permutations(n):
    return np.asarray(list(permutations(range(n))))


def assign_overlap(overlap):
    """Global one-to-one assignment for the small (at most seven mode) controls."""
    n = len(overlap)
    if not 1 <= n <= 7 or np.shape(overlap) != (n, n):
        raise ValueError("expected a square overlap matrix of order 1 to 7")
    choices = _permutations(n)
    return choices[np.argmax(overlap[np.arange(n), choices].sum(axis=1))].copy()


def _aligned(build, center, x):
    e, v = lab09.diagonalize(build(x))
    overlap = abs(center.conj().T @ v)**2
    order = assign_overlap(overlap)
    return e[order], overlap[np.arange(len(e)), order].min()


def _stencil(build, center, h):
    e, v = lab09.diagonalize(build(center))
    data = [_aligned(build, v, center + h * k) for k in (-2, -1, 1, 2)]
    l, lm, rm, r = (pair[0] for pair in data)
    cd = (rm - lm) / (2 * h)
    return cd, (4 * cd - (r - l) / (4 * h)) / 3, lab09.port_weights(v), min(row[1] for row in data)


def _max(a):
    return float(np.max(abs(a)))


def _crossing(ring):
    # Reflection about contact 0 decouples odd states. Split the bare parity partners.
    A = ring.copy()
    A[[1, 5], [1, 5]] += 8.
    groups = lab09.mode_groups(A)
    dark = min(row["energy"] for row in groups if row["site0_weight"] < 1e-15)
    bright = [row for row in groups if row["site0_weight"] > 1e-12]
    g = 1.
    # Schur complement restricted to the coupled (even) space, regular at E_dark.
    root = dark - g * g * sum(row["site0_weight"] / (dark - row["energy"]) for row in bright)
    def spectrum(nu):
        return lab09.diagonalize(lab09.hamiltonian(A, nu, g))
    e0, v0 = spectrum(root)
    pair = np.argsort(abs(e0 - dark))[:2]
    port_block = v0[PORT, pair]
    # Eigenvalues of compressed Pp give the two slopes inside the degenerate space.
    derivatives = np.linalg.eigvalsh(np.outer(port_block.conj(), port_block))
    def across(center, h):
        left, vl = spectrum(center - h)
        right, vr = spectrum(center + h)
        j = int(np.argmin(abs(left - dark)))
        k = assign_overlap(abs(vl.conj().T @ vr)**2)[j]
        return dict(h_mhz=h, left_slot=j, right_slot=int(k),
                    tracked_dark_slope=(right[k] - left[j]) / (2 * h),
                    tracked_dark_port_weight=max(abs(vl[PORT, j])**2, abs(vr[PORT, k])**2),
                    sorted_slope_in_dark_slot=(right[j] - left[j]) / (2 * h),
                    min_dark_overlap=abs(np.vdot(vl[:, j], vr[:, k]))**2)
    rows = [across(root, h) for h in (.3, .8, 2.)]
    return dict(dark_energy_mhz=dark, crossing_nu_p_mhz=root, offset_mhz=root - dark,
                max_double_root_residual_mhz=_max(e0[pair] - dark), slopes_at_crossing=derivatives,
                **rows[0], exact_center_scan=rows, logged_bare_center_scan=[across(dark, h) for h in (.3, .8, 2.)])


def _open(ring, gamma):
    target, g, h = lab09.LINES_MHZ[1], .2, .001
    def spec(x):
        H = lab09.hamiltonian(ring, target + x, g)
        H[PORT, PORT] -= .5j * gamma
        # Remove the carrier before solving for the small complex splittings.
        e, v = np.linalg.eig(H - target * np.eye(7))
        return e, v / np.linalg.norm(v, axis=0)
    _, v = spec(0)
    generalized = np.linalg.inv(v)[:, PORT] * v[PORT]
    def diff(step):
        def matched(x):
            e, u = spec(x)
            return e[assign_overlap(abs(v.conj().T @ u)**2)]
        return (matched(step) - matched(-step)) / (2 * step)
    cd = diff(h)
    refined = (4 * diff(h / 2) - cd) / 3
    return dict(gamma_mhz=gamma, max_abs_generalized_minus_numerical=_max(generalized - cd),
                richardson_error=_max(generalized - refined), max_abs_imag=_max(generalized.imag),
                max_abs_bare_probability_minus_real_derivative=_max(abs(v[PORT])**2 - generalized.real),
                min_real=generalized.real.min(), max_real=generalized.real.max(),
                sum_real=generalized.sum().real, sum_imag=generalized.sum().imag,
                eigenvector_condition=np.linalg.cond(v))


def _tuning(x):
    # Reconstructed smooth fixture: same tangent and unit half-span secant as the log.
    return 6600. + 8.385827515983658 * x + .3 * x * x + .665655020464968 * x**3


def make_sweep(name, source_id):
    """Noise-free synthetic observations plus a known joint Gaussian instrument model."""
    ring, _ = ring_matrix()
    mode = ("trace" if name in ("hf_trace_detuned", "hf_trace_sum_claimed") else
            "both" if name == "hf_both_detuned" else "calibrated")
    channels = 7 if mode == "trace" else 8
    steps = [.005, .01, .02, .04]
    offsets = np.unique([0., *(a * h for h in steps for a in (-1., -.5, .5, 1.))])
    build = lambda x: lab09.hamiltonian(ring, _tuning(x), 1 + (.5 * x if "impure" in name else 0.))
    _, center = lab09.diagonalize(build(0))
    samples = np.array([_aligned(build, center, x)[0] for x in offsets])
    if channels == 8:
        samples = np.column_stack([samples, _tuning(offsets)])
    # Channel-correlated point noise and a common offset across settings.
    block = (2e-8)**2 * (np.eye(channels) + .35 * np.ones((channels, channels)))
    cov = np.kron(np.eye(len(offsets)), block) + (1e-8)**2
    record = dict(normalization=mode, offsets=offsets, steps=steps, samples_mhz=samples,
                  sample_covariance_mhz2=cov, fifth_derivative_bounds=[2e5] * 7 + [0.] * (channels - 7),
                  pure_rank_one=name != "hf_impure_declared", closed_hermitian=True,
                  tracking=("frequency_order" if name == "hf_frequency_sort" else "synthetic_overlap"),
                  branch_ids=list(range(7)), calibration_source_id=source_id + "-tuning",
                  calibration_origin="independent_record", sum_claimed_independent=name == "hf_trace_sum_claimed")
    if name == "hf_missing_branch":
        record["samples_mhz"] = np.delete(samples, 4, axis=1)
    elif name == "hf_false_independence":
        record["calibration_source_id"] = source_id
    elif name == "hf_slope_from_sum":
        record["calibration_origin"] = "same_line_sum"
    return record


def _resolvent(ring, nu, g):
    bare, v = lab09.diagonalize(ring)
    levels, dressed = lab09.diagonalize(lab09.hamiltonian(ring, nu, g))
    errors = []
    for e, w in zip(levels, lab09.port_weights(dressed)):
        if min(abs(e - bare)) < 1e-8:
            continue
        weight = 1 / (1 + g * g * np.sum(abs(v[0])**2 / (e - bare)**2))
        errors.append(weight - w)
    return dict(compared=len(errors), skipped_bare_eigenvalues=len(levels) - len(errors), max_abs=_max(np.array(errors)))


def _two_mode():
    # Two-mode resonant pair, followed by a detuning of forty couplings.
    pair = lambda t: np.array([[0., 1.], [1., t]])
    two = (np.linalg.eigvalsh(pair(.001)) - np.linalg.eigvalsh(pair(-.001))) / .002
    return dict(analytic_resonant=[.5, .5], numerical_central_difference=two,
                    max_abs_numerical=_max(two - .5), large_detuning_weights=abs(np.linalg.eigh(pair(40))[1][1])**2)


def _impurity_controls(H, nu):
    impurity = {}
    for name, i, j, scale in (("g_derivative", 0, 6, .5), ("off_diagonal_ring", 0, 1, 1.), ("diagonal_ring_site", 1, 1, .25)):
        def perturbed(x):
            M = H(nu + x)
            M[i, j] += scale * x
            if i != j:
                M[j, i] += scale * x
            return M
        _, si, pi, _ = _stencil(perturbed, 0., .001)
        impurity[name] = dict(slope_sum=si.sum(), slope_sum_minus_dnu=si.sum() - 1,
                              trace_derivative=scale if i == j else 0., max_abs_trace_minus_vector=_max(si / si.sum() - pi))
    return impurity


def _nonlinear_control(H):
    _, sn, pn, _ = _stencil(lambda x: H(_tuning(x)), 0., .001)
    slope = 8.385827515983658
    wide = (_tuning(1.) - _tuning(-1.)) / 2
    return dict(local_dnu_dlambda=slope, wide_secant=wide, trace_max_abs=_max(sn / sn.sum() - pn),
                     local_calibrated_max_abs=_max(sn / slope - pn), wide_secant_max_abs=_max(sn / wide - pn), slope_sum=sn.sum())


def _omission_control(s, p):
    def omitted(j):
        keep = np.arange(len(p)) != j
        return _max(s[keep] / s[keep].sum() - p[keep])
    return dict(omit_dark_max_abs=omitted(np.argmin(p)), omit_largest_max_abs=omitted(np.argmax(p)), largest_weight=max(p))


def _degenerate_basis(ring):
    groups = lab09.mode_groups(ring)
    group = next(row for row in groups if row["degeneracy"] == 2)
    u = np.column_stack((group["bright"], group["dark"]))
    rotated = u @ (np.array([[1, 1], [1, -1]]) / np.sqrt(2))
    return dict(energy=group["energy"], bright_dark_contact_weights=abs(u[0])**2,
                 eigh_sum=np.sum(abs(u[0])**2), rotated_contact_weights=abs(rotated[0])**2, rotated_sum=np.sum(abs(rotated[0])**2))


def _trace_covariance(ring):
    target = lab09.LINES_MHZ[1]
    _, v = lab09.diagonalize(lab09.hamiltonian(ring, target, .2))
    pr = lab09.port_weights(v)
    noise = np.eye(7) * 1e-8
    jac = np.eye(7) - pr[:, None]
    cw = jac @ noise @ jac.T
    j = int(np.argmax(pr))
    wrong = noise[j, j] + pr[j]**2 * np.sum(noise)
    return dict(null_quadratic_form=cw.sum(), min_eigenvalue=np.linalg.eigvalsh(cw)[0],
                      max_eigenvalue=np.linalg.eigvalsh(cw)[-1], hybrid_index=j, hybrid_weight=pr[j], correct_variance=cw[j, j],
                      variance_if_t_pretended_independent=wrong, omitted_covariance_term=wrong - cw[j, j])


def _opposite_bond(ring, c):
    expected = np.repeat(lab09.LINES_MHZ, [1, 2, 2, 1])
    half_c = c.copy()
    half_c[3] /= 2
    return dict(full_max_abs_vs_lines=_max(np.linalg.eigvalsh(ring) - expected),
                half_max_abs_vs_lines=_max(np.linalg.eigvalsh(lab09.circulant(half_c)) - expected),
                opposite_element_mhz=c[3], operator_prefactor_mhz=c[3] / 2)


def _step_scan(ring, nu):
    target = lab09.LINES_MHZ[1]
    step = []
    for name, t, g, hs in (("detuned", nu, 1., (.2, .05, .01, .001)), ("resonant_lower", target, .2, (.2, .05, .01, .001)),
                        ("resonant_shoulder", target + .12, .2, (.15,))):
        for h in hs:
            central, rich, pv, _ = _stencil(lambda x: lab09.hamiltonian(ring, x, g), t, h)
            step.append(dict(case=name, h_mhz=h, center_mhz=t, central_max_abs=_max(central - pv), richardson_max_abs=_max(rich - pv)))
    return step


def _calibration_control(p):
    sweep = make_sweep("hf_both_detuned", "known-answer")
    fit = recover(sweep)
    ci = fit["intervals"]
    return dict(confidence=fit["confidence"], step=fit["step"], candidates=sweep["steps"], max_abs=_max(fit["weights"] - p),
                       truth_inside_all=bool(np.all((ci[:, 0] <= p) & (p <= ci[:, 1]))),
                       port_dominant_index=int(np.argmax(p)), dominant_interval=ci[np.argmax(p)], dominant_weight=max(p),
                       trace_calibration_difference=fit["trace_calibration_difference"])


def campaign():
    ring, c = ring_matrix()
    H = lambda nu: lab09.hamiltonian(ring, nu, 1.)
    nu = 6600.
    _, s, p, overlap = _stencil(H, nu, .001)
    pure = dict(nu_p_mhz=nu, g_mhz=1., max_abs_richardson_minus_vector=_max(s - p),
                max_abs_trace_minus_vector=_max(s / s.sum() - p), slope_sum=s.sum(),
                min_assignment_overlap=overlap, port_weights_are_dressed=True)
    damping = [_open(ring, gamma) for gamma in (0., .05, .2, .4, .6, 1.)]
    report = dict(
        pure_6plus1=pure, two_mode=_two_mode(), crossing=_crossing(ring),
        impurity=_impurity_controls(H, nu), nonlinear_calibration=_nonlinear_control(H),
        omission=_omission_control(s, p), covariance=_trace_covariance(ring),
        open_system=damping[-1], damping_scan=damping, opposite_bond=_opposite_bond(ring, c),
        resolvent_cross_check=_resolvent(ring, nu, 1.), step_bias=_step_scan(ring, nu),
        degeneracy_basis=_degenerate_basis(ring), calibrated_recovery=_calibration_control(p),
    )
    return lab09.jsonable(report)


def assert_spectral(report=None):
    r = report if report is not None else campaign()
    def require(condition, message):
        if not condition:
            raise AssertionError(message)
    pure = r["pure_6plus1"]
    require(pure["max_abs_trace_minus_vector"] < 3e-8 and pure["max_abs_richardson_minus_vector"] < 3e-8
            and abs(pure["slope_sum"] - 1) < 3e-8, "pure 6+1 weights")
    pair = r["two_mode"]
    require(pair["max_abs_numerical"] < 1e-9 and min(pair["large_detuning_weights"]) < .001, "two-level limits")
    cross = r["crossing"]
    require(cross["max_double_root_residual_mhz"] < 1e-8 and abs(cross["offset_mhz"]) > .1,
            "center must be a double eigenvalue at the dressed crossing")
    require(abs(cross["slopes_at_crossing"][0]) < 1e-10 and .9 < cross["slopes_at_crossing"][1] < 1,
            "compressed projector at crossing")
    for row in cross["exact_center_scan"]:
        require(row["left_slot"] != row["right_slot"] and .4 < row["sorted_slope_in_dark_slot"] < .6,
                "frequency sorting did not exchange branches at the dark crossing")
        require(abs(row["tracked_dark_slope"]) < 1e-8 and row["min_dark_overlap"] > .999999
                and row["tracked_dark_port_weight"] < 1e-15, "a different dark branch was tracked")
    np.testing.assert_allclose([row["sorted_slope_in_dark_slot"] for row in cross["logged_bare_center_scan"]],
                               [.7155076022, .5690573925, .5203518294], atol=1e-7, rtol=0)
    for key, floor in (("g_derivative", .01), ("off_diagonal_ring", .3), ("diagonal_ring_site", .18)):
        item = r["impurity"][key]
        require(item["max_abs_trace_minus_vector"] > floor
                and abs(item["slope_sum"] - 1 - item["trace_derivative"]) < 1e-7, "impurity " + key)
    shape = r["nonlinear_calibration"]
    require(max(shape["local_calibrated_max_abs"], shape["trace_max_abs"]) < 1e-7
            and shape["wide_secant_max_abs"] > .07, "nonlinear tuning")
    require(r["omission"]["omit_dark_max_abs"] < 1e-7 and r["omission"]["omit_largest_max_abs"] > .7,
            "incomplete trace")
    cov = r["covariance"]
    require(abs(cov["null_quadratic_form"]) < 1e-19 and cov["min_eigenvalue"] > -1e-19 and
            0 < cov["correct_variance"] < cov["variance_if_t_pretended_independent"], "ratio covariance")
    basis = r["degeneracy_basis"]
    np.testing.assert_allclose(basis["rotated_contact_weights"], [1 / 6] * 2, atol=1e-10)
    require(abs(basis["rotated_sum"] - basis["eigh_sum"]) < 1e-12, "degenerate subspace")
    bond = r["opposite_bond"]
    require(bond["full_max_abs_vs_lines"] < 1e-8 and bond["half_max_abs_vs_lines"] > 2.6, "opposite bond")
    resolvent = r["resolvent_cross_check"]
    require(resolvent["compared"] == 5 and resolvent["skipped_bare_eigenvalues"] == 2
            and resolvent["max_abs"] < 1e-9, "resolvent residues")
    shoulder = next(row for row in r["step_bias"] if row["case"] == "resonant_shoulder")
    require(.009 < shoulder["richardson_max_abs"] < shoulder["central_max_abs"] < .03, "finite step at shoulder")
    scan = r["damping_scan"]
    require([row["gamma_mhz"] for row in scan] == [0, .05, .2, .4, .6, 1], "damping scan settings")
    for row in scan:
        require(row["richardson_error"] < 1e-7 and abs(row["sum_real"] - 1) < 1e-10
                and abs(row["sum_imag"]) < 1e-10, "biorthogonal sensitivity")
    require(scan[0]["max_abs_bare_probability_minus_real_derivative"] < 1e-9 and scan[2]["max_abs_imag"] > .2
            and scan[-1]["min_real"] < -.06 and scan[-1]["max_real"] > 1.06
            and scan[-1]["max_abs_bare_probability_minus_real_derivative"] > .12, "loss sensitivity limits")
    fit = r["calibrated_recovery"]
    require(fit["truth_inside_all"] and fit["max_abs"] < 1e-7 and fit["step"] in fit["candidates"],
            "combined calibration or interval")
    return True
