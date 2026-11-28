"""Port weights from branch-labelled frequency samples. No model vectors enter this fit."""
from itertools import product
from statistics import NormalDist

import numpy as np


class SweepError(ValueError):
    def __init__(self, gate, message):
        super().__init__(message)
        self.gate = gate


def design(offsets, steps, channels, sample_covariance, fifth_bounds, denominator, z):
    """Choose a stencil before reading line values. Noise and truncation are in slope units."""
    offsets = np.asarray(offsets, float)
    cov = np.asarray(sample_covariance, float)
    bounds = np.asarray(fifth_bounds, float)
    size = offsets.size * channels
    if (offsets.ndim != 1 or not np.all(np.isfinite(offsets))
            or np.unique(offsets).size != offsets.size or bounds.shape != (channels,)
            or not np.all(np.isfinite(bounds)) or np.any(bounds < 0)):
        raise SweepError("STENCIL_DESIGN", "invalid offsets or fifth derivative bounds")
    if cov.shape != (size, size) or size == 0 or not np.all(np.isfinite(cov)):
        raise SweepError("SAMPLE_COVARIANCE", "supply the joint point-major frequency covariance")
    tol = 64 * size * np.finfo(float).eps * np.max(abs(cov))
    if np.max(abs(cov - cov.T)) > tol or np.linalg.eigvalsh(cov)[0] < -tol:
        raise SweepError("SAMPLE_COVARIANCE", "joint covariance must be symmetric positive semidefinite")

    choices = []
    for h in steps:
        if not np.isfinite(h) or h <= 0:
            raise SweepError("STENCIL_DESIGN", "steps must be finite and positive")
        weights = np.zeros(offsets.size)
        for offset, coefficient in zip((-h, -h / 2, h / 2, h), (1, -8, 8, -1)):
            hit = np.flatnonzero(np.isclose(offsets, offset, rtol=1e-12, atol=0))
            if hit.size != 1:
                raise SweepError("STENCIL_DESIGN", "Richardson step lacks four distinct samples")
            weights[hit[0]] = coefficient / (6 * h)
        transform = np.kron(weights[None, :], np.eye(channels))
        slope_cov = transform @ cov @ transform.T
        # Taylor remainder using absolute stencil coefficients on the whole interval.
        bias = bounds * h**4 / 288
        # For w in [0,1], the maximum variance of s_j - w*d is at an endpoint.
        diff = np.eye(channels)[:7] - denominator
        noise = np.sqrt(np.maximum.reduce([np.zeros(7), np.diag(slope_cov)[:7],
                                           np.diag(diff @ slope_cov @ diff.T)]))
        score = float(np.max(z * noise + bias[:7] + abs(denominator) @ bias))
        choices.append((score, h, weights, slope_cov, bias))
    if not choices:
        raise SweepError("STENCIL_DESIGN", "at least one candidate step is required")
    return min(choices, key=lambda row: (row[0], row[1]))


def ratio(slopes, cov, bias, denominator, z):
    """Fieller pointwise interval, enveloped over independent bounds on truncation bias."""
    n = slopes[:7]
    d = denominator @ slopes
    vd = max(0., float(denominator @ cov @ denominator))
    bd = abs(denominator) @ bias
    if abs(d) <= bd + z * np.sqrt(vd):
        raise SweepError("UNRESOLVED_CALIBRATION", "the local tuning slope is consistent with zero")
    vn = np.maximum(0., np.diag(cov)[:7])
    cnd = cov[:7] @ denominator
    w = n / d
    jac = (np.eye(len(slopes))[:7] - w[:, None] * denominator) / d
    wcov = jac @ cov @ jac.T
    lower, upper = np.full(7, np.inf), np.full(7, -np.inf)
    # Solve the Fieller quadratic around nc/dc to avoid cancellation in the discriminant.
    for sn, sd in product((-1, 1), repeat=2):
        nc, dc = n + sn * bias[:7], d + sd * bd
        center = nc / dc
        a = dc**2 - z * z * vd
        b = z * z * (cnd - center * vd)
        v = np.maximum(0., vn - 2 * center * cnd + center**2 * vd)
        rad = np.sqrt(b * b + a * z * z * v)
        lower = np.minimum(lower, center + (-b - rad) / a)
        upper = np.maximum(upper, center + (-b + rad) / a)
    return dict(weights=w, covariance=wcov, intervals=np.column_stack([lower, upper]),
                denominator=d, denominator_sigma=np.sqrt(vd), denominator_bias_bound=bd)


def recover(sweep, confidence=0.95):
    """Columns follow the central record's branch IDs, with independent calibration last."""
    if not 0 < confidence < 1:
        raise ValueError("confidence must lie in (0,1)")
    z = NormalDist().inv_cdf((1 + confidence) / 2)
    mode = sweep["normalization"]
    if mode not in ("trace", "calibrated", "both"):
        raise SweepError("CALIBRATED_READOUT", "unknown spectral normalization")
    channels = 7 if mode == "trace" else 8
    samples = np.asarray(sweep["samples_mhz"], float)
    if samples.shape != (len(sweep["offsets"]), channels) or not np.all(np.isfinite(samples)):
        raise SweepError("SPECTRUM_COMPLETE", "each setting needs seven labelled lines and the declared calibration")
    trace = np.r_[np.ones(7), np.zeros(channels - 7)]
    den = trace if mode == "trace" else np.eye(channels)[-1]
    score, h, weights, cov, bias = design(
        sweep["offsets"], sweep["steps"], channels, sweep["sample_covariance_mhz2"],
        sweep["fifth_derivative_bounds"], den, z)
    # Subtract the common per-line frequency offset before differencing GHz-scale carriers.
    slopes = weights @ (samples - samples[0])
    estimated = ratio(slopes, cov, bias, den, z)
    result = dict(**estimated, step=h, slopes=slopes, slope_covariance=cov,
                  slope_bias_bounds=bias, confidence=confidence, design_score=score)
    if mode == "both":
        result["trace_estimate"] = ratio(slopes, cov, bias, trace, z)
        contrast = trace - den
        result["trace_calibration_difference"] = contrast @ slopes
        result["trace_calibration_sigma"] = np.sqrt(max(0., contrast @ cov @ contrast))
        result["trace_calibration_bias_bound"] = abs(contrast) @ bias
    return result


