"""Six n <-> p rates for arbitrary isotropic electron-neutrino spectra.

This is the static-nucleon, tree-level (Born) calculation, normalized to a
declared vacuum neutron lifetime. It is not the precision PRIMAT correction
set. Equations and the deliberately open corrections are documented in
NUMERICS_KINETICS_NEUTRINOS.md. No upstream source code is copied here.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math
import warnings

import numpy as np
from scipy.integrate import IntegrationWarning, quad
from scipy.special import expit

from .common import InputError, OpenInput, finite

ELECTRON_MASS_MEV = 0.51099895
NEUTRON_PROTON_GAP_MEV = 1.29333236
DEFAULT_NEUTRON_LIFETIME_S = 879.4  # explicit default, matching pinned LINX
APPROXIMATION = "Born_static_nucleons_lifetime_normalized"
OMITTED_CORRECTIONS = (
    "finite_nucleon_mass_and_recoil", "weak_magnetism", "Coulomb_corrections",
    "zero_temperature_radiative_corrections", "finite_temperature_radiative_corrections",
    "thermal_QED_electron_dispersion", "flavour_density_matrix_evolution",
)


@dataclass(frozen=True)
class ThermalSpectrum:
    """Exact massless Fermi-Dirac occupation; no finite momentum cutoff."""
    T_MeV: float
    mu_MeV: float = 0.0

    def __post_init__(self):
        object.__setattr__(self, "T_MeV", finite(self.T_MeV, "neutrino temperature", positive=True))
        object.__setattr__(self, "mu_MeV", finite(self.mu_MeV, "neutrino chemical potential"))

    def __call__(self, energy):
        return expit((self.mu_MeV-np.asarray(energy))/self.T_MeV)

    @property
    def knots(self):
        return ()

    @property
    def description(self):
        return {"kind": "thermal_FD", "T_MeV": self.T_MeV, "mu_MeV": self.mu_MeV,
                "support": "[0,infinity)"}


class TabulatedSpectrum:
    """Piecewise linear occupation with explicit low-energy/tail policies.

    A declared zero tail defines a compact-support model, not an assertion
    that a physical high-energy tail is unimportant. The caller must refine
    the grid and extend its support. Its last supplied occupation must be 0.
    """
    def __init__(self, energy_MeV, occupation, *, low_energy=None, tail=None):
        self.energy = np.asarray(energy_MeV, dtype=float)
        self.occupation = np.asarray(occupation, dtype=float)
        if (self.energy.ndim != 1 or len(self.energy) < 2 or self.occupation.shape != self.energy.shape
                or not np.isfinite(self.energy).all() or not np.isfinite(self.occupation).all()
                or self.energy[0] < 0 or np.any(np.diff(self.energy) <= 0)
                or np.any(self.occupation < 0) or np.any(self.occupation > 1)):
            raise InputError("invalid neutrino energy grid or fermion occupation outside [0,1]")
        if self.energy[0] > 0 and low_energy not in {"constant", "zero"}:
            raise OpenInput("positive first energy requires an explicit low_energy='constant'/'zero' policy or a point at zero")
        if low_energy not in (None, "constant", "zero"):
            raise InputError("unknown low-energy spectrum policy")
        if tail != "zero" or self.occupation[-1] != 0:
            raise OpenInput("tabulated spectrum needs explicit zero tail and a zero final occupation")
        self.low_energy, self.tail = low_energy, tail

    def __call__(self, energy):
        return np.interp(energy, self.energy, self.occupation,
                         left=0. if self.low_energy == "zero" else self.occupation[0], right=0.)

    @property
    def knots(self):
        return self.energy

    @property
    def description(self):
        return {"kind": "piecewise_linear", "energy_range_MeV": [float(self.energy[0]), float(self.energy[-1])],
                "grid_points": len(self.energy), "low_energy": self.low_energy, "tail": self.tail,
                "grid_and_tail_error": "not included in quadrature estimate; requires independent refinement"}


class BinnedSpectrum:
    """Cell-constant massless spectrum, exactly matching MomentumGrid cells."""
    def __init__(self, energy_edges_MeV, occupation):
        self.edges = np.asarray(energy_edges_MeV, dtype=float)
        self.occupation = np.asarray(occupation, dtype=float)
        if (self.edges.ndim != 1 or len(self.edges) < 2 or self.occupation.shape != (len(self.edges)-1,)
                or not np.isfinite(self.edges).all() or not np.isfinite(self.occupation).all()
                or self.edges[0] != 0 or np.any(np.diff(self.edges) <= 0)
                or np.any(self.occupation < 0) or np.any(self.occupation > 1)):
            raise InputError("invalid cell edges or fermion occupation outside [0,1]")

    def __call__(self, energy):
        energy = np.asarray(energy)
        index = np.searchsorted(self.edges, energy, side="right")-1
        valid = (energy >= 0) & (energy < self.edges[-1])
        return np.where(valid, self.occupation[np.clip(index, 0, len(self.occupation)-1)], 0.)

    @property
    def knots(self):
        return self.edges

    @property
    def description(self):
        return {"kind": "cell_constant", "energy_range_MeV": [0., float(self.edges[-1])],
                "cells": len(self.occupation), "tail": "zero",
                "grid_and_tail_error": "not included in quadrature estimate; requires independent refinement"}


def _spectrum(value):
    if isinstance(value, (ThermalSpectrum, TabulatedSpectrum, BinnedSpectrum)):
        return value
    if not isinstance(value, dict):
        raise InputError("use a declared ThermalSpectrum, TabulatedSpectrum or BinnedSpectrum")
    kind = value.get("kind", "tabulated")
    if kind == "thermal":
        return ThermalSpectrum(value["T_MeV"], value.get("mu_MeV", 0.))
    if kind == "binned":
        return BinnedSpectrum(value["energy_edges_MeV"], value["occupation"])
    if kind == "tabulated":
        return TabulatedSpectrum(value["energy_MeV"], value["occupation"],
                                 low_energy=value.get("low_energy"), tail=value.get("tail"))
    raise InputError("unknown neutrino spectrum representation")


def _integrate(function, low, high, knots, *, epsrel, epsabs):
    points = sorted({float(x) for x in knots if low < x < high})
    intervals = [low, *points, high]
    result, error = 0., 0.
    # Splitting every interpolation breakpoint makes the quadrature estimate
    # meaningful even for narrow nonthermal features or discontinuous cells.
    with warnings.catch_warnings():
        warnings.simplefilter("error", IntegrationWarning)
        try:
            for left, right in zip(intervals[:-1], intervals[1:]):
                val, err = quad(function, left, right, epsrel=epsrel,
                                epsabs=epsabs/max(1, len(intervals)-1), limit=150)
                result += val
                error += err
        except IntegrationWarning as exc:
            raise InputError(f"weak-rate quadrature did not converge: {exc}") from exc
    if not math.isfinite(result) or result < 0 or not math.isfinite(error):
        raise InputError("weak-rate quadrature returned an invalid rate/error")
    return result, error


@lru_cache(maxsize=16)
def _vacuum_integral(me, delta):
    return quad(lambda e: e*math.sqrt(max(e*e-me*me, 0.))*(delta-e)**2,
                me, delta, epsabs=1e-14, epsrel=1e-12, limit=150)


def nucleon_rates(T_gamma_MeV, nu_spectrum, antinu_spectrum, *,
                  neutron_lifetime_s=DEFAULT_NEUTRON_LIFETIME_S, mu_e_MeV=0.,
                  electron_mass_MeV=ELECTRON_MASS_MEV,
                  neutron_proton_gap_MeV=NEUTRON_PROTON_GAP_MEV,
                  epsrel=1e-8, epsabs_MeV5=1e-12):
    """Return physical s^-1 rates for all six allowed charged-current processes.

    Electrons/positrons have a thermal FD bath with chemical potentials +mu_e
    and -mu_e. Neutrino occupations need not be thermal or equal. Nucleons
    are dilute, at rest, and infinitely massive except for a fixed mass gap.
    """
    temperature = finite(T_gamma_MeV, "electron bath temperature", nonnegative=True)
    mu = finite(mu_e_MeV, "electron chemical potential")
    me = finite(electron_mass_MeV, "electron mass", positive=True)
    delta = finite(neutron_proton_gap_MeV, "neutron proton gap", positive=True)
    tau = finite(neutron_lifetime_s, "neutron lifetime", positive=True)
    rel = finite(epsrel, "quadrature relative tolerance", positive=True)
    absolute = finite(epsabs_MeV5, "quadrature absolute tolerance", positive=True)
    if delta <= me or rel < 1e-13 or rel >= 1:
        raise InputError("require neutron decay threshold and 1e-13 <= epsrel < 1")
    nu, anu = _spectrum(nu_spectrum), _spectrum(antinu_spectrum)

    def electron(e, charge):
        potential = mu if charge == -1 else -mu
        if temperature == 0:
            return float(e < potential) + .5*float(e == potential)
        return float(expit((potential-e)/temperature))

    def kernel(e, enu):
        return e*math.sqrt(max(e*e-me*me, 0.))*enu*enu

    # In each row the same phase-space kernel is used for a process and its
    # inverse. Positive-energy occupations expose every blocking factor.
    integrands = {
        "n_nu_to_p_e": (lambda e: kernel(e, e-delta)*float(nu(e-delta))*(1-electron(e, -1)),
                         delta, math.inf, [delta+x for x in nu.knots]),
        "p_e_to_n_nu": (lambda e: kernel(e, e-delta)*electron(e, -1)*(1-float(nu(e-delta))),
                         delta, math.inf, [delta+x for x in nu.knots]),
        "n_positron_to_p_antinu": (lambda e: kernel(e, e+delta)*electron(e, +1)*(1-float(anu(e+delta))),
                                    me, math.inf, [x-delta for x in anu.knots]),
        "p_antinu_to_n_positron": (lambda e: kernel(e, e+delta)*float(anu(e+delta))*(1-electron(e, +1)),
                                    me, math.inf, [x-delta for x in anu.knots]),
        "neutron_decay": (lambda e: kernel(e, delta-e)*(1-electron(e, -1))*(1-float(anu(delta-e))),
                           me, delta, [delta-x for x in anu.knots]),
        "inverse_neutron_decay": (lambda e: kernel(e, delta-e)*electron(e, -1)*float(anu(delta-e)),
                                   me, delta, [delta-x for x in anu.knots]),
    }
    # A zero-temperature degenerate electron bath has a sharp Fermi surface.
    if temperature == 0:
        integrands = {name: (fn, low, high, [*knots, abs(mu)])
                      for name, (fn, low, high, knots) in integrands.items()}
    vacuum, vacuum_error = _vacuum_integral(me, delta)
    normalization = 1/(tau*vacuum)
    channels, errors = {}, {}
    for name, (function, low, high, knots) in integrands.items():
        value, error = _integrate(function, low, high, knots, epsrel=rel, epsabs=absolute)
        channels[name] = normalization*value
        errors[name] = normalization*error + channels[name]*vacuum_error/vacuum
    forward = ("n_nu_to_p_e", "n_positron_to_p_antinu", "neutron_decay")
    backward = ("p_e_to_n_nu", "p_antinu_to_n_positron", "inverse_neutron_decay")
    return {"lambda_n_to_p_s_inv": sum(channels[x] for x in forward),
            "lambda_p_to_n_s_inv": sum(channels[x] for x in backward),
            "channels_s_inv": channels,
            "quadrature_abs_error_s_inv": {"n_to_p": sum(errors[x] for x in forward),
                                            "p_to_n": sum(errors[x] for x in backward)},
            "quadrature_channel_abs_error_s_inv": errors,
            "unit": "s^-1", "neutron_lifetime_s": tau,
            "electron_mass_MeV": me, "neutron_proton_gap_MeV": delta,
            "vacuum_phase_space_MeV5": vacuum,
            "approximation": APPROXIMATION, "omitted_corrections": list(OMITTED_CORRECTIONS),
            "production_precision_validated": False,
            "spectra": {"nu_e": nu.description, "antinu_e": anu.description},
            "source": "Pitrou et al. Phys.Rept.754 (2018), Eqs.77-79,89-91; original six-process quadrature"}


def weak_rates_from_history(history, *, neutron_lifetime_s=DEFAULT_NEUTRON_LIFETIME_S,
                            mu_e_MeV=0., low_energy=None, tail=None, **quadrature):
    """Integrate each time slice; return the existing P8 weak-rate contract.

    Spectra may carry ``energy_edges_MeV`` for cell-constant data. Otherwise
    their positive node grid uses the explicitly declared low-energy policy.
    A single grid or a grid for each time is accepted for cell edges only.
    No temperature sorting or thermal fitting is performed.
    """
    from .observations import bridge_hash

    t = np.asarray(history.get("time_s"), float)
    tg = np.asarray(history.get("T_gamma_MeV"), float)
    if (t.ndim != 1 or len(t) < 2 or tg.shape != t.shape or not np.isfinite(t).all()
            or not np.isfinite(tg).all() or t[0] < 0 or np.any(np.diff(t) <= 0) or np.any(tg < 0)):
        raise InputError("invalid weak history time/temperature arrays")
    if not all(name in history for name in ("f_nu_e", "f_antinu_e")):
        raise OpenInput("arbitrary-spectrum weak rates require f_nu_e and f_antinu_e")
    mu = np.asarray(mu_e_MeV, float)
    if mu.ndim == 0:
        mu = np.full(len(t), float(mu))
    if mu.shape != t.shape or not np.isfinite(mu).all():
        raise InputError("invalid electron chemical-potential history")

    def row_spectrum(name, i):
        spec = history[name]
        values = np.asarray(spec.get("values"), float)
        if values.ndim != 2 or values.shape[0] != len(t):
            raise InputError(f"{name}: missing time/momentum occupation array")
        if "energy_edges_MeV" in spec:
            edges = np.asarray(spec["energy_edges_MeV"], float)
            if edges.ndim == 2:
                if edges.shape[0] != len(t):
                    raise InputError("cell-edge time axis differs from history")
                edges = edges[i]
            return BinnedSpectrum(edges, values[i])
        return TabulatedSpectrum(spec["energy_MeV"], values[i],
                                 low_energy=spec.get("low_energy", low_energy), tail=spec.get("tail", tail))

    rows = [nucleon_rates(tg[i], row_spectrum("f_nu_e", i), row_spectrum("f_antinu_e", i),
                          neutron_lifetime_s=neutron_lifetime_s, mu_e_MeV=mu[i], **quadrature)
            for i in range(len(t))]
    return {"time_s": t.tolist(), "unit": "s^-1", "source": rows[0]["source"],
            "lambda_n_to_p_s_inv": [r["lambda_n_to_p_s_inv"] for r in rows],
            "lambda_p_to_n_s_inv": [r["lambda_p_to_n_s_inv"] for r in rows],
            "neutrino_spectra_sha256": bridge_hash({name: history[name] for name in ("f_nu_e", "f_antinu_e")}),
            "neutron_lifetime_s": float(neutron_lifetime_s),
            "approximation": APPROXIMATION, "omitted_corrections": list(OMITTED_CORRECTIONS),
            "production_precision_validated": False,
            "quadrature_abs_error_s_inv": [r["quadrature_abs_error_s_inv"] for r in rows],
            "channels_s_inv": [r["channels_s_inv"] for r in rows],
            "spectrum_domain": {name: rows[0]["spectra"][key]
                                for name, key in (("f_nu_e", "nu_e"), ("f_antinu_e", "antinu_e"))}}
