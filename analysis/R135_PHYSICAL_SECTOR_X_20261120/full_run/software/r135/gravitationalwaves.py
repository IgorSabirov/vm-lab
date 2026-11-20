"""Energy-conserving, subhorizon GW cells coupled to the actual P7 history.

The source is a supplied spectral power law. This module does not infer a GW
efficiency from latent heat, nor turn a detector response into a full likelihood.
Frequency q is comoving cyclic frequency: q = a*f in Hz for the SAME arbitrary
scale-factor normalization as P7. A cell value is d rho_GW / d ln(q), in MeV^4.
"""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import numpy as np
from scipy.integrate import quad

from .common import (G_NEWTON_MEV_MINUS2, HBAR_MEV_S, InputError, OpenInput,
                     canonical_hash, finite, require_source, sha256)

HERE = Path(__file__).resolve().parents[1]
CORNERS = ("00", "10", "01", "11full", "11add")
KEYS = ("point_id", "model_id", "thermal_path")


def critical_density(H_s_inv):
    return 3 * (np.asarray(H_s_inv, float)*HBAR_MEV_S)**2/(8*np.pi*G_NEWTON_MEV_MINUS2)


def _positive_array(values, name, *, minimum=2):
    x = np.asarray(values, float)
    if x.ndim != 1 or len(x) < minimum or not np.isfinite(x).all() or np.any(x <= 0):
        raise InputError(f"{name}: expected a positive finite vector")
    return x


def _source_text(definition, name):
    value = definition.get(name)
    if not isinstance(value, str) or not value.strip():
        raise OpenInput(f"GW requires {name}")
    return value


