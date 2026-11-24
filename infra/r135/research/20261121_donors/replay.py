"""Reproduce donor benchmarks. Download once, validate before parsing."""
import argparse
import csv
import hashlib
import io
import json
import os
import re
import shutil
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
from scipy.integrate import quad

SOURCES = {
    "data.tar.gz": ("https://zenodo.org/api/records/18395360/files/data.tar.gz/content",
                    "1e6d6f61c4bbf535785021a4f4f5ec154280c0056a74c7ba497ff5c8c58a8244"),
    "8.zip": ("https://zenodo.org/api/records/8124749/files/8.zip/content",
              "87e7c3a7a6b96f4334fa7636c090144ca28fa71b0e802e48eee27937f64fed19"),
    "hpr.src": ("https://arxiv.org/src/2512.14530v2",
                "82044e31b143856fbf5ccaf32fc5c77a5b08d65ef2e5547e97983fcc71a72205"),
    "leonard.v2": ("https://arxiv.org/src/nucl-ex/0601035v2",
                   "32ed1c1dab730aa1028f12aaa8acf5ef0fd9663f89cee899f9b597801d05e2f7"),
    "ism.src": ("https://arxiv.org/src/hep-lat/0206020v3",
                "86ee497e70cf63415000de318cc6cf1cb04c7fbafc640cd195b77830053a139e"),
    "DataDescription.txt": ("https://zenodo.org/records/8124749/files/DataDescription.txt",
                            "b0b7d205417d97dfdcc332d4f5314c3c6d02f0ef389d710caccf03151242a986"),
}


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def acquire(cache, name, offline):
    url, expected = SOURCES[name]
    path = cache / name
    if path.is_file() and sha(path) == expected:
        return path
    if offline:
        raise ValueError(f"Missing or changed cached source: {name}")
    with tempfile.NamedTemporaryFile(dir=cache, delete=False) as dest:
        temp = Path(dest.name)
    try:
        with urllib.request.urlopen(url, timeout=90) as src, temp.open("wb") as dest:
            shutil.copyfileobj(src, dest)
        if sha(temp) != expected:
            raise ValueError(f"Source digest differs: {name}")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    return path


def source_tex(path, name):
    with tarfile.open(path, "r:gz") as archive:
        return archive.extractfile(name).read().decode("latin1")


def thermal_weights(energy, temperature):
    weights = np.zeros(len(energy))
    for j, (lo, hi) in enumerate(zip(energy[:-1], energy[1:])):
        def weight(e):
            return e * np.exp(-e / temperature)
        weights[j] += quad(lambda e: weight(e) * (hi - e) / (hi - lo), lo, hi)[0]
        weights[j + 1] += quad(lambda e: weight(e) * (e - lo) / (hi - lo), lo, hi)[0]
    check = quad(lambda e: e * np.exp(-e / temperature), energy[0], energy[-1])[0]
    np.testing.assert_allclose(weights.sum(), check, rtol=1e-12, atol=0)
    return weights


def leonard(path):
    tex = source_tex(path, "dd.tex")
    before = tex.split(r"\label{tab:totalsfact}")[0].rsplit(r"\begin{tabular}", 1)[1]
    cross_sections = np.array([[float(x) for x in re.findall(r"[0-9.]+", row)]
                               for row in before.splitlines() if re.match(r"^\d+\.\d+ &", row)])
    matrix_text = tex.split(r"\label{tab:discmat}")[0].rsplit(r"\begin{tabular}", 1)[1]
    rows = []
    labels = []
    for line in matrix_text.splitlines():
        name = re.match(r"^([pn]) \{\\it E\}=([\d.]+) &", line)
        if name:
            rows.append([float(a) * 10 ** int(b) for a, b in
                         re.findall(r"([\d.]+)\$\\rm \\times 10\^\{(-?\d+)\}\$", line)])
            labels.append((name[1], float(name[2])))
    if cross_sections.shape != (8, 5) or np.shape(rows) != (32, 8):
        raise ValueError("Unexpected Leonard table shape")
    expected = [(label, e) for label in "pn" for e in cross_sections[:, 0]]
    if labels != expected * 2:
        raise ValueError("Unexpected channel or energy order")
    cov = (4 * np.pi) ** 2 * np.hstack((rows[:16], rows[16:]))
    np.testing.assert_allclose(cov, cov.T, rtol=0, atol=1e-12)
    np.linalg.cholesky(cov)
    quoted = np.r_[cross_sections[:, 2], cross_sections[:, 4]]
    diagonal_error = np.max(np.abs(np.sqrt(np.diag(cov)) - quoted))
    if diagonal_error > 0.0051:
        raise ValueError("Diagonal disagrees with rounded cross-section uncertainties")
    # Ascending centre-of-mass energy, two equal-mass deuterons, lab keV -> MeV.
    energy = cross_sections[::-1, 0] / 2000
    means = np.r_[cross_sections[:, 1], cross_sections[:, 3]]
    results = []
    for temp in (0.06, 0.08, 0.10):
        weights = thermal_weights(energy, temp)[::-1]
        zeros = np.zeros_like(weights)
        W = np.array([np.r_[weights, zeros], np.r_[zeros, weights]])
        projected = W @ cov @ W.T
        rms_independent = np.sqrt(np.trace(projected))
        results.append({
            "kT_MeV": temp,
            "channel_correlation": round(projected[0, 1] / np.sqrt(np.prod(projected.diagonal())), 8),
            "rms_channel_sum_over_same_marginals_independent":
                round(np.sqrt(projected.sum()) / rms_independent, 8),
            "rms_channel_sum_percent": round(100 * np.sqrt(projected.sum()) / (W @ means).sum(), 8),
        })
    return {"Ecm_window_keV": [energy.min() * 1000, energy.max() * 1000],
            "covariance_order": 16, "max_error_diagonal_mb": round(diagonal_error, 8),
            "scope": "linear interpolation of sigma inside measured window; fit covariance only; common 1% normalization excluded",
            "projected": results}


