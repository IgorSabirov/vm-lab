"""P3: frozen plaquette strata and a chain-preserving block bootstrap.

The estimand and masks are those of run_design/EXPERIMENT.md.  Measurement and
single-table cumulants are reused from that directory.  Autocorrelation times
are in SAVED CONFIGURATIONS, never seconds.  The implemented conservative
initial-positive-pair estimator is explicitly distinct from a claim to have
measured all metastable modes.  Relevant background: U. Wolff,
https://arxiv.org/abs/hep-lat/0306017 (especially the finite-record limitation).

No cut, chain length, mask or block length is selected using the heldout D4.
The bootstrap reselects entire chronological blocks within each chain and
only then applies the immutable calibration cuts.  Every marginal of the
connected estimator comes from the same pooled four-dimensional table.
"""
from __future__ import annotations

import hashlib
import importlib.util
import itertools
import json
import math
from pathlib import Path

import numpy as np


def _load_reference(name):
    path = Path(__file__).resolve().parents[3] / "run_design" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_r135_reference_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_cumulants = _load_reference("cumulants")
count_windows = _load_reference("measure_field").count_windows
estimate = _cumulants.estimate
PARTITIONS = tuple(_cumulants.partitions(tuple(range(4))))
PATTERNS = tuple(p for a in range(3) for p in
                 ((a, (a + 1) % 3, a, (a + 1) % 3),
                  ((a + 1) % 3, a, (a + 1) % 3, a)))
SUBSETS = tuple(tuple(i for i in range(4) if mask & (1 << i))
                for mask in range(1, 16))
