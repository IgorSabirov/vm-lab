"""Finite CTMC review, n=3; deterministic linear solves, no Monte Carlo.

Q uses row-generator convention. Expected rewards solve (-Q) u = r.
Absorbing transitions contribute to the diagonal and absorption flux.
"""
from __future__ import annotations
import itertools
import json
import platform
import time
from pathlib import Path
import numpy as np
import scipy
from scipy.linalg import solve
from scipy.optimize import brentq
import sympy as sp

PAIRS = ((0, 1), (0, 2), (1, 2))
REWARDS = ("time", "edge_time", "productive_time", "births", "deaths", "gains", "losses")
CHECKS = []


def events(l, b, nu, mode, lam0, cap, allow_birth=True):
    out = []
    for e, (i, j) in enumerate(PAIRS):
        if b >> e & 1:
            out.append((l, b & ~(1 << e), .3, "deaths"))
        elif allow_birth and b.bit_count() < cap:
            rate = lam0 if mode == "C2" else int(bool(l & ((1 << i) | (1 << j))))
            if rate:
                out.append((l, b | (1 << e), rate, "births"))
    for i in range(3):
        if l >> i & 1:
            out.append((l & ~(1 << i), b, nu, "losses"))
        else:
            neighbors = sum(1 for e, (a, c) in enumerate(PAIRS)
                            if b >> e & 1 and ((a == i and l >> c & 1)
                                               or (c == i and l >> a & 1)))
            if neighbors:
                out.append((l | (1 << i), b, float(neighbors), "gains"))
    return out


def chain(nu, mode, lam0=0., cap=3, budget=None):
    states = [(l, b) for l in range(1, 8) for b in range(8) if b.bit_count() <= cap]
    ix = {s: i for i, s in enumerate(states)}
    n = len(states)
    previous = None
    levels = range(budget + 1) if budget is not None else (None,)
    max_residual = 0.
    for remaining in levels:
        Q = np.zeros((n, n))
        R = np.zeros((n, len(REWARDS)))
        absorb = np.zeros((n, 8))
        cross = np.zeros((n, n))
        for row, (l, b) in enumerate(states):
            R[row, :3] = (1, b.bit_count(), sum(1 for e, (i, j) in enumerate(PAIRS)
                                if b >> e & 1 and ((l >> i) & 1) != ((l >> j) & 1)))
            for l2, b2, rate, kind in events(l, b, nu, mode, lam0, cap, remaining != 0):
                Q[row, row] -= rate
                R[row, REWARDS.index(kind)] += rate
                if l2 == 0:
                    absorb[row, b2] += rate
                elif budget is not None and kind == "births":
                    cross[row, ix[l2, b2]] += rate
                else:
                    Q[row, ix[l2, b2]] += rate
        rhs = np.column_stack((R, absorb))
        if previous is not None:
            rhs += cross @ previous
        u = solve(-Q, rhs)
        max_residual = max(max_residual, float(np.max(np.abs(-Q @ u - rhs))))
        previous = u
    row = u[ix[1, 0]]
    result = dict(zip(REWARDS, map(float, row[:len(REWARDS)])))
    probs = row[len(REWARDS):]
    final_edges = sum(float(p) * b.bit_count() for b, p in enumerate(probs))
    residuals = {
        "absorption_mass": abs(float(sum(probs)) - 1),
        "edge_balance": abs(result["births"] - result["deaths"] - final_edges),
        "mark_balance": abs(result["losses"] - result["gains"] - 1),
        "productive_identity": abs(result["gains"] - result["productive_time"]),
        "linear_residual": max_residual,
    }
    assert max(residuals.values()) < 2e-8, residuals
    if budget is not None:
        assert result["births"] <= budget + 1e-9
    result.update(expected_final_edges=final_edges, residuals=residuals, states=n,
                  budget_levels=(budget + 1 if budget is not None else 1))
    return result


def canonical(l, b):
    images = []
    for perm in itertools.permutations(range(3)):
        ll = sum(((l >> i) & 1) << perm[i] for i in range(3))
        bb = 0
        for e, (i, j) in enumerate(PAIRS):
            if b >> e & 1:
                bb |= 1 << PAIRS.index(tuple(sorted((perm[i], perm[j]))))
        images.append((ll, bb))
    return min(images)


def symbolic_control(nu, cap):
    """Exact lumping under node permutations, lambda0=x, all other rates rational."""
    x = sp.Symbol("x", positive=True)
    states = sorted({canonical(l, b) for l in range(1, 8)
                     for b in range(8) if b.bit_count() <= cap})
    ix = {s: i for i, s in enumerate(states)}
    Q = sp.zeros(len(states))
    for row, (l, b) in enumerate(states):
        for l2, b2, rate, kind in events(l, b, float(nu), "C2", 1., cap):
            exact_rate = x if kind == "births" else (
                sp.Rational(3, 10) if kind == "deaths" else nu if kind == "losses" else sp.Integer(rate))
            Q[row, row] -= exact_rate
            if l2:
                Q[row, ix[canonical(l2, b2)]] += exact_rate
    sol = sp.linsolve((-Q, sp.ones(len(states), 1)))
    expr = sp.factor(next(iter(sol))[ix[canonical(1, 0)]])
    limit = sp.limit(expr, x, sp.oo)
    gap = sp.factor(limit - expr)
    derivative = sp.factor(sp.diff(expr, x))
    def positive_coeffs(e):
        num, den = sp.fraction(sp.cancel(e))
        nn = sp.Poly(num, x).all_coeffs(); dd = sp.Poly(den, x).all_coeffs()
        if all(c <= 0 for c in dd):
            nn = [-c for c in nn]; dd = [-c for c in dd]
        return all(c >= 0 for c in nn + dd) and any(c > 0 for c in nn) and any(c > 0 for c in dd)
    assert positive_coeffs(gap)
    assert positive_coeffs(derivative)
    # Independent check against the un-lumped floating generator.
    for v in (sp.Rational(2, 3), sp.Integer(1), sp.Integer(4)):
        full = chain(float(nu), "C2", float(v), cap)["time"]
        assert abs(float(expr.subs(x, v)) - full) < 2e-8
    return {"nu": str(nu), "capacity": cap, "orbits": len(states),
            "T_C2_exact": str(expr), "limit_exact": str(limit), "limit": float(limit),
            "limit_minus_T": str(gap), "derivative": str(derivative),
            "positive_coefficients_prove_strict_increase_and_upper_bound": True}