def ishii(path):
    tex = source_tex(path, "glueball.tex")
    table = tex.split(r"\label{L-table-S}", 1)[1].split(r"\end{tabular}", 1)[0]
    out = []
    for m in re.finditer(r"^(275|284) & \d+ & [^&]+ &\s*(\d+)\(\s*(\d+)\)", table, re.M):
        temperature, width, error = map(int, m.groups())
        out.append({"T_MeV_donor": temperature, "Gamma_MeV": width, "fit_error_MeV": error,
                    "T_over_Gamma": round(temperature / width, 6)})
    if len(out) != 2:
        raise ValueError("Missing rows of the scalar Breit-Wigner fit")
    return {"operator": "smeared scalar 0++", "Tc_MeV_approx_donor": 280, "rows": out}


def llr(path):
    peaks = []
    with zipfile.ZipFile(path) as archive:
        tables = sorted(n for n in archive.namelist() if n.endswith("/CSV/obs_critical.csv"))
        for name in tables:
            with archive.open(name) as raw:
                data = list(csv.DictReader(io.TextIOWrapper(raw)))
            beta = np.array([float(row["b"]) for row in data])
            cu = np.array([float(row["Cu"]) for row in data])
            dims = {(float(row["V"]), float(row["Lt"])) for row in data}
            if (len(beta) != 1000 or dims != {(32000, 4)} or
                    not np.all(np.diff(beta) > 0) or not np.isfinite(cu).all()):
                raise ValueError(f"Unexpected lattice grid in {name}")
            index = int(np.argmax(cu))
            if index in (0, len(beta) - 1):
                raise ValueError(f"Unresolved peak in {name}")
            peaks.append(beta[index])
    if len(peaks) != 20:
        raise ValueError("Expected 20 reconstructions from the 8-interval set")
    return {"source_file_bytes": path.stat().st_size, "reconstructions": len(peaks),
            "beta_grid_points_per_reconstruction": 1000, "Nt": 4, "Ns": 20,
            "beta_at_Cu_grid_max_mean": round(np.mean(peaks), 8),
            "beta_at_Cu_grid_max_sample_sd": round(np.std(peaks, ddof=1), 8),
            "scope": "finite-volume grid maximum of Cu, eight LLR intervals; SD across 20 author reconstructions"}



def simplicity(path):
    series = []
    with tarfile.open(path, "r:gz") as archive:
        for beta in ("5.6600", "5.6900", "5.7200"):
            member = f"data/observables/betti/4.20.20.20/betti_NtNsNsNs=4202020_b={beta}.csv"
            betti = np.loadtxt(archive.extractfile(member), delimiter=",", dtype=int)
            if betti.shape != (600, 2) or np.any(betti[:, 1] == 0):
                raise ValueError(f"Unexpected Betti-number series at beta={beta}")
            ratios = betti[:, 0] / betti[:, 1]
            series.append({"beta": float(beta), "configurations": len(ratios),
                           "mean_b0_over_b1": round(np.mean(ratios), 8)})
    return {"Nt": 4, "Ns": 20, "rows": series,
            "scope": "sample means of the published projected-current graph observable, no D4 or independent error assessment"}


def thin_wall(path):
    tex = source_tex(path, "GW-SUN.tex")
    table = tex.split(r"\label{fig: Sigma table}")[0].rsplit(r"\begin{tabular}", 1)[1]
    row = re.search(r"^\s*3 & ([.\d]+)\(\d+\) & ([.\d]+)\(\d+\) &", table, re.M)
    if row is None:
        raise ValueError("Missing SU(3) input row in HPR Table 2")
    latent, tension = map(float, row.groups())
    coefficient = 16 * np.pi * tension ** 3 / (3 * latent ** 2)
    return {"L_over_Tc4": latent, "sigma_over_Tc3": tension,
            "lim_delta_squared_S3_over_T": round(coefficient, 12),
            "scope": "leading thin-wall limit, delta=1-T/Tc, delta_p=L*delta; no prefactor or percolation"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    paths = {name: acquire(args.cache, name, args.offline) for name in SOURCES}
    result = {"sources": {name: {"url": url, "sha256": digest}
                          for name, (url, digest) in SOURCES.items()},
              "leonard": leonard(paths["leonard.v2"]), "ishii": ishii(paths["ism.src"]),
              "llr": llr(paths["8.zip"]), "simplicity": simplicity(paths["data.tar.gz"]),
              "HPR_thin_wall": thin_wall(paths["hpr.src"])}
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
