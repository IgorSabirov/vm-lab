#!/usr/bin/env python3
"""Reproduce R137 from the four public Lumina tables, using only Python 3."""
import argparse
import hashlib
import json
import math
from pathlib import Path
from urllib.request import Request, urlopen

BASE_URL = "https://lumina-simulation.com/data/"
FILES = {
    "HI_reion_lumina.txt": "e5f3b99fd5a99be26f7296d5624537e8db239111ebe52533dbb1d52fa22c0b70",
    "HeIII_reion_lumina.txt": "b6aba40dd00d10329ccf00f9d475a3681980a25d88ce2de93d99fc05cb95e1e6",
    "sfrd_lumina.txt": "a15cf35aa5004b09f1c2cd6c5c24cb7e927bcc85e3dfc4ec0bc319568679c2bd",
    "tau_cmb_vs_z_lumina.txt": "2dcc52854764c6a52f9f6bd98777e3b51804a057240d9b1dfe9a7d2939814386",
}


def load(name, directory):
    if directory:
        data = (directory / name).read_bytes()
    else:
        request = Request(BASE_URL + name, headers={"User-Agent": "R137-Lumina/1.0 (+https://github.com/IgorSabirov/vm-lab/issues/196)"})
        with urlopen(request, timeout=60) as response:
            data = response.read()
    if hashlib.sha256(data).hexdigest() != FILES[name]:
        raise ValueError(f"Source changed: {name}. Review the published revision.")
    return [tuple(map(float, line.split())) for line in data.splitlines()
            if line.strip() and not line.lstrip().startswith(b"#")]


def crossing(rows, level):
    # Column 2 is the median across subvolumes. Retain its native z bracket.
    hits = []
    for (z0, y0, *_), (z1, y1, *_) in zip(rows, rows[1:]):
        if min(y0, y1) < level <= max(y0, y1):
            hits.append({"z": z0 + (z1 - z0) * (level - y0) / (y1 - y0),
                         "bracket": sorted([z0, z1])})
    if len(hits) != 1:
        raise ValueError(f"Expected one crossing, found {len(hits)}.")
    return hits[0]


def tau_below_three(intervals):
    # Zier et al., Table 2, sections 5.3 and 8.4. SI units throughout.
    c, sigma_t, proton_mass = 299792458., 6.6524587321e-29, 1.67262192369e-27
    grav, stefan_boltzmann = 6.67430e-11, 5.670374419e-8
    hubble = 67.66e3 / 3.0856775814913673e22
    rho_crit = 3 * hubble**2 / (8 * math.pi * grav)
    omega_gamma = 4 * stefan_boltzmann * 2.7255**4 / (c**3 * rho_crit)
    omega_r = omega_gamma * (1 + 3 * (7/8) * (1.9524/2.7255)**4)
    # Approximate H and He nuclear masses by mp and 4 mp.
    electron_density_today = .04897 * rho_crit * (1 - .24/2) / proton_mass
    def integrand(z):
        u = 1 + z
        expansion = math.sqrt(.3096*u**3 + .6903 + omega_r*u**4)
        return c * sigma_t * electron_density_today * u**2 / (hubble * expansion)
    dz = 3 / intervals
    total = math.fsum(integrand(i * dz) for i in range(1, intervals))
    return dz * (total + (integrand(0) + integrand(3)) / 2)


def analyze(directory):
    data = {name: load(name, directory) for name in FILES}
    hi, he, sfr, optical = (data[k] for k in FILES)
    tau = dict(optical)
    if not all(z1 > z0 and t1 >= t0 for (z0, t0), (z1, t1) in zip(optical, optical[1:])):
        raise ValueError("Optical depth must increase with redshift.")
    integrated = tau_below_three(4096)
    limits = [0, 3, 6, 10, 49]
    bins = []
    for low, high in zip(limits, limits[1:]):
        delta = tau[high] - tau[low]
        bins.append({"z": [low, high], "delta_tau": delta, "fraction": delta / tau[49]})
    return {
        "sources": {name: {"url": BASE_URL + name, "sha256": FILES[name],
                           "rows": len(rows), "z_range": sorted([rows[0][0], rows[-1][0]])}
                    for name, rows in data.items()},
        "median_volume_fraction_crossings": {"HI_half": crossing(hi, .5), "HeIII_half": crossing(he, .5)},
        "SFRD_at_last_sample_Msun_per_yr_per_cMpc3": sfr[-1][1],
        "tau_tabulated": {z: tau[z] for z in limits},
        "tau_bins": bins,
        "tau_3_to_49": tau[49] - tau[3],
        "fully_ionized_low_z_control": {
            "model": "published rounded background + HII and HeIII, Yp=0.24",
            "tau_0_to_3_integrated": integrated,
            "relative_residual_vs_table": integrated / tau[3] - 1,
            "quadrature_abs_change_2048_to_4096": abs(integrated - tau_below_three(2048)),
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, help="Use previously downloaded tables")
    args = parser.parse_args()
    print(json.dumps(analyze(args.data_dir), indent=2, allow_nan=False))
