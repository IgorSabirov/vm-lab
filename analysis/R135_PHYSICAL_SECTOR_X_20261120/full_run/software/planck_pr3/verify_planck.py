"""Verify the ESA PR3 baseline payload and evaluate the three released likelihoods."""
import argparse
from hashlib import file_digest
import json
import math
import os
from pathlib import Path
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent


def check(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def unpack_verified(archive, lock, destination):
    expected = lock["archive"]
    check(archive.stat().st_size == expected["bytes"] and digest(archive) == expected["sha256"],
          "ESA archive size or SHA-256 mismatch")
    components = {item["path"] for item in lock["components"].values()}
    inventory = lock["members"]
    seen = set()
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle:
            if not any(member.name.startswith(base + "/") for base in components):
                continue
            if member.isdir():
                continue
            check(member.isfile() and member.name in inventory and member.name not in seen,
                  f"Unexpected archive member: {member.name}")
            target = destination / member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            bundle.extract(member, path=destination, filter="data")
            size, checksum = inventory[member.name]
            check(target.stat().st_size == size and digest(target) == checksum,
                  f"Member failed verification: {member.name}")
            seen.add(member.name)
    check(seen == inventory.keys(), "Missing likelihood members")


def log_prior(values, policy):
    total = 0.0
    for name, spec in policy["parameters"].items():
        x = values[name]
        if "fixed" in spec:
            check(x == spec["fixed"], f"Fixed nuisance changed: {name}")
            continue
        prior = spec["prior"]
        if prior["dist"] == "uniform":
            if not prior["min"] <= x <= prior["max"]:
                return -math.inf
            total -= math.log(prior["max"] - prior["min"])
        elif prior["dist"] == "norm":
            total += gaussian_logpdf(x, prior["loc"], prior["scale"])
        else:
            raise ValueError(f"Unknown prior: {name}")
    sz = policy["joint_SZ"]
    total += gaussian_logpdf(sum(k * values[n] for n, k in sz["weights"].items()),
                             sz["mean"], sz["sigma"])
    return total


def gaussian_logpdf(x, mean, sigma):
    return -0.5 * ((x - mean) / sigma) ** 2 - math.log(sigma * math.sqrt(2 * math.pi))


def verify_covariances(root, lock):
    import numpy as np
    from astropy.io import fits

    def read_path(name, relative):
        return root / lock["components"][name]["path"] / "clik" / "lkl_0" / relative

    plik = lock["covariance"]["Plik"]
    precision = fits.getdata(read_path("Plik", plik["precision"])).reshape(plik["shape"])
    check(np.array_equal(precision, precision.T), "Plik precision matrix is asymmetric")
    np.linalg.cholesky(precision)
    with fits.open(read_path("Commander", "_external/sigma.fits")) as hdus:
        covariance = hdus[2].data
        first = 2 - hdus[0].header["LMIN"]
        check(list(covariance.shape) == lock["covariance"]["Commander"]["stored_shape"],
              "Commander covariance dimensions changed")
        np.linalg.cholesky(covariance[first:first+28, first:first+28])
    table = fits.getdata(read_path("SimAll", "probEE"))
    check(table.size == math.prod(lock["covariance"]["SimAll"]["shape"]), "SimAll grid mismatch")


def evaluate(root, lock, policy, theory_file=None):
    os.environ["CLIPY_NOJAX"] = "1"
    import clipy
    import numpy as np

    likelihoods = {}
    released = {}
    for name, entry in lock["components"].items():
        path = str(root / entry["path"])
        likelihood = clipy.clik(path)
        check(list(likelihood.extra_parameter_names) == entry["nuisance_order"],
              f"Nuisance order mismatch: {name}")
        value = float(likelihood(likelihood.default_par))
        expected = float(clipy.cldf.open(path)["clik/check_value"])
        check(math.isclose(value, expected, abs_tol=1e-5, rel_tol=0), f"Self-check failed: {name}")
        released[name] = dict(result=value, expected=expected)
        likelihoods[name] = likelihood

    # One C_ell spectrum and one calibration for all components; raw C_ell in microK^2.
    high = likelihoods["Plik"]
    spectra, nuisance = high.normalize(high.default_par)
    check(set(nuisance) == set(policy["parameters"]), "Prior policy differs from Plik")
    for name, spec in policy["parameters"].items():
        if "fixed" in spec:
            nuisance[name] = spec["fixed"]
    def component_values(cls):
        out = {}
        for name, likelihood in likelihoods.items():
            relevant = cls[:, :max(likelihood.lmax) + 1]
            out[name] = float(likelihood(np.array(relevant), nuisance))
        return out

    contributions = component_values(spectra)
    prior = log_prior(nuisance, policy)
    total = sum(contributions.values())
    check(math.isfinite(total + prior), "Joint fixture outside likelihood or prior support")
    result = dict(release_selfchecks=released, common_spectrum_logL=contributions, logL=total,
                  global_log_prior=prior, shared_A_planck=float(nuisance["A_planck"]))
    if theory_file is not None:
        expected = lock["zero_X_theory"]
        check(theory_file.stat().st_size == expected["bytes"] and
              digest(theory_file) == expected["sha256"], "LCDM theory SHA-256 mismatch")
        table = np.loadtxt(theory_file)
        ell = np.arange(2, spectra.shape[1])
        check(np.array_equal(table[:, 0], ell), "Wrong theory multipole coverage")
        # ESA columns: ell, D_TT, D_TE, D_EE, D_BB, PP. clik expects raw C_ell.
        lcdm = np.zeros_like(spectra)
        lcdm[[0, 3, 1, 2], 2:] = table[:, 1:5].T * (2*np.pi/(ell*(ell+1)))
        result["zero_X_logL"] = component_values(lcdm)
        result["zero_X_total"] = sum(result["zero_X_logL"].values())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("theory", type=Path, help="ESA R3.01 minimum-theory spectrum")
    args = parser.parse_args()
    lock = json.loads((HERE / "release.json").read_text())
    policy = json.loads((HERE / "nuisance.json").read_text())
    with tempfile.TemporaryDirectory() as tmp:
        unpack_verified(args.archive, lock, Path(tmp))
        verify_covariances(Path(tmp), lock)
        result = evaluate(Path(tmp), lock, policy, args.theory)
    reference = lock["common_spectrum_reference"]
    for key, expected in reference.items():
        actual = result["common_spectrum_logL"].get(key, result.get(key))
        check(math.isclose(actual, expected, abs_tol=1e-5, rel_tol=0), f"Joint regression: {key}")
    for name, expected in lock["zero_X_reference"].items():
        check(math.isclose(result["zero_X_logL"][name], expected, abs_tol=1e-5, rel_tol=0),
              f"LCDM reference mismatch: {name}")
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
