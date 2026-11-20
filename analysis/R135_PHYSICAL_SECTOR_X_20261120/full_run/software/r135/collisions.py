"""P6: isotropic 2<->2 collision integrals, decays and thermal transfer models.

The invariant measure is dPi=d^3p/((2pi)^3 2E). Matrix elements are explicit
spin-summed/averaged model inputs, with a separately declared degeneracy and
symmetry factor. All four statistical factors and the inverse reaction are
retained. Rates in natural units are converted to seconds only at the interface.
No hidden-glue portal matrix element is inferred from an energy budget.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from numpy.polynomial.legendre import leggauss
from scipy.special import expit, kv
from scipy.interpolate import RegularGridInterpolator

from .common import (HBAR_MEV_S, InputError, OpenInput, finite, read_json,
                     require_source, write_csv, write_json)

CORNERS = ("00", "10", "01", "11full", "11add")


def kallen(x, y, z):
    return x*x + y*y + z*z - 2*(x*y+x*z+y*z)


class Distribution:
    """Isotropic occupation of a single quantum state, not a number density."""
    def __init__(self, spec):
        self.spec = spec
        self.mass = finite(spec["mass_MeV"], "mass", nonnegative=True)
        self.statistics = spec["statistics"]
        if self.statistics not in {"MB", "FD", "BE"}:
            raise InputError("statistics must be MB, FD or BE")
        self.kind = spec.get("kind", "thermal")
        if self.kind == "thermal":
            self.temperature = finite(spec["T_MeV"], "temperature", positive=True)
            self.mu = finite(spec.get("mu_MeV", 0), "chemical potential")
            if self.statistics == "BE" and self.mu > self.mass:
                raise InputError("bosonic chemical potential exceeds the mass")
        elif self.kind == "tabulated":
            self.p = np.asarray(spec["p_MeV"], float)
            self.f = np.asarray(spec["occupation"], float)
            if self.p.ndim != 1 or len(self.p) < 3 or self.f.shape != self.p.shape or not np.isfinite(self.p).all() or not np.isfinite(self.f).all() or self.p[0] != 0 or np.any(np.diff(self.p) <= 0) or np.any(self.f < 0):
                raise InputError("invalid occupation grid")
            if self.statistics == "FD" and np.any(self.f > 1):
                raise InputError("fermion occupation exceeds one")
            if spec.get("tail") != "zero" or self.f[-1] != 0:
                raise OpenInput("tabulated distributions require an explicit, tested zero tail")
        else:
            raise InputError("unknown distribution kind")

    def at_energy(self, energy):
        e = np.asarray(energy)
        if self.kind == "tabulated":
            return np.interp(np.sqrt(np.maximum(e*e-self.mass*self.mass, 0)), self.p, self.f, right=0)
        x = (e-self.mu)/self.temperature
        if self.statistics == "FD":
            return expit(-x)
        if self.statistics == "BE":
            with np.errstate(over="ignore", divide="ignore"):
                return 1/np.expm1(x)
        return np.exp(np.clip(-x, -745, 700))

    def final_factor(self, occupation):
        return 1 + ({"BE": 1, "FD": -1, "MB": 0}[self.statistics])*occupation


class PolynomialAmplitude:
    """A coherent amplitude sum with supplied complex polynomial coefficients.

    Each term is coefficient*s**s_power*t**t_power. Dimensions, normalization,
    matching scheme and validity ceiling are mandatory physical model data.
    The modulus is squared AFTER adding terms from the same final state.
    """
    def __init__(self, spec):
        require_source(spec, "matrix element")
        if not spec.get("normalization") or not spec.get("coefficient_units"):
            raise InputError("amplitude normalization and coefficient units are required")
        self.maximum = finite(spec["sqrt_s_max_MeV"], "EFT domain", positive=True)
        self.terms = spec["terms"]
        if not self.terms:
            raise InputError("empty amplitude")
        for t in self.terms:
            if t.get("portal", 0) not in {0, 1, 2}:
                raise InputError("portal must be 0 (background), 1 or 2")
            for p in ("s_power", "t_power"):
                if type(t[p]) is not int or t[p] < 0:
                    raise InputError("amplitude powers must be nonnegative integers")
            exponent = -2*(t["s_power"]+t["t_power"])
            expected_unit = "dimensionless" if exponent == 0 else f"MeV^{exponent}"
            if t.get("unit", spec["coefficient_units"]) != expected_unit:
                raise InputError(f"matrix-element coefficient must have unit {expected_unit}")
            finite(t["real"], "amplitude coefficient")
            finite(t.get("imag", 0), "amplitude coefficient")

    def squared(self, s, t, corner):
        if math.sqrt(max(s, 0)) > self.maximum:
            raise InputError("collision quadrature exceeds the amplitude EFT domain")
        if corner == "11add":
            return self.squared(s, t, "10") + self.squared(s, t, "01") - self.squared(s, t, "00")
        if corner not in CORNERS:
            raise InputError("unknown portal corner")
        enabled = {0} | ({1} if corner in {"10", "11full"} else set()) | ({2} if corner in {"01", "11full"} else set())
        a = sum(complex(x["real"], x.get("imag", 0))*s**x["s_power"]*t**x["t_power"]
                for x in self.terms if x.get("portal", 0) in enabled)
        return abs(a)**2


def _quadrature(n, low, high):
    x, w = leggauss(n)
    return low+(x+1)*(high-low)/2, w*(high-low)/2


def collision_2to2(distributions, amplitude, *, p_max_MeV, order=8,
                   symmetry_factor=1., degeneracy=1., corner="11full"):
    """Five-dimensional invariant quadrature; signed moments for all four legs.

    Momentum truncation and angular/radial refinement are explicit caller
    responsibilities. This routine integrates a finite declared domain and
    reports it, rather than treating a thermal cutoff as an exact infinity.
    """
    if len(distributions) != 4 or type(order) is not int or order < 2:
        raise InputError("four distributions and quadrature order >=2 required")
    ds = [d if isinstance(d, Distribution) else Distribution(d) for d in distributions]
    amp = amplitude if isinstance(amplitude, PolynomialAmplitude) else PolynomialAmplitude(amplitude)
    maxp = np.asarray(p_max_MeV, float)
    if maxp.shape != (2,) or not np.isfinite(maxp).all() or np.any(maxp <= 0):
        raise InputError("two explicit positive incoming momentum cutoffs required")
    sym = finite(symmetry_factor, "symmetry factor", positive=True)
    deg = finite(degeneracy, "degeneracy", positive=True)
    p1s, w1s = _quadrature(order, 0, maxp[0])
    p2s, w2s = _quadrature(order, 0, maxp[1])
    cs, ws = leggauss(order)
    phis = 2*np.pi*(np.arange(2*order)+.5)/(2*order)
    angular = [(z, phi, wz*np.pi/order) for z, wz in zip(cs, ws) for phi in phis]
    m1, m2, m3, m4 = [d.mass for d in ds]
    number = np.zeros(4)
    energy = np.zeros(4)
    forward = reverse = 0.
    for p1, w1 in zip(p1s, w1s):
        e1 = math.hypot(p1, m1)
        for p2, w2 in zip(p2s, w2s):
            e2 = math.hypot(p2, m2)
            for c, wc in zip(cs, ws):
                s = m1*m1+m2*m2+2*(e1*e2-p1*p2*c)
                if s <= (m3+m4)**2:
                    continue
                rs = math.sqrt(s)
                # The measure before final-state solid angle.
                pstar = math.sqrt(max(kallen(s, m3*m3, m4*m4), 0))/(2*rs)
                measure = deg/sym * (p1*p1*p2*p2*w1*w2*wc)/(32*np.pi**4*e1*e2)*pstar/(16*np.pi**2*rs)
                beta = np.array([p2*math.sqrt(max(1-c*c, 0)), 0., p1+p2*c])/(e1+e2)
                beta2 = float(beta@beta)
                gamma = (e1+e2)/rs
                e3star = (s+m3*m3-m4*m4)/(2*rs)
                f1, f2 = float(ds[0].at_energy(e1)), float(ds[1].at_energy(e2))
                for z, phi, wa in angular:
                    pstarv = pstar*np.array([math.sqrt(1-z*z)*math.cos(phi), math.sqrt(1-z*z)*math.sin(phi), z])
                    bdot = float(beta@pstarv)
                    e3 = gamma*(e3star+bdot)
                    p3v = pstarv + (((gamma-1)*bdot/beta2 if beta2 > 1e-28 else 0)+gamma*e3star)*beta
                    e4 = e1+e2-e3
                    f3, f4 = float(ds[2].at_energy(e3)), float(ds[3].at_energy(e4))
                    fwd = f1*f2*ds[2].final_factor(f3)*ds[3].final_factor(f4)
                    rev = f3*f4*ds[0].final_factor(f1)*ds[1].final_factor(f2)
                    t = m1*m1+m3*m3-2*(e1*e3-p1*p3v[2])
                    weight = measure*wa*amp.squared(s, t, corner)
                    net = weight*(fwd-rev)
                    number += net*np.array([-1., -1., 1., 1.])
                    energy += net*np.array([-e1, -e2, e3, e4])
                    forward += weight*fwd
                    reverse += weight*rev
    scale = max(abs(forward), abs(reverse), 1e-300)
    return {"number_MeV4": number.tolist(), "energy_MeV5": energy.tolist(),
            "Q_MeV4_s": (energy/HBAR_MEV_S).tolist(),
            "forward_MeV4": forward, "reverse_MeV4": reverse,
            "energy_closure_MeV5": float(energy.sum()),
            "relative_equilibrium_residual": float(np.max(np.abs(number))/scale),
            "order": order, "p_max_MeV": maxp.tolist(), "domain_is_truncated": True,
            "formal_signed_control": corner == "11add"}


def two_body_width(mass_MeV, final_masses_MeV, matrix_element_squared_MeV2, symmetry_factor=1.):
    m = finite(mass_MeV, "parent mass", positive=True)
    m1, m2 = [finite(x, "daughter mass", nonnegative=True) for x in final_masses_MeV]
    a2 = finite(matrix_element_squared_MeV2, "matrix element squared", nonnegative=True)
    sym = finite(symmetry_factor, "symmetry factor", positive=True)
    if m <= m1+m2:
        return 0.
    return a2*math.sqrt(max(kallen(m*m, m1*m1, m2*m2), 0))/(16*np.pi*m**3*sym)


def decay_table(definition):
    result = []
    for species in definition:
        require_source(species, "relic spectrum")
        mass = finite(species["mass_MeV"], "relic mass", positive=True)
        channels = []
        for c in species.get("channels", []):
            require_source(c, "partial width")
            if c.get("kind") == "two_body_constant_amplitude":
                width = two_body_width(mass, c["daughter_masses_MeV"], c["matrix_element_squared_MeV2"], c.get("symmetry_factor", 1))
            elif c.get("kind") == "supplied_width":
                width = finite(c["width_MeV"], "partial width", nonnegative=True)
                if mass <= sum(c["daughter_masses_MeV"]) and width > 0:
                    raise InputError("positive partial width below threshold")
            else:
                raise InputError("unsupported decay width model")
            channels.append((c, width))
        total = sum(x[1] for x in channels)
        if not channels:
            channels = [({"id": "stable", "recipient": "relic", "source": species["source"]}, 0.)]
        for channel, width in channels:
            result.append({"species": species["id"], "channel": channel["id"],
                "recipient": channel["recipient"], "mass_MeV": mass, "width_MeV": width,
                "total_width_MeV": total, "branching_fraction": width/total if total else 0.,
                "lifetime_s": HBAR_MEV_S/total if total else None,
                "stable": total == 0, "source": channel["source"]})
    return result


class ThermalTransfer:
    """Explicit phase-dependent moment closure for thermal baths.

    Q_j = |a_0+c1*a_1+c2*a_2|² (T_X**power-T_j**power), where
    amplitudes carry the declared units. This phenomenological moment model
    must be matched to a supplied calculation; it is not a derived glue portal.
    Direct collision quadratures above can supply independently tested moments.
    """
    def __init__(self, definition):
        self.definition = definition
        require_source(definition, "collision model")
        self.channels = definition.get("thermal_channels", [])
        self.tables = {}
        ids = [x["id"] for x in self.channels]
        if len(set(ids)) != len(ids):
            raise InputError("duplicate collision channel; coherent final states must be combined")
        for c in self.channels:
            require_source(c, "thermal collision moment")
            if c["recipient"] not in {"gamma", "nu", "free"}:
                raise InputError("unknown thermal recipient")
            if c.get("kind") == "tabulated_moment":
                if c.get("unit") != "MeV^4/s":
                    raise InputError("tabulated energy moment must be in MeV^4/s")
                tx, tj = [np.asarray(c[k], float) for k in ("T_X_MeV", "T_recipient_MeV")]
                if any(x.ndim != 1 or len(x) < 2 or not np.isfinite(x).all() or np.any(np.diff(x) <= 0) or x[0] < 0 for x in (tx, tj)):
                    raise InputError("invalid temperature axes for collision moment")
                tables = {}
                for corner in ("00", "10", "01", "11full"):
                    q = np.asarray(c["Q_MeV4_s"][corner], float)
                    if q.shape != (len(tx), len(tj)) or not np.isfinite(q).all():
                        raise InputError("moment grid must cover all four physical corners")
                    tol = finite(c.get("absolute_error_MeV4_s", 0), "moment error", nonnegative=True)
                    if np.any(q*(tx[:, None]-tj[None, :]) < -tol*np.maximum(1, np.abs(tx[:, None]-tj[None, :]))):
                        raise InputError("zero-chemical-potential thermal moment has negative entropy production")
                    tables[corner] = RegularGridInterpolator((tx, tj), q, bounds_error=True)
                lo, hi = max(tx[0], tj[0]), min(tx[-1], tj[-1])
                if lo <= hi:
                    axis = np.unique(np.r_[tx[(tx >= lo) & (tx <= hi)], tj[(tj >= lo) & (tj <= hi)], np.linspace(lo, hi, 31)])
                    for interp in tables.values():
                        if np.max(np.abs(interp(np.column_stack([axis, axis])))) > tol+1e-12:
                            raise InputError("interpolated collision moment violates detailed balance")
                self.tables[c["id"]] = tables
                continue
            if c.get("kind") != "matched_power_law":
                raise OpenInput("thermal transfer requires a computed table or an independently matched power law")
            if c.get("coefficient_unit") != f"MeV^{4-int(c['power'])}/s":
                raise InputError("thermal coefficient dimension mismatch")
            if type(c["power"]) is not int or c["power"] <= 0:
                raise InputError("thermal power must be a positive integer")
            if len(c.get("amplitudes", [])) != 3:
                raise InputError("provide the background, portal 1 and portal 2 amplitudes")
            for x in c["amplitudes"]:
                finite(x, "moment amplitude")
            lo, hi = c["T_range_MeV"]
            if not 0 <= lo < hi:
                raise InputError("invalid moment temperature range")

    def at(self, state, corner="11full"):
        if corner == "11add":
            a, b, z = [self.at(state, x) for x in ("10", "01", "00")]
            return {k: a[k]+b[k]-z[k] for k in a}
        if corner not in CORNERS:
            raise InputError("unknown corner")
        temperatures = {k: state["T_"+k+"_MeV"] for k in ("X", "gamma", "nu", "free")}
        f = finite(state["phase_fraction"], "phase fraction")
        if not 0 <= f <= 1:
            raise InputError("phase fraction must lie in [0,1]")
        for key, temperature in temperatures.items():
            finite(temperature, key+" temperature", nonnegative=True)
        result = {x: 0. for x in ("X", "gamma", "nu", "free")}
        for channel in self.channels:
            target = channel["recipient"]
            tx, tj = temperatures["X"], temperatures[target]
            phase = channel.get("phase_weights", {"hot": 1., "cold": 1.})
            ph = finite(phase["hot"], "hot rate", nonnegative=True)*(1-f) + finite(phase["cold"], "cold rate", nonnegative=True)*f
            if channel["kind"] == "tabulated_moment":
                try:
                    q = ph*float(self.tables[channel["id"]][corner]((tx, tj)))
                except ValueError as exc:
                    raise InputError("collision moment requested outside tabulated domain") from exc
                result[target] += q
                result["X"] -= q
                continue
            lo, hi = channel["T_range_MeV"]
            if not lo <= tx <= hi or not lo <= tj <= hi:
                raise InputError("collision moment requested outside matching domain")
            a0, a1, a2 = channel["amplitudes"]
            amp = a0 + (a1 if corner in {"10", "11full"} else 0) + (a2 if corner in {"01", "11full"} else 0)
            q = ph*amp**2*(tx**channel["power"]-tj**channel["power"])
            result[target] += q
            result["X"] -= q
        return result

    def equilibrium_tolerance(self, state, corner):
        f = state["phase_fraction"]
        tolerances = {s: 0. for s in ("X", "gamma", "nu", "free")}
        for channel in self.channels:
            phase = channel.get("phase_weights", {"hot": 1., "cold": 1.})
            tol = channel.get("absolute_error_MeV4_s", 0.)*(phase["hot"]*(1-f)+phase["cold"]*f)
            tol *= 3 if corner == "11add" else 1
            tolerances[channel["recipient"]] += tol
            tolerances["X"] += tol
        return tolerances


def cannibal_rate(n_MeV3, T_MeV, mass_MeV, coefficient_MeV_minus5, degeneracy=1.):
    """MB 3<->2 number loss, including the equilibrium inverse term."""
    n = finite(n_MeV3, "number density", nonnegative=True)
    t = finite(T_MeV, "temperature", positive=True)
    m = finite(mass_MeV, "mass", positive=True)
    c = finite(coefficient_MeV_minus5, "3to2 coefficient", nonnegative=True)
    degeneracy = finite(degeneracy, "relic degeneracy", positive=True)
    neq = degeneracy*m*m*t*kv(2, m/t)/(2*np.pi**2)
    return c*n*n*(n-neq)/HBAR_MEV_S


def run(config, inputs, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    donor_controls = {}
    selected = [name for name in ("donor_scalar_portal", "donor_3to2") if name in config]
    if selected:
        from .donor_inputs import load_prepared, scalar_partonic_width, nda_3to2
        prepared, binding = load_prepared(inputs)
        write_json(out / "donor_relic_spectrum.json", {
            **prepared["relic_spectrum_control"], "prepared_input": binding})
        if "donor_scalar_portal" in config:
            partial = scalar_partonic_width(prepared, config["donor_scalar_portal"])
            partial["prepared_input"] = binding
            # This partial partonic result must never populate relic channels,
            # a total lifetime, branching fractions, or thermal Q automatically.
            write_json(out / "scalar_portal_partial_width.json", partial)
            donor_controls["scalar_portal"] = partial
        if "donor_3to2" in config:
            number_model = nda_3to2(prepared, config["donor_3to2"])
            number_model["prepared_input"] = binding
            write_json(out / "number_changing_model.json", number_model)
            donor_controls["number_changing"] = number_model
    definition = read_json(inputs["collision_definition"]) if "collision_definition" in inputs else config.get("model")
    if not definition:
        raise OpenInput("P6 requires matrix elements or independently matched collision moments")
    model = ThermalTransfer(definition)
    decay = decay_table(definition.get("relics", []))
    integrals = []
    for reaction in definition.get("reactions", []):
        require_source(reaction, "reaction")
        results = {}
        for corner in CORNERS:
            results[corner] = collision_2to2(reaction["distributions"], reaction["amplitude"],
                p_max_MeV=reaction["p_max_MeV"], order=config.get("quadrature_order", 8),
                symmetry_factor=reaction["symmetry_factor"], degeneracy=reaction["degeneracy"], corner=corner)
        integrals.append({"id": reaction["id"], "source": reaction["source"], "corners": results})
    controls = []
    for state in config.get("check_states", []):
        eq = dict(state)
        for recipient in ("gamma", "nu", "free"):
            eq["T_"+recipient+"_MeV"] = eq["T_X_MeV"]
        for corner in CORNERS:
            q = model.at(state, corner)
            qeq = model.at(eq, corner)
            eqtol = model.equilibrium_tolerance(eq, corner)
            controls.append({"corner": corner, "Q_MeV4_s": q,
                             "sum_Q_MeV4_s": sum(q.values()), "equilibrium": qeq,
                             "equilibrium_tolerance_MeV4_s": eqtol})
            if any(abs(v) > eqtol[s]+1e-12 for s, v in qeq.items()):
                raise RuntimeError("detailed balance control failed")
    thermalization = definition.get("thermalization")
    if thermalization is None:
        thermalization = {"status": "OPEN_INPUT", "reason": "scattering/cascade and thermalization model missing"}
    write_json(out / "collision_model.json", {"schema": "R135-collision-model-v1", "definition": definition,
               "quadratures": integrals, "controls": controls,
               "donor_controls": donor_controls,
               "supplied_matching_refs": definition.get("matching_artifacts", []),
               "independent_matching_status": "REQUIRES_VALIDATION_OF_SUPPLIED_EVIDENCE"})
    write_csv(out / "decay_table.csv", decay, ["species", "channel", "recipient", "mass_MeV", "width_MeV",
               "total_width_MeV", "branching_fraction", "lifetime_s", "stable", "source"])
    write_json(out / "thermalization_model.json", thermalization)
    partial_only = "scalar_portal" in donor_controls
    limitations = ["Portal coefficients, spectrum, matching and thermalization are external physical inputs",
                   "Thermal moment closure does not evolve nonthermal cascades"]
    if partial_only:
        limitations.append("The selected FMS gg helper supplies a partonic partial width only; complete decay channels, hadronic matching, inverse reactions and deposition remain OPEN_INPUT. Its width is not included in decay_table or Q.")
    if "number_changing" in donor_controls:
        limitations.append("The sourced 3<->2 coefficient is an NDA sensitivity input for a single scalar MB closure; its kinetic relaxation and temperature domain must remain valid throughout P7.")
    acceptance = {"schema": "R135-P6-donor-acceptance-v1",
                  "status": "OPEN_INPUT" if partial_only else "CONDITIONAL",
                  "selected_donor_controls": selected,
                  "partial_width_used_in_total_or_energy_source": False,
                  "limitations": limitations}
    if selected:
        write_json(out / "donor_physical_acceptance.json", acceptance)
    return {"software_status": "PASS", "evidence_status": acceptance["status"],
            "physical_input_status": acceptance["status"],
            "metrics": {"reaction_integrals": len(integrals), "decay_channels": len(decay),
                        "donor_controls": len(donor_controls)},
            "limitations": limitations}
