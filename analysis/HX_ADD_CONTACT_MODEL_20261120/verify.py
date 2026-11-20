#!/usr/bin/env python3
"""First effective classical H_X candidate from the ADD contact-balance result.

k_B=1. Fixed-L canonical sector. Matter bits a_i,b_i and two radiation
port bits r_i^L,r_i^R per vertex.
H_X = h L + J sum_i a_i a_{i+1} a_{i+2} a_{i+3}
      + h sum_i (r_i^L+r_i^R).
The four-a term is the neighbor-sensitive E4 term from contact_balance/REPORT.md.
The radiation bit energy h is a physical identification hypothesis, not supplied
as a dimensional constant by Arrighi-Dowek-Durbec.
"""
from collections import defaultdict, Counter
from itertools import product
import json, math
import numpy as np
from scipy.linalg import eigh


def n4_distribution(L):
    """Exact counts of cyclic binary strings by N4, using 16 initial 4-tuples."""
    dist = [0] * (L + 1)
    for first in range(16):
        bits = tuple((first >> (3-j)) & 1 for j in range(4))
        k0 = bits[0] * bits[1] * bits[2] * bits[3]
        dp = {(bits[1:], k0): 1}
        for _ in range(4, L):
            nd = defaultdict(int)
            for (last3, k), count in dp.items():
                for x in (0, 1):
                    nk = k + int(last3[0] and last3[1] and last3[2] and x)
                    nd[(last3[1:] + (x,), nk)] += count
            dp = nd
        for (last3, k), count in dp.items():
            wrap = int(last3[0] and last3[1] and last3[2] and bits[0])
            wrap += int(last3[1] and last3[2] and bits[0] and bits[1])
            wrap += int(last3[2] and bits[0] and bits[1] and bits[2])
            dist[k + wrap] += count
    assert sum(dist) == 2**L
    return dist


def canonical(L, g=0.5, J_over_h=1.0):
    """Canonical thermodynamics at fixed L; energies in units of h."""
    dist = n4_distribution(L)
    betaJ = J_over_h * g
    weights = np.array([count * math.exp(-betaJ*n)
                        for n, count in enumerate(dist)], float)
    za = float(weights.sum())
    probs = weights / za
    ns = np.arange(L+1, dtype=float)
    mean_n4 = float(probs @ ns)
    var_n4 = float(probs @ ((ns-mean_n4)**2))
    f_rad = 1.0 / (math.exp(g) + 1.0)
    # b_i gives 2^L zero-energy degeneracy; two radiation bits per vertex.
    logz = -g*L + L*math.log(2.0) + math.log(za) + 2*L*math.log1p(math.exp(-g))
    u_over_t = g*L + betaJ*mean_n4 + 2*g*L*f_rad
    entropy = logz + u_over_t
    heat_capacity = betaJ**2*var_n4 + 2*g**2*L*f_rad*(1.0-f_rad)
    return {
        "L": L, "h_over_T": g, "J_over_h": J_over_h,
        "logZ": logz, "F_over_T": -logz, "U_over_T": u_over_t,
        "S_over_kB": entropy, "C_fixed_L_over_kB": heat_capacity,
        "mean_N4": mean_n4, "var_N4": var_n4,
        "mean_radiation_bits": 2*L*f_rad,
        "state_count_check": sum(dist)
    }