class GWSource:
    """Append radiation-density cells; root P7 supplies reciprocal X/free Q.

    The source is piecewise linear in physical time and cell-constant in ln q.
    Its zero endpoints make the explicit compact time support continuous.
    ``time_knots_s`` must be included in P7's integration and sampling boundaries.
    Other radiation in the free sector is retained; these cells are additive.
    """
    def __init__(self, definition, *, offset):
        self.offset = int(offset)
        self.enabled = definition is not None
        self.size = self.offset
        self.slice = slice(self.offset, self.offset)
        self.time_knots_s = np.array([], float)
        self.definition = definition
        if not self.enabled:
            return
        if not isinstance(definition, dict):
            raise InputError("GW source must be a mapping")
        require_source(definition, "GW spectral power")
        if definition.get("kind") != "comoving_frequency_power":
            raise OpenInput("P7 GW coupling requires a supplied comoving-frequency power history")
        for name in ("support_source", "uncertainty_source", "scale_factor_convention"):
            _source_text(definition, name)
        self.edges = _positive_array(definition["q_frequency_edges_Hz"], "GW q edges")
        if np.any(np.diff(self.edges) <= 0):
            raise InputError("GW comoving-frequency edges are not ordered")
        self.widths = np.diff(np.log(self.edges))
        self.time_knots_s = np.asarray(definition["time_s"], float)
        if (self.time_knots_s.ndim != 1 or len(self.time_knots_s) < 2
                or not np.isfinite(self.time_knots_s).all() or self.time_knots_s[0] < 0
                or np.any(np.diff(self.time_knots_s) <= 0)):
            raise InputError("GW source times must be finite and strictly increasing")
        self.power_table = np.asarray(definition["power_MeV4_s_per_logq"], float)
        if (self.power_table.shape != (len(self.time_knots_s), len(self.widths))
                or not np.isfinite(self.power_table).all() or np.any(self.power_table < 0)):
            raise InputError("invalid nonnegative GW source-power table")
        if definition.get("zero_outside_time_support") is not True:
            raise OpenInput("GW source time tails must be explicitly supplied or zero")
        if np.any(self.power_table[[0, -1]] != 0):
            raise InputError("compact piecewise-linear GW source requires zero endpoint powers")
        app = definition.get("applicability", {})
        require_source(app, "GW applicability")
        if (app.get("subhorizon_geometric_optics") is not True
                or app.get("free_propagation_after_source") is not True
                or app.get("statistically_isotropic") is not True):
            raise OpenInput("general tensor propagation or anisotropic GW stress is not implemented")
        self.maximum_fraction = finite(app["maximum_rho_GW_over_total"],
                                       "GW weak-field density domain", positive=True)
        if self.maximum_fraction >= 1:
            raise InputError("GW weak-field domain must be below the total density")
        tail = finite(definition["omitted_frequency_energy_fraction_bound"],
                      "GW frequency-tail bound", nonnegative=True)
        if tail >= 1:
            raise InputError("unbounded omitted GW frequency support")
        self.initial = np.asarray(definition.get("initial_rho_MeV4_per_logq",
                                                np.zeros(len(self.widths))), float)
        if (self.initial.shape != self.widths.shape or not np.isfinite(self.initial).all()
                or np.any(self.initial < 0)):
            raise InputError("invalid initial GW cell density")
        if np.any(self.initial):
            _source_text(definition, "initial_spectrum_source")
        multipliers = definition.get("corner_multipliers", {c: 1. for c in CORNERS})
        if set(multipliers) != set(CORNERS):
            raise InputError("GW source must name all five corner multipliers")
        self.multipliers = {c: finite(v, "GW corner multiplier", nonnegative=True)
                            for c, v in multipliers.items()}
        self.size += len(self.widths)
        self.slice = slice(self.offset, self.size)
        self.source_sha256 = canonical_hash(definition)

    def initialize(self, state):
        if self.enabled:
            state[self.slice] = self.initial
        return state

    def moments(self, state):
        rho = float(np.dot(np.asarray(state)[self.slice], self.widths)) if self.enabled else 0.
        return rho, rho/3

    def power(self, time_s, corner):
        if not self.enabled:
            return np.array([], float)
        if corner not in self.multipliers:
            raise InputError("unknown GW source corner")
        return np.array([np.interp(time_s, self.time_knots_s, col, left=0., right=0.)
                         for col in self.power_table.T])*self.multipliers[corner]

    def rhs(self, time_s, state, a, H_s_inv, corner):
        if not self.enabled:
            return np.array([], float), 0., None
        a = finite(a, "GW scale factor", positive=True)
        H = finite(H_s_inv, "GW Hubble rate", positive=True)
        density = np.asarray(state, float)[self.slice]
        power = self.power(time_s, corner)
        occupied = (density > 0) | (power > 0)
        if np.any(2*np.pi*self.edges[:-1][occupied]/a <= H):
            raise OpenInput("a GW cell is not fully subhorizon; tensor evolution is required")
        rho = float(np.dot(density, self.widths))
        fraction = rho/float(critical_density(H))
        if fraction > self.maximum_fraction:
            raise OpenInput("GW density left the declared weak-field source domain")
        q = float(np.dot(power, self.widths))
        record = dict(q_frequency_edges_Hz=self.edges.tolist(),
                      rho_MeV4_per_logq=density.tolist(),
                      power_MeV4_s_per_logq=power.tolist(), rho_GW_MeV4=rho,
                      Q_GW_MeV4_s=q, rho_GW_over_total=fraction,
                      source_definition=self.definition, source_sha256=self.source_sha256,
                      corner=corner, included_in_sector="free",
                      reciprocal_source_sector="X")
        return -4*H*density + power, q, record

    def validate_accepted(self, state):
        if self.enabled:
            rho = np.asarray(state, float)[self.slice]
            if not np.isfinite(rho).all() or np.any(rho < 0):
                raise InputError("accepted GW cell density is negative or nonfinite; refine the solve")


def source_artifact(definition, key=None):
    identity = {k: key[k] for k in KEYS} if key else {}
    if definition is None:
        return dict(schema="R135-GW-source-v1", **identity, status="OPEN_INPUT",
                    missing=["physical spectral power and its time/frequency support",
                             "source uncertainty and applicability"])
    source = GWSource(definition, offset=0)
    return dict(schema="R135-GW-source-v1", **identity, status="CONDITIONAL",
                definition=definition, source_sha256=source.source_sha256,
                source_derivation="supplied independently; not inferred from latent heat",
                units=dict(q="a*f in Hz", power="MeV^4/s per d ln q"))


def payload_from_records(records):
    selected = [row.get("gw") for row in records]
    if not any(item is not None for item in selected):
        return None
    if any(item is None for item in selected):
        raise InputError("GW records disappeared within one P7 history")
    first = selected[0]
    invariant = ("source_sha256", "source_definition", "q_frequency_edges_Hz", "corner",
                 "included_in_sector", "reciprocal_source_sector")
    if any(any(item[k] != first[k] for k in invariant) for item in selected):
        raise InputError("GW source or frequency convention changed inside a P7 history")
    result = {k: first[k] for k in invariant}
    for name in ("rho_MeV4_per_logq", "power_MeV4_s_per_logq", "rho_GW_MeV4",
                 "Q_GW_MeV4_s", "rho_GW_over_total"):
        result[name] = [item[name] for item in selected]
    return dict(schema="R135-GW-history-v1", **result)


