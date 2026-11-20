"""Pinned electromagnetic cascades and post-BBN photodisintegration.

This is an adapter to the *actual* ACROPOLIS collision kernels and nuclear
cross sections, not the often invalid universal photon spectrum.  The donor
is fetched only at an immutable commit and all imported files are verified.
The supplied physical background is used at each time, including its baryon
density.  A time-ordered nuclear evolution then acts on nine explicit initial
abundances.  It does not compute low-energy heat deposition, hadronisation,
hadronic interconversion, or fusion during thermal BBN.

Our adapter and additions are original code. ACROPOLIS is an external GPL-3.0
program; its license and hashes accompany every fetched copy. See
NUMERICS_CASCADES.md for units, numerical tests, and applicability limits.
"""
from __future__ import annotations

import argparse
import copy
import importlib
import importlib.metadata
import json
import math
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

import numpy as np
from scipy.integrate import cumulative_trapezoid, solve_ivp

from .common import (HBAR_MEV_S, HBARC_MEV_CM, InputError, OpenInput, canonical_hash, finite,
                     read_json, require_source, sha256, write_json)


SPECIES = ("n", "p", "d", "t", "He3", "He4", "Li6", "Li7", "Be7")
MASS_NUMBER = np.array([1, 1, 2, 3, 3, 4, 6, 7, 7], dtype=float)
CHARGE = np.array([0, 1, 1, 1, 2, 2, 3, 3, 4], dtype=float)
EM_SPECIES = ("photon", "electron", "positron")
LOCK_PATH = Path(__file__).resolve().parents[1] / "cascade_sources.lock.json"
ACROPOLIS_SHA = "3bbbc243e0c101142ff1df81216638eb0d8e6d27"
ENERGY_CUTOFF_MEV = 1.5
_IMPORT_PATH = None


def _array(value, shape, name, *, positive=False, nonnegative=False):
    try:
        out = np.asarray(value, dtype=float)
    except (TypeError, ValueError) as exc:
        raise InputError(f"{name}: expected a numerical array") from exc
    if out.shape != shape or not np.isfinite(out).all():
        raise InputError(f"{name}: expected finite array of shape {shape}")
    if (positive and np.any(out <= 0)) or (nonnegative and np.any(out < 0)):
        raise InputError(f"{name}: values outside the permitted domain")
    return out


def fetch_acropolis(destination: Path, *, fetch=True) -> dict:
    """Fetch/verify a minimal pinned donor tree; never execute before hashing.

    No `pip install` is performed. NumPy/SciPy are the R135 dependencies;
    optional Numba accelerates the exact same donor kernels. All data files,
    including the rate database, are subject to the source lock.
    """
    destination = Path(destination).expanduser().resolve()
    lock = read_json(LOCK_PATH)
    if lock["commit"] != ACROPOLIS_SHA:
        raise InputError("ACROPOLIS lock does not match the adapter commit")
    records = []
    for rel, record in lock["files"].items():
        target = destination / rel
        if not target.is_file():
            if not fetch:
                raise OpenInput(f"missing pinned ACROPOLIS file: {target}")
            target.parent.mkdir(parents=True, exist_ok=True)
            # URLs are constructed from the fixed public upstream, never inputs.
            url = f"https://raw.githubusercontent.com/hep-mh/acropolis/{ACROPOLIS_SHA}/{rel}"
            with urllib.request.urlopen(url, timeout=60) as response:
                data = response.read(record["bytes"] + 1)
            if len(data) != record["bytes"]:
                raise InputError(f"ACROPOLIS size mismatch: {rel}")
            import hashlib
            if hashlib.sha256(data).hexdigest() != record["sha256"]:
                raise InputError(f"ACROPOLIS download hash mismatch: {rel}")
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as tmp:
                tmp.write(data)
                temporary = Path(tmp.name)
            temporary.replace(target)
        if target.stat().st_size != record["bytes"] or sha256(target) != record["sha256"]:
            raise InputError(f"ACROPOLIS hash mismatch: {rel}")
        records.append({"path": rel, **record})
    return {"name": "ACROPOLIS", "version": lock["version"], "commit": ACROPOLIS_SHA,
            "license": lock["license"], "source": lock["repository"],
            "lock_sha256": sha256(LOCK_PATH), "files": records}