def glauber_relaxation(L, betaJ):
    """Finite-L heat-bath relaxation for a_i; Gamma0 is factored out."""
    nstates = 1 << L
    energies = np.zeros(nstates)
    for state in range(nstates):
        a = [(state >> i) & 1 for i in range(L)]
        energies[state] = sum(a[i]*a[(i+1)%L]*a[(i+2)%L]*a[(i+3)%L]
                              for i in range(L))
    logpi = -betaJ*energies
    logpi -= logpi.max()
    pi = np.exp(logpi)
    pi /= pi.sum()
    Q = np.zeros((nstates, nstates))
    for state in range(nstates):
        for i in range(L):
            nxt = state ^ (1 << i)
            de = energies[nxt] - energies[state]
            rate = 1.0 / (1.0 + math.exp(betaJ*de))
            Q[state, nxt] += rate
            Q[state, state] -= rate
    root = np.sqrt(pi)
    sym = root[:, None] * Q / root[None, :]
    sym = (sym + sym.T) / 2
    eigs = eigh(sym, eigvals_only=True, subset_by_index=[nstates-2, nstates-1])
    gap = -float(eigs[0])
    return {"L":L,"betaJ":betaJ,"states":nstates,
            "lambda_gap_over_Gamma0":gap,"tau_Gamma0":1.0/gap,
            "rate_model":"single-site heat-bath Glauber; detailed balance; not deterministic ADD F=QI"}


def contact_event_gaps(max_L=8):
    """All cyclic C1 words with exactly one 12 merge and no pre-existing 3."""
    out = Counter()
    examples = {}
    def n4(w):
        n=len(w)
        return sum(int(all((w[(i+j)%n] & 1) for j in range(4))) for i in range(n))
    for L in range(3, max_L+1):
        for w in product(range(4), repeat=L):
            if 3 in w:
                continue
            starts=[i for i in range(L) if w[i]==1 and w[(i+1)%L]==2]
            if len(starts)!=1:
                continue
            i=starts[0]
            merged=[3]
            for k in range(2,L):
                merged.append(w[(i+k)%L])
            delta=n4(tuple(merged))-n4(w)
            out[delta]+=1
            examples.setdefault(delta, (''.join(map(str,w)), ''.join(map(str,merged))))
    return {
        "counts_by_delta_N4": {str(k):v for k,v in sorted(out.items())},
        "examples": {str(k):list(v) for k,v in sorted(examples.items())},
        "energy_release_over_h_for_J_over_h_1": {str(k):1-k for k in sorted(out)},
        "scope":"cyclic words L=3..8, no state 3, exactly one 12 redex"
    }


def main():
    therm = [canonical(24, g, ratio)
             for g in (0.25,0.5,1.0,2.0) for ratio in (0.5,1.0,2.0)]
    relax = [glauber_relaxation(8, betaJ) for betaJ in (0.25,0.5,1.0,2.0)]
    target = 0.044518075411783944
    xi = 0.5
    required_product = target / xi**4
    return {
      "model":"H_X=hL+J*N_1111(a)+h*N_gamma; N_gamma=sum_i(r_i^L+r_i^R); N_1111=sum_i a_i a_{i+1} a_{i+2} a_{i+3}; all bits binary; k_B=1",
      "interpretation":"h is the proposed contact/radiation energy scale; J is the neighbor-sensitive E4 coupling. ADD does not supply dimensional h. J/h remains a parameter.",
      "ensemble":"canonical, fixed graph length L=24; b-sector is a 2^L degeneracy; two radiation two-level port bits per vertex; exact transfer-DP count for N_1111; heat capacity is at fixed L, not yet physical C_R",
      "thermodynamics":therm,
      "kinetics":relax,
      "contact_event_balance":contact_event_gaps(),
      "BBN":{
        "target_Delta_rho_over_Tgamma4":target,"xi":xi,
        "required_chi_nu_g":required_product,
        "if_g_equals_0p5_required_chi_times_nu":required_product/0.5,
        "warning":"nu is physical ADD event density per V*T_X^3, not equilibrium radiation occupation. Model does not derive nu, chi, h/T_X or V."
      },
      "identifiability":[
        "Fixed-L partition function and fixed-L heat capacity are defined for this explicit effective model; physical C_R needs L-to-R mapping.",
        "Fixed-L canonical ensemble is not the full ADD ensemble because ADD changes L.",
        "Glauber rates are a chosen detailed-balance bath dynamics; Gamma0 is free and is not derived from ADD.",
        "tau_X=tau_Gamma0/Gamma0; comparison with H^-1 requires a physical Gamma0/H.",
        "No physical BBN prediction is claimed; only the required parameter combination is evaluated."
      ]
    }


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
