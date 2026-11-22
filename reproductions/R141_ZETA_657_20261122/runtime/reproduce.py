"""Full 657-zero numerical replay for R141. No network or external data."""
import hashlib, json, math, os, platform, sys, time, traceback
from pathlib import Path
import mpmath as mp

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results"
OUT.mkdir(parents=True, exist_ok=True)
START = time.perf_counter()
SPOT = [1, 2, 10, 60, 100, 300, 500, 596, 617, 650, 651, 657]
COUNTS = [10, 30, 100, 595, 596, 616, 617, 650, 657]
TOL = mp.mpf("1e-3")

def write(name, obj):
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def bisect_siegelz(a, b, digits=45):
    with mp.workdps(digits):
        a, b = mp.mpf(a), mp.mpf(b)
        fa, fb = mp.siegelz(a), mp.siegelz(b)
        if fa * fb >= 0:
            raise ArithmeticError("Root bracket lost its true Siegel-Z sign change")
        for _ in range(digits * 4):
            m = (a + b) / 2
            fm = mp.siegelz(m)
            if fm == 0:
                return +m
            if fa * fm < 0:
                b, fb = m, fm
            else:
                a, fa = m, fm
            if b - a < mp.power(10, -(digits - 8)):
                break
        return +(a + b) / 2

def xi(s):
    return s * (s - 1) / 2 * mp.power(mp.pi, -s / 2) * mp.gamma(s / 2) * mp.zeta(s)

