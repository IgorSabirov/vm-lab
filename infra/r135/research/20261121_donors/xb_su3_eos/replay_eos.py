"""Reconstruct the stable, dimensionless literature EOS. Run next to donor_inputs.json."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.integrate import quad
from scipy.interpolate import PchipInterpolator
from scipy.special import kv

HERE = Path(__file__).resolve().parent
DOMAIN = {"cold": (0.8, 1.0), "hot": (1.0, 3.433)}


def rational(w, coeff):
    a, b, c, d, e = coeff
    num, den = a + w * (b + c*w), 1 + w * (d + e*w)
    value = num / den
    slope = (b + 2*c*w - value*(d + 2*e*w)) / den
    return value, slope


def fits(data, phase, temperature):
    """Return s/T^3, p_fit/T^4, dq_s/dlnT. Scalar and array inputs share domain checks."""
    x = np.asarray(temperature, dtype=float)
    lo, hi = DOMAIN[phase]
    if not np.all(np.isfinite(x) & (x >= lo) & (x <= hi)):
        raise ValueError(f"{phase} equilibrium fit requires {lo} <= T/Tc <= {hi}")
    if phase == "hot":
        w = np.log(x)
        qs, qp, slope = (np.empty(x.shape) for _ in range(3))
        for j, mask in enumerate((x <= 1.1, x > 1.1)):
            qs[mask], slope[mask] = rational(w[mask], data["entropy_fit"]["hot"][j])
            qp[mask] = rational(w[mask], data["pressure_fit"]["hot"][j])[0]
        if x.ndim == 0:
            return qs.item(), qp.item(), slope.item()
        return qs, qp, slope
    u = np.cbrt(1-x)
    a, b, c, d = data["entropy_fit"]["cold"]
    qs = a + u*(b + u*(c + u*d))
    qp = np.polynomial.polynomial.polyval(1-x, data["pressure_fit"]["cold"])
    slope = np.full(x.shape, np.nan)
    np.divide(-x*(b + 2*c*u + 3*d*u*u), 3*u*u, out=slope, where=u > 0)
    if x.ndim == 0:
        return qs.item(), float(qp), slope.item()
    return qs, qp, slope


def glue_gas(data, scale, x):
    """Ideal Bose gas. scale = Tc/sqrt(sigma_string)."""
    n = np.arange(1, 100)
    qp, qs = 0.0, 0.0
    for _, spin, mass, _ in data["glueball_m_over_sqrt_string_tension"]:
        z = mass / (scale*x)
        prefactor = (2*spin+1)*z*z/(2*np.pi**2)
        p = prefactor * np.sum(kv(2,n*z) / n**2)
        qp += p
        qs += 4*p + prefactor*z*np.sum(kv(1,n*z)/n)
    return qp, qs


def knots(data, phase):
    rows = [r for r in data["table3"] if (r["T_over_Tc"] < 1) == (phase == "cold")]
    endpoint = dict(T_over_Tc=1., **data["coexistence"][phase])
    return sorted([*rows, endpoint], key=lambda r:r["T_over_Tc"])


def anchor(data, scale, sigma_shift=0):
    """Explicit reconstruction choice: linear log(s/T^3) between measured x knots."""
    rows = knots(data, "cold")
    x = [r["T_over_Tc"] for r in rows]
    log_q = np.log([r["value"] + sigma_shift*r["sigma"] for r in rows])
    gas_p = x[0]**4*glue_gas(data, scale, x[0])[0]
    area = quad(lambda u: u**3*np.exp(np.interp(u,x,log_q)), x[0], 1,
                points=x[1:-1], epsabs=1e-12)[0]
    return gas_p + area


def stable_row(data, phase, x, pc, interp):
    qs, qp, slope = (float(v) for v in fits(data, phase, x))
    def entropy_at(u):
        return u**3*float(fits(data, phase, u)[0])
    pressure = pc + quad(entropy_at, 1., x, points=[1.1] if x > 1.1 else None,
                         epsabs=1e-12)[0]
    entropy = x**3 * qs
    enthalpy = x*entropy
    derivative = 3*qs + slope
    fit_cs2 = qs / derivative if np.isfinite(derivative) and derivative > 0 else None
    if fit_cs2 is not None and fit_cs2 > 1:
        fit_cs2 = None
    # Derivative of a shape-preserving interpolation of measured s/Tc^3 only.
    point_cs2 = None
    if interp.x[0] <= x <= interp.x[-1]:
        ds = float(interp.derivative()(x))
        if ds > 0:
            point_cs2 = float(interp(x)) / (x*ds)
    return dict(x=x, s_Tc3=entropy, p_Tc4=pressure, rho_Tc4=enthalpy-pressure,
                w_Tc4=enthalpy, p_fit_residual_Tc4=x**4*qp-pressure,
                cs2_fit_diagnostic=fit_cs2, cs2_table_pchip_diagnostic=point_cs2)


def nearest_root(coeff):
    roots = np.roots(coeff)
    return float(max(np.exp(z.real) for z in roots if abs(z.imag)<1e-12 and z.real<0))


def review_controls(data, pc):
    """Controls of numerical claims in the second review; no physical history is run."""
    from scipy.optimize import brentq

    cold = knots(data,"cold")
    x = np.array([r["T_over_Tc"] for r in cold])
    s = x**3*np.array([r["value"] for r in cold])
    err = x**3*np.array([r["sigma"] for r in cold])
    secant = PchipInterpolator(x,s)
    pull = []
    for row in data["table3"]:
        t = row["T_over_Tc"]
        phase = "cold" if t < 1 else "hot"
        residual = float(fits(data,phase,t)[0]) - row["value"]
        pull.append(abs(residual)/row["sigma"])
    # Two declared covariance scenarios, centered quadratic on measured s/Tc^3.
    X = np.polynomial.polynomial.polyvander(x-1,2)
    alternatives = {}
    for corr in (0.,0.5):
        cov_y = (1-corr)*np.diag(err**2) + corr*np.outer(err,err)
        whiten = np.linalg.cholesky(cov_y)
        D = np.linalg.solve(whiten,X)
        coeff = np.linalg.lstsq(D,np.linalg.solve(whiten,s),rcond=None)[0]
        cov_b = np.linalg.solve(D.T@D,np.eye(3))
        grad = np.array([1/coeff[1],-coeff[0]/coeff[1]**2,0])
        alternatives[str(corr)] = {
            "coef_sbar_quadratic_in_x_minus_1":coeff.tolist(),
            "conditional_coefficient_covariance":cov_b.tolist(),
            "endpoint_cs2":float(coeff[0]/coeff[1]),
            "linearized_conditional_sigma":float(np.sqrt(grad@cov_b@grad)),
            "positive_slope_on_fitted_interval":bool(min(coeff[1],coeff[1]-.4*coeff[2])>0)
        }
    endpoint_refits = {}
    for degree in (2,3,4):
        poly = np.polynomial.Polynomial.fit(x,s,degree)
        deriv = poly.deriv()
        critical = [float(z.real) for z in deriv.deriv().roots()
                    if abs(z.imag)<1e-12 and x[0] < z.real < 1.]
        min_slope = min(float(deriv(t)) for t in [x[0],1.,*critical])
        endpoint_refits[str(degree)] = {
            "cs2_at_Tc":float(poly(1.)/deriv(1.)),
            "minimum_dsbar_dx_over_interval":min_slope}
    def cold_heat(t):
        q,_,d = fits(data,"cold",t)
        return float(3*q+d)
    turning = brentq(cold_heat,1-1e-4,1-1e-8,xtol=1e-15)
    nominal_t = 0.99931
    cold_row = stable_row(data,"cold",nominal_t,pc,secant)
    e_minus,p_minus = cold_row["rho_Tc4"],cold_row["p_Tc4"]
    e_plus = data["coexistence"]["hot"]["value"] - pc
    product = (pc-p_minus)/(e_plus-e_minus)
    ratio = (e_minus+pc)/(e_plus+p_minus)
    v_minus,v_plus = np.sqrt(product/ratio),np.sqrt(product*ratio)
    entropy_flux_gain = (cold_row["s_Tc3"]*v_minus/np.sqrt(1-v_minus**2)
                         -data["coexistence"]["hot"]["value"]*v_plus/np.sqrt(1-v_plus**2))
    scale = data["Tc_over_sqrt_string_tension"]["repository"]["value"]
    pc_from_fit = 0.8**4*glue_gas(data,scale,0.8)[0] + quad(
        lambda t:t**3*float(fits(data,"cold",t)[0]),0.8,1)[0]
    return {"max_absolute_pull_25_table_rows":max(pull),
            "scale_author":scale, "mass_over_Tc":[m/scale for _,_,m,_ in data["glueball_m_over_sqrt_string_tension"]],
            "gas_s_T3_on_author_scale":{str(t):glue_gas(data,scale,t)[1] for t in (0.8,0.9,0.95,1.0)},
            "common_anchor_using_cold_fit":pc_from_fit,
            "last_cold_fit_heat_capacity_zero_x":turning,
            "smooth_fit_scenarios":alternatives, "unweighted_sbar_refits":endpoint_refits,
            "rankine_hugoniot_example":{"T_plus_Tc":1,"T_minus_Tc":nominal_t,
                "v_minus_wall_frame":v_minus,"v_plus_wall_frame":v_plus,
                "out_minus_in_entropy_flux_Tc3":entropy_flux_gain,
                "scope":"prescribed temperatures and planar flux conservation; no velocity-selection law or percolation"},
            "alpha_at_Tc_from_combined_L":data["latent_heat"]["combined"][0]/(3*data["coexistence"]["hot"]["value"])}


def build(data, source_hash):
    scales = {k:v["value"] for k,v in data["Tc_over_sqrt_string_tension"].items()}
    pc = anchor(data, scales["repository"])
    grids = {}
    for phase in DOMAIN:
        rows = knots(data, phase)
        xx = np.array([r["T_over_Tc"] for r in rows])
        yy = [r["value"] for r in rows]
        interp = PchipInterpolator(xx, xx**3*yy, extrapolate=False)
        extra = [0.99931] if phase == "cold" else [3.433]
        grids[phase] = [stable_row(data,phase,x,pc,interp) for x in sorted(set(xx) | set(extra))]
    a,b,c,d,e = data["entropy_fit"]["hot"][0]
    join = []
    for co in data["entropy_fit"]["hot"]:
        q,dq = rational(np.log(1.1),co)
        join.append(dict(s_T3=q,cs2_fit_diagnostic=q/(3*q+dq)))
    hp = data["pressure_fit"]["hot"][0]
    cp = data["pressure_fit"]["cold"]
    return {
        "name":"XB_SU3_EOS_PAIR_v0.1", "status":"STABLE_EQUILIBRIUM_DONOR_CONTROL",
        "peer_review_controls":review_controls(data,pc),
        "input_sha256":source_hash, "physical_launch_authorized":False, "x":"T/Tc",
        "source":data["provenance"], "domain":DOMAIN, "stable":grids,
        "anchor":{"p_Tc4":pc, "method":"four-state gas at 0.8, then linear log(s/T^3) in x at cold knots; integrate x^3 q_s",
                  "by_scale":{k:anchor(data,v) for k,v in scales.items()},
                  "simultaneous_one_marginal_error_lower_upper_at_fixed_scale":
                      [anchor(data,scales["repository"],shift) for shift in (-1,1)],
                  "scope":"scale choices and cold-node envelope; partial sensitivity only"},
        "cold_gas_control":{k:{str(x):dict(zip(("p_T4","s_T3"),glue_gas(data,v,x)))
                               for x in (0.8,1.0)} for k,v in scales.items()},
        "diagnostics":{"nearest_hot_fit_pole_x":nearest_root([e,d,1]),
                       "nearest_hot_fit_numerator_zero_x":nearest_root([c,b,a]),
                       "hot_join_left_right":join,
                       "entropy_from_pressure_fit_at_Tc":{"hot":4*hp[0]+hp[1]-hp[0]*hp[3],"cold":4*cp[0]-cp[1]}},
        "covariance":{"status":"OPEN_INPUT","matrix":None,
                      "available":"marginal Table 3 / phase errors in donor_inputs.json; the combined latent heat shares inputs",
                      "cs2":"interpolation sensitivity; endpoint and knot estimates have no calibrated joint uncertainty"},
        "metastability":{"status":"OPEN_INPUT","hot_below_Tc":None,"cold_above_Tc":None,
                         "candidates":["SFtX figure 15; finite-volume phase-resolved enthalpy",
                                       "HPR effective potential; test phase-wise thermodynamics and common background",
                                       "LLR/SNOBEX; require physical conversion or source table and systematics"]},
        "delta_p_Tc4":{"at_coexistence":0.,"off_coexistence":None},
        "handoff":{"hydro_ready":False,"A_T":None,"physical_v_wall":None,"GW_source":None}
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = (HERE/"donor_inputs.json").read_bytes()
    data = json.loads(raw)
    result = build(data,hashlib.sha256(raw).hexdigest())
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+"\n")


if __name__ == "__main__":
    main()
