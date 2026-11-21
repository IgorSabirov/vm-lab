"""Scale, interface and within-phase hydrodynamic controls with explicit error assumptions."""

import math
import re

try:  # Package use by the executable stages; retain the standalone CLI.
    from .extract import article, one, measurement, NUMBER, WITH_ERROR
except ImportError:
    from extract import article, one, measurement, NUMBER, WITH_ERROR


def scales(p, files):
    source = article(files["flow-su3"], "main.tex")
    table = next(
        t
        for t in re.findall(r"\\begin\{table\}.*?\\end\{table\}", source, re.S)
        if r"\label{tab:params_sim_pure_gauge}" in t
    )
    pattern = (
        r"^\$("
        + r"[\d.]+)\$\s*&\s*\$(\d+)\$\s*&[^&]+&\s*\$"
        + WITH_ERROR
        + r"\$\s*&\s*\$"
        + NUMBER
        + r"\$"
    )
    rows = []
    for beta, length, am, err, t in re.findall(pattern, table, re.M):
        mass = measurement((am, err))
        x = mass["value"] * math.sqrt(float(t))
        rows.append(
            dict(
                beta=float(beta),
                L_over_a=int(length),
                m0_sqrt_t0=x,
                mass_only_sigma=mass["sigma"] * math.sqrt(float(t)),
                mixed_continuum_Tc_over_finite_a_mass=p["Tc_sqrt_t0"]["value"] / x,
            )
        )
    if len(rows) != 3:
        raise ValueError("Expected three pure-gauge ensembles")
    tc = p["Tc_sqrt_t0"]["value"]
    r0 = p["r0_Tc"]["value"] / tc
    return dict(
        finite_a_Wilson=rows,
        converted_r0_over_sqrt_t0=r0,
        converted_m0_sqrt_t0=p["r0_m0"]["value"] / r0,
        independent_continuum_scale=False,
    )


def coefficient(sigma, latent):
    s, es = sigma["value"], sigma["sigma"]
    l, el = latent["value"], latent["sigma"]
    central = 16 * math.pi * s**3 / (3 * l * l)
    a, b = 3 * es / s, 2 * el / l
    return dict(
        K=central,
        absolute_sigma_zero_covariance=central * math.hypot(a, b),
        linearized_sigma_range_if_correlation_unknown=[
            central * abs(a - b),
            central * (a + b),
        ],
    )


def matched_interface(files):
    source = article(files["improved-su3"], "latent34.tex", "latin1")
    # Same improved tadpole action, Nt=4, Ns=32 in both published tables.
    s = measurement(
        one(r"4&\$32\^3\$&[\d.]+~\(\d+\)&" + NUMBER + r"~\((\d+)\)", source)
    )
    l = measurement(
        one(r"Symanzik \(tadpole\) &\$32\^3\$&4&~" + NUMBER + r"~\((\d+)\)", source)
    )
    return dict(Nt=4, Ns=32, sigma_over_Tc3=s, latent_over_Tc4=l, **coefficient(s, l))


def eos_intervals(p):
    """Box on measured s at tabulated endpoints, propagated into a finite-volume derivative in T."""
    intervals = []
    for phase in ("cold", "hot"):
        branch = [
            r
            for r in p["continuum_s_over_T3"]
            if (r["T_over_Tc"] < 1) == (phase == "cold")
        ]
        endpoint = {"T_over_Tc": 1.0, **p["phase_entropy"][phase]}
        branch = sorted([*branch, endpoint], key=lambda r: r["T_over_Tc"])
        for lo, hi in zip(branch, branch[1:]):
            a, b = lo["T_over_Tc"], hi["T_over_Tc"]
            s1, s2 = lo["value"] * a**3, hi["value"] * b**3
            e1, e2 = lo["sigma"] * a**3, hi["sigma"] * b**3

            def secant(x, y):
                return (x + y) * (b - a) / ((a + b) * (y - x))

            ok = s2 - e2 > s1 + e1
            vals = [secant(s1 - e1, s2 + e2), secant(s1 + e1, s2 - e2)] if ok else None
            intervals.append(
                dict(
                    phase=phase,
                    T_over_Tc=[a, b],
                    cs2_secant=secant(s1, s2),
                    cs2_endpoint_box=vals,
                    lower_slope_positive=ok,
                    delta_p_over_Tc4_trapezoid=(s1 + s2) * (b - a) / 2,
                    delta_p_box_halfwidth=(e1 + e2) * (b - a) / 2,
                )
            )
    return intervals