def main():
    mp.mp.dps = 30
    started = time.perf_counter()
    first = [mp.im(mp.zetazero(n)) for n in range(1, 61)]
    roots = list(first)
    brackets = [{"a": mp.nstr(g-mp.mpf("1e-5"), 35), "b": mp.nstr(g+mp.mpf("1e-5"), 35),
                 "method": "mpmath.zetazero", "index": i+1} for i, g in enumerate(first)]
    scan_start = roots[-1]
    step = mp.mpf("0.1")
    left = scan_start
    fleft = mp.siegelz(left)
    scan_intervals = 0
    scan_limit = mp.mpf("1200")
    while len(roots) < 657:
        right = left + step
        if right > scan_limit:
            raise RuntimeError("Scan reached safety limit before 657 roots")
        fright = mp.siegelz(right)
        scan_intervals += 1
        if fleft * fright < 0:
            root = bisect_siegelz(left, right, 48)
            if root <= roots[-1] + mp.mpf("1e-20"):
                raise ArithmeticError("Duplicate or non-monotone root detected")
            roots.append(root)
            brackets.append({"a": mp.nstr(left, 40), "b": mp.nstr(right, 40),
                             "method": "siegelz_sign_change_bisection", "index": len(roots)})
            if len(roots) % 50 == 0:
                print(f"found {len(roots)}/657 at gamma={mp.nstr(root, 12)}", flush=True)
        left, fleft = right, fright

    if len(roots) != 657 or any(roots[i] >= roots[i+1] for i in range(656)):
        raise AssertionError("Expected exactly 657 strictly increasing roots")

    # Verify a true local sign change for every root using the same Siegel Z.
    mp.mp.dps = 50
    sign_checks = []
    for i, g0 in enumerate(roots):
        g = mp.mpf(g0)
        if i < 60:
            eps = mp.mpf("1e-6")
            a, b = g-eps, g+eps
        else:
            a, b = mp.mpf(brackets[i]["a"]), mp.mpf(brackets[i]["b"])
        za, zb = mp.siegelz(a), mp.siegelz(b)
        sign_checks.append({"index": i+1, "left_sign": int(mp.sign(za)),
                            "right_sign": int(mp.sign(zb)), "true_sign_change": bool(za*zb < 0)})
    if not all(x["true_sign_change"] for x in sign_checks):
        raise AssertionError("At least one indexed root lacks a verified Siegel-Z sign change")

    spot_checks = []
    for n in SPOT:
        ref = mp.im(mp.zetazero(n))
        delta = abs(ref - roots[n-1])
        spot_checks.append({"n": n, "scan_or_seed": mp.nstr(roots[n-1], 45),
                            "mpmath_zetazero": mp.nstr(ref, 45), "abs_difference": mp.nstr(delta, 8),
                            "match_1e-25": bool(delta < mp.mpf("1e-25"))})
    if not all(x["match_1e-25"] for x in spot_checks):
        raise AssertionError("Indexed zetazero spot-check mismatch")

    zeros_payload = {
        "schema": "R141-zeta-zeros-657-v1", "mpmath_version": mp.__version__,
        "dps_root_scan": 30, "dps_bisection": 48, "scan_step": "0.1",
        "seed_method": "mpmath.zetazero(1..60)", "additional_method": "mpmath.siegelz sign-change scan + same-function bisection",
        "scan_intervals": scan_intervals, "roots": [
            {"n": i+1, "gamma": mp.nstr(g, 48), "source": brackets[i]["method"],
             "bracket": [brackets[i]["a"], brackets[i]["b"]]} for i, g in enumerate(roots)],
        "sign_checks": sign_checks, "spot_checks": spot_checks
    }
    write("zeros657.json", zeros_payload)

    # Hadamard partial products; Xi(1)/Xi(0) is independently evaluated from zeta and Gamma.
    target = mp.re(xi(mp.mpf("0.5") + 1j) / xi(mp.mpf("0.5")))
    partial = mp.mpf(1)
    table, first_abs, first_rel = {}, None, None
    for n, g in enumerate(roots, 1):
        partial *= 1 - 1 / (g*g)
        ea, er = abs(partial-target), abs(partial-target)/abs(target)
        if n in COUNTS:
            table[str(n)] = {"partial_product": mp.nstr(partial, 45),
                             "absolute_error": mp.nstr(ea, 18), "relative_error": mp.nstr(er, 18)}
        if first_abs is None and ea < TOL: first_abs = n
        if first_rel is None and er < TOL: first_rel = n
    if first_abs != 596 or first_rel != 617:
        raise AssertionError(f"Unexpected first crossings: abs={first_abs}, rel={first_rel}")

    gaussian = {}
    for aval in ("0.01", "0.1", "1.0"):
        a = mp.mpf(aval)
        s60 = 2 * mp.fsum(mp.exp(-a*g*g) for g in roots[:60])
        s657 = 2 * mp.fsum(mp.exp(-a*g*g) for g in roots)
        gaussian[aval] = {"first_60": mp.nstr(s60, 24), "all_657": mp.nstr(s657, 24),
                          "abs_tail_61_to_657": mp.nstr(abs(s657-s60), 8)}

    # Independent CCC+TL clock integral; do not combine with zeta evidence.
    with mp.workdps(50):
        alpha = -mp.mpf("0.8") * mp.mpf("59.5") / mp.mpf("3.0856775814913673e19")
        fs, u = mp.mpf("3.66"), mp.mpf(1000)
        clock_s = -mp.log(1-alpha*fs*u)/alpha
        clock_rel = (clock_s-mp.mpf(3660))/mp.mpf(3660)

    results = {
        "schema": "R141-zeta-replay-results-v1", "root_count": len(roots),
        "scan_intervals": scan_intervals, "xi_ratio_z1": mp.nstr(target, 45),
        "hadamard_product": {"threshold": "1e-3", "first_absolute_crossing_N": first_abs,
                             "first_relative_crossing_N": first_rel, "table": table},
        "gaussian_sums": gaussian,
        "ccc_tl_clock_separate": {"s_1000_seconds": mp.nstr(clock_s, 25),
                                  "relative_deviation_from_3660": mp.nstr(clock_rel, 8)},
        "timing": {"calculation_seconds": time.perf_counter()-started,
                   "total_seconds": time.perf_counter()-START},
        "environment": {"python": sys.version, "mpmath": mp.__version__,
                        "platform": platform.platform(), "machine": platform.machine(),
                        "cpu_count": os.cpu_count(), "mp_dps_final": mp.mp.dps}
    }
    checks = {
        "root_count_657": len(roots) == 657,
        "strictly_increasing": all(roots[i] < roots[i+1] for i in range(656)),
        "unique": len(set(map(str, roots))) == 657,
        "all_657_true_siegelz_sign_changes": all(x["true_sign_change"] for x in sign_checks),
        "all_indexed_spot_checks_match": all(x["match_1e-25"] for x in spot_checks),
        "hadamard_first_absolute_crossing_596": first_abs == 596,
        "hadamard_first_relative_crossing_617": first_rel == 617,
        "all_requested_product_rows": all(str(n) in table for n in COUNTS),
        "gaussian_three_weights": len(gaussian) == 3,
        "clock_integral_separate": True
    }
    if not all(checks.values()):
        raise AssertionError("One or more R141 replay checks failed")
    write("results.json", results)
    write("CHECKS.json", {"status": "PASS_NUMERICAL_REPLAY", "checks": checks})
    print(json.dumps({"status": "PASS_NUMERICAL_REPLAY", "roots": len(roots),
                      "scan_intervals": scan_intervals, "first_abs": first_abs,
                      "first_rel": first_rel, "seconds": results["timing"]["calculation_seconds"]}), flush=True)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        write("FAILURE.json", {"status": "FAILED", "traceback": traceback.format_exc(),
                               "elapsed_seconds": time.perf_counter()-START})
        raise
