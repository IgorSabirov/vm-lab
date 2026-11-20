"""P1: pressure-based phase EOS, scale provenance and thermal initial surfaces.

Natural units are MeV, MeV^3, MeV^4 throughout. Independent entropy/density
measurements validate a pressure interpolant; they are never spliced into it.
A phase boundary is a pair of one-sided functions, not a differentiated jump.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path

from .common import InputError, OpenInput, read_json

import numpy as np
from numpy.polynomial import Polynomial
from scipy.integrate import quad
from scipy.interpolate import CubicSpline
from scipy.optimize import brentq
from scipy.special import expit


class EOSDomainError(InputError):
    """An input asks an EOS to extrapolate beyond its declared phase window."""


def _finite(value, name, positive=False):
    x = np.asarray(value, dtype=float)
    if not np.all(np.isfinite(x)) or (positive and np.any(x <= 0)):
        raise InputError(f"{name} must be finite" + (" and positive" if positive else ""))
    return x


def _source(spec):
    if not isinstance(spec.get("source"), str) or not spec["source"].strip():
        raise OpenInput("EOS source is required, including for diagnostic laws")


class PhaseEOS:
    """One stable/metastable phase from a pressure law or measured pressure nodes.

    A table contains T_MeV, p_MeV4 and either pressure_covariance_MeV8 or
    p_sigma_MeV4. The covariance describes the input pressure measurements;
    interpolation truncation uncertainty must be supplied separately. For a
    polynomial coefficients[n] multiplies T**n, in units MeV**(4-n).
    """
    def __init__(self, spec):
        self.spec = copy.deepcopy(spec)
        _source(spec)
        self.phase = str(spec.get("phase", "unnamed"))
        self.kind = spec["kind"]
        self.offset = float(spec.get("pressure_offset_MeV4", 0.0))
        if self.offset and not spec.get("pressure_offset_source"):
            raise InputError("a pressure offset requires its independent source")
        if not math.isfinite(self.offset):
            raise InputError("pressure offset is not finite")
        self.cov = None
        self.validation = {}
        if self.kind == "pressure_polynomial":
            c = _finite(spec["coefficients"], "coefficients")
            if c.ndim != 1 or len(c) < 2:
                raise InputError("pressure polynomial needs at least two coefficients")
            self.poly = Polynomial(c)
            self.poly_cov = np.asarray(spec.get("coefficient_covariance",np.zeros((len(c),len(c)))),float)
            if self.poly_cov.shape!=(len(c),len(c)) or not np.all(np.isfinite(self.poly_cov)) or not np.allclose(self.poly_cov,self.poly_cov.T,rtol=1e-12,atol=1e-30):
                raise InputError("polynomial coefficient covariance has invalid shape/symmetry")
            if np.linalg.eigvalsh(self.poly_cov).min() < -1e-12*max(float(np.max(np.abs(self.poly_cov))),1e-300):
                raise InputError("polynomial coefficient covariance is not positive semidefinite")
            self.minimum, self.maximum = map(float, spec["T_range_MeV"])
        elif self.kind == "pressure_table":
            self.axis = _finite(spec["T_MeV"], "T_MeV", positive=True)
            self.pressure = _finite(spec["p_MeV4"], "p_MeV4")
            if self.axis.ndim != 1 or len(self.axis) < 4 or self.pressure.shape != self.axis.shape:
                raise InputError("pressure table needs at least four matching one-dimensional nodes")
            if np.any(np.diff(self.axis) <= 0):
                raise InputError("temperature nodes must be strictly increasing")
            self.minimum, self.maximum = float(self.axis[0]), float(self.axis[-1])
            self.spline = CubicSpline(self.axis, self.pressure, extrapolate=False)
            self.basis = CubicSpline(self.axis, np.eye(len(self.axis)), axis=0, extrapolate=False)
            if "pressure_covariance_MeV8" in spec:
                self.cov = _finite(spec["pressure_covariance_MeV8"], "pressure covariance")
            elif "p_sigma_MeV4" in spec:
                sigma = _finite(spec["p_sigma_MeV4"], "pressure errors")
                if sigma.shape != self.axis.shape or np.any(sigma < 0):
                    raise InputError("invalid pressure errors")
                self.cov = np.diag(sigma**2)
            else:
                raise InputError("pressure uncertainties/covariance must be explicit (zeros allowed for a diagnostic law)")
            if self.cov.shape != (len(self.axis), len(self.axis)) or not np.allclose(self.cov, self.cov.T, rtol=1e-12, atol=1e-20):
                raise InputError("pressure covariance must be symmetric with matching shape")
            if np.linalg.eigvalsh(self.cov).min() < -1e-12 * max(float(np.max(np.abs(self.cov))), 1e-300):
                raise InputError("pressure covariance is not positive semidefinite")
        else:
            raise InputError(f"unsupported EOS kind {self.kind!r}")
        if not (math.isfinite(self.minimum) and math.isfinite(self.maximum) and 0 < self.minimum < self.maximum):
            raise InputError("invalid EOS temperature domain")
        # Inspect every interpolation segment, not only the knots.
        sample = (np.unique(np.concatenate([np.linspace(a, b, 9) for a, b in zip(self.axis[:-1], self.axis[1:])]))
                  if self.kind == "pressure_table" else np.geomspace(self.minimum, self.maximum, 129))
        states = self.at(sample)
        if np.any(states["s_MeV3"] <= 0) or np.any(states["cv_MeV3"] <= 0):
            raise InputError("phase has nonpositive entropy or heat capacity inside the interpolation domain")
        self._validate_measurements()

    @classmethod
    def from_dict(cls, spec):
        return cls(spec)

    def at(self, T_MeV):
        t = _finite(T_MeV, "temperature", positive=True)
        if np.any(t < self.minimum) or np.any(t > self.maximum):
            raise EOSDomainError(f"{self.phase}: temperature outside [{self.minimum}, {self.maximum}] MeV")
        if self.kind == "pressure_polynomial":
            p, s, d2 = self.poly(t) + self.offset, self.poly.deriv(1)(t), self.poly.deriv(2)(t)
            powers=np.arange(len(self.poly.coef))
            b=t[...,None]**powers
            bs=np.where(powers>0,powers*t[...,None]**np.maximum(powers-1,0),0)
            br=t[...,None]*bs-b
            var_p=np.einsum("...i,ij,...j->...",b,self.poly_cov,b)
            var_s=np.einsum("...i,ij,...j->...",bs,self.poly_cov,bs)
            var_rho=np.einsum("...i,ij,...j->...",br,self.poly_cov,br)
        else:
            p, s, d2 = self.spline(t) + self.offset, self.spline(t, 1), self.spline(t, 2)
            b, bs = self.basis(t), self.basis(t, 1)
            br = t[..., None] * bs - b
            var_p = np.einsum("...i,ij,...j->...", b, self.cov, b)
            var_s = np.einsum("...i,ij,...j->...", bs, self.cov, bs)
            var_rho = np.einsum("...i,ij,...j->...", br, self.cov, br)
        offset_sigma=float(self.spec.get("pressure_offset_sigma_MeV4",0))
        if not math.isfinite(offset_sigma) or offset_sigma<0:
            raise InputError("invalid pressure zero uncertainty")
        var_p=var_p+offset_sigma**2;var_rho=var_rho+offset_sigma**2
        result = {"p_MeV4": p, "s_MeV3": s, "rho_MeV4": t*s-p,
                  "cv_MeV3": t*d2, "cs2": np.divide(s, t*d2),
                  "p_sigma_MeV4": np.sqrt(np.maximum(var_p, 0)),
                  "s_sigma_MeV3": np.sqrt(np.maximum(var_s, 0)),
                  "rho_sigma_MeV4": np.sqrt(np.maximum(var_rho, 0))}
        return {k: float(v) if t.ndim == 0 else v for k, v in result.items()}

    def _validate_measurements(self):
        if self.kind != "pressure_table":
            return
        state = self.at(self.axis)
        n_sigma = float(self.spec.get("validation_n_sigma", 3.0))
        if not math.isfinite(n_sigma) or n_sigma <= 0:
            raise InputError("validation_n_sigma must be positive")
        for observable, uncertainty in (("s_MeV3", "s_sigma_MeV3"), ("rho_MeV4", "rho_sigma_MeV4")):
            if observable not in self.spec:
                continue
            observed = _finite(self.spec[observable], observable)
            errors = _finite(self.spec.get(uncertainty, np.zeros_like(observed)), uncertainty)
            trunc = _finite(self.spec.get("interpolation_error", {}).get(observable, 0.0), "interpolation_error")
            if observed.shape != self.axis.shape or errors.shape != observed.shape or np.any(errors < 0) or np.any(trunc < 0):
                raise InputError(f"invalid {observable} measurement array")
            allowed = n_sigma*np.sqrt(errors**2 + state[uncertainty]**2) + trunc
            residual = np.abs(observed-state[observable])
            tolerance = 64*np.finfo(float).eps*np.maximum(np.maximum(np.abs(observed), np.abs(state[observable])), 1)
            if np.any(residual > allowed + tolerance):
                raise InputError(f"thermodynamic inconsistency: independent {observable} disagrees with pressure derivatives")
            self.validation[observable] = {"max_absolute_residual": float(residual.max()),
                                           "max_allowed_residual": float(np.max(allowed))}

    def temperature_for_density(self, rho_MeV4):
        rho = float(_finite(rho_MeV4, "density"))
        low, high = self.at(self.minimum)["rho_MeV4"], self.at(self.maximum)["rho_MeV4"]
        if not low <= rho <= high:
            raise EOSDomainError("density outside the EOS domain")
        return brentq(lambda t: self.at(t)["rho_MeV4"]-rho, self.minimum, self.maximum,
                      xtol=max(self.minimum*1e-13, 1e-14))


class EOSBundle:
    """Phase-aware EOS. Fraction f is the new (cold) phase volume fraction."""
    def __init__(self, spec):
        spec = spec.get("definition", spec)
        self.spec = copy.deepcopy(spec)
        self.phases = {name: PhaseEOS(dict(value, phase=name)) for name, value in spec["phases"].items()}
        if not self.phases:
            raise InputError("EOS bundle has no phases")
        self.transitions = copy.deepcopy(spec.get("transitions", []))
        self.Tc_MeV = float(self.transitions[0]["T_c_MeV"]) if self.transitions else None
        for tr in self.transitions:
            T = float(tr["T_c_MeV"])
            hot, cold = self.at(T, tr["hot"]), self.at(T, tr["cold"])
            tolerance = float(tr.get("pressure_matching_tolerance_MeV4", 0.0))
            error = math.hypot(hot["p_sigma_MeV4"], cold["p_sigma_MeV4"])
            residual = hot["p_MeV4"]-cold["p_MeV4"]
            if abs(residual) > tolerance+3*error+1e-12*max(abs(hot["p_MeV4"]), abs(cold["p_MeV4"]), 1):
                raise InputError("phases have incompatible pressure zeros at the declared transition")
            latent = hot["rho_MeV4"]-cold["rho_MeV4"]
            if latent <= 0:
                raise InputError("hot-to-cold transition must have positive latent heat")
            if "latent_heat_MeV4" in tr:
                e = float(tr.get("latent_heat_sigma_MeV4", 0))
                rho_error = math.hypot(hot["rho_sigma_MeV4"], cold["rho_sigma_MeV4"])
                if abs(latent-float(tr["latent_heat_MeV4"])) > 3*math.hypot(e, rho_error)+1e-12*max(latent, 1):
                    raise InputError("latent heat does not belong to the supplied absolute EOS branch")
            tr["derived_latent_heat_MeV4"] = latent
            tr["pressure_matching_residual_MeV4"] = residual

    @classmethod
    def from_dict(cls, spec):
        return cls(spec)

    def at(self, T_MeV, phase):
        return self.phases[phase].at(T_MeV)

    def mixture(self, T_MeV, f, hot="hot", cold="cold"):
        if not math.isfinite(f) or not 0 <= f <= 1:
            raise InputError("phase fraction must lie in [0,1]")
        # A completed postconfinement preparation needs only its occupied
        # phase. Do not extrapolate the absent metastable branch to late times.
        if f in (0,1):
            active=cold if f==1 else hot
            other=hot if f==1 else cold
            if not self.phases[other].minimum<=T_MeV<=self.phases[other].maximum:
                a=self.at(T_MeV,active)
                return {**{k:a[k] for k in ("p_MeV4","rho_MeV4","s_MeV3","cv_MeV3")},
                        "drho_df_MeV4":0.0,"phase_derivative_available":False}
        h, c = self.at(T_MeV, hot), self.at(T_MeV, cold)
        r = {k: (1-f)*h[k]+f*c[k] for k in ("p_MeV4", "rho_MeV4", "s_MeV3", "cv_MeV3")}
        r["drho_df_MeV4"] = c["rho_MeV4"]-h["rho_MeV4"]
        return r


def merge_pressure_tables(segments, n_sigma=3.0):
    """Validate overlapping same-phase tables and combine pressure observations.

    The union of original knots is the output grid. Errors of different input
    segments are treated as independent; that assumption is recorded. With
    correlated releases callers must supply a single joint covariance table.
    """
    eos = [PhaseEOS(s) for s in segments]
    if not eos or any(e.kind != "pressure_table" for e in eos):
        raise InputError("merge expects pressure tables")
    if len({e.phase for e in eos}) != 1:
        raise InputError("cannot splice different phases")
    eos.sort(key=lambda e: e.minimum)
    for left, right in zip(eos[:-1], eos[1:]):
        lo, hi = right.minimum, min(left.maximum, right.maximum)
        if hi <= lo:
            raise InputError("EOS segments need a finite overlap")
        t = np.linspace(lo, hi, 33)
        a, b = left.at(t), right.at(t)
        err = n_sigma*np.hypot(a["p_sigma_MeV4"], b["p_sigma_MeV4"])
        if np.any(np.abs(a["p_MeV4"]-b["p_MeV4"]) > err+1e-11*np.maximum(np.abs(a["p_MeV4"]), 1)):
            raise InputError("EOS overlap disagrees; pressure zero cannot be silently shifted")
        serr=n_sigma*np.hypot(a["s_sigma_MeV3"],b["s_sigma_MeV3"])
        if np.any(np.abs(a["s_MeV3"]-b["s_MeV3"])>serr+1e-10*np.maximum(np.abs(a["s_MeV3"]),1)):
            raise InputError("EOS overlap entropy derivatives disagree")
    axis = np.unique(np.concatenate([e.axis for e in eos]))
    transform = np.zeros((len(axis), sum(len(e.axis) for e in eos)))
    pressures = np.zeros(len(axis))
    covariance = np.zeros((transform.shape[1], transform.shape[1]))
    offsets, cursor = [], 0
    for e in eos:
        offsets.append(cursor)
        covariance[cursor:cursor+len(e.axis), cursor:cursor+len(e.axis)] = e.cov+float(e.spec.get("pressure_offset_sigma_MeV4",0))**2
        cursor += len(e.axis)
    for i, t in enumerate(axis):
        active = [(j,e,e.at(t)) for j,e in enumerate(eos) if e.minimum <= t <= e.maximum]
        zero = [x for x in active if x[2]["p_sigma_MeV4"] == 0]
        selected = zero[:1] if zero else active
        weights = np.array([1.0 if zero else 1/x[2]["p_sigma_MeV4"]**2 for x in selected])
        weights /= weights.sum()
        for weight, (j,e,state) in zip(weights, selected):
            pressures[i] += weight*state["p_MeV4"]
            transform[i, offsets[j]:offsets[j]+len(e.axis)] = weight*e.basis(t)
    return {"kind":"pressure_table", "phase":eos[0].phase,
            "source":"validated merge: " + "; ".join(e.spec["source"] for e in eos),
            "T_MeV":axis.tolist(), "p_MeV4":pressures.tolist(),
            "pressure_covariance_MeV8":(transform@covariance@transform.T).tolist(),
            "cross_segment_covariance_assumption":"independent input segments"}


def ideal_gas(T_MeV, mass_MeV, degeneracy, statistics="fermion"):
    """Equilibrium zero-chemical-potential ideal gas with exact mass dependence.

    This supplies photons/e+- and thermal neutrinos, not interacting high-T SM
    QCD. The independent SM table remains required outside this explicit model.
    """
    T, mass, g = float(T_MeV), float(mass_MeV), float(degeneracy)
    if not (math.isfinite(T) and T > 0 and math.isfinite(mass) and mass >= 0 and math.isfinite(g) and g > 0):
        raise InputError("invalid ideal-gas parameters")
    if statistics not in ("fermion", "boson"):
        raise InputError("statistics must be fermion or boson")
    if mass == 0:
        rho = g*math.pi**2*T**4/30*(7/8 if statistics == "fermion" else 1)
        return {"rho_MeV4":rho, "p_MeV4":rho/3, "s_MeV3":4*rho/(3*T), "cv_MeV3":4*rho/T}
    z = mass/T
    def occ(e):
        return float(expit(-e)) if statistics == "fermion" else math.exp(-e)/(-math.expm1(-e))
    def integrand(x, kind):
        e = math.hypot(x,z)
        f = occ(e)
        if kind == "rho": return x*x*e*f
        if kind == "p": return x**4/e*f/3
        return x*x*e*e*f*(1-f if statistics == "fermion" else 1+f)
    vals = {k: quad(lambda x: integrand(x,k), 0, np.inf, epsabs=1e-11, epsrel=1e-10)[0] for k in ("rho","p","cv")}
    norm = g/(2*math.pi**2)
    rho,p = norm*T**4*vals["rho"],norm*T**4*vals["p"]
    return {"rho_MeV4":rho,"p_MeV4":p,"s_MeV3":(rho+p)/T,"cv_MeV3":norm*T**3*vals["cv"]}


def scale_from_anchor(spec):
    """Multiply a dimensionless ratio by an explicitly sourced MeV anchor."""
    anchor, ratio = spec["anchor"], spec["ratio"]
    for item in (anchor,ratio):
        if item.get("origin") not in ("measured_independently","derived","external_model","parameter_scan","diagnostic") or not item.get("source"):
            raise InputError("scale input needs source and parameter origin")
        _finite(item["value"], "scale value", positive=True)
        if float(item.get("sigma", 0)) < 0:
            raise InputError("negative scale uncertainty")
    if anchor.get("unit") != "MeV" or ratio.get("unit") != "1":
        raise InputError("scale anchor must be MeV and ratio dimensionless")
    a, r, sa, sr = (float(anchor["value"]),float(ratio["value"]),float(anchor.get("sigma",0)),float(ratio.get("sigma",0)))
    corr = float(spec.get("correlation",0))
    if not -1 <= corr <= 1 or not all(math.isfinite(x) for x in (sa,sr,corr)):
        raise InputError("invalid scale covariance")
    return {"T_c_MeV":a*r,"sigma_T_c_MeV":math.sqrt((r*sa)**2+(a*sr)**2+2*a*r*corr*sa*sr),
            "input":copy.deepcopy(spec),"absolute_prediction":anchor["origin"] == "measured_independently",
            "correlation_assumption":"provided" if "correlation" in spec else "independent inputs"}


def _load(config, inputs, key):
    if key in inputs:
        return read_json(Path(inputs[key]))
    if key in config:
        return config[key]
    raise OpenInput(f"missing required P1 input {key}")


def run(config, inputs, out):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    spec = _load(config,inputs,"eos")
    bundle = EOSBundle(spec)
    scale = scale_from_anchor(_load(config,inputs,"scale"))
    for transition in bundle.transitions:
        error=scale["sigma_T_c_MeV"]+float(transition.get("T_c_sigma_MeV",0))
        if abs(scale["T_c_MeV"]-float(transition["T_c_MeV"]))>3*error+1e-11*scale["T_c_MeV"]:
            raise InputError("dimensionful scale and EOS transition temperatures disagree")
    initial = copy.deepcopy(_load(config,inputs,"initial_history"))
    for key in ("a0","T_X_MeV","T_gamma_MeV","eta_b"):
        _finite(initial[key],key,positive=True)
    if not initial.get("source") or not initial.get("neutrinos"):
        raise InputError("initial surface needs provenance and neutrino distribution/thermal preparation")
    if initial.get("phase") not in bundle.phases:
        raise InputError("initial surface phase absent from EOS")
    nu=initial["neutrinos"]
    if nu.get("kind")=="thermal":
        _finite(nu["T_MeV"],"initial neutrino temperature",positive=True)
    elif nu.get("kind")=="spectral":
        momentum=_finite(nu["p_MeV"],"initial neutrino momentum")
        occupancy=_finite(nu["occupation"],"initial neutrino occupancy")
        if momentum.ndim!=1 or len(momentum)<3 or np.any(np.diff(momentum)<=0) or momentum[0]<0 or occupancy.shape[-1]!=len(momentum) or np.any(occupancy<0) or np.any(occupancy>1):
            raise InputError("invalid initial fermion spectrum")
    else:
        raise OpenInput("initial neutrino preparation must be thermal or a supplied spectrum")
    initial["X_state"] = bundle.at(initial["T_X_MeV"],initial["phase"])
    eos_output = {"schema":"R135-phase-eos-v1","units":{"T":"MeV","p":"MeV^4","rho":"MeV^4","s":"MeV^3"},
                  "definition":spec,"transitions":bundle.transitions,
                  "validation":{k:v.validation for k,v in bundle.phases.items()},
                  "no_extrapolation":True}
    for name,data in (("scale.json",scale),("eos_bundle.json",eos_output),("initial_history.json",initial)):
        (out/name).write_text(json.dumps(data,sort_keys=True,indent=2,allow_nan=False)+"\n")
    return {"software_status":"PASS","evidence_status":"CONDITIONAL",
            "metrics":{"phase_count":len(bundle.phases),"T_c_MeV":scale["T_c_MeV"]},
            "limitations":["Thermodynamic consistency does not establish the origin of a model's energy scale."]}
