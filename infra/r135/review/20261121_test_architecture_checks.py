#!/usr/bin/env python3
"""Reproduce mathematical examples in the 2026-11-21 external review.

Run from any directory with Python, NumPy and SciPy installed:
    python infra/r135/review/20261121_test_architecture_checks.py

This is a standalone mathematical review calculation. It imports no project
modules, runs neither LINX nor PRIMAT nor the physical R135 pipeline, and adopts
no testing architecture, scientific acceptance criterion or power requirement.
The selected alpha and sample sizes illustrate one explicitly defined test.
The JSON records the source and this script's hashes and the actual environment.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
import time

import numpy as np
import scipy
from scipy.integrate import quad
from scipy.stats import binom, chi2


SEED = 20261121
N_MC = 400_000
NOMINAL_COVERAGE = 0.95
ILLUSTRATIVE_ALPHA = 0.01
ILLUSTRATIVE_SAMPLE_SIZES = (100, 1000, 2000)


def file_record(path: Path) -> dict:
    contents = path.read_bytes()
    return {
        "filename": path.name,
        "sha256": hashlib.sha256(contents).hexdigest(),
        "bytes": len(contents),
    }


def source_monte_carlo() -> dict:
    """Keep the source snippet's numeric operations and RNG draw order."""
    L = np.array([[1.0, 0.0], [3 / 5, 4 / 5]])
    Cq = L @ L.T
    C_true = np.array([[1.0, 0.8], [0.8, 1.0]])
    C_wrong = np.eye(2)
    r2 = chi2.ppf(0.95, df=2)
    rng = np.random.default_rng(20261121)
    N = 400_000
    x = rng.multivariate_normal([0, 0], C_true, size=N)
    quad_wrong = np.einsum("ij,ij->i", x, x)
    cov_wrong_region = np.mean(quad_wrong <= r2)
    Cinv = np.linalg.inv(C_true)
    quad_true = np.einsum("ij,jk,ik->i", x, Cinv, x)
    cov_true_region = np.mean(quad_true <= r2)
    se = np.sqrt(cov_wrong_region * (1 - cov_wrong_region) / N)

    wrong = float(cov_wrong_region)
    correct = float(cov_true_region)
    return {
        "source_lines": [313, 350],
        "seed": SEED,
        "N": N_MC,
        "rng_constructor": "numpy.random.default_rng(20261121)",
        "bit_generator": type(rng.bit_generator).__name__,
        "sampling_call": "rng.multivariate_normal([0, 0], C_true, size=400_000)",
        "sampling_method": "NumPy default multivariate_normal method: svd",
        "L": L.tolist(),
        "L_times_L_transpose": Cq.tolist(),
        "C_true": C_true.tolist(),
        "C_wrong": C_wrong.tolist(),
        "eigenvalues_C_true": np.linalg.eigvalsh(C_true).tolist(),
        "nominal_coverage": NOMINAL_COVERAGE,
        "chi2_df": 2,
        "region_radius_squared": float(r2),
        "covered_wrong_region": int(np.count_nonzero(quad_wrong <= r2)),
        "covered_correct_region": int(np.count_nonzero(quad_true <= r2)),
        "coverage_wrong_region": wrong,
        "coverage_correct_region": correct,
        "coverage_deficit_wrong_region": NOMINAL_COVERAGE - wrong,
        "mc_standard_error_wrong_plugin": float(se),
        "mc_standard_error_correct_plugin": math.sqrt(correct * (1 - correct) / N),
        "standardized_deficit_using_plugin_se_not_power": (
            (NOMINAL_COVERAGE - wrong) / float(se)
        ),
        "standardized_deficit_using_null_se_not_power": (
            (NOMINAL_COVERAGE - wrong)
            / math.sqrt(NOMINAL_COVERAGE * (1 - NOMINAL_COVERAGE) / N)
        ),
        "source_reported_rounded_outputs": {
            "coverage_wrong_region": 0.9266,
            "coverage_correct_region": 0.9505,
            "coverage_deficit_wrong_region": 0.0234,
            "mc_standard_error_wrong_plugin": 0.00041,
        },
        "observed_rounded_outputs": {
            "coverage_wrong_region": round(wrong, 4),
            "coverage_correct_region": round(correct, 4),
            "coverage_deficit_wrong_region": round(NOMINAL_COVERAGE - wrong, 4),
            "mc_standard_error_wrong_plugin": round(float(se), 5),
        },
        "interpretation": (
            "These are one-sample Monte Carlo coverage estimates. A standardized "
            "coverage deficit is not power and is not automatically a calibrated "
            "Gaussian tail significance. The source reports no software versions; "
            "bitwise reproduction across different numeric builds is not assumed."
        ),
    }


