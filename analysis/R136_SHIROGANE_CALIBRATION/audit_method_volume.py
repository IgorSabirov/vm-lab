"""R136 / U013, issue 201. Reproduce the two-volume method interaction."""
import json
from pathlib import Path

import numpy as np
from scipy.stats import chi2, norm

from audit_statistical_budget import contour, zscore

HERE = Path(__file__).resolve().parent
VOLUMES = ("48", "64")


def summarize(derivative, sftx):
    derivative = np.asarray(derivative)
    sftx = np.asarray(sftx)
    residual = derivative[:, 0] - sftx[:, 0]
    sigma = np.hypot(derivative[:, 1], sftx[:, 1])
    delta = float(residual[0] - residual[1])
    sd = np.linalg.norm(sigma)
    mean = np.mean(residual)
    independent_z = delta / sd
    weights = 1 / sigma**2
    return {
        "method_minus_sftx": residual.tolist(), "sigma_diagonal": sigma.tolist(),
        "individual_z": (residual/sigma).tolist(),
        "equal_weight_mean": mean, "mean_sigma_diagonal": sd/2, "mean_z": mean/(sd/2),
        "largest_mean_sigma_at_fixed_residual_errors": sum(sigma)/2,
        "inverse_variance_constant_fit": np.average(residual, weights=weights),
        "constant_fit_sigma": 1/np.sqrt(sum(weights)),
        "interaction": delta, "interaction_sigma_diagonal": sd,
        "interaction_z": independent_z, "nominal_two_sided_p": 2*norm.sf(abs(independent_z)),
        "both_residuals_zero_nominal_p_df2": chi2.sf(sum((residual/sigma)**2), 2),
        "interaction_z_by_residual_correlation": {
            str(r): delta/np.sqrt(sd**2 - 2*r*np.prod(sigma)) for r in (-.5, 0, .3, .5)
        },
        "residual_correlation_at_1_96": (sd**2 - (delta/1.96)**2)/(2*np.prod(sigma)),
    }


def main():
    figs = json.loads((HERE/"FIGURES.json").read_text())
    checks = json.loads((HERE/"CHECKS.json").read_text())
    budget = json.loads((HERE/"STATISTICAL_BUDGET.json").read_text())
    derivative = [figs[v]["fig13_derivative_jump_error"] for v in VOLUMES]
    methods = {t: summarize(derivative, [figs[v]["fig3_jump_error"][t] for v in VOLUMES])
               for t in ("0", "1.4")}
    gap = np.array([checks["volumes"][v]["fig15_fig3_curve"]["residual"] for v in VOLUMES])
    central = budget["provenance"]["canonical_curve_reconstruction"]["value"]
    rows = budget["local_inputs"]
    k48, k64 = np.abs(budget["axis"]["horizontal_derivatives"])
    # For fixed nonnegative rho_153 the variance is convex in rho_hc, so its
    # maximum on [0,1] is attained at an endpoint (sqrt of an affine function).
    thresholds = [contour(rows, central, h, 0.) for h in (0., 1.)]
    threshold_all = max(thresholds)
    hgrid = np.linspace(0,1,1001)
    assert np.isclose(min(zscore(rows, central, hgrid, threshold_all, 0)),1.96)
    # Direct transcription: Shirogane 2016 Table VI, 2021 Table 2 NNLO mu0.
    trace_deriv = [(1.48,.08), (1.04,.03)]
    trace_sftx = [(1.256,.034), (1.171,.028)]
    trace = summarize(trace_deriv, trace_sftx)
    max_sigma = sum(v[1] for v in trace_deriv + trace_sftx)
    # Conventionally rounded last digits of the four displayed values and errors.
    rounding_margin = .005+.005+.0005+.0005
    trace.update(derivative_inputs=trace_deriv,sftx_inputs=trace_sftx,
                 upper_sigma_all_PSD_for_displayed_marginals=max_sigma,
                 min_abs_z_displayed=abs(trace["interaction"])/max_sigma,
                 conservative_rounding_sensitivity=(abs(trace["interaction"])-rounding_margin)/(max_sigma+rounding_margin))
    m0, m14 = methods["0"], methods["1.4"]
    delta15 = gap[0]-gap[1]
    d13 = derivative[0][0]-derivative[1][0]
    j15 = [checks["volumes"][v]["fig15_fig3_curve"]["J_at_beta_c"] for v in VOLUMES]
    same_time = m14["interaction"]-delta15
    assert np.isclose(same_time,d13-(j15[0]-j15[1]),rtol=0,atol=2e-7)  # archived fields rounded
    r48, r64 = m0["method_minus_sftx"]
    data = dict(
        question="R136 / U013 / #201", scientific_status="OPEN",
        assumptions="First-order Gaussian sensitivity; diagonal errors unless varied. Times and observables share data. Tables and EPS carry published marginal errors only.",
        source_files=["FIGURES.json","CHECKS.json","STATISTICAL_BUDGET.json"],
        axis=dict(common_k=k64-k48,opposite_k=-(k48+k64),differential_coordinate="dx48=+h, dx64=-h"),
        D_scenarios=dict(hc_endpoints_thresholds=thresholds, uniform_threshold=threshold_all,
            z_hc1_r153_082=zscore(rows,central,1,.82,0),z_hc1_r153_1=zscore(rows,central,1,1,0),
            beta_c_scenarios=[dict(rho_beta=rb,sigma_D=abs(central)/zscore(rows,central,0,0,rb),
                                   z_uncorrelated_J=zscore(rows,central,0,0,rb),
                                   z_hc09_r15309=zscore(rows,central,.9,.9,rb))
                              for rb in (0,.5,1)]),
        method_enthalpy=methods, method_trace_t0=trace,
        shared_data=dict(fig15_minus_fig3_at_predicted_beta=delta15,
            ratio_t0_to_fig15=m0["interaction"]/delta15,
            ratio_t14_to_fig15=m14["interaction"]/delta15,
            enthalpy_interaction_time_difference=m14["interaction"]-m0["interaction"],
            fig13_minus_fig15_volume_contrast_t14=same_time),
        two_point_extrapolation=dict(intercepts={str(power):r64-(r48-r64)/((64/48)**power-1) for power in (2,3)},
                                     degrees_of_freedom=0))
    print(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
