"""Symbolic equilibrium tests for YM_THERMAL_BRIDGE. Requires SymPy (tested with 1.14.0)."""
import json

import sympy as sp


T, R, c, scale, h = sp.symbols("T R c Lambda h", positive=True)


def thermodynamics(f):
    entropy = -sp.diff(f, T)
    energy = f + T*entropy
    pressure = -sp.diff(f, R)/(3*c*R**2)
    trace = sp.simplify(energy - 3*pressure*c*R**3)
    heat_capacity = T*sp.diff(entropy, T)
    return entropy, energy, pressure, trace, heat_capacity


def local_flows():
    f = sp.Function("F")(T, R)
    entropy, _, pressure, trace, cap = thermodynamics(f)
    assert sp.simplify(trace - (f-T*sp.diff(f, T)+R*sp.diff(f, R))) == 0
    assert sp.simplify(pressure.subs(c, 2*sp.pi**2) + sp.diff(f, R)/(6*sp.pi**2*R**2)) == 0
    t_slope = -sp.diff(entropy, R)/sp.diff(entropy, T)
    assert sp.simplify(1 + R*t_slope/T - sp.diff(trace, T)/cap) == 0
    boundary_t_slope = sp.symbols("boundary_t_slope")
    sc_slope = R*(sp.diff(entropy, R) + boundary_t_slope*sp.diff(entropy, T))
    assert sp.simplify(R*(t_slope-boundary_t_slope)/T + sc_slope/cap) == 0
    shape = sp.Function("phi")
    assert thermodynamics(shape(T*R)/R)[3] == 0
    scaled = shape(T*R, scale*R)/R
    assert sp.simplify(thermodynamics(scaled)[3] - scale*sp.diff(scaled, scale)) == 0


def cancellation():
    # Explicit R-dependence of both total free energies. The review supplied
    # their restriction to R=1 and first-derivative data there.
    f1 = R**3*(-T**4+h*T**2)
    f2 = -2*R**3*T**4 + 1/R + R**3
    s1, e1, _, d1, cap = thermodynamics(f1)
    _, e2, _, d2, cap2 = thermodynamics(f2)
    w = sp.symbols("w", positive=True)  # w=Tc^4 at R=1 in the chosen units
    t0 = w**sp.Rational(1, 4)
    h0 = (2-w)/sp.sqrt(w)
    point = {R: 1, T: t0, h: h0}
    assert sp.simplify((f2-f1).subs(point)) == 0
    theta = sp.factor((sp.diff(d1, T)/cap - (d2-d1)/(e2-e1)).subs(point))
    assert sp.factor(theta + (9*w**2-2*w-8)/((w+2)*(7*w-2))) == 0
    root = (1+sp.sqrt(73))/9
    assert sp.simplify(theta.subs(w, root)) == 0

    def at_star(expr):
        return sp.simplify(expr.subs(point).subs(w, root))

    assert all(at_star(v) > 0 for v in (e2-e1, d2-d1, cap, cap2))
    # If G(T,R)=constant, compute the first two derivatives of ln(T) w.r.t.
    # ln(R) by implicit differentiation without sampling neighboring roots.
    def log_slopes(g):
        dt_dr = -sp.diff(g, R)/sp.diff(g, T)
        first = R*dt_dr/T
        second = R*(sp.diff(first, R) + dt_dr*sp.diff(first, T))
        return first, second

    first_s, second_s = log_slopes(s1)
    first_c, second_c = log_slopes(f2-f1)
    assert at_star(first_s-first_c) == 0
    curvature = at_star(second_s-second_c)
    assert sp.simplify(curvature - (627*sp.sqrt(73)-6009)/1024) == 0
    return dict(Tc=float(t0.subs(w, root)), h=float(h0.subs(w, root)),
                delta_D=float(at_star(d2-d1)), delta_E=float(at_star(e2-e1)),
                common_log_TR_slope=float(at_star(sp.diff(d1,T)/cap)),
                relative_slope=0, relative_curvature=float(curvature))


def stationary_boundary():
    f1 = -R**3*T**4 + R**3*T**2/2
    f2 = -2*R**3*T**4 + 1/R + R**3*T**2/2
    _, e1, _, d1, cap = thermodynamics(f1)
    _, e2, _, d2, _ = thermodynamics(f2)
    point = {R: 1, T: 1}
    assert (f2-f1).subs(point) == 0 and (d2-d1).subs(point) == 0
    assert (e2-e1).subs(point) == 4
    assert (sp.diff(d1,T)/cap).subs(point) == sp.Rational(2,11)


if __name__ == "__main__":
    local_flows()
    stationary_boundary()
    print(json.dumps(dict(cancellation=cancellation(), stationary_boundary_relative_slope="2/11"),
                     indent=2))