def polar_reference(radius_squared: float) -> dict:
    """Integrate the independent polar-coordinate expression, without MC data."""
    # With Z ~ N(0, I), its angle is uniform and |Z|^2 ~ chi2(df=2).
    # X'X = |Z|^2 * (1.8 cos(phi)^2 + 0.2 sin(phi)^2).
    def radial_survival(phi: float) -> float:
        variance = 1.8 * math.cos(phi) ** 2 + 0.2 * math.sin(phi) ** 2
        return math.exp(-radius_squared / (2 * variance))

    integral, error_estimate = quad(
        radial_survival, 0.0, 2 * math.pi,
        epsabs=1e-13, epsrel=1e-13, limit=200,
    )
    return {
        "method": "scipy.integrate.quad of polar-coordinate survival probability",
        "independent_of_monte_carlo_samples": True,
        "eigenvalues_used": [1.8, 0.2],
        "formula": (
            "1 - integral_0^(2*pi) exp(-q / "
            "(2*(1.8*cos(phi)^2 + 0.2*sin(phi)^2))) dphi / (2*pi)"
        ),
        "quadrature_options": {"epsabs": 1e-13, "epsrel": 1e-13, "limit": 200},
        "coverage_wrong_region": 1 - integral / (2 * math.pi),
        "quadrature_absolute_error_ESTIMATE": error_estimate / (2 * math.pi),
        "error_interpretation": (
            "The quadrature algorithm's estimated absolute error, not a rigorous "
            "bound and not Monte Carlo error; it excludes uncertainty in the model."
        ),
        "coverage_correct_region_analytic": NOMINAL_COVERAGE,
    }


def binomial_power(n: int, p1: float) -> dict:
    """Largest integer cutoff with size <= alpha for H0: p >= 0.95."""
    p0 = NOMINAL_COVERAGE
    alpha = ILLUSTRATIVE_ALPHA
    # For rejection K <= k, the worst-case H0 probability is at p = p0.
    k = int(binom.ppf(alpha, n, p0))
    while k >= 0 and binom.cdf(k, n, p0) > alpha:
        k -= 1
    while k < n and binom.cdf(k + 1, n, p0) <= alpha:
        k += 1
    size = float(binom.cdf(k, n, p0))
    next_size = float(binom.cdf(k + 1, n, p0))
    if not (size <= alpha < next_size):
        raise ArithmeticError("Could not verify the largest valid binomial cutoff")
    return {
        "N": n,
        "reject_when_K_at_most": k,
        "actual_size_at_null_boundary": size,
        "size_for_next_integer_cutoff": next_size,
        "largest_cutoff_condition_verified": True,
        "power_at_specified_alternative": float(binom.cdf(k, n, p1)),
    }


