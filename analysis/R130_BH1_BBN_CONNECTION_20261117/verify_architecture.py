#!/usr/bin/env python3
"""Exact checks for conditional architecture deductions; no ADD/BH1/BBN run."""
from fractions import Fraction as F
from pathlib import Path
import hashlib
import json
import time

def check():
    started = time.perf_counter()
    rows = []
    # s is the exponent a(t) ~ t**s, gamma defines V ~ L**gamma,
    # beta defines physical time t ~ iteration**beta. All are assumptions.
    examples = [
        ("C1_forward_radius_linear_clock", F(1,2), F(3), F(1), F(1,2), F(1,3)),
        ("C1_forward_volume_linear_clock", F(1,2), F(1), F(1), F(1,6), F(3)),
        ("C1_forward_radius_half_power_clock", F(1,2), F(3), F(1,2), F(1), F(-1,3)),
        ("C1_inverse_radius_linear_clock", F(1), F(3), F(1), F(1), F(-1,3)),
        ("C1_inverse_volume_linear_clock", F(1), F(1), F(1), F(1,3), F(1)),
    ]
    for name, alpha, gamma, beta, expected_s, expected_w in examples:
        s = alpha*gamma/(3*beta)
        w = 2/(3*s)-1
        assert (s,w) == (expected_s,expected_w)
        # Independent flat-GR power-law consistency: rho~t^-2,
        # rho~a^[-3(1+w)] => -3*s*(1+w) = -2.
        assert -3*s*(1+w) == -2
        rows.append(dict(name=name,alpha=str(alpha),gamma=str(gamma),
                         beta=str(beta),a_exponent=str(s),w=str(w)))

    # Same graph exponent permits distinct expansion exponents. No selection
    # of these clocks/volumes or equation of state is made here.
    assert len({r["a_exponent"] for r in rows[:3]}) == 3

    # For a conserved, constant particle energy: E const, V changing,
    # dE/dt + p*dV/dt = 0 demands p=0, independent of Friedmann.
    E, V, dV = F(7), F(5), F(2)
    dust_residual = F(0) + F(0)*dV
    radiation_residual = F(0) + (E/V/F(3))*dV
    assert dust_residual == 0 and radiation_residual != 0
    # E~V^-w restores dE/dV=-w E/V; p=w E/V cancels it.
    w=F(1,3)
    assert -w*E/V + w*E/V == 0

    # Coarse graining need not be dynamically closed, even for reversible F.
    permutation = [2,3,0,1]
    macro = [0,0,1,0]
    assert sorted(permutation) == list(range(4))
    assert macro[0] == macro[1]
    assert macro[permutation[0]] != macro[permutation[1]]

    # Passive reparameterization rescales ALL rates as well as the clock.
    dt, rate, expansion, clock_scale = F(2), F(3), F(5), F(7)
    assert (rate/clock_scale)*(dt*clock_scale) == rate*dt
    assert (rate/clock_scale)/(expansion/clock_scale) == rate/expansion
    assert rate*(dt*clock_scale) != rate*dt

    # A periodic observable cannot carry strict positive entropy increments.
    entropy = [F(1),F(3),F(2)]
    increments = [entropy[(i+1)%3]-entropy[i] for i in range(3)]
    assert sum(increments) == 0 and not all(x>0 for x in increments)

    # Independent cancellation of internal X/em/nu exchange, any signed fluxes.
    q_xem,q_xnu,q_emnu=F(2),F(-3),F(5)
    assert (-q_xem-q_xnu)+(q_xem-q_emnu)+(q_xnu+q_emnu) == 0

    return {
        "schema":"vm-lab-r130-bh1-bbn-architecture-checks-v1",
        "status":"PASS",
        "mode":"exact_algebra_and_logical_counterexamples",
        "physical_model_selected":False,
        "scientific_acceptance":False,
        "new_ADD_BH1_BBN_runs":0,
        "power_law_examples":rows,
        "checks":{
            "flat_GR_power_law_consistency":True,
            "clock_volume_nonidentifiability":True,
            "constant_particle_energy_is_not_radiation":True,
            "coarse_projection_not_automatically_closed":True,
            "passive_clock_change_differs_from_fixed_physical_rates":True,
            "periodic_observable_has_no_strict_entropy_arrow":True,
            "internal_energy_sources_cancel":True,
        },
        "limits":[
            "Power laws are asymptotic ansatzes, not differentiations of finite integer raw traces.",
            "w inference additionally assumes flat 3+1 GR, zero Lambda, one dominant constant-w perfect fluid.",
            "Generic four-state counterexample is not an observed violation of a particular R130 coarse graining.",
            "No microscopic energy, clock, portal or collision term is inferred by these checks.",
            "Theorem 5 damping dynamics of the ADD paper is not executed or attested here.",
        ],
        "script_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "code_wall_seconds":time.perf_counter()-started,
        "preparation_and_publication_excluded":True,
    }

if __name__=="__main__":
    result=check()
    out=Path(__file__).with_name("ARCHITECTURE_CHECKS.json")
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"status":result["status"],"file":str(out),
                      "exact_check_groups":len(result["checks"]),
                      "new_physical_runs":0},ensure_ascii=False))