def has_gw_energy(history):
    gw = history.get("gw", {})
    return bool(np.any(np.asarray(gw.get("rho_GW_MeV4", []), float) != 0))


def _arrays(history):
    if not isinstance(history.get("gw"), dict):
        raise OpenInput("P7 has no coupled GW spectral history")
    t = np.asarray(history["time_s"], float)
    a = _positive_array(history["scale_factor"], "P7 scale factor")
    H = _positive_array(history["H_s_inv"], "P7 Hubble rate")
    if (t.shape != a.shape or H.shape != t.shape or not np.isfinite(t).all()
            or np.any(np.diff(t) <= 0) or np.any(np.diff(a) <= 0)):
        raise InputError("invalid chronological P7 GW background")
    gw = history["gw"]
    source = GWSource(gw["source_definition"], offset=0)
    if (gw.get("source_sha256") != source.source_sha256
            or gw.get("included_in_sector") != "free"
            or gw.get("reciprocal_source_sector") != "X"
            or gw.get("q_frequency_edges_Hz") != source.edges.tolist()):
        raise InputError("GW history source binding or energy-sector assignment changed")
    density = np.asarray(gw["rho_MeV4_per_logq"], float)
    power = np.asarray(gw["power_MeV4_s_per_logq"], float)
    if (density.shape != (len(t), len(source.widths)) or power.shape != density.shape
            or not np.isfinite(density).all() or np.any(density < 0)
            or not np.isfinite(power).all() or np.any(power < 0)):
        raise InputError("invalid saved GW density or power cells")
    return t, a, H, gw, source, density, power


def audit_history(history, *, quadrature_rtol=1e-3):
    """Rebuild energy and source integrals from saved cells, not P7 ledgers."""
    if "gw" not in history:
        return dict(status="OPEN_INPUT", missing=["coupled GW source/history"])
    t, a, H, gw, source, density, power = _arrays(history)
    if not np.allclose(density[0], source.initial, rtol=1e-12, atol=0):
        raise InputError("GW initial density differs from its declared initial spectrum")
    expected_power = np.array([source.power(x, gw["corner"]) for x in t])
    if not np.allclose(power, expected_power, rtol=1e-12, atol=0):
        raise InputError("saved GW power differs from the declared source")
    rho = density @ source.widths
    q = power @ source.widths
    for name, expected in (("rho_GW_MeV4", rho), ("Q_GW_MeV4_s", q),
                           ("rho_GW_over_total", rho/critical_density(H))):
        if not np.allclose(np.asarray(gw[name]), expected, rtol=1e-10, atol=0):
            raise InputError(f"GW {name} differs from independent cell integral")
    if np.any(rho > np.asarray(history["rho_free_MeV4"], float)*(1+1e-12)):
        raise InputError("GW energy is absent from, or exceeds, the actual P7 free density")
    if np.any(rho/critical_density(H) > source.maximum_fraction):
        raise OpenInput("saved GW energy exceeds the registered weak-field domain")
    for j in range(len(t)):
        occupied = (density[j] > 0) | (power[j] > 0)
        if np.any(2*np.pi*source.edges[:-1][occupied]/a[j] <= H[j]):
            raise OpenInput("saved GW history contains a non-subhorizon occupied cell")
    # Piecewise-linear a(t) is independently reconstructed from saved rows.
    # Break at every saved epoch and every source knot, never integrate across
    # an unrecorded source burst as though it were zero.
    if any(not np.any(np.isclose(t, knot, rtol=0, atol=max(abs(knot),1)*1e-12))
           for knot in source.time_knots_s if t[0] < knot < t[-1]):
        raise InputError("P7 omitted a required GW source knot from the saved history")
    integral = np.zeros(len(source.widths))
    for lo, hi in zip(t[:-1], t[1:]):
        for k in range(len(integral)):
            integral[k] += quad(lambda x: np.interp(x,t,a)**4*source.power(x,gw["corner"])[k],
                                lo,hi,epsabs=1e-100,epsrel=2e-10)[0]
    change = a[-1]**4*density[-1] - a[0]**4*density[0]
    scale = np.maximum(np.maximum(abs(change),abs(integral)),1e-300)
    error = float(np.max(abs(change-integral)/scale))
    return dict(status="RECONSTRUCTED" if error <= quadrature_rtol else "PARTIAL",
                maximum_relative_radiation_balance=error,
                radiation_source_integral_MeV4_per_logq=integral.tolist(),
                reconstructed_rho_GW_MeV4=rho.tolist(),
                BBN_energy_already_in_P7_Friedmann=True,
                no_additional_DeltaNeff_density_to_be_added=True,
                remaining=[] if error <= quadrature_rtol else ["GW_OUTPUT_QUADRATURE_UNRESOLVED"])