def _load_donor(path, *, fetch):
    global _IMPORT_PATH
    if path is None:
        path = os.environ.get("R135_ACROPOLIS_PATH")
    if path is None:
        path = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "r135" / ("acropolis-" + ACROPOLIS_SHA)
    path = Path(path).expanduser().resolve()
    receipt = fetch_acropolis(path, fetch=fetch)
    if _IMPORT_PATH is not None and _IMPORT_PATH != path:
        raise InputError("ACROPOLIS already imported from a different path; use a fresh process")
    if "acropolis" in sys.modules:
        actual = Path(sys.modules["acropolis"].__file__).resolve().parents[1]
        if actual != path:
            raise InputError("unverified ACROPOLIS already imported; use a fresh process")
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
    cascade = importlib.import_module("acropolis.cascade")
    nuclear = importlib.import_module("acropolis.nucl")
    flags = importlib.import_module("acropolis.flags")
    _IMPORT_PATH = path
    flags.verbose = False
    flags.universal = False
    flags.usedb = True
    receipt["environment"] = {"python": sys.version.split()[0]}
    for package in ("numpy", "scipy", "numba", "llvmlite"):
        try:
            receipt["environment"][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            receipt["environment"][package] = None
    return cascade, nuclear, receipt


def linear_spectrum_moment(energy, spectrum, *, energy_weighted=True):
    """Exact number/energy integral of a piecewise *linear* input spectrum."""
    energy = np.asarray(energy, dtype=float)
    spectrum = np.asarray(spectrum, dtype=float)
    if not energy_weighted:
        return np.sum(np.diff(energy) * (spectrum[..., :-1] + spectrum[..., 1:]) / 2, axis=-1)
    lo, hi, width = energy[:-1], energy[1:], np.diff(energy)
    return np.sum(width / 6 * ((2*lo+hi)*spectrum[..., :-1] +
                              (lo+2*hi)*spectrum[..., 1:]), axis=-1)


def validate_config(config):
    """Validate physical units, domains and source/energy accounting up front."""
    if config.get("schema") != "r135.em_cascade.v1":
        raise InputError("expected schema r135.em_cascade.v1")
    if "stable_projection" in config and not isinstance(config["stable_projection"], bool):
        raise InputError("stable_projection must be an explicit boolean")
    for name in ("background", "initial_abundances", "injection"):
        if not isinstance(config.get(name), dict):
            raise OpenInput(f"missing {name} definition")
    bg, initial, injection = (config[k] for k in ("background", "initial_abundances", "injection"))
    for name, value in (("background", bg), ("initial abundances", initial), ("injection", injection)):
        require_source(value, name)
    t = np.asarray(bg.get("time_s"), dtype=float)
    if t.ndim != 1 or len(t) < 2 or not np.isfinite(t).all() or np.any(np.diff(t) <= 0) or t[0] < 0:
        raise InputError("time_s must be a strictly increasing nonnegative grid")
    nt = len(t)
    if "time_s" in injection and not np.array_equal(np.asarray(injection["time_s"], float), t):
        raise InputError("injection times do not match the physical background")
    T, nb, H, a = [_array(bg.get(key), (nt,), key, positive=True) for key in
                   ("T_gamma_MeV", "n_b_MeV3", "H_s", "a")]
    if np.min(T) < 1e-6 or np.max(T) > 5e-3:
        raise OpenInput("this post-BBN cascade supports 1 eV <= T_gamma <= 5 keV")
    if np.any(np.diff(a) < 0):
        raise InputError("expanding-background scale factor decreases")
    baryon = nb * (a/a[0])**3
    if np.max(np.abs(baryon/baryon[0]-1)) > 1e-4:
        raise InputError("background n_b*a^3 is not conserved")
    # Integral check avoids a noisy numerical derivative on irregular grids.
    lna = cumulative_trapezoid(H, t, initial=0)
    expansion_error = float(np.max(np.abs(np.log(a/a[0])-lna)))
    allowed_expansion_error = finite(config.get("numerics", {}).get("background_integral_atol", .01),
                                    "background_integral_atol", positive=True)
    if expansion_error > allowed_expansion_error:
        raise InputError("supplied H, time and a are inconsistent or undersampled")
    if initial.get("species") != list(SPECIES):
        raise OpenInput("nine explicit initial abundances required, including Li6")
    Y = _array(initial.get("Y"), (9,), "initial Y", nonnegative=True)
    if not np.isclose(MASS_NUMBER @ Y, 1, atol=1e-9, rtol=1e-9):
        raise InputError("initial Y must be number per baryon: sum(A_i Y_i)=1")
    if finite(initial.get("epoch_time_s"), "abundance epoch", nonnegative=True) != t[0]:
        raise InputError("initial abundances must refer to the first supplied physical time")
    covariance = None
    if "covariance" in initial:
        covariance = _array(initial["covariance"], (9, 9), "initial covariance")
        if not np.allclose(covariance, covariance.T, rtol=1e-10, atol=1e-30):
            raise InputError("initial covariance is not symmetric")
        if np.min(np.linalg.eigvalsh(covariance)) < -1e-12 * max(np.max(np.abs(covariance)), 1e-300):
            raise InputError("initial covariance is not positive semidefinite")
    E = np.asarray(injection.get("energy_MeV", [ENERGY_CUTOFF_MEV, 2.]), dtype=float)
    if E.ndim != 1 or len(E) < 2 or not np.isfinite(E).all() or E[0] <= 0 or np.any(np.diff(E) <= 0):
        raise InputError("injection energy grid must be positive and strictly increasing")
    if E[-1] > 1000:
        raise OpenInput("ACROPOLIS full-cascade injection is restricted to <= 1 GeV")
    continuous = np.array([_array(injection.get(f"{s}_dN_dVdt_dE_MeV2_s", np.zeros((nt, len(E)))),
                                  (nt, len(E)), s + " injection", nonnegative=True) for s in EM_SPECIES])
    if np.any(continuous[1:, :, E < .511] != 0):
        raise InputError("electron/positron energy is total energy and cannot be below m_e")
    first_mass_bin = int(np.searchsorted(E, .511))
    if 0 < first_mass_bin < len(E) and np.any(continuous[1:, :, first_mass_bin] != 0):
        raise InputError("linear electron injection would extend below m_e; add a zero boundary at m_e")
    lines = []
    for entry in injection.get("lines", []):
        if entry.get("species") not in EM_SPECIES:
            raise OpenInput("only photon/electron/positron injection is implemented here")
        e = finite(entry.get("energy_MeV"), "line total energy", positive=True)
        if e > 1000 or (entry["species"] != "photon" and e < .511):
            raise OpenInput("injection line outside supported total-energy domain")
        rates = _array(entry.get("dN_dVdt_MeV3_s"), (nt,), "line injection", nonnegative=True)
        lines.append((EM_SPECIES.index(entry["species"]), e, rates))
    q = np.sum(linear_spectrum_moment(E, continuous), axis=0)
    number = linear_spectrum_moment(E, continuous, energy_weighted=False)
    for s, e, rates in lines:
        q += e * rates
        number[s] += rates
    stated_q = _array(injection.get("power_MeV4_s"), (nt,), "declared injection power", nonnegative=True)
    q_scale = max(float(np.max(q)), float(np.max(stated_q)), 1e-300)
    if np.max(np.abs(q-stated_q)) > 1e-7 * q_scale:
        raise InputError("injection spectrum/lines do not reproduce the declared EM power")
    if np.max(np.abs(number[1]-number[2])) > 1e-9 * max(float(np.max(number[1:])), 1e-300):
        raise OpenInput("net electric charge injection needs an evolving charged background")
    domain = config.get("applicability", {})
    if domain.get("fully_ionized") is not True:
        raise OpenInput("a fully ionized background must be justified explicitly")
    require_source(domain, "cascade applicability")
    if domain.get("thermal_nuclear_reactions_negligible") is not True:
        raise OpenInput("post-BBN cascade requires negligible thermal fusion at the input epoch")
    max_energy = finite(domain.get("max_injected_radiation_fraction", .01),
                        "max_injected_radiation_fraction", positive=True)
    if max_energy > .01:
        raise OpenInput("large-injection backreaction requires a coupled low-energy deposition calculation")
    rho_gamma = math.pi**2 / 15 * T**4
    # Redshift the injected relativistic energy on the *supplied* background.
    injected_rho = cumulative_trapezoid(q * (a/a[0])**4, t, initial=0) / (a/a[0])**4
    energy_fraction = float(np.max(injected_rho/rho_gamma))
    if energy_fraction > max_energy:
        raise OpenInput("injection exceeds the declared perturbative-background domain")
    return {"time": t, "T": T, "nb": nb, "H": H, "a": a, "Y": Y, "covariance": covariance,
            "E": E, "continuous": continuous, "lines": lines, "power": q,
            "injected_radiation_fraction": energy_fraction, "expansion_integral_error": expansion_error}


def config_from_p7(history, injection, initial_abundances, *, start_index, applicability, numerics=None):
    """Bind one actual P7 corner to a separately sourced late injection model.

    `history` is one entry of channel_history.json['histories'], not a mixture
    of corners. Injection MUST provide time_s on either that full grid or its
    exact suffix. No source/history is resampled, fitted or replaced by an
    SM history. Initial abundances must already be evolved to the suffix's
    first epoch, including all nine nuclei. A specified source-history hash
    is checked. This postprocessor does not feed thermal heat back into P7.

    Optionally `p7_power_binding='positive_Q_gamma'` requires the entire
    nonthermal injection power to equal positive Q_gamma from that history.
    It is never the default: net bath heat and gross nonthermal production
    need not be the same physical source.
    """
    if not isinstance(start_index, int) or isinstance(start_index, bool):
        raise InputError("cascade start_index must be an integer")
    t = np.asarray(history.get("time_s"), dtype=float)
    if t.ndim != 1 or not (0 <= start_index < len(t)-1):
        raise InputError("P7 cascade suffix must contain at least two time samples")
    history_hash = canonical_hash(history)
    if injection.get("source_history_sha256", history_hash) != history_hash:
        raise InputError("cascade injection was prepared for a different P7 history")
    source_time = np.asarray(injection.get("time_s"), dtype=float)
    if np.array_equal(source_time, t):
        offset = start_index
    elif np.array_equal(source_time, t[start_index:]):
        offset = 0
    else:
        raise InputError("injection must use the complete P7 time grid or its exact cascade suffix")
    bound = copy.deepcopy(injection)
    bound["time_s"] = t[start_index:].tolist()
    source_count = len(source_time)
    for key in ("power_MeV4_s", *(s+"_dN_dVdt_dE_MeV2_s" for s in EM_SPECIES)):
        if key in bound:
            values = np.asarray(bound[key], dtype=float)
            if values.ndim < 1 or len(values) != source_count:
                raise InputError(f"injection {key} is not aligned with its declared time grid")
            bound[key] = values[offset:].tolist()
    for line in bound.get("lines", []):
        values = _array(line.get("dN_dVdt_MeV3_s"), (source_count,), "P7 line injection", nonnegative=True)
        line["dN_dVdt_MeV3_s"] = values[offset:].tolist()
    bound["source_history_sha256"] = history_hash
    background = {"time_s": t[start_index:].tolist(),
                  "source": "actual P7 history sha256:" + history_hash,
                  "source_history_sha256": history_hash,
                  "p7_start_index": start_index}
    for src, dst, factor in (("T_gamma_MeV", "T_gamma_MeV", 1),
                             ("n_b_cm3", "n_b_MeV3", HBARC_MEV_CM**3),
                             ("H_s_inv", "H_s", 1), ("scale_factor", "a", 1)):
        background[dst] = (_array(history.get(src), (len(t),), "P7 "+src, positive=True)[start_index:]*factor).tolist()
    power_binding = injection.get("p7_power_binding")
    if power_binding is not None:
        if power_binding != "positive_Q_gamma":
            raise InputError("unknown P7 nonthermal-power binding")
        qgamma = _array(history.get("Q_MeV4_s", {}).get("gamma"), (len(t),), "P7 Q_gamma")
        expected = np.maximum(qgamma[start_index:], 0)
        supplied = _array(bound.get("power_MeV4_s"), expected.shape, "bound injection power", nonnegative=True)
        if np.max(np.abs(expected-supplied)) > 1e-7*max(float(np.max(expected)), float(np.max(supplied)), 1e-300):
            raise InputError("nonthermal source does not match the declared P7 positive-Q_gamma binding")
    config = {"schema": "r135.em_cascade.v1", "background": background,
              "initial_abundances": copy.deepcopy(initial_abundances), "injection": bound,
              "applicability": copy.deepcopy(applicability), "numerics": copy.deepcopy(numerics or {}),
              "p7_handoff": {"history_sha256": history_hash,
                  "source_injection_sha256": canonical_hash(injection), "start_index": start_index,
                  "thermal_feedback": "NOT_COMPUTED_POSTPROCESSING_ONLY",
                  "power_binding": power_binding or "SEPARATELY_SOURCED_NONTHERMAL_INJECTION"}}
    validate_config(config)
    return config


class _BackgroundAtTime:
    """Minimal public donor input protocol; never uses a donor SM history."""
    def __init__(self, Y, T, nb):
        self.Y, self.T, self.nb = Y, T, nb

    def bbn_abundances_0(self):
        return self.Y

    def parameter(self, name):
        if name != "eta":
            raise InputError(f"unexpected donor background parameter {name}")
        from scipy.special import zeta
        return self.nb / (2 * zeta(3) / math.pi**2 * self.T**3)


def _set_actual_densities(generator, Y, nb):
    # Bound instance callbacks change the density input, not a microscopic rate.
    # All fully ionized species enter charge and Z^2 sums, including d/t/Li/Be.
    ne, nZ2 = float(CHARGE @ Y) * nb, float((CHARGE**2) @ Y) * nb
    for wrapper in generator._sRW.values():
        wrapper._nb = lambda T, v=nb: v
        wrapper._ne = lambda T, v=ne: v
        wrapper._nNZ2 = lambda T, v=nZ2: v


def _one_cascade(cascade, nuclear, Y, T, nb, E0, line, energy, continuous, ne_pd, ne_min):
    """Actual donor spectrum and cross-section integrals for one linear source."""
    cascade.NE_pd, cascade.NE_min = ne_pd, ne_min
    ii = _BackgroundAtTime(Y, T, nb)
    generator = cascade.SpectrumGenerator(ii)
    _set_actual_densities(generator, Y, nb)
    # Convert rates per physical second to donor natural-time sources.
    s0 = [lambda temp, x=x: x * HBAR_MEV_S for x in line]
    sc = [lambda E, temp, row=row: float(np.interp(E, energy, row, left=0, right=0)) * HBAR_MEV_S
          for row in continuous]
    spectrum = generator.get_spectrum(E0, s0, sc, T, allX=True)
    eg, fg = spectrum[0], spectrum[1:]
    if not np.isfinite(spectrum).all() or np.any(fg < 0):
        raise InputError("non-finite or negative ACROPOLIS spectrum")
    reactor = nuclear.NuclearReactor(s0, sc, (T, T), E0, ii)
    reactor._sGen = generator
    # Use the donor's exact integral/rate implementation, sharing this spectrum.
    # Returning the cached result avoids solving the expensive cascade twice.
    original_get = generator.get_spectrum
    generator.get_spectrum = lambda *args, **kw: spectrum[:2]
    try:
        natural_rates = reactor._pdi_rates(T)
    finally:
        generator.get_spectrum = original_get
    # Upstream uses 1e-200 solely as a logarithmic interpolation floor.
    # Exact zero channels must stay zero and preserve source linearity.
    rates = np.array([0. if natural_rates[i] <= nuclear.approx_zero*(1+1e-12)
                      else natural_rates[i] / HBAR_MEV_S for i in range(1, 18)])
    # Delta peaks are separate from the continuous spectrum, as in the donor.
    destruction = np.array([[generator._rate_x(s, e, T) for e in eg] for s in range(3)])
    peak_number = np.array(line) * HBAR_MEV_S / destruction[:, -1]
    rho_nt = float(np.sum(np.trapezoid(fg * eg, x=eg, axis=1)) + E0 * np.sum(peak_number))
    min_rate = float(np.min(destruction) / HBAR_MEV_S)
    return rates, {"energy_MeV": eg.tolist(), "dn_dE_MeV2": fg.tolist(),
                   "delta_energy_MeV": E0, "delta_number_MeV3": peak_number.tolist()}, rho_nt, min_rate


def nuclear_generators(rates, *, neutron_lifetime_s=879.4, tritium_lifetime_s=5.605e8):
    """17 measured-channel rates -> baryon-conserving augmented generators.

    Donor channel 11 is inclusive `Li6+gamma -> X`. Its products are not
    supplied. A tenth *unresolved Li6 event* coordinate preserves its six
    baryons without inventing exclusive isotope yields. It is never silently
    assigned to protons, deuterium or helium.
    """
    rates = np.asarray(rates, dtype=float)
    if rates.ndim != 2 or rates.shape[1] != 17 or not np.isfinite(rates).all() or np.any(rates < 0):
        raise InputError("photodisintegration rates must have shape (N,17), nonnegative")
    channels = [(2, {0: 1, 1: 1}), (3, {0: 1, 2: 1}), (3, {0: 2, 1: 1}),
                (4, {1: 1, 2: 1}), (4, {0: 1, 1: 2}), (5, {1: 1, 3: 1}),
                (5, {0: 1, 4: 1}), (5, {2: 2}), (5, {0: 1, 1: 1, 2: 1}),
                (6, {0: 1, 1: 1, 5: 1}), (6, {9: 1}), (7, {3: 1, 5: 1}),
                (7, {0: 1, 6: 1}), (7, {0: 2, 1: 1, 5: 1}), (8, {4: 1, 5: 1}),
                (8, {1: 1, 6: 1}), (8, {1: 2, 0: 1, 5: 1})]
    generators = np.zeros((len(rates), 10, 10))
    for r, (parent, products) in enumerate(channels):
        generators[:, parent, parent] -= rates[:, r]
        for daughter, multiplicity in products.items():
            generators[:, daughter, parent] += multiplicity * rates[:, r]
    for parent, daughter, lifetime in ((0, 1, neutron_lifetime_s), (3, 4, tritium_lifetime_s)):
        lifetime = finite(lifetime, "nuclear lifetime", positive=True)
        generators[:, parent, parent] -= 1/lifetime
        generators[:, daughter, parent] += 1/lifetime
    return generators


def evolve_abundances(time_s, rate_s, Y0, *, rtol=1e-8, atol=1e-14, stable_projection=False):
    """Time-ordered network evolution; no exp(integral R) commutation assumption."""
    t = np.asarray(time_s, dtype=float)
    y0 = _array(Y0, (9,), "initial abundances", nonnegative=True)
    generators = nuclear_generators(rate_s)
    if len(generators) != len(t) or np.any(np.diff(t) <= 0):
        raise InputError("nuclear times/rates mismatch")
    def matrix_at(ti):
        k = min(max(int(np.searchsorted(t, ti))-1, 0), len(t)-2)
        f = (ti-t[k])/(t[k+1]-t[k])
        return (1-f)*generators[k] + f*generators[k+1]
    u0 = np.eye(10)[:, :9]
    solution = solve_ivp(lambda ti, u: (matrix_at(ti) @ u.reshape(10, 9)).ravel(),
                         (t[0], t[-1]), u0.ravel(), method="BDF", t_eval=t,
                         jac=lambda ti, u: np.kron(matrix_at(ti), np.eye(9)),
                         rtol=rtol, atol=atol)
    if not solution.success:
        raise InputError("photodisintegration network failed: " + solution.message)
    transfer = solution.y.T.reshape(len(t), 10, 9)
    history = transfer @ y0
    if np.min(history) < -100*atol:
        raise InputError("photodisintegration network lost positivity")
    augmented_A = np.append(MASS_NUMBER, 6.)
    residual = float(np.max(np.abs(history @ augmented_A - MASS_NUMBER @ y0)))
    if residual > max(1e-9, 100*atol):
        raise InputError("photodisintegration network failed its baryon ledger")
    final_transfer = transfer[-1].copy()
    if stable_projection:
        decay = np.eye(10)
        for parent, daughter in ((0, 1), (3, 4), (8, 7)):
            decay[parent, parent], decay[daughter, parent] = 0, 1
        final_transfer = decay @ final_transfer
    return {"abundance_history": history[:, :9], "unresolved_Li6_history": history[:, 9],
            "final_Y": (final_transfer @ y0)[:9], "transfer_matrix": final_transfer[:9],
            "unresolved_transfer_row": final_transfer[9], "baryon_residual": residual,
            "network_nfev": solution.nfev, "stable_projection": stable_projection}


def run_electromagnetic_cascade(config, *, donor_path=None, fetch=True) -> dict:
    """Execute a sourced physical-time EM cascade and post-BBN response.

    Every supplied time is a collision-kernel sample. Refine the source/time
    grid and energy_points_per_decade for a requested observable accuracy.
    Arbitrary sharp sources between supplied samples cannot be inferred.
    """
    data = validate_config(config)
    numerics, domain = config.get("numerics", {}), config["applicability"]
    ne_pd = int(numerics.get("energy_points_per_decade", 120))
    ne_min = int(numerics.get("energy_points_min", 10))
    if ne_pd < 10 or ne_min < 10:
        raise InputError("cascade energy grid is too small")
    cascade, nuclear, receipt = _load_donor(donor_path, fetch=fetch)
    spectra, all_rates, density, fastest_ratio = [], [], [], []
    t, q = data["time"], data["power"]
    evolution_rate = np.maximum(data["H"], np.abs(np.gradient(np.log(data["T"]), t)))
    qfloor = max(float(np.max(q))*1e-12, 1e-300)
    evolution_rate = np.maximum(evolution_rate, np.abs(np.gradient(q, t))/np.maximum(q, qfloor))
    for i, (T, nb) in enumerate(zip(data["T"], data["nb"])):
        rate, rho, minimum = np.zeros(17), 0., math.inf
        components = []
        continuous = data["continuous"][:, i, :]
        sources = []
        if np.any(continuous != 0) and data["E"][-1] > ENERGY_CUTOFF_MEV:
            sources.append((data["E"][-1], np.zeros(3), continuous))
        # Linearity permits exact distinct delta energies, without broadening
        # a monochromatic source into a continuum bin.
        groups = {}
        for species, energy, numbers in data["lines"]:
            if energy > ENERGY_CUTOFF_MEV and numbers[i] != 0:
                groups.setdefault(energy, np.zeros(3))[species] += numbers[i]
        for energy, numbers in groups.items():
            sources.append((energy, numbers, np.zeros_like(continuous)))
        for energy, line, continuum in sources:
            rr, spectrum, rn, minimum_rate = _one_cascade(
                cascade, nuclear, data["Y"], T, nb, energy, line, data["E"], continuum, ne_pd, ne_min)
            rate += rr
            rho += rn
            minimum = min(minimum, minimum_rate)
            components.append(spectrum)
        all_rates.append(rate)
        spectra.append({"time_s": float(t[i]), "T_gamma_MeV": float(T), "components": components})
        density.append(rho)
        fastest_ratio.append(None if not sources else minimum/max(float(evolution_rate[i]), 1e-300))
    rates = np.array(all_rates)
    finite_ratios = [r for r in fastest_ratio if r is not None]
    required_ratio = finite(domain.get("min_collision_to_evolution_ratio", 100), "quasistatic rate ratio", positive=True)
    if finite_ratios and min(finite_ratios) < required_ratio:
        raise OpenInput("quasistatic cascade rate is too slow for this injection/background variation")
    rho_fraction = float(np.max(np.array(density)/(math.pi**2/15 * data["T"]**4)))
    if rho_fraction > .01:
        raise OpenInput("nonthermal radiation is not a small perturbation to the cascade bath")
    result = evolve_abundances(t, rates, data["Y"], rtol=float(numerics.get("rtol", 1e-8)),
                               atol=float(numerics.get("atol", 1e-14)),
                               stable_projection=bool(config.get("stable_projection", False)))
    composition_change = float(np.max(np.abs(result["abundance_history"][:, [1, 5]] - data["Y"][[1, 5]]) /
                                     np.maximum(data["Y"][[1, 5]], 1e-300)))
    allowed_change = finite(domain.get("max_fractional_p_He4_change", .01), "composition tolerance", positive=True)
    if allowed_change > .01 or composition_change > allowed_change:
        raise OpenInput("fixed-target cascade requires an iterative composition/background calculation")
    unresolved = 6 * float(result["unresolved_Li6_history"][-1])
    unresolved_limit = finite(domain.get("max_unresolved_baryon_fraction", 1e-12), "unresolved baryon tolerance", positive=True)
    if unresolved > unresolved_limit:
        raise OpenInput("inclusive Li6 channel requires exclusive nuclear yields for this preparation")
    final = result["final_Y"]
    result.update({"schema": "r135.em_cascade_result.v1", "software_status": "PASS",
                   "physical_scope": "POST_BBN_PERTURBATIVE_EM_CASCADE",
                   "species": list(SPECIES), "time_s": t, "rate_ids": list(range(1, 18)),
                   "nonthermal_species": list(EM_SPECIES),
                   "spectrum_units": {"energy": "MeV_total_energy", "continuous_dn_dE": "MeV^2",
                                      "delta_number_density": "MeV^3"},
                   "photodisintegration_rates_s_inv": rates, "spectra": spectra,
                   "D_over_H": float(final[2]/final[1]), "Y_p": float(4*final[5]),
                   "donor": receipt, "input_sha256": canonical_hash(config),
                   "implementation": {"adapter_sha256": sha256(Path(__file__)),
                       "cascade_method": "ACROPOLIS_full_coupled_photon_electron_positron",
                       "network_method": "time_ordered_BDF_fundamental_matrix"},
                   "background_sha256": canonical_hash(config["background"]),
                   "injection_sha256": canonical_hash(config["injection"]),
                   "initial_abundances_sha256": canonical_hash(config["initial_abundances"]),
                   "energy_ledger": {"injected_power_MeV4_s": q,
                       "injected_comoving_energy_MeV4": float(np.trapezoid(q*(data["a"]/data["a"][0])**3, x=t)),
                       "injected_radiation_fraction_max": data["injected_radiation_fraction"],
                       "nonthermal_density_MeV4": density,
                       "nonthermal_density_fraction_max": rho_fraction,
                       "thermal_deposition_power_MeV4_s": None,
                       "thermal_deposition_status": "OPEN_BELOW_1P5_MEV_NOT_COMPUTED"},
                   "domain_checks": {"collision_to_evolution_ratios": fastest_ratio,
                       "max_fractional_p_He4_change": composition_change,
                       "unresolved_baryon_fraction": unresolved,
                       "expansion_integral_error": data["expansion_integral_error"]},
                   "hadronic_status": "NOT_INCLUDED_REQUIRES_EXCLUSIVE_INJECTION_AND_TRANSPORT",
                   "cross_section_uncertainty": "NOT_PROPAGATED_DONOR_DEFAULTS_ARE_NOT_AN_ERROR_MODEL"})
    if data["covariance"] is not None:
        u = result["transfer_matrix"]
        result["final_covariance"] = u @ data["covariance"] @ u.T
        result["covariance_scope"] = "INITIAL_ABUNDANCES_ONLY_AT_FIXED_BACKGROUND_AND_RATES"
    if "p7_handoff" in config:
        result["p7_handoff"] = copy.deepcopy(config["p7_handoff"])
    return result


def hadronic_source_from_response(kinetic_MeV, injection_MeV2_s, response, n_b_MeV3, *, background_Y=None):
    """Convolve externally calculated exclusive hadronic yields, without fits.

    `response[projectile, energy, nuclear_species]` is the net isotope change
    per injected p/n, and must explicitly include baryon accounting. This
    algebraic operation does not manufacture the required transport table.
    It is available to a future verified transport donor and cannot by itself
    make the hadronic branch physically complete.
    """
    K = np.asarray(kinetic_MeV, dtype=float)
    if K.ndim != 1 or len(K) < 2 or not np.isfinite(K).all() or K[0] <= 0 or np.any(np.diff(K) <= 0):
        raise InputError("hadronic kinetic-energy grid must be finite, positive, increasing")
    source = _array(injection_MeV2_s, (2, len(K)), "p/n differential injection", nonnegative=True)
    require_source(response, "exclusive hadronic response")
    if response.get("projectiles") != ["p", "n"] or response.get("species") != list(SPECIES):
        raise InputError("hadronic response species/order mismatch")
    if response.get("energy_MeV") != K.tolist():
        raise InputError("hadronic response must be provided on the actual injection grid")
    xi = _array(response.get("net_yield"), (2, len(K), 9), "exclusive net yields")
    baryon_per_projectile = _array(response.get("net_baryons_per_projectile"), (2,), "net projectile baryons")
    if not np.allclose(xi @ MASS_NUMBER, baryon_per_projectile[:, None], rtol=1e-8, atol=1e-10):
        raise InputError("hadronic response violates its explicit baryon ledger")
    nb = finite(n_b_MeV3, "baryon density", positive=True)
    # Product of two piecewise-linear functions is integrated exactly.
    width = np.diff(K)[None, :, None]
    s0, s1 = source[:, :-1, None], source[:, 1:, None]
    x0, x1 = xi[:, :-1, :], xi[:, 1:, :]
    derivative = np.sum(width/6 * (2*s0*x0+s0*x1+s1*x0+2*s1*x1), axis=(0, 1))/nb
    baryon_source = float(MASS_NUMBER @ derivative)
    # If injected matter changes n_b, a number source/n_b alone is not dY/dt.
    normalized_derivative = None
    if background_Y is not None:
        Y = _array(background_Y, (9,), "hadronic background Y", nonnegative=True)
        if not np.isclose(MASS_NUMBER @ Y, 1, rtol=1e-9, atol=1e-9):
            raise InputError("hadronic background Y is not normalized per baryon")
        normalized_derivative = derivative - Y*baryon_source
    elif np.all(baryon_per_projectile == 0):
        normalized_derivative = derivative
    return {"production_over_nb_s_inv": derivative, "dY_dt_s_inv": normalized_derivative,
            "baryon_source_over_nb_s_inv": baryon_source,
            "injected_kinetic_power_MeV4_s": float(np.sum(linear_spectrum_moment(K, source))),
            "response_sha256": canonical_hash(response), "status": "EXTERNAL_RESPONSE_CONVOLUTION_ONLY"}


def run(config, inputs, outdir):
    """Stage-compatible wrapper; an external history is passed explicitly."""
    definition = read_json(Path(inputs["cascade_definition"])) if "cascade_definition" in inputs else config.get("cascade", config)
    result = run_electromagnetic_cascade(definition, donor_path=config.get("donor_path"), fetch=config.get("fetch_donor", True))
    outdir = Path(outdir)
    write_json(outdir / "cascade_input.json", definition)
    write_json(outdir / "cascade_result.json", result)
    return {"software_status": "PASS", "artifacts": ["cascade_input.json", "cascade_result.json"],
            "physical_scope": result["physical_scope"], "hadronic_status": result["hadronic_status"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--donor-path", type=Path)
    parser.add_argument("--no-fetch", action="store_true")
    args = parser.parse_args()
    result = run_electromagnetic_cascade(read_json(args.config), donor_path=args.donor_path, fetch=not args.no_fetch)
    write_json(args.output, result)
    print(json.dumps({k: result[k] for k in ("software_status", "physical_scope", "D_over_H", "Y_p")}))


if __name__ == "__main__":
    main()
