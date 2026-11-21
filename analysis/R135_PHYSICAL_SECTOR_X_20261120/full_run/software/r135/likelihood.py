"""Frozen BBN statistics and the full, released Planck PR3 likelihood.

The module evaluates likelihoods. It never labels a branch excluded merely
because an optimizer converged. A calibrated decision rule is a separate input.
"""
from __future__ import annotations

import importlib.metadata
import importlib.util
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
from scipy.optimize import minimize

from .common import InputError, OpenInput, canonical_hash, finite, read_json, sha256, write_json

PLANCK = Path(__file__).resolve().parents[1] / "planck_pr3"


def _reference_module():
    spec = importlib.util.spec_from_file_location("r135_planck_reference", PLANCK / "verify_planck.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_spectra(spectra, *, required_lmax=2508):
    """Return clik order TT,EE,BB,TE,TB,EB in microkelvin squared.

    No extrapolation, implicit D_l/C_l conversion, or silent truncation of a
    missing 2501--2508 tail is allowed. TE is signed; auto spectra are not.
    """
    if spectra.get("unit") != "microK^2" or spectra.get("convention") != "Cl":
        raise InputError("Planck requires raw Cl in microK^2")
    ell = np.asarray(spectra.get("ell"), dtype=float)
    if ell.ndim != 1 or not np.array_equal(ell, np.arange(2, len(ell) + 2)) or ell[-1] < required_lmax:
        raise InputError(f"CMB spectra must cover every ell=2..{required_lmax}")
    out = np.zeros((6, required_lmax + 1))
    for i, name in enumerate(("TT", "EE", "BB", "TE", "TB", "EB")):
        if name not in spectra:
            if name in ("TT", "EE", "TE"):
                raise InputError(f"missing CMB spectrum {name}")
            continue
        values = np.asarray(spectra[name], dtype=float)
        if values.shape != ell.shape or not np.isfinite(values).all():
            raise InputError(f"{name}: invalid spectrum shape or finite values")
        if name in ("TT", "EE", "BB") and np.any(values < 0):
            raise InputError(f"{name}: negative auto spectrum")
        out[i, 2:] = values[:required_lmax - 1]
    # A covariance-compatible sky cannot have |TE| > sqrt(TT EE).
    if np.any(out[3] ** 2 > out[0] * out[1] * (1 + 1e-8) + 1e-20):
        raise InputError("TE violates the angular covariance positivity bound")
    return out


def bbn_loglike(D_H, Yp, releases, theory_covariance):
    """Joint Gaussian in (log10(D/H), Yp), with explicit theory covariance."""
    finite(D_H, "D/H", positive=True)
    finite(Yp, "Yp", positive=True)
    if Yp >= 1:
        raise InputError("Yp must lie in (0,1)")
    by_name = {d["observable"]: d for d in releases
               if d.get("state", d.get("kind")) == "published_statistic"}
    if set(by_name) != {"log10_D_over_H", "Y_p"}:
        raise InputError("BBN likelihood requires exactly the frozen D/H and Yp statistics")
    order = ("log10_D_over_H", "Y_p")
    mean = np.array([by_name[k]["value"] for k in order], dtype=float)
    measurement = np.diag([by_name[k]["sigma"] ** 2 for k in order])
    theory = np.asarray(theory_covariance, dtype=float)
    if theory.shape != (2, 2) or not np.isfinite(theory).all() or not np.allclose(theory, theory.T, atol=1e-15):
        raise InputError("theory covariance must be a finite symmetric 2x2 matrix in logD/Yp units")
    if np.linalg.eigvalsh(theory)[0] < -1e-15:
        raise InputError("theory covariance must be positive semidefinite")
    covariance = measurement + theory
    factor = np.linalg.cholesky(covariance)
    residual = np.array([np.log10(D_H), Yp]) - mean
    standardized = np.linalg.solve(factor, residual)
    chi2 = float(standardized @ standardized)
    logdet = 2 * float(np.log(np.diag(factor)).sum())
    return {"logL_BBN": -.5 * (chi2 + logdet + 2 * math.log(2 * math.pi)),
            "chi2_BBN": chi2, "residual": residual.tolist(), "covariance": covariance.tolist(),
            "order": list(order)}


class PlanckLikelihood:
    """Full Plik + Commander + SimAll, with one shared calibration and SZ prior.

    ``root`` is the directory containing ``baseline/`` extracted from the
    verified ESA archive. All 134 member hashes are checked at construction.
    This interface uses the release's full matrices, never a Gaussian Neff
    surrogate. The data lock and nuisance policy are the existing P0 records.
    """
    def __init__(self, root, *, strict_environment=True):
        self.root = Path(root)
        self.lock = read_json(PLANCK / "release.json")
        self.policy = read_json(PLANCK / "nuisance.json")
        self.reference = _reference_module()
        for relative, (size, checksum) in self.lock["members"].items():
            path = self.root / relative
            if not path.is_file() or path.is_symlink() or path.stat().st_size != size or sha256(path) != checksum:
                raise InputError(f"Planck member missing/changed: {relative}")
        self.environment = {}
        for line in (PLANCK / "wheels.lock").read_text().splitlines():
            if "==" not in line or line.startswith("#"):
                continue
            package, value = line.split("==", 1)
            expected = value.split()[0]
            try:
                actual = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError as exc:
                raise OpenInput(f"Planck dependency missing: {package}") from exc
            self.environment[package] = actual
            if strict_environment and actual != expected:
                raise InputError(f"Planck dependency {package}: expected {expected}, got {actual}")
        os.environ["CLIPY_NOJAX"] = "1"
        try:
            import clipy
        except ImportError as exc:
            raise OpenInput("the pinned clipy backend is not installed") from exc
        self.environment["clipy-like"] = importlib.metadata.version("clipy-like")
        distribution = importlib.metadata.distribution("clipy-like")
        direct = json.loads(distribution.read_text("direct_url.json") or "{}")
        expected_archive = (PLANCK / "clipy.lock").read_text().split("--hash=sha256:")[1].strip()
        installed_archive = direct.get("archive_info", {}).get("hashes", {}).get("sha256")
        if installed_archive != expected_archive:
            raise InputError("clipy installed source is not the archive pinned in P0")
        verified_code = {}
        for record in distribution.files or []:
            if not str(record).startswith("clipy/") or not str(record).endswith(".py"):
                continue
            path = Path(distribution.locate_file(record))
            actual = base64.urlsafe_b64encode(hashlib.sha256(path.read_bytes()).digest()).decode().rstrip("=")
            if record.hash is None or record.hash.mode != "sha256" or actual != record.hash.value:
                raise InputError(f"installed clipy code differs from wheel RECORD: {record}")
            verified_code[str(record)] = sha256(path)
        if not verified_code:
            raise InputError("clipy installed code inventory is empty")
        self.clipy_source = {"archive_sha256": expected_archive, "code_sha256": canonical_hash(verified_code)}
        self.reference.verify_covariances(self.root, self.lock)
        self.components = {}
        self.selfchecks = {}
        for name, spec in self.lock["components"].items():
            component = clipy.clik(str(self.root / spec["path"]))
            if list(component.extra_parameter_names) != spec["nuisance_order"]:
                raise InputError(f"Planck nuisance order mismatch: {name}")
            val = float(component(component.default_par))
            if abs(val - spec["released_check_value"]) > 1e-5:
                raise InputError(f"Planck native selfcheck failed: {name}")
            self.components[name] = component
            self.selfchecks[name] = val
        _, nuisance = self.components["Plik"].normalize(self.components["Plik"].default_par)
        self.default_nuisance = {k: float(v) for k, v in nuisance.items()}
        for name, spec in self.policy["parameters"].items():
            if "fixed" in spec:
                self.default_nuisance[name] = spec["fixed"]
        self.evaluation_count = 0

    def evaluate(self, spectra, nuisance=None):
        cls = validate_spectra(spectra)
        values = dict(self.default_nuisance if nuisance is None else nuisance)
        if set(values) != set(self.policy["parameters"]):
            raise InputError("Planck nuisance vector must include exactly all 47 registered parameters")
        if not all(np.isfinite(v) for v in values.values()):
            raise InputError("nonfinite nuisance parameter")
        prior = self.reference.log_prior(values, self.policy)
        if not math.isfinite(prior):
            return {"logL": -math.inf, "log_prior": prior, "log_posterior": -math.inf,
                    "support": False}
        contributions = {name: float(likelihood(cls[:, :max(likelihood.lmax) + 1], values))
                         for name, likelihood in self.components.items()}
        self.evaluation_count += 1
        total = sum(contributions.values())
        if not math.isfinite(total):
            raise InputError("Planck likelihood returned a nonfinite value")
        return {"logL": total, "log_prior": prior, "log_posterior": total + prior,
                "components": contributions, "support": True,
                "spectra_sha256": canonical_hash(spectra), "nuisance": values}

    def profile(self, spectra, *, starts=None, maxiter=1000, ftol=1e-10):
        """Profile the 21 varied nuisances at fixed cosmology, retaining priors.

        Cosmological and X parameter variation is performed by the caller's
        registered grid. This is not automatically a calibrated confidence set.
        Multiple starting vectors may be supplied to expose optimizer minima.
        """
        names = [k for k, spec in self.policy["parameters"].items() if "fixed" not in spec]
        bounds, scales = [], []
        for k in names:
            prior = self.policy["parameters"][k]["prior"]
            if prior["dist"] == "uniform":
                bounds.append((prior["min"], prior["max"]))
                scales.append(prior["max"] - prior["min"])
            else:
                bounds.append((None, None))
                scales.append(prior["scale"])
        scale = np.asarray(scales)
        scaled_bounds = [(None if low is None else low / s,
                          None if high is None else high / s) for (low, high), s in zip(bounds, scale)]
        attempts = []
        starts = starts or [self.default_nuisance]
        for start in starts:
            if set(start) != set(self.default_nuisance):
                raise InputError("profile start must contain all nuisance parameters")
            x0 = np.array([start[k] for k in names]) / scale
            def evaluate_vector(x):
                vector = dict(self.default_nuisance)
                vector.update(zip(names, (x * scale).tolist()))
                return self.evaluate(spectra, vector)
            solution = minimize(lambda x: -evaluate_vector(x)["log_posterior"], x0,
                                method="L-BFGS-B", bounds=scaled_bounds,
                                options={"maxiter": int(maxiter), "ftol": ftol})
            final = evaluate_vector(solution.x)
            attempts.append({"success": bool(solution.success), "message": str(solution.message),
                             "nfev": int(solution.nfev), **final})
        successful = [a for a in attempts if a["success"] and a["support"]]
        if not successful:
            return {"status": "FAIL_PROFILE", "attempts": attempts}
        best = max(successful, key=lambda a: a["log_posterior"])
        return {"status": "PROFILED_FIXED_COSMOLOGY", "best": best,
                "attempts": attempts, "nuisance_count": len(names), "confidence_calibrated": False}

    def receipt(self):
        return {"likelihood_id": self.lock["data_id"], "release_sha256": sha256(PLANCK / "release.json"),
                "nuisance_sha256": sha256(PLANCK / "nuisance.json"), "verified_members": len(self.lock["members"]),
                "environment": self.environment, "clipy_source": self.clipy_source, "selfchecks": self.selfchecks,
                "actual_evaluations": self.evaluation_count}


def joint_loglike(bbn, cmb, *, extra_cmb_gaussians=None):
    if extra_cmb_gaussians:
        raise InputError("full Planck spectra cannot be combined with derived Neff/omega_b constraints from the same data")
    if not cmb.get("support", True):
        raise InputError("CMB vector outside prior support")
    return {"logL": bbn["logL_BBN"] + cmb["logL"], "log_prior": cmb["log_prior"],
            "log_posterior": bbn["logL_BBN"] + cmb["logL"] + cmb["log_prior"]}


def calibrated_decision(delta_statistic, calibration):
    """Only use a preregistered calibrated threshold, including boundary effects."""
    if not isinstance(calibration, dict) or not calibration.get("source") or not calibration.get("sampling_distribution_sha256"):
        raise OpenInput("a likelihood difference alone does not supply a calibrated exclusion threshold")
    threshold = finite(calibration.get("threshold"), "calibrated threshold", positive=True)
    delta = finite(delta_statistic, "likelihood-ratio statistic", nonnegative=True)
    return {"outcome": "EXCLUDED" if delta > threshold else "COMPATIBLE_AT_REGISTERED_THRESHOLD",
            "statistic": delta, "threshold": threshold, "calibration": calibration}


def evaluate_batch(request):
    """Evaluate a named batch in one verified Planck environment."""
    likelihood = PlanckLikelihood(request["data_root"])
    results = {}
    for key, task in request["spectra"].items():
        path = Path(task["path"])
        if sha256(path) != task["sha256"]:
            raise InputError(f"CMB spectrum changed before likelihood consumption: {key}")
        spectra = read_json(path)
        result = likelihood.evaluate(spectra, request.get("nuisance"))
        if request.get("profile_nuisance", False):
            profile = likelihood.profile(spectra, maxiter=request.get("profile_maxiter", 1000))
            if profile["status"] == "FAIL_PROFILE":
                raise RuntimeError(f"Planck nuisance profile failed: {key}")
            result = {**profile["best"], "profile": profile}
        results[key] = result
    return {"schema": "R135-Planck-evaluations-v1", "request_sha256": canonical_hash(request),
            "evaluations": results, "receipt": likelihood.receipt()}


def isolated_batch(request, interpreter, output, *, interpreter_sha256):
    """Use the existing Planck lock independently of the JAX dependency lock.

    The executable and invoked module are fixed inputs; no shell or arbitrary
    command is accepted. The returned receipt binds every consumed spectrum.
    """
    interpreter = Path(interpreter).absolute()
    if not interpreter.is_file() or sha256(interpreter) != interpreter_sha256:
        raise InputError("Planck interpreter executable does not match its registered hash")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    request_path, result_path = output / "request.json", output / "result.json"
    if result_path.exists():
        prior = read_json(result_path)
        manifest = read_json(output / "cache_manifest.json")
        if (prior.get("request_sha256") != canonical_hash(request)
                or manifest.get("result_sha256") != sha256(result_path)
                or manifest.get("module_sha256") != sha256(Path(__file__))
                or manifest.get("interpreter_sha256") != interpreter_sha256):
            raise InputError("Planck cache belongs to a different spectrum/nuisance request")
        return prior
    write_json(request_path, request)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    environment["CLIPY_NOJAX"] = "1"
    with (output / "worker.log").open("w") as log:
        subprocess.run([str(interpreter), "-m", "r135.likelihood", "--worker", str(request_path), str(result_path)],
                       env=environment, stdout=log, stderr=subprocess.STDOUT, check=True)
    result = read_json(result_path)
    if result.get("request_sha256") != canonical_hash(request):
        raise InputError("Planck worker returned a different request")
    result["receipt"]["worker_interpreter_sha256"] = interpreter_sha256
    result["receipt"]["worker_module_sha256"] = sha256(Path(__file__))
    write_json(result_path, result)
    write_json(output / "cache_manifest.json", {"result_sha256": sha256(result_path),
                                               "module_sha256": sha256(Path(__file__)),
                                               "interpreter_sha256": interpreter_sha256})
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Execute a hash-bound Planck likelihood batch")
    parser.add_argument("--worker", action="store_true", required=True)
    parser.add_argument("request", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    write_json(args.out, evaluate_batch(read_json(args.request)))
