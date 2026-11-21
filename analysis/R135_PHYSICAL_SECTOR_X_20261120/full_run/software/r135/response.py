"""P4: explicitly prepared real-time response and censored relaxation estimates.

A row-generator evolves row probability vectors as p(t)=p(0) exp(Q t).
Its time coordinate is physical seconds only when an independent calibration
is supplied. Monte Carlo sweep numbers and Euclidean time are not accepted as
seconds. Scalar single-exponential fits are a declared estimator, not a claim
that every correlator has one pole. Two-time data retain each preparation time.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

from .common import InputError, OpenInput, read_json

import numpy as np
from scipy.integrate import trapezoid
from scipy.linalg import expm


def validate_generator(generator, stationary=None, tolerance=1e-11):
    q = np.asarray(generator,dtype=float)
    if q.ndim != 2 or q.shape[0] != q.shape[1] or len(q) < 2 or not np.all(np.isfinite(q)):
        raise InputError("generator must be a finite square matrix of order at least two")
    off = q.copy(); np.fill_diagonal(off,0)
    scale = max(float(np.abs(q).max()),1)
    if np.any(off < 0) or not np.allclose(q.sum(axis=1),0,rtol=0,atol=tolerance*scale):
        raise InputError("row generator needs nonnegative off-diagonals and zero row sums")
    if stationary is not None:
        pi = np.asarray(stationary,dtype=float)
        if pi.shape != (len(q),) or not np.all(np.isfinite(pi)) or np.any(pi < 0) or not np.isclose(pi.sum(),1,atol=tolerance):
            raise InputError("invalid stationary probability distribution")
        if np.max(np.abs(pi@q)) > tolerance*scale:
            raise InputError("provided equilibrium is not stationary for the generator")
    return q


def generator_response(generator, observable, perturbation, times, stationary=None):
    """Compute the impulse-preparation response δp exp(Qt) O without fitting.

    perturbation is an explicitly supplied zero-sum derivative of the prepared
    probability distribution. Its normalization defines the response units.
    """
    q=validate_generator(generator,stationary)
    obs=np.asarray(observable,float); dp=np.asarray(perturbation,float); t=np.asarray(times,float)
    if obs.shape != (len(q),) or dp.shape != obs.shape or not np.all(np.isfinite(obs)) or not np.all(np.isfinite(dp)):
        raise InputError("observable and perturbation must match generator states")
    if abs(dp.sum()) > 1e-12*max(float(np.abs(dp).sum()),1):
        raise InputError("probability perturbation must have zero sum")
    if t.ndim!=1 or len(t)<3 or not np.all(np.isfinite(t)) or np.any(np.diff(t)<=0) or t[0]!=0:
        raise InputError("response times must start at zero and increase strictly")
    response=np.array([dp@expm(q*ti)@obs for ti in t])
    # Eigenvalue zero cannot contribute to a normalized perturbation if the
    # observable projects on a unique equilibrium; non-ergodicity is retained.
    return response


def equilibrium_response(generator, stationary, observable, times, temperature):
    """Detailed-balance Kubo response to an impulsive field coupled to O.

    R(t)=-dC(t)/dt/T for t>=0. Here Q is a physical-time Markov generator and
    detailed balance is explicitly checked before invoking this relation.
    """
    q=validate_generator(generator,stationary)
    pi=np.asarray(stationary,float); obs=np.asarray(observable,float)
    if obs.shape!=pi.shape or not math.isfinite(temperature) or temperature<=0:
        raise InputError("invalid equilibrium observable/temperature")
    flux=pi[:,None]*q
    if not np.allclose(flux,flux.T,rtol=1e-10,atol=1e-12*max(float(np.abs(q).max()),1)):
        raise InputError("Kubo implementation requires detailed balance")
    centered=obs-pi@obs
    return generator_response(q,centered,-(pi*centered)@q/temperature,times,pi)


def relaxation_estimate(times, values, sigma=None, fit_window=None,
                        tail_threshold=0.02, require_resolved_tail=True):
    """Fit a single positive decay, separately retaining integral and tail error.

    The reported tau lower bound for an unresolved positive monotone trace is
    the observed area divided by its initial value. No fitted extrapolation is
    promoted to a measured decay when the requested tail criterion fails.
    Confidence bounds assume independent supplied point errors; correlated
    response measurements should be pre-resampled as independent replicates.
    """
    t=np.asarray(times,float); y=np.asarray(values,float)
    if t.ndim!=1 or y.shape!=t.shape or len(t)<4 or not np.all(np.isfinite(t)) or not np.all(np.isfinite(y)):
        raise InputError("response arrays must be finite and have at least four samples")
    if t[0]!=0 or np.any(np.diff(t)<=0) or y[0]==0:
        raise InputError("response starts at time zero with a nonzero observable overlap")
    normalized=y/y[0]
    if not math.isfinite(tail_threshold) or not 0<tail_threshold<1:
        raise InputError("invalid tail threshold")
    area=float(trapezoid(normalized,t))
    monotone=bool(np.all(np.diff(normalized)<=1e-10) and np.all(normalized>=0))
    result={"observed_integral":area,"final_relative_amplitude":float(normalized[-1]),
            "positive_monotone":monotone,"fit_model":"single exponential",
            "resolved":False,"tau":None,"tau_ci95":None,"tail_integral":None,
            "tau_lower_bound":area if monotone else None}
    if not monotone:
        result["reason"]="non-monotone or sign-changing response needs a registered multi-mode estimator"
        return result
    mask=(normalized>0)
    if fit_window is not None:
        lo,hi=map(float,fit_window)
        if not 0<=lo<hi<=t[-1]:
            raise InputError("fit window outside response domain")
        mask &= (t>=lo)&(t<=hi)
    if np.count_nonzero(mask)<3:
        result["reason"]="fewer than three positive samples in fit window"
        return result
    xx=t[mask]; yy=np.log(normalized[mask])
    if sigma is None:
        weights=np.ones(len(xx))
    else:
        err=np.asarray(sigma,float)
        if err.shape!=t.shape or not np.all(np.isfinite(err)) or np.any(err<=0):
            raise InputError("response measurement errors must be positive and finite")
        weights=(y[mask]/err[mask])**2
    design=np.column_stack([np.ones(len(xx)),xx])
    precision=design.T@(weights[:,None]*design)
    coeff=np.linalg.solve(precision,design.T@(weights*yy))
    residual=yy-design@coeff
    dof=len(xx)-2
    reduced=float(np.sum(weights*residual**2)/dof)
    cov=np.linalg.inv(precision)*(reduced if sigma is None else 1)
    slope=float(coeff[1]); slope_sigma=math.sqrt(max(float(cov[1,1]),0))
    result.update(fit_slope=slope,fit_slope_sigma=slope_sigma,
                  log_fit_residual_rms=float(np.sqrt(np.mean(residual**2))),reduced_chi_square=reduced)
    if slope>=0 or slope+1.96*slope_sigma>=0:
        result["reason"]="decay rate is unresolved"
        return result
    tau=-1/slope
    result["fitted_tau"]=tau
    result["fitted_tau_ci95"]=[-1/(slope-1.96*slope_sigma),-1/(slope+1.96*slope_sigma)]
    if require_resolved_tail and normalized[-1]>tail_threshold:
        result["reason"]="observed horizon does not resolve the registered tail threshold"
        return result
    # An exponential tail is accepted only with an adequate shape fit. The
    # threshold is a numerical/model check, not a confidence-level inference.
    if np.sqrt(np.mean(residual**2)) > 0.05 or (sigma is not None and reduced>4):
        result["reason"]="single-exponential response model fails the fit check"
        return result
    tail=float(normalized[-1]*tau)
    result.update(resolved=True,tau=tau,tau_ci95=result["fitted_tau_ci95"],tail_integral=tail,
                  integral_tau=area+tail,tail_model="continuation of checked exponential",
                  tail_error=float(normalized[-1]*(result["fitted_tau_ci95"][1]-result["fitted_tau_ci95"][0])/2))
    result["reason"]="resolved within the declared single-exponential estimator"
    return result


def check_linear_response(amplitudes, normalized_traces, rtol):
    """Quantify whether separately prepared responses share an amplitude limit."""
    a=np.asarray(amplitudes,float); traces=np.asarray(normalized_traces,float)
    if a.ndim!=1 or len(a)<2 or len(set(a))!=len(a) or np.any(a==0) or not np.all(np.isfinite(a)):
        raise InputError("linearity test needs distinct nonzero perturbation amplitudes")
    if traces.ndim!=2 or traces.shape[0]!=len(a) or not np.all(np.isfinite(traces)):
        raise InputError("linearity traces shape mismatch")
    scale=max(float(np.abs(traces).max()),1e-300)
    residual=float(np.max(np.abs(traces-traces[np.argmin(np.abs(a))]))/scale)
    return {"passed":residual<=rtol,"max_relative_trace_difference":residual,"tolerance":rtol}


def analyze_two_time(rows, **kwargs):
    groups={}
    for row in rows:
        groups.setdefault(float(row["preparation_time"]),[]).append(row)
    results={}
    for preparation, samples in sorted(groups.items()):
        samples.sort(key=lambda r:float(r["delay"]))
        results[preparation]=relaxation_estimate([float(r["delay"]) for r in samples],
                                               [float(r["response"]) for r in samples],**kwargs)
    return results


def _write_csv(path,rows):
    if not rows:
        raise InputError("cannot write empty response artifact")
    with path.open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def run(config,inputs,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    spec=read_json(Path(inputs["response"])) if "response" in inputs else config.get("response",config)
    if not spec.get("source") or not spec.get("operator") or not spec.get("phase"):
        raise InputError("P4 needs source, chosen operator and one-sided phase label")
    clock=spec.get("clock")
    physical=bool(clock and clock.get("unit")=="s" and clock.get("source") and clock.get("origin") in ("measured_independently","derived","external_model"))
    factor=float(clock["seconds_per_time_unit"]) if physical else 1.0
    if not math.isfinite(factor) or factor<=0:
        raise InputError("invalid physical-time calibration")
    rows=[]; estimates=[]
    cases=spec.get("cases",[spec])
    ids=[str(case.get("case_id",i)) for i,case in enumerate(cases)]
    if not cases or len(set(ids))!=len(ids):
        raise InputError("response case IDs must be nonempty and unique")
    (out/"response_spec.json").write_text(json.dumps(spec,sort_keys=True,indent=2,allow_nan=False)+"\n")
    (out/"response_cases.json").write_text(json.dumps([
        {"case_id":case_id,"analysis_file":f"response_analysis_{i}.json","case_index":i}
        for i,case_id in enumerate(ids)],sort_keys=True,indent=2,allow_nan=False)+"\n")
    for i,case in enumerate(cases):
        t=np.asarray(case["time"],float)
        if case.get("kind",spec.get("kind"))=="generator":
            y=generator_response(case["generator"],case["observable"],case["perturbation"],t,case.get("stationary"))
        elif case.get("kind",spec.get("kind"))=="measured":
            y=np.asarray(case["response"],float)
        else:
            raise InputError("response kind must be generator or measured")
        result=relaxation_estimate(t*factor,y,case.get("sigma"),
                                   [x*factor for x in case["fit_window"]] if "fit_window" in case else None,
                                   float(spec.get("tail_threshold",.02)))
        phase=case.get("phase",spec["phase"])
        mode_kind=case.get("mode_kind",spec.get("mode_kind","unidentified"))
        unit="s" if physical else "model_time"
        tau=result["tau"]
        H=case.get("H_s_inv",spec.get("H_s_inv"))
        if H is not None and (not math.isfinite(H) or H<0):
            raise InputError("invalid Hubble rate")
        Htau=H*tau if physical and tau is not None and H is not None and mode_kind=="within_phase" else None
        estimates.append({"case_id":ids[i],"phase":phase,"time_unit":unit,
                          "mode_kind":mode_kind,"resolved":result["resolved"],"tau":tau,
                          "tau_lower_bound":result["tau_lower_bound"],"H_tau":Htau,
                          "reason":result["reason"]})
        for tt,yy in zip(t*factor,y):
            rows.append({"case_id":ids[i],"phase":phase,"preparation_time":case.get("preparation_time",0)*factor,
                         "time":float(tt),"time_unit":unit,"response":float(yy)})
        (out/f"response_analysis_{i}.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    _write_csv(out/"retarded_response.csv",rows)
    _write_csv(out/"relaxation_times.csv",estimates)
    matching={"operator":spec["operator"],"source":spec["source"],"clock":clock,
              "physical_clock_calibration_declared":physical,"matching":spec.get("matching"),
              "response_type":spec.get("response_type","explicit preparation derivative"),
              "phase_switching_not_identified_as_within_phase":True}
    (out/"operator_matching.json").write_text(json.dumps(matching,indent=2,allow_nan=False)+"\n")
    return {"software_status":"PASS","evidence_status":"CONDITIONAL",
            "metrics":{"cases":len(cases),"resolved":sum(x["resolved"] for x in estimates),"physical_clock":physical},
            "limitations":["A physical relaxation claim requires independent clock, operator matching, amplitude and volume checks."]}
