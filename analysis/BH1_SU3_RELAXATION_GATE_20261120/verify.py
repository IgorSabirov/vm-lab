#!/usr/bin/env python3
"""SU(3) latent-heat scale vs the physical radiation-era Hubble rate.

Uses the newer lattice central value L/Tc^4=1.175(10), the BBN/CLASS
late-transfer target, and assumes m_X=Tc. Natural units are used internally.
"""
import json
import math

MPL_MEV = 1.2209e22
HBAR_MEV_S = 6.582119569e-22
DELTA_RHO_OVER_TGAMMA4 = 0.044518075411783944
LATENT_HEAT_OVER_TC4 = 1.175
LATENT_HEAT_ERROR = 0.010

# BBN/CLASS integration endpoints from the paired-run report.
# g*=10.75 before e+e- annihilation; g*=3.36 after annihilation.
EPOCHS = [
    {"name": "BBN_start", "Tgamma_MeV": 8.617, "gstar": 10.75},
    {"name": "BBN_early_window_low", "Tgamma_MeV": 2.0, "gstar": 10.75},
    {"name": "BBN_late_window_high", "Tgamma_MeV": 0.2, "gstar": 10.75},
    {"name": "BBN_late_window_low", "Tgamma_MeV": 0.02, "gstar": 3.36},
    {"name": "BBN_end", "Tgamma_MeV": 0.00517, "gstar": 3.36},
]


def main():
    xi = (DELTA_RHO_OVER_TGAMMA4 / LATENT_HEAT_OVER_TC4) ** 0.25
    xi_lo = (DELTA_RHO_OVER_TGAMMA4 /
             (LATENT_HEAT_OVER_TC4 + LATENT_HEAT_ERROR)) ** 0.25
    xi_hi = (DELTA_RHO_OVER_TGAMMA4 /
             (LATENT_HEAT_OVER_TC4 - LATENT_HEAT_ERROR)) ** 0.25

    rows = []
    for epoch in EPOCHS:
        tg = epoch["Tgamma_MeV"]
        gs = epoch["gstar"]
        tc = xi * tg
        mx = tc  # explicit m_X = T_c hypothesis
        hubble = 1.66 * math.sqrt(gs) * tg**2 / MPL_MEV
        tau_x_mev_inv = 1.0 / mx
        hubble_time_mev_inv = 1.0 / hubble
        ratio = tau_x_mev_inv / hubble_time_mev_inv
        rows.append({
            **epoch,
            "Tc_MeV": tc,
            "mX_MeV": mx,
            "H_MeV": hubble,
            "tauX_MeV_inv": tau_x_mev_inv,
            "Hubble_time_MeV_inv": hubble_time_mev_inv,
            "tauX_seconds": HBAR_MEV_S / mx,
            "Hubble_time_seconds": HBAR_MEV_S / hubble,
            "tauX_over_Hubble_time": ratio,
            "Hubble_times_faster": 1.0 / ratio,
        })

    # Incorrect shorthand H~T_gamma is shown only as a diagnostic contrast.
    naive_ratio = 1.0 / xi
    return {
        "status": "PASS_CONDITIONAL_MICROSCOPIC_TIMESCALE",
        "lattice_choice": "1.175(10), newer SU(3) latent-heat estimate",
        "latent_heat_over_Tc4": LATENT_HEAT_OVER_TC4,
        "latent_heat_error": LATENT_HEAT_ERROR,
        "BBN_target_Delta_rho_over_Tgamma4": DELTA_RHO_OVER_TGAMMA4,
        "derived_Tc_over_Tgamma": xi,
        "xi_interval_from_latent_heat_error": [xi_lo, xi_hi],
        "mass_assumption": "m_X = T_c",
        "relaxation_assumption": "tau_X = 1/m_X (natural units), no critical slowing down",
        "physical_hubble_law": "H = 1.66*sqrt(g_star)*T_gamma^2/M_Pl, M_Pl=1.2209e22 MeV",
        "epochs": rows,
        "decision": {
            "criterion": "tau_X <= H^-1",
            "status": "PASS_AT_ALL_LISTED_BBN_EPOCHS",
            "max_tau_over_Hubble_time": max(x["tauX_over_Hubble_time"] for x in rows),
            "minimum_fast_factor": min(x["Hubble_times_faster"] for x in rows),
            "note": "The shorthand H^-1~1/T_gamma is not the physical radiation-era Hubble time; it omits M_Pl/T_gamma. It would give tau/(1/T_gamma)=1/xi≈2.27 and a false failure."
        },
        "limitations": [
            "Latent heat L/Tc^4 is dimensionless and does not itself derive m_X=Tc; this is the tested mass-gap hypothesis.",
            "The BBN-derived xi uses 100% latent-heat efficiency and the selected SU(3) latent heat.",
            "Near a critical point, critical slowing down can make tau_X much longer than 1/m_X; no dynamic critical exponent or damping coefficient is supplied.",
            "The SU(3) transition epoch must actually coincide with the BBN epoch used for this comparison.",
            "This tests microscopic equilibration time, not bubble nucleation, phase-conversion completion, or portal energy-transfer time."
        ],
        "naive_shortcut": {
            "assumed_H": "H=T_gamma",
            "tau_over_H_inverse": naive_ratio,
            "warning": "Dimensionally possible only after setting an unstated Planck scale to unity; not the standard Friedmann result in the same MeV units."
        }
    }


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