def _key(key):
    if any(not isinstance(key.get(k),str) or not key[k] for k in KEYS):
        raise InputError("GW needs point, model and thermal-path identities")
    return {k:key[k] for k in KEYS}


def _late_background(history, policy, source, density):
    continuation = policy.get("propagation_history")
    if not isinstance(continuation,dict):
        raise OpenInput("GW transfer requires the sourced late H(a) history in the P7 a convention")
    require_source(continuation,"late GW propagation history")
    if continuation.get("interpolation") != "piecewise_linear_H_of_a":
        raise OpenInput("unsupported late GW propagation interpolation")
    if continuation.get("free_propagation") is not True:
        raise OpenInput("tensor damping/continued GW generation needs a transfer calculation")
    a = _positive_array(continuation["scale_factor"],"late scale factor")
    h = _positive_array(continuation["H_s_inv"],"late Hubble rate")
    if a.shape != h.shape or np.any(np.diff(a)<=0):
        raise InputError("invalid late H(a) table")
    if (not np.isclose(a[0],history["scale_factor"][-1],rtol=1e-10,atol=0)
            or not np.isclose(h[0],history["H_s_inv"][-1],rtol=1e-10,atol=0)):
        raise InputError("late GW history does not start at the actual final P7 state")
    max_ah = float(np.max(a*h))
    for al, ar, hl, hr in zip(a[:-1],a[1:],h[:-1],h[1:]):
        slope = (hr-hl)/(ar-al)
        if slope < 0:
            intercept = hl-slope*al
            vertex = -intercept/(2*slope)
            if al < vertex < ar:
                max_ah = max(max_ah,vertex*(slope*vertex+intercept))
    active = density[-1] > 0
    if np.any(2*np.pi*source.edges[:-1][active] <= max_ah):
        raise OpenInput("a GW cell leaves the horizon in the supplied late expansion history")
    # rho_GW scales as a^-4. On a positive piecewise-linear H(a), a^2 H
    # has no interior minimum, so its minimum is attained at a saved node.
    # This checks the density domain across the continuation, not just today.
    rho_late = float(density[-1] @ source.widths)*(a[0]/a)**4
    if np.any(rho_late/critical_density(h) > source.maximum_fraction):
        raise OpenInput("GW density leaves the weak-field domain during late propagation")
    return a[-1], h[-1], continuation