_SUBSET_INDEX = {part: index for index, part in enumerate(SUBSETS)}
_WORDS = np.array(tuple(itertools.product(range(3), repeat=4)))
_SELECTORS = np.array([
    [np.all(_WORDS[:, subset] == np.array(pattern)[list(subset)], axis=1)
     for subset in SUBSETS] for pattern in PATTERNS], dtype=float)


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def autocorrelation(values, window_factor=5.0):
    """FFT ACF, positive-pair truncation, explicit finite-record diagnostics.

    Returns tau=.5 for uncorrelated data in the convention ESS=N/(2*tau).
    Constant/too short streams cannot establish mixing and return tau=None.
    'stable' tests length and halves; it does not prove stationarity.
    """
    x = np.asarray(values, dtype=float)
    if x.ndim != 1 or not np.isfinite(x).all():
        raise ValueError("ACF requires a finite one-dimensional stream")
    if len(x) < 8:
        return dict(tau_int=None, ess=0.0, stable=False, reason="SHORT_STREAM", n=len(x))
    x = x - x.mean()
    variance = float(np.mean(x * x))
    if variance <= 0:
        return dict(tau_int=None, ess=0.0, stable=False, reason="CONSTANT_STREAM", n=len(x))

    def compute(z):
        n = len(z)
        z = z - z.mean()
        norm = float(np.dot(z, z) / n)
        if norm == 0:
            return None, 0, np.ones(1)
        fft = np.fft.rfft(z, n=1 << (2 * n - 1).bit_length())
        covariance = np.fft.irfft(fft * np.conjugate(fft))[:n] / np.arange(n, 0, -1)
        rho = covariance / norm
        tau = 0.5
        last = 0
        previous_pair = math.inf
        for k in range(1, min(n // 2, n - 1), 2):
            pair = float(rho[k] + rho[k + 1])
            if pair <= 0:
                break
            # Initial monotone positive sequence reduces noisy tails.
            pair = min(pair, previous_pair)
            previous_pair = pair
            tau += pair
            last = k + 1
            if last >= window_factor * tau:
                break
        return max(0.5, tau), last, rho

    tau, window, rho = compute(x)
    halves = [compute(part)[0] for part in np.array_split(x, 2)]
    half_stable = all(t is not None and abs(t - tau) <= max(tau, t) * 0.5
                      for t in halves)
    stable = len(x) >= 50 * tau and half_stable
    return dict(tau_int=float(tau), ess=float(len(x) / (2 * tau)), n=len(x),
                window=int(window), tau_error_estimate=float(tau * np.sqrt(4 * (window + 1) / len(x))),
                half_estimates=halves, stable=bool(stable),
                reason="FINITE_RECORD_CHECKS_PASSED" if stable else "SHORT_OR_NONSTATIONARY",
                acf=rho[:max(2, window + 1)].tolist())


def connected_many(counts):
    """Vectorized counterpart of the independent, existing single-table code."""
    n = np.asarray(counts)
    if n.ndim != 2 or n.shape[1] != 81 or n.dtype.kind not in "iu" or np.any(n < 0):
        raise ValueError("Expected a batch of 81 nonnegative integer counts")
    total = n.sum(axis=1)
    if np.any(total <= 0):
        raise ValueError("Empty stratum")
    moments = np.tensordot(n / total[:, None], _SELECTORS, axes=(1, 2))
    result = np.zeros(len(n), dtype=float)
    for blocks in PARTITIONS:
        ids = [_SUBSET_INDEX[tuple(sorted(block))] for block in blocks]
        coefficient = (-1) ** (len(blocks) - 1) * math.factorial(len(blocks) - 1)
        result += coefficient * np.prod(moments[:, :, ids], axis=2).sum(axis=1)
    return result


def _measurement(row, cut):
    matches = [entry for entry in row["counts_by_cut"]
               if abs(float(entry["cut_rad"]) - float(cut)) <= 1e-14]
    if len(matches) != 1:
        raise ValueError(f"Missing or duplicate mask {cut} for {row['config_id']}")
    return matches[0]


def pooled_counts(row, cut=0.0):
    entry = _measurement(row, cut)
    counts = np.zeros(81, dtype=np.int64)
    for axis in "xyz":
        data = entry["axes"][axis]
        current = np.asarray(data["counts"])
        if current.shape != (81,) or current.dtype.kind not in "iu" or np.any(current < 0):
            raise ValueError("Invalid 81-cell measurement")
        if int(current.sum()) != data["accepted"] or not 0 <= data["accepted"] <= data["total"]:
            raise ValueError("Invalid coverage")
        if data["total"] != int(np.prod(entry["shape"])):
            raise ValueError("Coverage total disagrees with periodic spatial volume")
        forward = sum(current[np.ravel_multi_index(p, (3,) * 4)] for p in PATTERNS[::2])
        backward = sum(current[np.ravel_multi_index(p, (3,) * 4)] for p in PATTERNS[1::2])
        if data["M_plus"] != forward + backward or data["M_minus"] != forward - backward:
            raise ValueError("Directional summary disagrees with the 81-cell table")
        counts += current.astype(np.int64)
    return counts


def validate_rows(rows):
    """Require distinct units of sampling and one fixed lattice per analysis."""
    if not rows:
        raise ValueError("No measurements")
    seen, chain_meta, last, cadence = set(), {}, {}, {}
    grid, window_settings = None, None
    for row in rows:
        if not isinstance(row.get("config_id"), str) or not row["config_id"]:
            raise ValueError("Missing configuration identity")
        if row["config_id"] in seen:
            raise ValueError("Duplicate configuration identity")
        seen.add(row["config_id"])
        if row.get("role") not in ("calibration", "heldout"):
            raise ValueError("Explicit calibration/heldout split required")
        chain = row["chain_id"]
        if not isinstance(chain, str) or not chain:
            raise ValueError("Missing independent chain identity")
        geometry = tuple(row["geometry"])
        meta = (row["role"], row.get("seed"), row.get("start"), geometry, row["beta"])
        if chain in chain_meta and chain_meta[chain] != meta:
            raise ValueError("One chain cannot change role, start, geometry or beta")
        chain_meta[chain] = meta
        current_grid = (geometry, row["beta"], row["grid_id"])
        if grid is not None and grid != current_grid:
            raise ValueError("Analyze different lattices in separate P3 units")
        grid = current_grid
        for scalar in ("plaquette", "polyakov_abs"):
            if not np.isfinite(row[scalar]):
                raise ValueError("Nonfinite gauge observable")
        if not isinstance(row["sweep"], int) or row["sweep"] < 0:
            raise ValueError("Invalid sweep coordinate")
        if chain in last:
            step = row["sweep"] - last[chain]
            if step <= 0 or (chain in cadence and step != cadence[chain]):
                raise ValueError("Measurements must be chronological and equally spaced per chain")
            cadence[chain] = step
        last[chain] = row["sweep"]
        cuts = []
        strides = []
        for item in row["counts_by_cut"]:
            cut = float(item["cut_rad"])
            if not 0 <= cut < np.pi / 3 or cut in cuts:
                raise ValueError("Invalid or duplicate sector mask")
            cuts.append(cut)
            stride = item["stride"]
            if not isinstance(stride, int) or stride < 1 or any(n % stride or n // stride < 4 for n in geometry[1:]):
                raise ValueError("Invalid measurement stride")
            strides.append(stride)
            if tuple(item["shape"]) != geometry[1:]:
                raise ValueError("Window geometry disagrees with source links")
            pooled_counts(row, cut)
        if not any(abs(cut) <= 1e-14 for cut in cuts):
            raise ValueError("Primary mask is absent")
        current_settings = (tuple(sorted(cuts)), tuple(strides))
        if len(set(strides)) != 1 or (window_settings is not None and current_settings != window_settings):
            raise ValueError("Mixed measurement masks or spatial strides")
        window_settings = current_settings
    seeds = [meta[1] for meta in chain_meta.values() if meta[1] is not None]
    if len(set(seeds)) != len(seeds):
        raise ValueError("Independent chains cannot share the same seed")
    return chain_meta


def _groups(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault(row["chain_id"], []).append(row)
    return grouped


def _streams(rows):
    counts = np.array([pooled_counts(row) for row in rows])
    pattern_codes = [np.ravel_multi_index(pattern, (3, 3, 3, 3)) for pattern in PATTERNS]
    den = counts.sum(axis=1)
    if np.any(den == 0):
        mplus = None
    else:
        mplus = counts[:, pattern_codes].sum(axis=1) / den
    return {"plaquette": [row["plaquette"] for row in rows],
            "polyakov_abs": [row["polyakov_abs"] for row in rows],
            "M_plus_density": mplus}


def _start_agreement(grouped):
    """Compare second halves of independently hot/cold initialized chains.

    The uncertainty is the larger of the between-chain and within-chain ACF
    estimates.  A missing start class or fewer than two replicas per class
    cannot certify agreement.  This is a diagnostic, not a bimodality test.
    """
    by_start = {start: {chain: values[len(values) // 2:]
                        for chain, values in grouped.items() if values[0].get("start") == start}
                for start in ("cold", "hot")}
    if any(len(chains) < 2 for chains in by_start.values()):
        return dict(status="UNRESOLVED", reason="NEED_TWO_CHAINS_PER_START", observables={})
    output = {}
    for observable in ("plaquette", "polyakov_abs", "M_plus_density"):
        summaries = {}
        for start, chains in by_start.items():
            means, within_variances = [], []
            for chain, values in chains.items():
                stream = _streams(values)[observable]
                if stream is None or len(stream) < 8:
                    return dict(status="UNRESOLVED", reason="INSUFFICIENT_START_HISTORY", observables=output)
                estimate_acf = autocorrelation(stream)
                tau = estimate_acf["tau_int"]
                if tau is None:
                    return dict(status="UNRESOLVED", reason="CONSTANT_START_OBSERVABLE", observables=output)
                means.append(float(np.mean(stream)))
                within_variances.append(float(np.var(stream, ddof=1) * 2 * tau / len(stream)))
            variance = max(float(np.var(means, ddof=1) / len(means)),
                           sum(within_variances) / len(means) ** 2)
            summaries[start] = dict(mean=float(np.mean(means)), variance=variance, chains=len(means))
        difference = summaries["hot"]["mean"] - summaries["cold"]["mean"]
        uncertainty = math.sqrt(summaries["hot"]["variance"] + summaries["cold"]["variance"])
        z = abs(difference) / uncertainty if uncertainty > 0 else None
        output[observable] = dict(start_summaries=summaries, difference=difference,
                                  standard_error=uncertainty, z=z, compatible=z is not None and z <= 3)
    return dict(status="COMPATIBLE" if all(x["compatible"] for x in output.values()) else "INCOMPATIBLE",
                observables=output)


def freeze_calibration(rows, source_sha256=None):
    """Use equal counts per independent calibration chain, no heldout input."""
    validate_rows(rows)
    if any(row["role"] != "calibration" for row in rows):
        raise ValueError("Heldout measurements must not determine cuts or pilot tau")
    grouped = _groups(rows)
    n = min(map(len, grouped.values()))
    if n < 8:
        raise ValueError("At least eight saved configurations per calibration chain required")
    equal = {chain: values[:n] for chain, values in grouped.items()}
    plaques = np.array([row["plaquette"] for values in equal.values() for row in values])
    low, high = np.quantile(plaques, [0.25, 0.75], method="linear")
    if not low < high:
        raise ValueError("Coincident plaquette quantiles do not define two strata")
    mixing = {}
    for chain, values in equal.items():
        mixing[chain] = {name: autocorrelation(stream) if stream is not None else
                         dict(tau_int=None, ess=0.0, stable=False, reason="ZERO_COVERAGE")
                         for name, stream in _streams(values).items()}
    taus = [entry["tau_int"] for values in mixing.values() for entry in values.values()
            if entry["tau_int"] is not None]
    tau = max(taus) if taus else None
    first = rows[0]
    start_agreement = _start_agreement(equal)
    burn_checks = {}
    for chain, values in equal.items():
        cadence = values[1]["sweep"] - values[0]["sweep"]
        required = None if tau is None else math.ceil(20 * tau * cadence)
        burn_checks[chain] = dict(actual_sweeps=values[0].get("burn_sweeps", 0),
                                  required_sweeps=required,
                                  sufficient=required is not None and values[0].get("burn_sweeps", 0) >= required)
    data = dict(schema="R135-P3-calibration-v1", grid_id=first["grid_id"],
                geometry=first["geometry"], beta=first["beta"],
                stride=first["counts_by_cut"][0]["stride"],
                cuts_rad=sorted(float(item["cut_rad"]) for item in first["counts_by_cut"]),
                calibration_chain_ids=sorted(grouped),
                calibration_seeds=[grouped[c][0].get("seed") for c in sorted(grouped)],
                n_per_chain=n, quantile_method="linear_equal_chain_weight",
                lower_cut=float(low), upper_cut=float(high),
                stratum_convention="plaquette<=lower; plaquette>=upper",
                tau_unit="saved_configuration", tau_max=tau,
                block_length=None if tau is None else max(1, math.ceil(10 * tau)),
                heldout_min_saves=None if tau is None else math.ceil(200 * tau),
                stable=(all(entry["stable"] for values in mixing.values() for entry in values.values())
                        and start_agreement["status"] == "COMPATIBLE"
                        and all(check["sufficient"] for check in burn_checks.values())),
                start_agreement=start_agreement,
                burn_checks=burn_checks,
                mixing=mixing,
                source_sha256=source_sha256 or _hash(rows),
                selected_config_ids=[row["config_id"] for values in equal.values() for row in values],
                observable_selection="plaquette,abs(mean(ell)),M_plus_density")
    data["lock_sha256"] = _hash(data)
    return data


def verify_calibration(calibration):
    data = dict(calibration)
    wanted = data.pop("lock_sha256", None)
    if wanted != _hash(data) or data.get("schema") != "R135-P3-calibration-v1":
        raise ValueError("Calibration lock was altered or has an unsupported schema")
    if not data["lower_cut"] < data["upper_cut"]:
        raise ValueError("Invalid frozen strata")


def _marginal_differences(lo, hi):
    p = lo.reshape((3,) * 4) / lo.sum()
    q = hi.reshape((3,) * 4) / hi.sum()
    answer = {}
    for order in (1, 2, 3):
        for keep in itertools.combinations(range(4), order):
            axes = tuple(i for i in range(4) if i not in keep)
            a, b = p.sum(axis=axes), q.sum(axis=axes)
            answer["".join(str(i + 1) for i in keep)] = dict(
                max_abs_difference=float(np.max(np.abs(b - a))),
                l1_difference=float(np.sum(np.abs(b - a))),
                low=a.ravel().tolist(), high=b.ravel().tolist())
    return answer


def _classify(interval, band):
    if interval is None:
        return "INCONCLUSIVE"
    lo, hi = interval
    if lo > band:
        return "POSITIVE_EFFECT"
    if hi < -band:
        return "NEGATIVE_EFFECT"
    if -band <= lo and hi <= band:
        return "PRACTICAL_ZERO"
    return "INCONCLUSIVE"


def block_bootstrap(rows, calibration, cut, block_length, draws=4000, seed=13590):
    """Bootstrap complete, nonoverlapping chronological blocks within chains.

    The last short block is kept.  Sampling it with the same probability as
    full blocks preserves the empirical record rather than silently trimming
    a phase at the end.  Each draw keeps the same number of blocks per chain;
    its exact count of configurations may vary and is reported by construction.
    """
    verify_calibration(calibration)
    if isinstance(block_length, bool) or int(block_length) != block_length or block_length < 1:
        raise ValueError("Invalid block length")
    if isinstance(draws, bool) or int(draws) != draws or draws < 20:
        raise ValueError("At least 20 bootstrap draws required; production protocol uses 4000")
    lower, upper = calibration["lower_cut"], calibration["upper_cut"]
    grouped = _groups(rows)
    rng = np.random.Generator(np.random.PCG64(seed))
    sampled_counts = np.zeros((draws, 2, 81), dtype=np.int64)
    actual_counts = np.zeros((2, 81), dtype=np.int64)
    occupied = np.zeros(2, dtype=int)
    n_config = np.zeros(2, dtype=int)
    per_chain, block_manifest = {}, {}
    for chain, values in grouped.items():
        blocks = []
        for begin in range(0, len(values), block_length):
            block = np.zeros((2, 81), dtype=np.int64)
            occupants = np.zeros(2, dtype=int)
            for row in values[begin:begin + block_length]:
                stratum = 0 if row["plaquette"] <= lower else 1 if row["plaquette"] >= upper else None
                if stratum is not None:
                    block[stratum] += pooled_counts(row, cut)
                    occupants[stratum] += 1
            blocks.append(block)
            occupied += occupants > 0
            n_config += occupants
        array = np.array(blocks)
        actual_counts += array.sum(axis=0)
        indices = rng.integers(len(array), size=(draws, len(array)))
        # Chunking avoids draws*nblocks*162 integer arrays on long histories.
        for begin in range(0, draws, 64):
            sampled_counts[begin:begin + 64] += array[indices[begin:begin + 64]].sum(axis=1)
        pooled = array.sum(axis=0)
        per_chain[chain] = None if np.any(pooled.sum(axis=1) == 0) else float(
            estimate(pooled[1])["connected_even"] - estimate(pooled[0])["connected_even"])
        block_manifest[chain] = dict(blocks=len(blocks),
                                    last_block_size=len(values) - (len(blocks) - 1) * block_length,
                                    saved_configurations=len(values))
    valid = np.all(sampled_counts.sum(axis=2) > 0, axis=1)
    empty_fraction = float(1 - valid.mean())
    values = np.array([])
    raw_even_samples, raw_odd_samples = np.array([]), np.array([])
    if np.any(valid):
        values = connected_many(sampled_counts[valid, 1]) - connected_many(sampled_counts[valid, 0])
        codes = [np.ravel_multi_index(p, (3,) * 4) for p in PATTERNS]
        probabilities = sampled_counts[valid] / sampled_counts[valid].sum(axis=2)[..., None]
        pattern_p = probabilities[:, :, codes]
        raw_even_samples = (pattern_p[:, 1] - pattern_p[:, 0]).sum(axis=1)
        raw_odd_samples = ((pattern_p[:, 1] - pattern_p[:, 0]) * np.array([1, -1] * 3)).sum(axis=1)
    interval = np.quantile(values, [0.025, 0.975]).tolist() if len(values) else None
    if np.any(actual_counts.sum(axis=1) == 0):
        point, low_est, high_est, marginals = None, None, None, None
    else:
        low_est, high_est = map(estimate, actual_counts)
        point = float(high_est["connected_even"] - low_est["connected_even"])
        marginals = _marginal_differences(actual_counts[0], actual_counts[1])
    return dict(D4=point, interval95=interval, low=low_est, high=high_est,
                pooled_counts=actual_counts.tolist(), marginal_differences=marginals,
                empty_draw_fraction=empty_fraction, valid_draws=int(valid.sum()), draws=draws,
                bootstrap_seed=seed, block_length=block_length,
                occupied_blocks=occupied.tolist(), configurations_in_strata=n_config.tolist(),
                chain_estimates=per_chain, blocks=block_manifest,
                raw_even_difference_interval95=(np.quantile(raw_even_samples, [.025, .975]).tolist()
                                                if len(raw_even_samples) else None),
                raw_odd_difference_interval95=(np.quantile(raw_odd_samples, [.025, .975]).tolist()
                                               if len(raw_odd_samples) else None),
                bootstrap_values=values.tolist())


def analyze_chains(rows, calibration, *, cuts=(0.0, np.pi / 30), draws=4000,
                   seed=13590, equivalence_band=1e-3, min_ess=100, min_blocks=20,
                   independent_plaquette=None):
    """Analyze one geometry without using the result to tune the protocol."""
    validate_rows(rows)
    verify_calibration(calibration)
    if any(row["role"] != "heldout" for row in rows):
        raise ValueError("Analyze only heldout measurements; calibration remains separately frozen")
    grouped = _groups(rows)
    if set(grouped) & set(calibration["calibration_chain_ids"]):
        raise ValueError("Calibration and heldout chains overlap")
    seeds = {row.get("seed") for row in rows if row.get("seed") is not None}
    if seeds & set(calibration.get("calibration_seeds", [])):
        raise ValueError("Calibration and heldout PRNG seeds overlap")
    if any(row["config_id"] in set(calibration["selected_config_ids"]) for row in rows):
        raise ValueError("A calibration configuration leaked into heldout data")
    first = rows[0]
    if (first["geometry"] != calibration["geometry"] or first["beta"] != calibration["beta"]
            or first["grid_id"] != calibration["grid_id"]):
        raise ValueError("Calibration lock belongs to a different ensemble")
    if (first["counts_by_cut"][0]["stride"] != calibration["stride"] or
            sorted(float(item["cut_rad"]) for item in first["counts_by_cut"]) != calibration["cuts_rad"]):
        raise ValueError("Calibration lock belongs to different masks or spatial stride")
    if calibration["block_length"] is None:
        raise ValueError("Unresolved pilot autocorrelation cannot define heldout block length")
    reasons = []
    if not calibration["stable"]:
        reasons.append("CALIBRATION_MIXING_UNRESOLVED")
    if len(grouped) < 4 or len(calibration["calibration_chain_ids"]) < 4:
        reasons.append("FEWER_THAN_FOUR_INDEPENDENT_CHAINS_PER_SPLIT")
    if draws < 4000:
        reasons.append("FEWER_THAN_4000_PREREGISTERED_BOOTSTRAPS")
    mixing = {}
    for chain, values in grouped.items():
        diagnostics = {name: autocorrelation(stream) if stream is not None else
                       dict(tau_int=None, ess=0.0, stable=False, reason="ZERO_COVERAGE")
                       for name, stream in _streams(values).items()}
        mixing[chain] = diagnostics
        if any(not item["stable"] for item in diagnostics.values()):
            reasons.append(f"HELDOUT_MIXING_UNRESOLVED:{chain}")
        if len(values) < calibration["heldout_min_saves"]:
            reasons.append(f"HELDOUT_TOO_SHORT:{chain}")
        cadence = values[1]["sweep"] - values[0]["sweep"] if len(values) > 1 else 1
        if values[0].get("burn_sweeps", 0) < 20 * calibration["tau_max"] * cadence:
            reasons.append(f"INSUFFICIENT_BURN_IN:{chain}")
        measured_taus = [d["tau_int"] for d in diagnostics.values() if d["tau_int"] is not None]
        if measured_taus and max(measured_taus) > calibration["block_length"] / 10:
            reasons.append(f"PILOT_BLOCK_TOO_SHORT_FOR_HELDOUT:{chain}")
    starts = {values[0].get("start") for values in grouped.values()}
    if not {"cold", "hot"}.issubset(starts):
        reasons.append("HOT_COLD_START_COMPARISON_UNAVAILABLE")
    start_agreement = _start_agreement(grouped)
    if start_agreement["status"] != "COMPATIBLE":
        reasons.append("HOT_COLD_SECOND_HALF_NOT_COMPATIBLE")
    # Independent plaquette comparator is an actual external numeric reference.
    # It validates the declared beta/volume/action, not a hard-coded universal number.
    comparator = None
    if independent_plaquette is None:
        reasons.append("NO_INDEPENDENT_PLAQUETTE_COMPARATOR")
    else:
        reference = independent_plaquette
        if not reference.get("source") or reference.get("geometry") != first["geometry"] or reference.get("beta") != first["beta"]:
            raise ValueError("Plaquette comparator lacks source or uses another ensemble")
        if not np.isfinite(reference["value"]) or not np.isfinite(reference["sigma"]) or reference["sigma"] <= 0:
            raise ValueError("Invalid plaquette comparator uncertainty")
        means = np.array([np.mean([r["plaquette"] for r in values]) for values in grouped.values()])
        variances = []
        for chain, values in grouped.items():
            tau = mixing[chain]["plaquette"]["tau_int"]
            variances.append(float(np.var([r["plaquette"] for r in values], ddof=1) *
                                   2 * (tau or len(values)) / len(values)))
        mean = float(means.mean())
        mean_sigma = float(np.sqrt(sum(variances)) / len(variances))
        sigma = math.hypot(mean_sigma, reference["sigma"])
        z = abs(mean - reference["value"]) / sigma
        comparator = dict(mean=mean, sigma=mean_sigma, reference=reference, z=float(z), compatible=bool(z <= 3))
        if z > 3:
            reasons.append("INDEPENDENT_PLAQUETTE_MISMATCH")
    if any(row.get("link_verification") != "VERIFIED_LINKS" for row in rows):
        reasons.append("UNVERIFIED_LINKS")
    estimates = []
    for cut in cuts:
        for row in rows:
            _measurement(row, cut)
        primary = block_bootstrap(rows, calibration, cut, calibration["block_length"], draws, seed)
        doubled = block_bootstrap(rows, calibration, cut, 2 * calibration["block_length"], draws, seed)
        leave_one = {}
        if len(grouped) > 1:
            for number, chain in enumerate(sorted(grouped)):
                other = [row for row in rows if row["chain_id"] != chain]
                leave_one[chain] = block_bootstrap(other, calibration, cut, calibration["block_length"],
                                                  draws, seed + number + 1)
        cut_reasons = list(reasons)
        for label, result in (("primary", primary), ("double_block", doubled),
                              *((f"leave_out_{k}", v) for k, v in leave_one.items())):
            if result["empty_draw_fraction"] > 0.01:
                cut_reasons.append(f"EMPTY_BOOTSTRAP_STRATUM:{label}")
            if min(result["occupied_blocks"]) < min_blocks:
                cut_reasons.append(f"TOO_FEW_OCCUPIED_BLOCKS:{label}")
        # Stratum occupancy autocorrelations retain the unconditioned chronology.
        # This avoids claiming the thinned list of phase visits is independent.
        stratum_ess = []
        for stratum in (0, 1):
            ess = 0.0
            for chain, values in grouped.items():
                visit = np.array([r["plaquette"] <= calibration["lower_cut"] if stratum == 0 else
                                  r["plaquette"] >= calibration["upper_cut"] for r in values], dtype=float)
                entry = autocorrelation(visit)
                tau = entry["tau_int"]
                if tau is not None:
                    ess += visit.sum() / (2 * max(tau, calibration["tau_max"]))
            stratum_ess.append(float(ess))
        if min(stratum_ess) < min_ess:
            cut_reasons.append("INSUFFICIENT_STRATUM_ESS")
        classification = _classify(primary["interval95"], equivalence_band)
        for result in (doubled, *leave_one.values()):
            if _classify(result["interval95"], equivalence_band) != classification:
                cut_reasons.append("BLOCK_OR_CHAIN_SENSITIVITY")
                break
        estimates.append(dict(cut_rad=float(cut), primary=primary, doubled_block=doubled,
                              leave_one_chain_out=leave_one, stratum_ess=stratum_ess,
                              raw_interval_classification=classification,
                              classification="INCONCLUSIVE" if cut_reasons else classification,
                              reasons=sorted(set(cut_reasons))))
    return dict(schema="R135-P3-statistics-v1", grid_id=first["grid_id"],
                geometry=first["geometry"], beta=first["beta"],
                stride=first["counts_by_cut"][0]["stride"],
                calibration_lock_sha256=calibration["lock_sha256"],
                frozen_cuts=[calibration["lower_cut"], calibration["upper_cut"]],
                equivalence_band=equivalence_band, estimates=estimates, mixing=mixing,
                start_agreement=start_agreement,
                plaquette_comparator=comparator,
                phase_interpretation="LOW_AND_HIGH_PLAQUETTE_STRATA_ONLY",
                volume_and_spacing_status="REQUIRES_OTHER_PREREGISTERED_GRIDS",
                heldout_chain_ids=sorted(grouped),
                scientific_status="INCONCLUSIVE" if any(e["reasons"] for e in estimates) else "CONDITIONAL",
                limitations=["Finite-record ACF cannot rule out an unseen metastable mode.",
                             "A D4 measurement alone does not validate the graph-to-SU3 map."])


def compare_grids(reports):
    """Independent finite-volume/spacing consistency check for all four grids.

    This never calls two lattice spacings a continuum extrapolation.  Missing
    grids, incompatible intervals or sensitivity to volume remain explicit.
    """
    expected = {(4, 24, 1), (8, 48, 2), (4, 32, 1), (8, 64, 2)}
    indexed = {}
    for report in reports:
        geometry = report["geometry"]
        if len(set(geometry[1:])) != 1:
            raise ValueError("The registered four-grid comparison uses cubic spatial volumes")
        key = (geometry[0], geometry[1], report["stride"])
        if key in indexed:
            raise ValueError("Duplicate grid in four-grid comparison")
        if key not in expected:
            raise ValueError("Unregistered grid in four-grid comparison")
        primary = [r for r in report["estimates"] if abs(r["cut_rad"]) <= 1e-14]
        if len(primary) != 1:
            raise ValueError("Missing or duplicate primary sector mask")
        indexed[key] = primary[0]
    missing = sorted(expected - set(indexed))
    if missing:
        return dict(status="INCONCLUSIVE", missing_grids=[list(x) for x in missing], comparisons=[])
    comparisons = []
    for first, second, purpose in (((4, 24, 1), (4, 32, 1), "volume_Nt4"),
                                   ((8, 48, 2), (8, 64, 2), "volume_Nt8"),
                                   ((4, 24, 1), (8, 48, 2), "spacing_aspect6"),
                                   ((4, 32, 1), (8, 64, 2), "spacing_aspect8")):
        a, b = indexed[first], indexed[second]
        ia, ib = a["primary"]["interval95"], b["primary"]["interval95"]
        overlap = ia is not None and ib is not None and max(ia[0], ib[0]) <= min(ia[1], ib[1])
        same = a["classification"] == b["classification"] and a["classification"] != "INCONCLUSIVE"
        comparisons.append(dict(purpose=purpose, first=list(first), second=list(second),
                                interval_overlap=bool(overlap), same_resolved_classification=bool(same)))
    return dict(status="CONSISTENT_ON_REGISTERED_GRIDS" if all(
        c["interval_overlap"] and c["same_resolved_classification"] for c in comparisons) else "INCONCLUSIVE",
                missing_grids=[], comparisons=comparisons,
                continuum_limit="NOT_ESTABLISHED_BY_TWO_SPACINGS")