def from_records(kit):
    """Read spectral samples, with an explicit declaration of how the branches were matched."""
    port = kit["port_on"]
    sweep = port.get("spectral_sweep")
    if not isinstance(sweep, dict):
        raise SweepError("SPECTRUM_COMPLETE", "missing spectral sweep")
    if sweep.get("closed_hermitian") is not True:
        raise SweepError("CLOSED_HERMITIAN", "probability readout requires a closed Hermitian system")
    if sweep.get("pure_rank_one") is not True:
        raise SweepError("PURE_RANK_ONE_CONTROL", "tuning must perturb only the port diagonal")
    ids = port.get("branch_ids")
    if (not isinstance(ids, list) or len(ids) != 7
            or not all(type(label) in (str, int) for label in ids) or len(set(ids)) != 7
            or sweep.get("branch_ids") != ids):
        raise SweepError("BRANCH_TRACKING", "sweep columns must match the seven central branch labels")
    tracking = sweep.get("tracking")
    if not ((tracking == "synthetic_overlap" and kit.get("synthetic") is True)
            or (tracking == "measured_labels" and sweep.get("tracking_source_id"))):
        raise SweepError("BRANCH_TRACKING", "need independently identifiable branches across settings")
    mode = sweep.get("normalization")
    if mode in ("calibrated", "both") and (
            not sweep.get("calibration_source_id")
            or sweep["calibration_source_id"] == port.get("source_id")
            or sweep.get("calibration_origin") != "independent_record"):
        raise SweepError("FALSE_INDEPENDENCE", "independent local tuning calibration needs a distinct record")
    if mode in ("trace", "both") and sweep.get("sum_claimed_independent"):
        raise SweepError("TRACE_SUM_NOT_INDEPENDENT", "trace normalization enforces the sum algebraically")
    try:
        fit = recover(sweep)
        center = np.flatnonzero(np.asarray(sweep["offsets"]) == 0)
        if len(center) != 1:
            raise SweepError("SWEEP_CENTER", "supply the central record at offset zero")
        samples = np.asarray(sweep["samples_mhz"], float)
        observation = samples[center[0]]
        if not np.allclose(observation[:7], port["frequencies_mhz"], rtol=0, atol=1e-8):
            raise SweepError("SWEEP_CENTER", "central branch frequencies disagree with the port-on record")
        z = float(kit.get("tolerances", {}).get("z_max", 5.))
        off = kit["port_off"]
        if abs(off["nu_p_mhz"] - kit["locked"]["nu_p_mhz"]) > z * off["sigma_nu_p_mhz"]:
            raise SweepError("SWEEP_CENTER", "port-off operating point disagrees with the lock")
        if mode in ("calibrated", "both"):
            # Unknown cross-record covariance: the sum of standard deviations is conservative.
            pos = int(center[0]) * samples.shape[1] + 7
            sigma = np.sqrt(max(0., sweep["sample_covariance_mhz2"][pos][pos])) + off["sigma_nu_p_mhz"]
            if abs(observation[-1] - off["nu_p_mhz"]) > z * sigma:
                raise SweepError("SWEEP_CENTER", "independent calibration is centered at a different tuning")
        return fit
    except SweepError:
        raise
    except (KeyError, ValueError, TypeError, np.linalg.LinAlgError) as exc:
        raise SweepError("STENCIL_DESIGN", str(exc)) from exc


def slope_scores(fit, mode, prediction, order, z_max):
    """Test n_j - w_j*d directly, including covariance of n and d and bounded bias."""
    s = fit["slopes"]
    cov = fit["slope_covariance"]
    bias = fit["slope_bias_bounds"]
    n = np.eye(len(s))[:7][order]
    den = n.sum(axis=0) if mode == "trace" else np.eye(len(s))[-1]
    def scores(coeff):
        residual = np.maximum(0., abs(coeff @ s) - abs(coeff) @ bias)
        sd = np.sqrt(np.maximum(0., np.diag(coeff @ cov @ coeff.T)))
        # Roundoff allowance also covers exactly deterministic linear combinations.
        floor = 32 * np.finfo(float).eps * max(1., np.max(abs(s)))
        return residual / np.maximum(sd, floor)
    if abs(den @ s) <= abs(den) @ bias + z_max * np.sqrt(max(0., den @ cov @ den)):
        raise SweepError("UNRESOLVED_CALIBRATION", "denominator is unresolved at the acceptance threshold")
    individual = scores(n - prediction[:, None] * den)
    sum_score = None if mode == "trace" else scores((n.sum(axis=0) - den)[None, :])[0]
    return max(individual), sum_score
