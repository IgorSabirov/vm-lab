"""P9 native-network adapters, CLASS execution and the five-corner experiment.

Derived from the *interfaces* exercised in vm-lab PR144, pinned at
d503ee0f1f89c99c8560803dc46277d544ef15ba. No prescribed heating curve from that
control is reused here. Both nuclear kernels read the computed P7 time history,
the same nuclear tables and explicitly supplied weak rates.

Primary API sources:
https://github.com/cgiovanetti/LINX/tree/bfba07c77a5fcba1cc772d42f2d9e9be8a542df8
https://github.com/CyrilPitrou/primat/tree/6f7e5680614fb119d65a6c9c65a292240b27c61e
https://github.com/lesgourg/class_public/tree/e85808324f51fc694d12e3ed7439552a3c3f9540
"""
from __future__ import annotations

import importlib
import importlib.metadata
import json
import math
from pathlib import Path
import subprocess

import numpy as np
from scipy.integrate import solve_ivp

from .common import (HBARC_MEV_CM, InputError, OpenInput, canonical_hash, finite, read_json,
                     require_input, require_source, sha256, write_csv, write_json)
from .observations import (BRIDGE, CORNERS, MASSES, SPECIES, _bridge_validate,
                           bridge_hash, validate_history, validate_weak_rates)

PINS = {"linx": "bfba07c77a5fcba1cc772d42f2d9e9be8a542df8",
        "primat": "6f7e5680614fb119d65a6c9c65a292240b27c61e",
        "class": "e85808324f51fc694d12e3ed7439552a3c3f9540"}
AMU_G = 1.66053906660e-24


def capabilities():
    """Implementation coverage, deliberately separate from installed backends."""
    return {"implemented": ["time-indexed common-input LINX and PRIMAT kernels", "nonmonotone-temperature histories",
                            "supplied nonthermal weak rates bound to neutrino spectra", "native thermal weak integrals",
                            "all five histories at three precision levels", "actual input-consumption receipts",
                            "lensed native CLASS spectra through ell=2508 in established free-streaming domain",
                            "import of independently computed general-X spectra with execution provenance",
                            "full frozen Planck and joint BBN likelihood", "fixed-cosmology nuisance profiling"],
            "not_implemented_here": ["general interacting-X Boltzmann perturbation equations",
                                     "nonthermal nuclear/photodisintegration cascade kernels",
                                     "weak integrals of arbitrary neutrino spectra without supplied rates"],
            "required_model_inputs": ["actual P7 history and initial abundances", "physical weak/nuclear-rate realization",
                                      "CMB perturbation applicability or independently computed spectra",
                                      "propagated theory covariance", "calibrated statistical decision rule"],
            "optional_backends": PINS, "physical_R135_execution_implied": False}