def exact_model_time(nu, cap):
    states = sorted({canonical(l, b) for l in range(1, 8)
                     for b in range(8) if b.bit_count() <= cap})
    ix = {s: i for i, s in enumerate(states)}
    Q = sp.zeros(len(states))
    for row, (l, b) in enumerate(states):
        for l2, b2, rate, kind in events(l, b, float(nu), "M", 0., cap):
            r = nu if kind == "losses" else sp.Rational(3, 10) if kind == "deaths" else sp.Integer(rate)
            Q[row, row] -= r
            if l2:
                Q[row, ix[canonical(l2, b2)]] += r
    return sp.factor((-Q).inv()[ix[canonical(1, 0)], :] * sp.ones(len(states), 1))[0]


def main():
    start = time.perf_counter()
    rows = []
    for nu in (.2, .1):
        for cap in (1, 2, 3):
            m = chain(nu, "M", cap=cap)
            lo = chain(nu, "C2", 2/3, cap)
            hi = chain(nu, "C2", 1., cap)
            row = {"nu": nu, "capacity": cap, "M": m, "C2_low": lo, "C2_high": hi,
                   "ratio_M_C2_high": m["time"] / hi["time"]}
            if cap >= 2:
                root = brentq(lambda x: chain(nu, "C2", x, cap)["time"] - m["time"],
                              2/3, 4., xtol=1e-13)
                row["lambda0_equal_mean_time"] = root
                row["C2_equal_time"] = chain(nu, "C2", root, cap)
            rows.append(row)
    exact = [symbolic_control(nu, cap) for nu in (sp.Rational(1, 5), sp.Rational(1, 10))
             for cap in (1, 2)]
    for e in exact:
        row = next(r for r in rows if r["nu"] == float(sp.Rational(e["nu"])) and r["capacity"] == e["capacity"])
        exact_m = exact_model_time(sp.Rational(e["nu"]), e["capacity"])
        e["T_M_exact"] = str(exact_m)
        assert abs(float(exact_m) - row["M"]["time"]) < 2e-8
        if e["capacity"] == 1:
            assert exact_m > sp.Rational(e["limit_exact"])
            e["M_minus_C2_supremum_exact"] = str(exact_m - sp.Rational(e["limit_exact"]))
            e["no_positive_lambda0_root"] = True
            e["M_over_C2_supremum"] = row["M"]["time"] / e["limit"]
        else:
            assert row["C2_high"]["time"] < row["M"]["time"] < e["limit"]
            e["unique_positive_root"] = row["lambda0_equal_mean_time"]
    budget_rows = []
    for nu, budget in ((.2, 10), (.2, 40), (.1, 100)):
        m = chain(nu, "M", budget=budget)
        lo = chain(nu, "C2", 2/3, budget=budget)
        hi = chain(nu, "C2", 1., budget=budget)
        budget_rows.append({"nu": nu, "birth_budget": budget, "M": m, "C2_low": lo,
                            "C2_high": hi, "ratio_low": m["time"]/lo["time"],
                            "ratio_high": m["time"]/hi["time"]})
    output = {"schema": "g3-contact-capacity-v1", "base_commit": "22c08c86853e8b7ecb7b02cb888a00161d86185f",
              "status": "EXPLORATORY_CLASS_LEVEL_COMPUTED", "parameters": {
                  "n": 3, "lambda_A": 1., "mu_A": .3, "lambda_l": 1., "initial_marks": [1,0,0],
                  "initial_edges": [], "allowed_pairs": list(PAIRS), "divisions": False,
                  "capacity_rule": "Block edge births when number of extant edges equals capacity; no eviction.",
                  "budget_rule": "Successful edge birth consumes one unit; no replenishment; independent of capacity experiments."},
              "capacity_rows": rows, "exact_control_functions": exact, "budget_rows": budget_rows,
              "scope": "Finite declared class only; capacity was selected exploratorily; no physical origin of capacity established.",
              "environment": {"python": platform.python_version(), "numpy": np.__version__,
                              "scipy": scipy.__version__, "sympy": sp.__version__, "platform": platform.platform()},
              "compute_wall_seconds": time.perf_counter()-start}
    target = Path(__file__).with_name("RESULTS.json")
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({"capacity": [{"nu":r["nu"],"Emax":r["capacity"],"M":r["M"]["time"],
            "C2_low":r["C2_low"]["time"],"C2_high":r["C2_high"]["time"],
            "root":r.get("lambda0_equal_mean_time")} for r in rows],
        "limits":[{"nu":e["nu"],"Emax":e["capacity"],"limit":e["limit"],"exact":e["limit_exact"]} for e in exact],
        "budget_ratios":[{"nu":r["nu"],"B":r["birth_budget"],"low":r["ratio_low"],"high":r["ratio_high"]} for r in budget_rows],
        "seconds":output["compute_wall_seconds"]},ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
