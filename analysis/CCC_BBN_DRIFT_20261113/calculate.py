"""Evaluate the published CCC drift, without a BBN-network surrogate.

Run: python analysis/CCC_BBN_DRIFT_20261113/calculate.py
Uses decimal arithmetic so changes of order 1e-18 are not rounded to zero.
"""
from decimal import Decimal as D, getcontext
import hashlib
import json
import math
from pathlib import Path
import platform
import time

getcontext().prec = 80
ROOT = Path(__file__).resolve().parent


def record(x):
    return format(x, ".25E")


def main():
    started = time.perf_counter()
    plan = json.loads((ROOT / "PLAN.json").read_text())
    p = plan["inputs"]
    alpha = D(p["alpha_over_Hc"]) * D(p["Hc_km_s_Mpc"]) / D(p["Mpc_km"])
    year = D(p["Julian_year_seconds"])
    f0 = D(p["early_f_reported_2024"])
    power = {"c": 1, "hbar": 2, "k_B": 2, "G": 3}
    rows = []
    float_errors = []
    for sec in plan["durations_seconds"]:
        dt = D(sec)
        row = {"delta_t_seconds": sec, "fractional_change": {}}
        for name, n in power.items():
            x = D(n) * alpha * dt
            exact = x.exp() - 1
            row["fractional_change"][name] = record(exact)
            stable = math.expm1(float(x))
            float_errors.append(abs(D(str(stable)) / exact - 1))
        # Exact operational time relative to the left-endpoint f0 approximation.
        u = ((-alpha * dt).exp() - 1) / (-alpha * f0)
        row["operational_seconds"] = record(u)
        row["clock_correction_vs_fixed_f0_fraction"] = record(u / (dt / f0) - 1)
        rows.append(row)

    # Invert u(t) analytically, then integrate 1/f(t) independently.
    clock_rows = []
    quadrature_errors = []
    for seconds in plan["clock_reference_seconds"]:
        u = D(seconds)
        dt = -(1 - alpha * f0 * u).ln() / alpha
        segments = 64
        h = dt / segments
        values = [(-alpha * h * j).exp() / f0 for j in range(segments + 1)]
        quadrature = h / 3 * (values[0] + values[-1]
                                   + 4 * sum(values[1:-1:2])
                                   + 2 * sum(values[2:-1:2]))
        error = abs(quadrature / u - 1)
        quadrature_errors.append(error)
        clock_rows.append({
            "reference_clock_seconds": seconds,
            "CCC_seconds_under_common_scaling": record(dt),
            "fractional_change_G": record((3 * alpha * dt).exp() - 1),
            "correction_vs_f0_times_reference_fraction": record(dt / (f0 * u) - 1),
            "independent_clock_integral_relative_error": record(error),
        })

    assert max(float_errors) < D("5e-16"), "unstable binary-float evaluation"
    assert max(quadrature_errors) < D("1e-60"), "clock inverse/integral disagreement"
    # Quantify how much faster the law would have to run for a 1% shift.
    one_percent = {name: record(D("0.99").ln() / (n * alpha) / year)
                   for name, n in power.items()}
    target_dt = D(1000)
    required_alpha_c = D("0.99").ln() / target_dt
    payload = {
        "status": "DRIFT_EVALUATED_CONDITIONAL_CLOCK_IDENTITY",
        "alpha_s_inverse": record(alpha),
        "alpha_Gyr_inverse": record(alpha * year * D("1e9")),
        "e_folding_Gyr": record(-1 / alpha / year / D("1e9")),
        "early_to_today_ratios_from_reported_f": {name: record(f0 ** n) for name, n in power.items()},
        "rounded_age_crosscheck": {
            "f_from_rounded_26_7_Gyr": record((-alpha * D(p["age_Gyr_rounded_crosscheck_only"]) * year * D("1e9")).exp()),
            "age_Gyr_implied_by_reported_f_3_66": record(-f0.ln() / alpha / year / D("1e9")),
            "meaning": "Rounded inputs are not an additional fit; calculations use the reported f=3.66."
        },
        "drift_grid": rows,
        "conditional_clock_grid": clock_rows,
        "years_for_one_percent_decrease": one_percent,
        "alpha_multiplier_for_one_percent_c_decrease_in_1000_s": record(required_alpha_c / alpha),
        "invariant_exponents": {
            "G_over_hbar_c_fixed_mass": 3 - 2 - 1,
            "rest_energy_over_kBT_fixed_T": 2 - 2,
            "Gamma_over_H_under_common_scaling": -1 - (-1)
        },
        "verification": {
            "decimal_precision_digits": getcontext().prec,
            "max_float_expm1_relative_error": record(max(float_errors)),
            "max_quadrature_relative_error": record(max(quadrature_errors)),
            "passed": True
        },
        "provenance": {
            "base_commit": plan["base_commit"],
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "plan_sha256": hashlib.sha256((ROOT / "PLAN.json").read_bytes()).hexdigest(),
            "python": platform.python_version(),
            "machine_seconds": time.perf_counter() - started,
            "nuclear_network_run": False
        }
    }
    (ROOT / "RESULTS.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
