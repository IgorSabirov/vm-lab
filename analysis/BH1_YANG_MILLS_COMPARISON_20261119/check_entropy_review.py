"""Exact checks for ENTROPY_REVIEW.md. Run with Python and SymPy 1.14.0."""
import json

import sympy as sp


def zero(expr):
    assert sp.simplify(expr) == 0, expr


def contact_identity():
    # In log-temperature coordinates S_q = C_R. Differentiate the equality
    # S(q_c + y,z) = S0 at a contact of equal slope (y = y' = 0).
    z = sp.symbols("z", real=True)
    q, slope, acceleration, curvature = sp.symbols("q slope acceleration curvature")
    entropy = sp.Function("S")(q, z)
    first = entropy.diff(z) + slope*entropy.diff(q)
    second = first.diff(z) + slope*first.diff(q) + acceleration*first.diff(slope)
    # Compute the two derivatives at the same (q,z) and the same first slope.
    zero(second.subs(acceleration, acceleration + curvature) - second
         - entropy.diff(q)*curvature)

    # Stationary inflection at a genuine coexistence line, with positive
    # heat capacity and nonzero latent heat on both sides of z=0.
    t, c, s0, latent = sp.symbols("T c S0 L", positive=True)
    f1 = -(s0 + z**3)*(t-1) - c*(t-1)**2/2
    f2 = f1 - latent*(t-1)
    entropy1 = -f1.diff(t)
    trajectory = 1 - z**3/c
    zero((f2-f1).subs(t, 1))
    zero(-(f2-f1).diff(t) - latent)
    zero(t*entropy1.diff(t) - c*t)
    zero(entropy1.subs(t, trajectory) - s0)
    for k in (1, 2):
        zero(sp.diff(sp.log(trajectory), z, k).subs(z, 0))
    zero(sp.diff(sp.log(trajectory), z, 3).subs(z, 0) + 6/c)


def global_control():
    u, h = sp.symbols("u h", positive=True)
    q = u**2 + h*u - 1  # R^(-4) on the coexistence line
    sc = 2*sp.sqrt(u)*(2*u-h)/q**sp.Rational(3, 4)
    denominator = 4*u*(2*u-h)*q
    p = 10*h*u**2 + (h**2-12)*u + 2*h
    zero(denominator * sc.diff(u)/sc - p)
    w = (1+sp.sqrt(73))/9
    u0 = sp.sqrt(w)
    h0 = (2-w)/u0
    zero(q.subs({h: h0, u: u0}) - 1)
    zero(p.subs(h, h0) - 10*h0*(u-u0)*(u-1/(5*u0)))
    # q is strictly increasing at u>0. Hence u_inf lies between 1/2 and
    # u0; the smaller root of p is outside the physical interval q>0.
    assert (0 < h0) and (h0 < 1) and (u0 > 1)
    assert q.subs({h: h0, u: sp.Rational(1, 2)}) < 0
    zero(sp.limit(sc, u, sp.oo) - 4)
    s_min = 2*sp.sqrt(u0)*(2*u0-h0)
    assert (s_min > 0) and (s_min < 4)
    du_dz = -4*q/(2*u+h)
    cap = 2*sp.sqrt(u0)*(6*u0-h0)
    curvature = (627*sp.sqrt(73)-6009)/1024
    # At the stationary point sc'=p=0, hence sc_zz = (du/dz)^2 * sc*p'/den.
    # Take the ratio to C_R before inserting radicals (q=1 at R=1).
    heat_here = 2*sp.sqrt(u)*(6*u-h)
    ratio = sp.factor(du_dz**2 * sc * p.diff(u)/(denominator*heat_here))
    ratio_at_one = sp.factor(ratio / q**sp.Rational(1, 4))
    # Stripped factor q^(1/4) is exactly one at the contact.
    aux = sp.symbols("v", positive=True)
    reduced_ratio = sp.factor(ratio_at_one.subs({u: aux, h: (2-aux**2)/aux}))
    zero(reduced_ratio.subs(aux, u0) + curvature)
    sc_second = -cap*curvature
    return dict(S_min=float(s_min), C_R=float(cap), S_c_second=float(sc_second),
                relative_curvature=float(curvature), R_to_zero_entropy_limit=4)


def ym_matching():
    # Eq. (1.2), hep-th/0608156; coupling conversion directly after (5.1).
    # Eq. (4.1), hep-th/0412029, for alpha_s*N = lambda_std/(4*pi).
    std, a, log_scale = sp.symbols("lambda_std lambda_A L", positive=True)
    alpha_n = std/(4*sp.pi)
    beta_std = 4*sp.pi*(-sp.Rational(11, 3)*alpha_n**2/(2*sp.pi))
    beta_a = beta_std.subs(std, 2*a)/2
    slope_a = -beta_a/(12*sp.pi**2)  # leading term in d ln(Tc R)/d ln R
    slope_std = -beta_std/(24*sp.pi**2)
    zero(slope_a.subs(a, std/2) - slope_std)
    zero(slope_std - 11*std**2/(576*sp.pi**4))
    std_running = 24*sp.pi**2/(11*log_scale)
    zero(std_running.diff(log_scale) - beta_std.subs(std, std_running))
    zero(slope_std.subs(std, std_running) - 1/(11*log_scale**2))
    return [dict(L=int(k), lambda_std=float(std_running.subs(log_scale, k)),
                 lambda_A=float(std_running.subs(log_scale, k)/2),
                 relative_TcR_shift_LL=float(1/(11*k)),
                 v_c_LL=float(1/(11*k**2))) for k in map(sp.Integer, (10, 20, 100))]


def free_planar_jump():
    x = sp.symbols("x", positive=True)
    z_v = (6*x**2-2*x**3)/(1-x)**3
    x_h = 2-sp.sqrt(3)
    zero(z_v.subs(x, x_h) - 1)
    # Eq. (5.15), hep-th/0310285, implies R*Delta E/N^2=x_H*z'_V(x_H)/4.
    reduced_energy = sp.simplify((x*z_v.diff(x)/4).subs(x, x_h))
    zero(reduced_energy - sp.Rational(3, 4))
    entropy_jump = reduced_energy*sp.log(2+sp.sqrt(3))
    return dict(R_delta_E_per_N2=str(reduced_energy), delta_S_per_N2=float(entropy_jump))


if __name__ == "__main__":
    contact_identity()
    print(json.dumps(dict(global_control=global_control(), free_planar=free_planar_jump(),
                          one_loop_examples=ym_matching()), indent=2))