def verify_checkout(root, expected):
    root = Path(root).resolve()
    try:
        head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
        dirty = subprocess.check_output(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"], text=True)
    except (subprocess.CalledProcessError, OSError) as exc:
        raise OpenInput(f"a pinned source checkout is required: {root}") from exc
    if head != expected or dirty:
        raise InputError(f"backend source revision differs or tracked sources changed: {root}")
    return {"source_commit": head, "source_root": str(root), "tracked_sources_clean": True}


def _import_pinned(name):
    try:
        module = importlib.import_module(name)
    except ImportError as exc:
        raise OpenInput(f"optional native backend is not installed: {name}") from exc
    path = Path(module.__file__).resolve()
    root = next((p for p in path.parents if (p / ".git").exists()), None)
    if root is None:
        raise OpenInput(f"{name}: source checkout with the registered commit is required on PYTHONPATH")
    return module, verify_checkout(root, PINS[name])


def _linx():
    _, source = _import_pinned("linx")
    import jax
    jax.config.update("jax_enable_x64", True)
    import jax.numpy as jp
    from linx import const
    from linx.nuclear import NuclearRates
    return jax, jp, const, NuclearRates(nuclear_net="key_PRIMAT_2023", interp_type="linear"), source


def prepare_native_rates(q=None):
    """Freeze the LINX realization used by BOTH common-input native kernels."""
    _, jp, _, net, _ = _linx()
    q = np.zeros(len(net.reactions)) if q is None else np.asarray(q, dtype=float)
    if q.shape != (len(net.reactions),) or not np.isfinite(q).all():
        raise InputError("nuclear_rates_q has the wrong length or nonfinite entries")
    tables = net.precompute_rate_tables(jp.asarray(q))
    mapping = {r["linx_id"]: r for r in read_json(BRIDGE / "NETWORK_MAP.json")["reactions"]}
    reactions = [{"id": r.name, "reactants": mapping[r.name]["reactants"],
                  "products": mapping[r.name]["products"], "T9": np.asarray(r.T9_vec).tolist(),
                  "values": np.asarray(table).tolist()} for r, table in zip(net.reactions, tables)]
    rates = {"network_id": "PRIMAT_SMALL_TO_LINX_KEY_PRIMAT_2023", "species": list(SPECIES),
             "reactions": reactions, "temperature_unit": "T9",
             "rate_units": "cm3 mol-1 s-1 (forward two-body nuclear rates)",
             "interpolation": "linear", "extrapolation": "upstream-zero-linear",
             "detailed_balance_policy": "LINX alpha*T9**beta*exp(gamma/T9), both engines"}
    reverse = np.array([[float(r.alpha), float(r.beta), float(r.gamma)] for r in net.reactions]).T.tolist()
    return rates, reverse


def validate_thermal_weak_domain(history, policy):
    """Check the registered closure's domain before loading a native backend.

    A positive temperature and an applicability boolean do not establish that
    SBBN weak corrections apply to a high-temperature X preparation. The
    native implementation envelope is checked separately against its source.
    """
    domain = policy.get("applicability")
    if not isinstance(domain, dict):
        raise OpenInput("thermal weak closure needs explicit temperature and chemical-potential applicability bounds")
    require_source(domain, "thermal weak applicability")
    xi = finite(policy.get("xi_nu", 0.), "xi_nu")
    for field, values in (("T_gamma_range_MeV", history["T_gamma_MeV"]),
                          ("T_nu_range_MeV", history["T_nu_MeV"]),
                          ("xi_nu_range", [xi])):
        limits = domain.get(field)
        if not isinstance(limits, (list, tuple)) or len(limits) != 2:
            raise OpenInput(f"thermal weak applicability needs {field}")
        lo, hi = [finite(x, field, positive=field != "xi_nu_range") for x in limits]
        if lo > hi or (field != "xi_nu_range" and lo == hi):
            raise InputError(f"invalid thermal weak applicability interval: {field}")
        if np.min(values) < lo or np.max(values) > hi:
            raise OpenInput(f"computed BBN history is outside the registered thermal weak domain: {field}; supply a physically matched BBN segment or independently calculated weak rates")
    return xi


def thermal_weak_rates(history, policy):
    """Evaluate thermal rates point by point, without T_gamma inversion.

    The supplied policy must explicitly establish the thermal closure and the
    applicability of the native SBBN thermal-correction table. Arbitrary spectra
    require externally calculated weak rates bound to their spectral hash.
    """
    require_source(policy, "thermal weak-rate closure")
    if policy.get("fermi_dirac_electron_neutrinos") is not True:
        raise OpenInput("thermal weak rates require a justified Fermi-Dirac closure")
    if policy.get("native_thermal_corrections_applicable") is not True:
        raise OpenInput("native weak thermal-correction applicability is not established")
    history = validate_history(history)
    if "T_nu_MeV" not in history or "f_nu_e" in history:
        raise OpenInput("thermal weak closure needs T_nu and cannot replace supplied nonthermal spectra")
    xi = validate_thermal_weak_domain(history, policy)
    jax, jp, const, _, source = _linx()
    from linx.weak_rates import WeakRates
    weak = WeakRates()
    # The upstream interpolation clamps its tabulated corrections outside
    # their support. Such clamping is not an authorized physical extrapolation.
    thermal_axes = [np.asarray(axis, dtype=float) * float(const.kB) for axis in
                    (weak.T_nTOp_thermal_interval, weak.T_pTOn_thermal_interval)]
    native_lo = max(float(const.T_end), *(float(axis.min()) for axis in thermal_axes))
    native_hi = min(float(const.T_start), *(float(axis.max()) for axis in thermal_axes))
    if (np.min(history["T_gamma_MeV"]) < native_lo or np.max(history["T_gamma_MeV"]) > native_hi
            or np.max(history["T_nu_MeV"]) > float(const.T_start)):
        raise OpenInput("history exceeds the pinned LINX BBN weak-rate implementation envelope; supply a physically matched BBN segment or independently calculated weak rates")
    native_domain = {"T_gamma_range_MeV": [native_lo, native_hi],
                     "T_nu_max_MeV": float(const.T_start),
                     "source": "pinned linx.const.T_start/T_end and both weak thermal-correction table supports",
                     "scope": "implementation envelope; model applicability remains the separately registered closure"}
    def at_time(tg, tn):
        # Both reference nodes encode exactly the *current* Tnu/Tgamma; their
        # purpose is satisfying the native interpolation API, not an assumption
        # that two times at the same photon temperature have equal weak rates.
        reference_tg = tg * jp.asarray([.999999, 1.000001])
        reference_tn = tn * jp.asarray([.999999, 1.000001])
        result = weak.nTOp_rates(jp.asarray([tg]), (reference_tg, reference_tn), const.me, jp.asarray(xi))
        return jp.asarray([result[0][0], result[1][0]]) / const.tau_n
    calculated = np.asarray(jax.jit(jax.vmap(at_time))(jp.asarray(history["T_gamma_MeV"]),
                                                     jp.asarray(history["T_nu_MeV"])))
    result = {"time_s": history["time_s"], "lambda_n_to_p_s_inv": calculated[:, 0].tolist(),
              "lambda_p_to_n_s_inv": calculated[:, 1].tolist(), "unit": "s^-1",
              "source": "LINX pinned thermal weak integral; " + policy["source"],
              "source_commit": source["source_commit"], "closure": policy,
              "native_implementation_domain": native_domain,
              "thermal_history_sha256": bridge_hash({k: history[k] for k in ("time_s", "T_gamma_MeV", "T_nu_MeV")})}
    return validate_weak_rates(result, history)


class HistoryInterpolator:
    """Strict physical-time interpolation, valid for cooling and reheating."""
    def __init__(self, item, kB_MeV_K):
        _bridge_validate(item["canonical"])
        self.history = validate_history(item["canonical"]["history"])
        self.weak = validate_weak_rates(item["weak_rates"], self.history)
        self.t = np.asarray(self.history["time_s"])
        self.weak_t = np.asarray(self.weak["time_s"])
        self.logtemp = np.log(self.history["T_gamma_MeV"])
        self.lognb = np.log(self.history["n_b_cm3"])
        self.kB = float(kB_MeV_K)
        self.calls = 0
        self.first_sample = None
        self.last_sample = None

    def value(self, t, *, side_temperature=None):
        if not self.t[0] <= t <= self.t[-1]:
            raise InputError("backend attempted to extrapolate outside the P7 history")
        temp = float(np.exp(np.interp(t, self.t, self.logtemp)))
        if side_temperature is not None:
            temp = side_temperature
        nb = float(np.exp(np.interp(t, self.t, self.lognb)))
        fw, bw = [float(np.interp(t, self.weak_t, self.weak[k])) for k in
                  ("lambda_n_to_p_s_inv", "lambda_p_to_n_s_inv")]
        self.calls += 1
        sample = {"time_s": float(t), "T_gamma_MeV": temp, "n_b_cm3": nb,
                  "lambda_n_to_p_s_inv": fw, "lambda_p_to_n_s_inv": bw}
        if self.first_sample is None:
            self.first_sample = sample
        self.last_sample = sample
        return temp, nb * AMU_G, fw, bw

    def segments(self, rates):
        """Restart at EVERY crossing of a tabulated rate's support edge."""
        thresholds = sorted({self.kB * 1e9 * r["T9"][i]
                             for r in rates["reactions"] for i in (0, -1)})
        points = {float(self.t[0]), float(self.t[-1])}
        for threshold in thresholds:
            logedge = math.log(threshold)
            for t0, t1, x0, x1 in zip(self.t[:-1], self.t[1:], self.logtemp[:-1], self.logtemp[1:]):
                if x0 != x1 and min(x0, x1) <= logedge <= max(x0, x1):
                    points.add(float(t0 + (t1 - t0) * (logedge - x0) / (x1 - x0)))
        points = sorted(p for p in points if self.t[0] <= p <= self.t[-1])
        return [(lo, hi) for lo, hi in zip(points[:-1], points[1:]) if hi - lo > 1e-14 * max(1., abs(lo))]

    def receipt(self):
        return {"history_reads": self.calls, "first_rhs_input": self.first_sample,
                "last_rhs_input": self.last_sample, "interpolation": "log-positive and linear-weak in physical time",
                "neutrino_spectra_read_by": "upstream weak-rate producer; native kernels consume bound rates",
                "history_sha256": bridge_hash(self.history), "weak_rates_sha256": canonical_hash(self.weak)}


def convergence_gate(values, floor=1e-6):
    """Protocol T3: each of five solutions AND the mixed residual must converge."""
    x = np.asarray(values, dtype=float)
    floor = finite(floor, "relative numerical floor", positive=True)
    if x.shape != (3, 5) or not np.isfinite(x).all() or np.any(x <= 0):
        return {"status": "FAIL_CONVERGENCE", "reason": "three levels of five finite positive observables required"}
    residual = (x[:, 3] - x[:, 4]) / x[:, 0]
    observable_errors = np.abs(np.diff(x, axis=0)) / x[1:]
    residual_errors = np.abs(np.diff(residual))
    if np.any(observable_errors > .1 * floor) or np.any(residual_errors > .1 * np.maximum(floor, np.abs(residual[1:]))):
        status = "FAIL_CONVERGENCE"
    else:
        status = "RESOLVED" if abs(residual[-1]) > floor else "BELOW_NUMERICAL_FLOOR"
    return {"status": status, "relative_floor": floor, "mixed_residual": residual.tolist(),
            "adjacent_relative_observable_errors": observable_errors.tolist(),
            "adjacent_residual_errors": residual_errors.tolist()}


class NativePair:
    """Two separately implemented nuclear kernels, evaluated on identical inputs.

    LINX's JAX RHS/Jacobian is integrated by BDF; PRIMAT's native compiled
    stoichiometry/Jacobian by Radau. This controlled-history mode does not call
    either package's self-generated cosmological background. The native
    baselines remain separately callable below.
    """
    def __init__(self):
        self.jax, self.jp, self.const, self.net, linx_source = _linx()
        _, primat_source = _import_pinned("primat")
        from primat.config import PRIMATConfig
        from primat.network_data import UpdateNuclearRates
        self.cfg = PRIMATConfig({"network": "small", "verbose": False})
        self.pr = UpdateNuclearRates(self.cfg)
        mapping = {r["linx_id"]: r for r in read_json(BRIDGE / "NETWORK_MAP.json")["reactions"]}
        self.names = list(self.net.reactions_names)
        if self.pr.species_LT != ["n", "p", "H2", "H3", "He3", "He4", "Li7", "Be7"] or self.pr._lt_net.names != ["n__p"] + [mapping[n]["primat_id"] for n in self.names]:
            raise InputError("native network order differs from the registered map")
        self.sources = {"linx": linx_source, "primat": primat_source}
        self.native_reverse = np.array([[float(r.alpha), float(r.beta), float(r.gamma)] for r in self.net.reactions]).T
        self.compiled = {}

    def _validate(self, item):
        _bridge_validate(item["canonical"])
        rates = item["canonical"]["rates"]
        if rates["interpolation"] != "linear" or rates["extrapolation"] != "upstream-zero-linear":
            raise InputError("native common-input adapter requires the pinned linear/zero table policy")
        if [r["id"] for r in rates["reactions"]] != self.names:
            raise InputError("nuclear rate order differs from actual native input order")
        for table, native in zip(rates["reactions"], self.net.reactions):
            if not np.array_equal(table["T9"], np.asarray(native.T9_vec)):
                raise InputError(f"{native.name}: supplied temperature grid differs from the native grid")
        abc = np.asarray(item["reverse_alpha_beta_gamma"], dtype=float)
        if abc.shape != self.native_reverse.shape or not np.allclose(abc, self.native_reverse, rtol=1e-14, atol=0):
            raise InputError("reverse detailed-balance coefficients differ from the registered native realization")
        y0 = np.asarray(item["initial_abundances"], dtype=float)
        if y0.shape != (8,) or not np.isfinite(y0).all() or np.any(y0 < 0) or abs(y0 @ MASSES - 1) > 1e-8:
            raise InputError("invalid initial abundances")
        return rates, abc, y0

    def _linx_functions(self, rates):
        key = bridge_hash(rates)
        if key not in self.compiled:
            jp = self.jp
            tables = [jp.asarray(r["values"]) for r in rates["reactions"]]
            tau = float(self.const.tau_n)
            def native(y, temp, rho, fw, bw):
                # Identical values at two arbitrary interpolation nodes inject
                # the actual instantaneous rates; they do not depend on Tgamma.
                derivative = self.net(tuple(y), temp, rho, jp.asarray([0., 1.]),
                                      jp.full(2, fw * tau), jp.full(2, bw * tau), rate_tables=tables)
                return jp.asarray(derivative)
            self.compiled[key] = (self.jax.jit(native), self.jax.jit(self.jax.jacfwd(native, argnums=0)))
        return self.compiled[key]

    def solve(self, item, engine, policy, output):
        if engine not in ("linx", "primat"):
            raise InputError("unknown native BBN engine")
        rates, abc, y = self._validate(item)
        rtol = finite(policy["rtol"], "rtol", positive=True)
        atol = finite(policy["atol"], "atol", positive=True)
        interpolator = HistoryInterpolator(item, self.const.kB)
        times = np.asarray(item["canonical"]["history"]["time_s"], dtype=float)
        segments = interpolator.segments(rates)
        output = Path(output)
        output.mkdir(parents=True, exist_ok=True)
        fingerprint = {"input": item, "engine": engine, "policy": policy,
                       "sources": {k: v["source_commit"] for k, v in self.sources.items()},
                       "adapter_sha256": sha256(Path(__file__))}
        cache_key = canonical_hash(fingerprint)
        if (output / "receipt.json").exists():
            receipt = read_json(output / "receipt.json")
            if receipt.get("input_cache_key") != cache_key:
                raise InputError("cache reuse attempted for different physics, rates, precision or code")
            for name, digest in receipt["files"].items():
                if sha256(output / name) != digest:
                    raise InputError("cached solver result was changed")
            return read_json(output / "observables.json"), {**receipt, "cache_reused": True}
        write_json(output / "input.json", fingerprint)
        if engine == "linx":
            rhs_native, jac_native = self._linx_functions(rates)
        grids = [r["T9"] for r in rates["reactions"]]
        values = [r["values"] for r in rates["reactions"]]
        trajectories = np.empty((len(times), 8))
        diagnostics = []
        for index, (lo, hi) in enumerate(segments):
            # Move only the evaluation of exact segment endpoints toward its
            # own side of each support discontinuity. Every reheating crossing
            # is included, unlike an inverse monotone T(t) shortcut.
            def current(s):
                t = min(hi, max(lo, lo + float(s)))
                ts = t
                if t == lo:
                    ts = min(hi, lo + (hi - lo) * 1e-11)
                elif t == hi:
                    ts = max(lo, hi - (hi - lo) * 1e-11)
                side = float(np.exp(np.interp(ts, interpolator.t, interpolator.logtemp)))
                return interpolator.value(t, side_temperature=side)
            def native_args(s):
                temp, rho, fw, bw = current(s)
                if engine == "linx":
                    return temp, rho, fw, bw
                t9 = temp / float(self.const.kB) * 1e-9
                forward = np.array([np.interp(t9, g, v, left=0., right=0.) for g, v in zip(grids, values)])
                reverse = abc[0] * t9 ** abc[1] * np.exp(abc[2] / t9) * forward
                buffer = np.empty(2 + 2 * len(forward))
                buffer[:2], buffer[2::2], buffer[3::2] = [fw, bw], forward, reverse
                return rho, buffer
            if engine == "linx":
                fun = lambda s, state: np.asarray(rhs_native(state, *native_args(s)), dtype=float)
                jac = lambda s, state: np.asarray(jac_native(state, *native_args(s)), dtype=float)
                method = "BDF"
            else:
                fun = lambda s, state: self.pr._K_LT.rhs(state, *native_args(s))
                jac = lambda s, state: self.pr._K_LT.jacobian(state, *native_args(s))
                method = "Radau"
            solution = solve_ivp(fun, (0., hi - lo), y, jac=jac, method=method,
                                 rtol=rtol, atol=atol, dense_output=True,
                                 max_step=finite(policy.get("max_step_s", hi - lo), "max_step_s", positive=True))
            diagnostics.append({"segment": index, "time_start_s": lo, "time_stop_s": hi,
                                "method": method, "nfev": solution.nfev, "njev": solution.njev,
                                "success": bool(solution.success), "message": solution.message})
            write_json(output / "segment_diagnostics.json", diagnostics)
            if not solution.success:
                raise RuntimeError(f"{engine} integration failed: {solution.message}")
            take = (times >= lo if index == 0 else times > lo) & (times <= hi)
            trajectories[take] = solution.sol(times[take] - lo).T
            y = solution.y[:, -1]
        baryon_error = float(np.max(np.abs(trajectories @ MASSES - 1)))
        if not np.isfinite(trajectories).all() or np.min(trajectories) < -10 * atol or baryon_error > 1e-6:
            raise RuntimeError("native BBN trajectory violated positivity or baryon conservation")
        yp = 4 * y[5]
        helium_mass = float(self.cfg.He4Overma) * yp / 4
        observables = {"D_H": float(y[2] / y[1]), "Yp": float(yp),
                       "YHe_CMB": float(helium_mass / (helium_mass + self.cfg.HOverma * (1 - yp))),
                       "He3_H_late": float((y[3] + y[4]) / y[1]), "Li7_H_late": float((y[6] + y[7]) / y[1]),
                       "max_baryon_error": baryon_error, "engine": engine,
                       "final_Y": y.tolist(), "rtol": rtol, "atol": atol,
                       "atomic_mass_ratios": {"He4Overma": float(self.cfg.He4Overma), "HOverma": float(self.cfg.HOverma)}}
        np.savez_compressed(output / "trajectory.npz", time_s=times, Y=trajectories, species=np.array(SPECIES))
        write_json(output / "observables.json", observables)
        receipt = {"schema": "R135-native-consumption-v1", "input_cache_key": cache_key,
                   "engine": engine, "cache_reused": False, "sources": self.sources,
                   "nuclear_rates_sha256": bridge_hash(rates), "reverse_coefficients_sha256": canonical_hash(abc),
                   "actual_kernel": "LINX.NuclearRates" if engine == "linx" else "PRIMAT._K_LT",
                   "integrator": "scipy.solve_ivp:BDF" if engine == "linx" else "scipy.solve_ivp:Radau",
                   "segments": len(segments), **interpolator.receipt(),
                   "files": {p.name: sha256(p) for p in output.iterdir() if p.is_file()}}
        write_json(output / "receipt.json", receipt)
        return observables, receipt


def native_baseline(engine, output):
    """Run the separate native baseline without replacing P7 inputs or caches."""
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise InputError("native baseline output must be a new isolated directory")
    output.mkdir(parents=True, exist_ok=True)
    if engine == "primat":
        _, source = _import_pinned("primat")
        from primat.backend import run_bbn
        options = {"network": "small", "Omegabh2": .02242, "DeltaNeff": 0., "verbose": False}
        answer = run_bbn(options, force_backend="python", progress=False)
        result = {"engine": engine, "source": source, "options": options,
                  "D_H": float(answer["DoH"]), "Yp": float(answer["YPBBN"]), "Neff": float(answer["Neff"])}
    elif engine == "linx":
        _, jp, const, net, source = _linx()
        from linx.background import BackgroundModel
        from linx.abundances import AbundanceModel
        t, a, rg, rn, rx, px, neff = BackgroundModel(n_out=512)(jp.asarray(0.))
        y = np.asarray(AbundanceModel(net)(rg, rn, rx, px, a_vec=a, t_vec=t))
        result = {"engine": engine, "source": source, "D_H": float(y[2] / y[1]),
                  "Yp": float(4 * y[5]), "Neff": float(neff[-1])}
    else:
        raise InputError("unknown native baseline backend")
    write_json(output / "native_baseline.json", result)
    return result


def run_class(class_input, source_root, output, *, YHe):
    """Call the pinned CLASS binary for an explicitly established native model."""
    from .observations import validate_class_model
    doc = validate_class_model(class_input)
    source = verify_checkout(source_root, PINS["class"])
    binary = Path(source_root).resolve() / "class"
    if not binary.is_file():
        raise OpenInput("the pinned CLASS checkout has not been built")
    out = Path(output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    cache_key = canonical_hash({"input": class_input, "YHe": YHe, "source": source["source_commit"],
                                "binary_sha256": sha256(binary), "adapter_sha256": sha256(Path(__file__))})
    if (out / "receipt.json").exists():
        receipt = read_json(out / "receipt.json")
        if receipt.get("input_cache_key") != cache_key:
            raise InputError("CLASS cache belongs to a different history, model or code")
        for name, digest in receipt["files"].items():
            if sha256(out / name) != digest:
                raise InputError("cached CLASS artifact changed")
        return read_json(out / "spectra.json"), {**receipt, "cache_reused": True}
    if any(out.iterdir()):
        raise InputError("CLASS has an incomplete checkpoint; preserve it and use a new isolated output directory")
    pars = dict(doc["parameters"])
    pars.update(doc["precision"])
    pars["YHe"] = finite(YHe, "BBN helium mass fraction", positive=True)
    if pars["YHe"] >= 1:
        raise InputError("helium fraction must be below one")
    pars.update({"N_ncdm": 0, "output": "tCl,pCl,lCl", "lensing": "yes", "l_max_scalars": 2508,
                 "root": str(out / "spectra_"), "headers": "yes", "format": "camb", "write background": "yes"})
    parameter_file = out / "parameters.ini"
    parameter_file.write_text("".join(f"{k} = {v}\n" for k, v in pars.items()))
    with (out / "CLASS.log").open("w") as log:
        subprocess.run([str(binary), str(parameter_file)], cwd=source_root,
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    files = list(out.glob("*cl_lensed.dat"))
    if len(files) != 1:
        raise RuntimeError("CLASS did not produce the lensed spectra required by Planck")
    table = np.loadtxt(files[0])
    ell = table[:, 0]
    if not np.array_equal(ell, np.arange(2, 2509)) or table.shape[1] < 5 or not np.isfinite(table).all():
        raise RuntimeError("CLASS output has invalid multipole coverage or nonfinite values")
    # In CAMB format CLASS writes l(l+1)Cl/(2pi) in microkelvin squared:
    # ell, TT, EE, BB, TE. Do not apply the (Tcmb*1e6)^2 conversion twice.
    factor = 2 * np.pi / (ell * (ell + 1))
    spectra = {"ell": ell.astype(int).tolist(), "unit": "microK^2", "convention": "Cl",
               **{name: (table[:, i] * factor).tolist() for i, name in enumerate(("TT", "EE", "BB", "TE"), 1)}}
    from .likelihood import validate_spectra
    validate_spectra(spectra)
    write_json(out / "spectra.json", spectra)
    receipt = {"source": source, "input_cache_key": cache_key, "cache_reused": False,
               "binary_sha256": sha256(binary), "parameters_sha256": sha256(parameter_file),
               "source_P7_history_sha256": class_input.get("source_P7_history_sha256"),
               "spectra_sha256": sha256(out / "spectra.json"), "input": doc, "matching": class_input.get("matching"),
               "actual_model": "standard native CLASS free-streaming radiation after matching",
               "files": {p.name: sha256(p) for p in out.iterdir() if p.is_file()}}
    write_json(out / "receipt.json", receipt)
    return spectra, receipt


def validate_class_refinement(levels):
    from .observations import validate_class_precision, CLASS_PRECISION_DIRECTION
    if not isinstance(levels, list) or len(levels) not in (2, 3):
        raise InputError("CLASS refinement requires two or three registered accuracy dictionaries")
    levels = [validate_class_precision(level) for level in levels]
    if not levels[0] or any(set(level) != set(levels[0]) for level in levels):
        raise InputError("CLASS refinement levels must explicitly set the same nonempty precision fields")
    for old, new in zip(levels[:-1], levels[1:]):
        if old == new or any(CLASS_PRECISION_DIRECTION[k] * (new[k] - old[k]) < 0 for k in old):
            raise InputError("CLASS accuracy levels must tighten monotonically and actually change")
    return levels


def class_refinement_gate(log_likelihoods, max_delta_logL):
    """Empirical CMB numerical gate at the SAME physics/nuisance prescription."""
    values = np.asarray(log_likelihoods, dtype=float)
    tolerance = finite(max_delta_logL, "maximum numerical delta logL", positive=True)
    if values.ndim != 1 or len(values) not in (2, 3) or not np.isfinite(values).all():
        raise InputError("CLASS likelihood refinement needs two or three finite evaluations")
    changes = np.abs(np.diff(values))
    return {"status": "PASS" if np.all(changes <= tolerance) else "FAIL_CMB_CONVERGENCE",
            "logL_by_accuracy": values.tolist(), "adjacent_delta_logL": changes.tolist(),
            "max_delta_logL": tolerance}


def run_class_refinements(class_input, source_root, output, *, YHe, levels):
    """Run registered tighter CLASS settings, keeping each raw spectrum."""
    from copy import deepcopy
    levels = validate_class_refinement(levels)
    results = []
    for index, precision in enumerate(levels):
        spec = deepcopy(class_input)
        spec["precision"] = precision
        destination = Path(output) if index == len(levels) - 1 else Path(output).with_name(Path(output).name + f".accuracy-{index}")
        spectra, receipt = run_class(spec, source_root, destination, YHe=YHe)
        results.append({"spectra": spectra, "receipt": receipt, "path": str((destination / "spectra.json").resolve()),
                        "precision": precision})
    return results


def matched_class_input(class_input, abundance, cfg):
    """Propagate P7 baryon number, including the BBN-predicted isotope masses."""
    from copy import deepcopy
    result = deepcopy(class_input)
    matching = result.get("matching")
    if not isinstance(matching, dict) or not matching.get("source_history_sha256"):
        raise OpenInput("CLASS parameters must be derived from a bound late P7 matching slice")
    eta = finite(matching["eta"], "late eta", positive=True)
    tcmb = result["parameters"]["T_cmb"]
    # CODATA kB [MeV/K] and G [cm^3 g^-1 s^-2]; masses and isotope identities
    # come from the exact pinned PRIMAT table used for the abundance solution.
    kB = 8.617333262145e-11
    n_gamma_today = 2 * 1.2020569031595942 / np.pi ** 2 * (kB * tcmb / HBARC_MEV_CM) ** 3
    late_names = ["p", "p", "H2", "He3", "He3", "He4", "Li7", "Li7"]
    masses_g = np.array([a * AMU_G + cfg.NuclExcessMass[name] * 1e-3 * 1.7826619216279e-27
                         for a, name in zip(MASSES, late_names)])
    mean_mass = np.asarray(abundance["final_Y"]) @ masses_g
    critical_per_h2 = 3 * (1e7 / 3.0856775814913673e24) ** 2 / (8 * np.pi * 6.67430e-8)
    omega = float(eta * n_gamma_today * mean_mass / critical_per_h2)
    result["parameters"]["omega_b"] = omega
    result["parameters"]["N_ur"] = matching["N_ur"]
    result["matching"]["omega_b"] = omega
    result["matching"]["late_isotope_masses_g"] = masses_g.tolist()
    result["matching"]["abundances_sha256"] = canonical_hash(abundance)
    return result


def import_computed_spectra(entry, class_input, history, abundance, inputs, out):
    """Import actual custom perturbation results, bound to this same experiment.

    The importer certifies artifact identity and input coverage. It cannot
    independently establish the correctness of an external equation system;
    that remains a physical/model validation condition in the claim matrix.
    """
    expected = class_input.get("external_solver", {})
    source = entry.get("producer", {})
    if (class_input.get("perturbation_model", {}).get("kind") != "external_computed_perturbations"
            or any(not expected.get(k) or source.get(k) != expected.get(k) for k in ("repository", "commit", "equations_source"))):
        raise InputError("external spectrum producer differs from the preregistered solver")
    history_hash = history["source_history_sha256"]
    abundance_hash = canonical_hash(abundance)
    if (entry.get("P7_history_sha256") != history_hash
            or class_input.get("source_P7_history_sha256") != history_hash
            or entry.get("BBN_observables_sha256") != abundance_hash):
        raise InputError("external CMB spectrum is not bound to this exact P7/BBN history")
    spectrum_path = require_input(inputs, entry["spectra_input"])
    receipt_path = require_input(inputs, entry["execution_receipt_input"])
    if sha256(spectrum_path) != entry.get("spectra_sha256") or sha256(receipt_path) != entry.get("execution_receipt_sha256"):
        raise InputError("external CMB data or execution receipt changed")
    receipt = read_json(receipt_path)
    if (receipt.get("producer") != source or receipt.get("state") != "COMPLETED"
            or receipt.get("exit_code") != 0
            or receipt.get("inputs", {}).get("P7_history_sha256") != history_hash
            or receipt.get("inputs", {}).get("BBN_observables_sha256") != abundance_hash
            or receipt.get("outputs", {}).get("spectra_sha256") != entry["spectra_sha256"]):
        raise InputError("external CMB execution receipt does not establish the declared computation")
    from .likelihood import validate_spectra
    spectra = read_json(spectrum_path)
    validate_spectra(spectra)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "spectra.json", spectra)
    write_json(out / "external_execution_receipt.json", receipt)
    result = {"source": source, "source_P7_history_sha256": history_hash,
              "BBN_observables_sha256": abundance_hash, "spectra_sha256": sha256(out / "spectra.json"),
              "external_original_spectra_sha256": entry["spectra_sha256"],
              "external_execution_receipt_sha256": entry["execution_receipt_sha256"],
              "actual_model": "VERIFIED_EXTERNAL_COMPUTATION",
              "physical_equations_independently_validated_here": False}
    write_json(out / "receipt.json", result)
    return spectra, result


def run(config, inputs, out):
    bundle_path = require_input(inputs, "bbn_inputs")
    bundle = read_json(bundle_path)
    if bundle.get("schema") != "R135-bbn-inputs-v1" or set(bundle.get("histories", {})) != set(CORNERS):
        raise OpenInput("P9 needs all five P8 histories")
    histories = bundle["histories"]
    if len({canonical_hash(h["initial_abundances"]) for h in histories.values()}) != 1:
        raise InputError("five-corner runs must start from the same registered preparation")
    data_path = require_input(inputs, "data_release_lock")
    data = read_json(data_path)
    releases = data.get("data_releases", data.get("releases", data.get("datasets", [])))
    planck_record = next((d for d in releases if d.get("data_id") == "Planck2018-TTTEEE-lowE"), None)
    if planck_record is None:
        raise OpenInput("P0 has not registered the Planck likelihood used by this module")
    software_root = Path(__file__).resolve().parents[1]
    for record in planck_record.get("files", []):
        relative = Path(record["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise InputError("unsafe Planck release path")
        actual = software_root / relative
        if not actual.is_file() or sha256(actual) != record["sha256"] or actual.stat().st_size != record["bytes"]:
            raise InputError(f"Planck module data differ from the frozen P0 release: {relative}")
    if not planck_record.get("files"):
        raise OpenInput("P0 Planck file binding is absent")
    write_json(out / "data_release_lock.json", data)
    applicability = bundle.get("applicability", {})
    if applicability.get("photodisintegration_or_nonthermal_nuclear_sources", False):
        raise OpenInput("nonthermal nuclear source terms need an implemented cascade/network kernel")
    tolerances = config.get("refinement")
    if not isinstance(tolerances, list) or len(tolerances) != 3:
        raise InputError("P9 requires three registered refinement levels")
    for coarse, fine in zip(tolerances[:-1], tolerances[1:]):
        if not (coarse["rtol"] > fine["rtol"] > 0 and coarse["atol"] > fine["atol"] > 0):
            raise InputError("both rtol and atol must decrease at each refinement")
    pair = NativePair()
    results, receipts, rows = {}, {}, []
    for engine in ("linx", "primat"):
        results[engine] = []
        for level, tolerance in enumerate(tolerances):
            layer = {}
            for corner in CORNERS:
                key = f"{engine}/{level}/{corner}"
                answer, receipt = pair.solve(histories[corner], engine, tolerance, out / "bbn" / key)
                layer[corner] = answer
                receipts[key] = receipt
                rows.append({"engine": engine, "level": level, "corner": corner,
                             **{k: answer[k] for k in ("D_H", "Yp", "YHe_CMB", "max_baryon_error", "rtol", "atol")}})
            results[engine].append(layer)
    write_csv(out / "abundances.csv", rows)
    gates = {}
    gate_rows = []
    for engine in results:
        for observable in ("D_H", "Yp"):
            gate = convergence_gate([[results[engine][level][corner][observable] for corner in CORNERS]
                                     for level in range(3)], config.get("relative_floor", 1e-6))
            gates[f"{engine}/{observable}"] = gate
            for level, residual in enumerate(gate.get("mixed_residual", [])):
                gate_rows.append({"engine": engine, "observable": observable, "level": level,
                                  "mixed_residual": residual, "status": gate["status"]})
    write_csv(out / "mixed_response.csv", gate_rows)
    write_json(out / "convergence.json", gates)
    write_json(out / "backend_consumption.json", {"source_P8_sha256": sha256(bundle_path), "runs": receipts})
    if any(g["status"] == "FAIL_CONVERGENCE" for g in gates.values()):
        write_json(out / "cmb_spectra_manifest.json", {"state": "NOT_EVALUATED", "reason": "FAIL_CONVERGENCE"})
        write_csv(out / "likelihood_grid.csv", [], ["corner", "engine", "logL", "status"])
        return {"software_status": "FAIL_CONVERGENCE", "evidence_status": "INCONCLUSIVE",
                "metrics": {"bbn_integrations": 30, "class_integrations": 0},
                "limitations": ["At least one abundance or mixed residual failed the frozen numerical gate."]}
    class_bundle = read_json(require_input(inputs, "class_inputs"))
    if set(class_bundle.get("histories", {})) != set(CORNERS):
        raise OpenInput("CLASS inputs must cover all five histories")
    cmb_mode = config.get("cmb_mode", "native_class")
    if cmb_mode not in ("native_class", "external_computed_spectra"):
        raise InputError("unknown CMB computation mode")
    external = read_json(require_input(inputs, "computed_spectra_manifest")) if cmb_mode == "external_computed_spectra" else None
    class_root = config.get("class_source_root")
    planck_root = config.get("planck_data_root")
    if (cmb_mode == "native_class" and not class_root) or not planck_root:
        raise OpenInput("CLASS source checkout and verified Planck release directory are required")
    from .likelihood import evaluate_batch, isolated_batch, bbn_loglike, joint_loglike
    if "theory_covariance_logD_Yp" not in config:
        raise OpenInput("BBN likelihood requires explicit propagated theory covariance in (logD,Yp) units")
    accuracy_levels = config.get("class_refinement")
    if accuracy_levels is not None:
        validate_class_refinement(accuracy_levels)
        finite(config.get("max_cmb_delta_logL"), "registered CMB delta-logL tolerance", positive=True)
        if cmb_mode != "native_class":
            raise InputError("external spectra need producer-supplied accuracy evidence; native CLASS refinement cannot be substituted")
    cmb_manifest, likelihood_rows, spectra_tasks, accuracy_keys = {}, [], {}, {}
    # At the converged level, retain each backend's YHe contribution rather than
    # silently selecting one; CLASS calls are counted separately from BBN calls.
    for engine in results:
        for corner in CORNERS:
            abundance = results[engine][-1][corner]
            if cmb_mode == "native_class":
                class_input = matched_class_input(class_bundle["histories"][corner], abundance, pair.cfg)
                if class_input["matching"]["source_history_sha256"] != histories[corner]["source_history_sha256"]:
                    raise InputError("CLASS matching and BBN input refer to different P7 histories")
                if accuracy_levels is None:
                    spectra, receipt = run_class(class_input, class_root,
                                                 out / "class" / engine / corner, YHe=abundance["YHe_CMB"])
                else:
                    refined = run_class_refinements(class_input, class_root, out / "class" / engine / corner,
                                                     YHe=abundance["YHe_CMB"], levels=accuracy_levels)
                    spectra, receipt = refined[-1]["spectra"], refined[-1]["receipt"]
                    accuracy_keys[f"{engine}/{corner}"] = []
                    for level, result in enumerate(refined):
                        tag = f"{engine}/{corner}" if level == len(refined) - 1 else f"{engine}/{corner}@accuracy{level}"
                        accuracy_keys[f"{engine}/{corner}"].append(tag)
                        spectra_tasks[tag] = {"path": result["path"], "sha256": sha256(Path(result["path"]))}
                    receipt = {**receipt, "refinements": [r["receipt"] for r in refined]}
            else:
                entry = external.get("spectra", {}).get(f"{engine}/{corner}")
                if entry is None:
                    raise OpenInput(f"missing independently computed CMB spectrum for {engine}/{corner}")
                spectra, receipt = import_computed_spectra(entry, class_bundle["histories"][corner],
                            histories[corner], abundance, inputs, out / "class" / engine / corner)
            cmb_manifest[f"{engine}/{corner}"] = receipt
            path = (out / "class" / engine / corner / "spectra.json").resolve()
            spectra_tasks[f"{engine}/{corner}"] = {"path": str(path), "sha256": sha256(path)}
    likelihood_request = {"data_root": str(Path(planck_root).resolve()), "spectra": spectra_tasks,
                          "nuisance": config.get("nuisance"), "profile_nuisance": config.get("profile_nuisance", False),
                          "profile_maxiter": config.get("profile_maxiter", 1000),
                          "adapter_sha256": sha256(Path(__file__).with_name("likelihood.py"))}
    if config.get("planck_python"):
        evaluations = isolated_batch(likelihood_request, config["planck_python"], out / "planck",
                                     interpreter_sha256=config.get("planck_python_sha256"))
    else:
        evaluations = evaluate_batch(likelihood_request)
    write_json(out / "planck_evaluations.json", evaluations)
    cmb_gates, cmb_gate_rows = {}, []
    for key in cmb_manifest:
        if key in accuracy_keys:
            gate = class_refinement_gate([evaluations["evaluations"][tag]["logL"] for tag in accuracy_keys[key]],
                                         config["max_cmb_delta_logL"])
        else:
            gate = {"status": "NOT_VALIDATED", "reason": "only one CLASS accuracy setting or imported producer result"}
        cmb_gates[key] = gate
        cmb_gate_rows.append({"key": key, "status": gate["status"],
                              "max_adjacent_delta_logL": max(gate.get("adjacent_delta_logL", [0.])) if "adjacent_delta_logL" in gate else None,
                              "registered_tolerance": gate.get("max_delta_logL")})
    write_json(out / "cmb_convergence.json", cmb_gates)
    write_csv(out / "cmb_convergence.csv", cmb_gate_rows)
    if any(g["status"] == "FAIL_CMB_CONVERGENCE" for g in cmb_gates.values()):
        write_json(out / "cmb_spectra_manifest.json", {"spectra": cmb_manifest, "Planck": evaluations["receipt"]})
        write_csv(out / "likelihood_grid.csv", [], ["corner", "engine", "logL", "status"])
        return {"software_status": "FAIL_CMB_CONVERGENCE", "evidence_status": "INCONCLUSIVE",
                "metrics": {"bbn_integrations": 30, "class_integrations": len(spectra_tasks)},
                "limitations": ["The registered CLASS accuracy refinement did not meet the CMB likelihood tolerance."]}
    for engine in results:
        for corner in CORNERS:
            abundance = results[engine][-1][corner]
            cmb = evaluations["evaluations"][f"{engine}/{corner}"]
            bbn = bbn_loglike(abundance["D_H"], abundance["Yp"], releases, config["theory_covariance_logD_Yp"])
            joint = joint_loglike(bbn, cmb, extra_cmb_gaussians=config.get("extra_cmb_gaussians"))
            likelihood_rows.append({"engine": engine, "corner": corner, **joint,
                                    "status": "CONDITIONAL_LIKELIHOOD", "confidence_calibrated": False,
                                    "cmb_precision_status": cmb_gates[f"{engine}/{corner}"]["status"]})
            write_json(out / "class" / engine / corner / "likelihood.json", {"BBN": bbn, "CMB": cmb, "joint": joint})
    write_json(out / "cmb_spectra_manifest.json", {"spectra": cmb_manifest, "Planck": evaluations["receipt"]})
    write_csv(out / "likelihood_grid.csv", likelihood_rows)
    return {"software_status": "PASS", "evidence_status": "DIAGNOSTIC" if config.get("_mode") == "validation" else "CONDITIONAL",
            "metrics": {"bbn_integrations": 30, "new_bbn_integrations": sum(not r["cache_reused"] for r in receipts.values()),
                        "class_integrations": len(spectra_tasks) if cmb_mode == "native_class" else 0,
                        "new_class_integrations": sum(sum(not s.get("cache_reused", False) for s in r.get("refinements", [r])) for r in cmb_manifest.values()) if cmb_mode == "native_class" else 0,
                        "imported_computed_spectra": len(cmb_manifest) if external is not None else 0,
                        "likelihood_evaluations": evaluations["receipt"]["actual_evaluations"]},
            "limitations": ["Likelihood values require registered nuisance/cosmology treatment and calibrated decision thresholds before exclusion."]
                            + (["CMB numerical accuracy is NOT_VALIDATED without registered CLASS refinement or external accuracy evidence."]
                               if any(g["status"] == "NOT_VALIDATED" for g in cmb_gates.values()) else [])}
