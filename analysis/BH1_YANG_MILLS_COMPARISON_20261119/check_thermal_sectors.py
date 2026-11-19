"""Reproduce the common-sector and weak-coupling checks in THERMAL_SECTORS.md."""
import json

import mpmath as mp
import sympy as sp


def check_additions():
    t, r, vol = sp.symbols("T R c", positive=True)
    a = sp.Function("a")(r)
    vac = sp.Function("E_vac")(r)
    phi = sp.Function("phi")
    x = sp.symbols("x", positive=True)
    first, second = [sp.diff(phi(x), x, n).subs(x, t*r) for n in (1, 2)]

    def changes(f):
        s = -f.diff(t)
        e = f+t*s
        p = -f.diff(r)/(3*vol*r**2)
        trace = e-3*p*vol*r**3
        return s, e, t*s.diff(t), trace, trace.diff(t), p

    const = sp.symbols("a0")
    expected = [
        (const*t, (-const, 0, 0, 0, 0, 0)),
        (t*a, (-a, 0, 0, r*t*a.diff(r), r*a.diff(r), -t*a.diff(r)/(3*vol*r**2))),
        (vac, (0, vac, 0, vac+r*vac.diff(r), 0, -vac.diff(r)/(3*vol*r**2))),
        (phi(t*r)/r, (-first, phi(t*r)/r-t*first, -t*r*second, 0, 0,
                      (phi(t*r)-r*t*first)/(3*vol*r**4))),
    ]
    for f, target in expected:
        assert all(sp.simplify(calc-ref) == 0 for calc, ref in zip(changes(f), target))


def summarize(data):
    return {key: mp.nstr(value, 22) for key, value in data.items()}


def photon():
    b = mp.log(2+mp.sqrt(3))  # beta/R
    x = mp.exp(-b)
    logz_modes = energy_modes = cap_modes = mp.mpf(0)
    for k in range(2, 141):
        g = 2*(k**2-1)
        occupation = x**k/(1-x**k)
        logz_modes -= g*mp.log1p(-x**k)
        energy_modes += g*k*occupation
        cap_modes += g*(b*k)**2*occupation*(1+occupation)

    # Bosonic winding-number expansion, evaluated independently.
    def winding(b, cutoff):
        def z(u):
            return (6*u**2-2*u**3)/(1-u)**3
        return sum(z(mp.exp(-b*n))/n for n in range(1, cutoff+1))

    winding_logz = winding(b, 80)
    winding_er = -mp.diff(lambda v: winding(v, 80), b)
    winding_c = b**2*mp.diff(lambda v: winding(v, 80), b, 2)
    differences = [abs(v-w) for v, w in zip(
        (logz_modes, energy_modes, cap_modes), (winding_logz, winding_er, winding_c))]
    assert max(differences) < mp.mpf("1e-45")
    entropy = logz_modes + b*energy_modes
    assert abs(entropy-mp.mpf("5.0871001377583")) < mp.mpf("1e-13")
    assert abs(cap_modes-mp.mpf("18.7486592368210")) < mp.mpf("1e-13")
    jump = 3*b/4
    return summarize(dict(logZ=logz_modes, thermal_ER=energy_modes, S=entropy, C_R=cap_modes,
                          max_two_sums_difference=max(differences), N3_planar_ratio=entropy/(9*jump),
                          S_gamma_c_lambda_A_coefficient=cap_modes/(12*mp.pi**2),
                          dS_gamma_c_dlnR_leading_at_lambda_std_0p1=
                          cap_modes*11*mp.mpf("0.1")**2/(576*mp.pi**4)))