def _load_external(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def detector_paths(cache, *, offline=True):
    donor=_load_external("r135_gw_pinned_fetch",HERE/"donors/fetch.py")
    return donor.acquire(Path(cache),{"gw"},offline)


def _detectors(edges, omega, hubble0, paths):
    donor=_load_external("r135_gw_pinned_fetch",HERE/"donors/fetch.py")
    definitions=donor.sources()
    for name in ("lvk-o4a-hl","ng15-kde","lvk-o4c1-paper"):
        if name not in paths or not donor.verified(Path(paths[name]),definitions[name]):
            raise InputError("GW detector data do not match pinned release: "+name)
    response=_load_external("r135_gw_donor_response",HERE/"gw/response.py")
    projected=response.detector_projection_cells(edges,omega,hubble0,paths)
    projected["source_files"]={k:dict(sha256=sha256(Path(paths[k])),bytes=Path(paths[k]).stat().st_size,
                                      url=definitions[k]["url"])
                               for k in ("lvk-o4a-hl","ng15-kde","lvk-o4c1-paper")}
    return projected


def response_from_p7(history, key, policy, donor_paths=None):
    identity=_key(key)
    for name,value in identity.items():
        if name in history and history[name]!=value:
            raise InputError("GW history belongs to another "+name)
    t,a,H,gw,source,density,power=_arrays(history)
    for name,value in identity.items():
        if name in source.definition and source.definition[name]!=value:
            raise InputError("GW source belongs to another "+name)
    if t[-1] < source.time_knots_s[-1]:
        raise OpenInput("GW source has not ended within the saved P7 history")
    if np.any(power[-1]):
        raise OpenInput("GW source still radiates at the end of P7")
    audit=audit_history(history,quadrature_rtol=policy.get("quadrature_rtol",1e-3))
    a_today,h0,continuation=_late_background(history,policy,source,density)
    edges=source.edges/a_today
    omega=density[-1]*(a[-1]/a_today)**4/float(critical_density(h0))
    epochs=policy.get("bbn_epochs")
    if not isinstance(epochs,list) or not epochs:
        raise OpenInput("GW BBN epochs and their physical selection must be specified")
    budget=[];seen=set()
    for epoch in epochs:
        require_source(epoch,"GW BBN epoch")
        target=finite(epoch["time_s"],"GW BBN epoch",nonnegative=True)
        selected=np.flatnonzero(np.isclose(t,target,rtol=0,atol=max(abs(target),1)*1e-12))
        if len(selected)!=1 or int(selected[0]) in seen:
            raise InputError("GW BBN epoch must identify one unique saved P7 sample")
        j=int(selected[0]);seen.add(j)
        cutoff=a[j]*H[j]/(2*np.pi)
        widths=np.maximum(np.log(source.edges[1:]/np.maximum(source.edges[:-1],cutoff)),0)
        fraction=float(density[j]@widths/critical_density(H[j]))
        budget.append(dict(time_s=float(t[j]),a_over_a_today=float(a[j]/a_today),
                           H_s_inv=float(H[j]),rho_GW_over_rho_total=fraction,
                           density_already_in_P7_Friedmann=True,
                           generation_handling="actual saved epoch density; never back-projected from future emission"))
    detectors = (_detectors(edges,omega,h0,donor_paths) if donor_paths is not None else
                 dict(status="OPEN_INPUT",missing=["pinned PTA/LVK donor data"]))
    return dict(schema="R135-GW-response-v2",**identity,corner=gw["corner"],
                status="CONDITIONAL",physical_completion_status="OPEN_INPUT",
                history_id=canonical_hash(history),P7_history_sha256=canonical_hash(history),
                source_sha256=source.source_sha256,propagation_history_sha256=canonical_hash(continuation),
                response_policy=policy,response_policy_sha256=canonical_hash(policy),
                source_kind=source.definition["kind"],source_provenance=source.definition["source"],
                spectrum_representation="cell_constant_per_dlnf",
                f_today_edges_Hz=edges.tolist(),Omega_GW_today_per_logf=omega.tolist(),
                integrated_Omega_GW_today=float(omega@source.widths),H0_s_inv=float(h0),
                a_today_in_P7_convention=float(a_today),bbn_budget=budget,detectors=detectors,
                energy_audit=audit,scalar_CMB_mapping_status="REQUIRES_SEPARATE_APPLICABILITY_PROOF",
                remaining=["PTA HD likelihood, astrophysical population and priors",
                           "LVK foreground/calibration/systematics treatment and dataset-overlap policy",
                           "physical source calibration and uncertainty propagation for this X"])


def responses_from_p7(channel_history, key, policy=None, donor_paths=None):
    """A missing GW source is recorded for every corner; it never becomes zero."""
    identity=_key(key)
    histories=channel_history.get("histories",{})
    if set(histories)!=set(CORNERS):
        raise InputError("GW requires the same five P7 corners")
    outputs={}
    for corner,hist in histories.items():
        if hist.get("gw") is not None and hist["gw"].get("corner") != corner:
            raise InputError("GW source corner differs from its P7 history key")
        chosen=(policy or {}).get("corners",{}).get(corner,policy or {})
        try:
            result=response_from_p7(hist,identity,chosen,donor_paths)
        except OpenInput as exc:
            result=dict(**identity,corner=corner,status="OPEN_INPUT",missing=[str(exc)],
                        P7_history_sha256=canonical_hash(hist))
        outputs[corner]=result
    return dict(schema="R135-GW-response-bundle-v1",**identity,
                P7_channel_history_sha256=canonical_hash(channel_history),histories=outputs,
                physical_completion_status="OPEN_INPUT",
                scientific_acceptance="owner_review")


def audit_response(history, response, key, donor_paths=None):
    """Numerically reconstruct a saved response from P7 and its registered policy."""
    identity=_key(key)
    if any(response.get(k)!=v for k,v in identity.items()):
        raise InputError("GW response identity differs from P7/request")
    if response.get("P7_history_sha256")!=canonical_hash(history):
        raise InputError("GW response is not bound to the actual P7 history")
    if response.get("status")=="OPEN_INPUT":
        if not response.get("missing"):
            raise InputError("GW OPEN_INPUT requires a concrete missing input")
        return dict(status="PARTIAL",remaining=response["missing"])
    if response.get("status") != "CONDITIONAL" or response.get("physical_completion_status") != "OPEN_INPUT":
        raise InputError("GW conditional numerical projection cannot claim completed physical inference")
    policy=response.get("response_policy")
    if canonical_hash(policy)!=response.get("response_policy_sha256"):
        raise InputError("GW response policy was changed")
    # Do not call response_from_p7 here. Reconstruct the transfer with scalar
    # cell sums and the physical critical-density constants, from the saved
    # energy densities rather than the reported end-spectrum/BBN numbers.
    t,a,H,record,source,density,_power=_arrays(history)
    if any(name in obj and obj[name] != value for obj in (history, source.definition)
           for name,value in identity.items()):
        raise InputError("GW source/history identity differs from the audited request")
    energy_audit=audit_history(history,quadrature_rtol=policy.get("quadrature_rtol",1e-3))
    if t[-1] < source.time_knots_s[-1] or np.any(source.power(t[-1],record["corner"])):
        raise InputError("GW response was transferred before generation ended")
    a_today,h0,continuation=_late_background(history,policy,source,density)
    rho_critical_today=3*(HBAR_MEV_S*float(h0))**2/(8*math.pi*G_NEWTON_MEV_MINUS2)
    frequencies=[float(q)/float(a_today) for q in source.edges]
    spectrum=[float(cell)*(float(a[-1])/float(a_today))**4/rho_critical_today for cell in density[-1]]
    widths=[math.log(float(hi)/float(lo)) for lo,hi in zip(source.edges[:-1],source.edges[1:])]
    integral=math.fsum(value*width for value,width in zip(spectrum,widths))

    def compare(actual, saved, name):
        if isinstance(actual,dict):
            if not isinstance(saved,dict) or set(actual)!=set(saved):
                raise InputError("GW independent reconstruction differs: "+name)
            for field,value in actual.items():compare(value,saved[field],name+"/"+field)
        elif isinstance(actual,(list,tuple)):
            if not isinstance(saved,(list,tuple)) or len(actual)!=len(saved):
                raise InputError("GW independent reconstruction differs: "+name)
            for i,(value,stored) in enumerate(zip(actual,saved)):compare(value,stored,name+"/"+str(i))
        elif isinstance(actual,(int,float,np.number)) and not isinstance(actual,bool):
            if not isinstance(saved,(int,float)) or not math.isfinite(saved) or not math.isclose(actual,saved,rel_tol=1e-10,abs_tol=0):
                raise InputError("GW independent reconstruction differs: "+name)
        elif actual!=saved:
            raise InputError("GW independent reconstruction differs: "+name)

    compare(frequencies,response.get("f_today_edges_Hz"),"f_today_edges_Hz")
    compare(spectrum,response.get("Omega_GW_today_per_logf"),"Omega_GW_today_per_logf")
    compare(integral,response.get("integrated_Omega_GW_today"),"integrated_Omega_GW_today")
    for name,expected in (("history_id",canonical_hash(history)),("source_sha256",source.source_sha256),
                          ("propagation_history_sha256",canonical_hash(continuation)),
                          ("corner",record["corner"]),("H0_s_inv",float(h0)),
                          ("a_today_in_P7_convention",float(a_today))):
        compare(expected,response.get(name),name)
    epochs=policy.get("bbn_epochs")
    if not isinstance(epochs,list) or not epochs:
        raise InputError("GW response has no registered BBN epochs")
    budgets=[];seen=set()
    for epoch in epochs:
        require_source(epoch,"GW BBN audit epoch")
        target=finite(epoch["time_s"],"GW BBN audit epoch",nonnegative=True)
        matches=[j for j,time in enumerate(t) if abs(time-target)<=max(abs(target),1)*1e-12]
        if len(matches)!=1 or matches[0] in seen:
            raise InputError("GW BBN audit epoch is not one unique saved P7 sample")
        j=matches[0];seen.add(j)
        qh=float(a[j])*float(H[j])/(2*math.pi)
        subhorizon_density=math.fsum(float(cell)*max(math.log(float(hi)/max(float(lo),qh)),0.)
                                   for cell,lo,hi in zip(density[j],source.edges[:-1],source.edges[1:]))
        critical=3*(HBAR_MEV_S*float(H[j]))**2/(8*math.pi*G_NEWTON_MEV_MINUS2)
        budgets.append(dict(time_s=float(t[j]),a_over_a_today=float(a[j]/a_today),H_s_inv=float(H[j]),
            rho_GW_over_rho_total=subhorizon_density/critical,density_already_in_P7_Friedmann=True,
            generation_handling="actual saved epoch density; never back-projected from future emission"))
    compare(budgets,response.get("bbn_budget"),"bbn_budget")
    if donor_paths is not None:
        detectors=_detectors(np.asarray(frequencies),np.asarray(spectrum),float(h0),donor_paths)
        compare(detectors,response.get("detectors"),"detectors")
    remaining=["PTA HD likelihood, astrophysical population and priors",
               "LVK foreground/calibration/systematics treatment and dataset-overlap policy",
               "physical source calibration and uncertainty propagation for this X"]
    return dict(status="PARTIAL",numerical_status=energy_audit["status"],
                reconstructed_history_sha256=canonical_hash(history),
                independent_transfer_method="scalar cell sums from raw P7 densities; producer response not called",
                reconstructed_integrated_Omega_GW_today=integral,
                remaining=remaining+energy_audit.get("remaining",[])+([] if donor_paths is not None else
                    ["GW detector-data reconstruction not executed without pinned donor files"]),
                no_second_BBN_energy_addition=True)


def coverage_status(points, responses_by_point):
    """Account for every P0 point/path; caller first verifies artifact receipts.

    A computed conditional response is distinguished from a missing source.
    Neither becomes full observational acceptance merely by occupying a row.
    """
    identifiers=[p["point_id"] for p in points]
    if len(set(identifiers))!=len(identifiers):
        raise InputError("duplicate P0 GW point")
    if set(responses_by_point)-set(identifiers):
        raise InputError("GW response supplied for an unregistered point")
    rows=[]
    for point in points:
        identity=_key(point)
        row=dict(**identity,role=point.get("role"),full_physical_completion=False)
        bundle=responses_by_point.get(point["point_id"])
        if bundle is None:
            row.update(status="OPEN_INPUT",missing=["common P5/P7 GW source and history"])
        else:
            declared = bundle.get("key") or bundle
            if any(declared.get(k)!=v for k,v in identity.items()):
                raise InputError("GW coverage bundle belongs to a different point/model/path")
            histories=bundle.get("histories",{})
            if bundle.get("status")=="OPEN_INPUT" and not histories:
                if not bundle.get("missing"):
                    raise InputError("GW OPEN_INPUT bundle must identify its missing input")
                row.update(status="OPEN_INPUT",missing=bundle["missing"],
                           response_bundle_sha256=canonical_hash(bundle))
                rows.append(row)
                continue
            if set(histories)!=set(CORNERS):
                raise InputError("GW coverage bundle is missing or duplicates an expected corner")
            for corner,response in histories.items():
                if any(response.get(k)!=v for k,v in identity.items()) or response.get("corner")!=corner:
                    raise InputError("GW coverage corner identity differs")
                if response.get("status") not in {"OPEN_INPUT","CONDITIONAL"}:
                    raise InputError("unsupported GW scientific status")
            missing=[f"{c}: {reason}" for c,r in histories.items()
                     for reason in r.get("missing",r.get("remaining",[]))]
            row.update(status="OPEN_INPUT" if any(r["status"]=="OPEN_INPUT" for r in histories.values())
                       else "CONDITIONAL",missing=missing,
                       response_bundle_sha256=canonical_hash(bundle))
        rows.append(row)
    return dict(schema="R135-GW-coverage-v2",points=len(rows),rows=rows,
                status="OPEN_INPUT" if any(r["status"]=="OPEN_INPUT" for r in rows) else "CONDITIONAL",
                full_physical_completion=False,scientific_acceptance="owner_review")