def measure_example() -> dict:
    lo, hi, valid_hi = 1.0, 100.0, 10.0
    uniform_T_fraction = (valid_hi - lo) / (hi - lo)
    log_lo, log_hi, log_valid_hi = map(math.log, (lo, hi, valid_hi))

    def pushforward_density(u: float) -> float:
        return math.exp(u) / (hi - lo)

    valid_mass, valid_error = quad(pushforward_density, log_lo, log_valid_hi)
    total_mass, total_error = quad(pushforward_density, log_lo, log_hi)
    pushforward_fraction = valid_mass / total_mass
    uniform_log_fraction = (log_valid_hi - log_lo) / (log_hi - log_lo)
    return {
        "T_support": [lo, hi],
        "valid_domain_in_T": [lo, valid_hi],
        "coordinate_change": "u = natural_log(T)",
        "uniform_T_density": "1/99 on [1,100]",
        "uniform_T_valid_fraction": uniform_T_fraction,
        "same_measure_pushforward_density_in_u": "exp(u)/99 on [0,log(100)]",
        "same_measure_pushforward_valid_mass_quadrature": valid_mass,
        "same_measure_pushforward_total_mass_quadrature": total_mass,
        "same_measure_pushforward_valid_fraction": pushforward_fraction,
        "same_measure_fraction_difference": pushforward_fraction - uniform_T_fraction,
        "pushforward_valid_mass_quadrature_error_ESTIMATE": valid_error,
        "pushforward_total_mass_quadrature_error_ESTIMATE": total_error,
        "new_uniform_log_density_in_u": "1/log(100) on [0,log(100)]",
        "new_uniform_log_density_in_T": "1/(T*log(100)) on [1,100]",
        "new_uniform_log_valid_fraction": uniform_log_fraction,
        "interpretation": (
            "Uniform T and its Jacobian-correct pushforward are the same measure "
            "and give the same domain fraction up to numerical rounding. Choosing "
            "a new uniform-log prior changes the measure and gives a different "
            "fraction. This is a mathematical example, not an adopted physical prior."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    directory = Path(__file__).resolve().parent
    parser.add_argument(
        "--source", type=Path,
        default=directory / "20261121_test_architecture_source.txt",
    )
    parser.add_argument(
        "--output", type=Path,
        default=directory / "20261121_test_architecture_checks.json",
    )
    args = parser.parse_args()
    started = time.perf_counter()
    source = file_record(args.source)
    source["line_count"] = len(args.source.read_bytes().splitlines())
    script = file_record(Path(__file__).resolve())
    mc = source_monte_carlo()
    reference = polar_reference(mc["region_radius_squared"])
    p1 = reference["coverage_wrong_region"]
    mc["coverage_wrong_minus_quadrature"] = mc["coverage_wrong_region"] - p1
    mc["mc_standard_error_wrong_using_reference"] = math.sqrt(p1 * (1 - p1) / N_MC)
    mc["mc_error_in_reference_standard_errors"] = (
        mc["coverage_wrong_minus_quadrature"]
        / mc["mc_standard_error_wrong_using_reference"]
    )
    mc["source_rounded_outputs_match_current_environment"] = (
        mc["source_reported_rounded_outputs"] == mc["observed_rounded_outputs"]
    )
    result = {
        "schema_version": 1,
        "purpose": "Reproducible mathematical checks of an external review",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_file": source,
        "script_file": script,
        "environment": {
            "python": sys.version,
            "python_implementation": platform.python_implementation(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "numpy_build_configuration": getattr(np.__config__, "CONFIG", {}),
            "scipy_build_configuration": getattr(scipy.__config__, "CONFIG", {}),
        },
        "monte_carlo_reproduction": mc,
        "independent_polar_quadrature": reference,
        "illustrative_power": {
            "status": "illustration_only_not_an_adopted_project_requirement",
            "null_hypothesis": "p >= 0.95",
            "alternative_hypothesis_p": p1,
            "sampling_model": "K ~ Binomial(N,p), independent identically distributed toys",
            "test": "Reject H0 when K <= k; choose largest k with size <= alpha",
            "alpha": ILLUSTRATIVE_ALPHA,
            "power_definition": "Probability of rejection under the specified alternative",
            "evaluation": "Binomial CDF, not an additional Monte Carlo experiment",
            "rows": [binomial_power(n, p1) for n in ILLUSTRATIVE_SAMPLE_SIZES],
        },
        "domain_measure_example": measure_example(),
        "limitations": [
            "Synthetic mathematical covariance; no measured lattice or nuclear covariance.",
            "No LINX, PRIMAT, physical R135 run, or physical calibration is performed.",
            "No inference implementation or physical uncertainty model is qualified.",
            "The reported power belongs only to the explicit iid binomial test and alternative.",
            "Quadrature errors are algorithmic estimates, not rigorous error bounds.",
            "No architecture, power threshold, resource rule, or prior is adopted as policy.",
            "No project scientific status, CI configuration, or task definition is modified.",
        ],
    }
    result["calculation_seconds_excluding_imports_and_json_write"] = time.perf_counter() - started
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output),
        "coverage_wrong_mc": mc["coverage_wrong_region"],
        "coverage_correct_mc": mc["coverage_correct_region"],
        "coverage_wrong_quadrature": p1,
        "source_rounded_outputs_match": mc["source_rounded_outputs_match_current_environment"],
        "illustrative_power": result["illustrative_power"]["rows"],
        "domain_fractions": {
            key: result["domain_measure_example"][key]
            for key in (
                "uniform_T_valid_fraction",
                "same_measure_pushforward_valid_fraction",
                "new_uniform_log_valid_fraction",
            )
        },
        "script_sha256": script["sha256"],
        "source_sha256": source["sha256"],
    }, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