def crossing_control():
    w = (1+mp.sqrt(73))/9
    h = (2-w)/mp.sqrt(w)

    def tc(z):
        return mp.sqrt((mp.sqrt(h**2+4*(1+mp.exp(-4*z)))-h)/2)

    def s(t, z):
        return mp.exp(3*z)*(4*t**3-2*h*t)

    def capacity(t, z):
        return mp.exp(3*z)*(12*t**3-2*h*t)

    def sc(z):
        return s(tc(z), z)

    s0 = sc(0) - mp.mpf("0.05")

    def gap(z, k):
        return s0-sc(z)+k*z

    # Compare both orientations of the integral and a contact.
    residuals = []
    for fixed_s in (s0, sc(0), mp.mpf("2.5"), mp.mpf("3.5"), mp.mpf(5)):
        tad = mp.findroot(lambda t: s(t, 0)-fixed_s, tc(0))
        y = mp.log(tad/tc(0))
        integral = mp.quad(lambda eta: capacity(tc(0)*mp.exp(eta), 0), [0, y])
        residuals.append(abs(integral-(fixed_s-sc(0))))
    assert max(residuals) < mp.mpf("1e-45")

    k = -mp.mpf("0.5")
    zroot = mp.findroot(lambda z: gap(z, k), (-4, -3), solver="bisect", maxsteps=200)
    assert zroot < 0 and abs(gap(zroot, k)) < mp.mpf("1e-45")
    signs = [gap(z, 1) for z in (0, mp.mpf("0.1"), mp.mpf("0.2"))]
    assert signs[0] < 0 < signs[1] and signs[2] < 0
    return summarize(dict(logR_root_minus_half=zroot, R_root_minus_half=mp.exp(zroot),
                          plus_one_gap_at_0=signs[0], plus_one_gap_at_0p1=signs[1],
                          plus_one_gap_at_0p2=signs[2], integral_max_residual=max(residuals)))


def interacting_cold_branch():
    # hep-th/0608156 (4.36). log Z agrees with Z-1 through degree 6.
    b, lam = sp.symbols("b lambda_A", positive=True)
    levels = [(4, 21, 4), (5, 96, 28), (6, 392, 178)]
    logz = sum(sp.exp(-k*b)*(d-coeff*lam*b/sp.pi**2) for k, d, coeff in levels)
    direct = logz-b*sp.diff(logz, b)
    s0 = sum(sp.exp(-k*b)*d*(1+k*b) for k, d, _ in levels)
    ds = -sum(sp.exp(-k*b)*k*coeff*b**2/sp.pi**2 for k, _, coeff in levels)
    assert sp.simplify(direct-s0-lam*ds) == 0
    # Cross-check free multiplicities using the confined SU(N) product
    # prod exp[-z_V(x^n)/n]/(1-z_V(x^n)), not the supplied level table.
    x = sp.symbols("x")
    free_logz = 0
    for n in (1, 2, 3):
        u = x**n
        zv = (6*u**2-2*u**3)/(1-u)**3
        free_logz += sp.series(-zv/n-sp.log(1-zv), x, 0, 7).removeO()
    assert sp.expand(free_logz) == sum(d*x**k for k, d, _ in levels)
    value = {b: sp.log(50), lam: sp.Rational(1, 20)}
    result = {name: str(expr.subs(value).evalf(18)) for name, expr in
            (("S_free_truncated", s0), ("dS_dlambda_A_truncated", ds),
             ("S_at_lambda_A_0p05_truncated", direct))}

    def free_log_product(b_real):
        total = mp.mpf(0)
        for n in range(1, 41):
            u = mp.exp(-n*b_real)
            zv = (6*u**2-2*u**3)/(1-u)**3
            total += -zv/n-mp.log1p(-zv)
        return total

    b_ref = mp.log(50)
    s_product = free_log_product(b_ref)-b_ref*mp.diff(free_log_product, b_ref)
    result["S_free_product_40_terms"] = mp.nstr(s_product, 22)
    result["S_free_omitted_levels"] = mp.nstr(s_product-mp.mpf(result["S_free_truncated"]), 15)
    return result


if __name__ == "__main__":
    mp.mp.dps = 55
    check_additions()
    print(json.dumps(dict(common_additions_checked=4, photon=photon(),
                          matched_initial_state=crossing_control(),
                          cold_SU_low_temperature=interacting_cold_branch()), indent=2))
