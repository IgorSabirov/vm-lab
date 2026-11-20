"""Infer confined-side thermal coordinates from fixed literature inputs."""
import argparse
from bisect import bisect_right
import hashlib
from itertools import product
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def entropy_table(path, source):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != source["sha256"]:
        raise ValueError("SM EOS SHA-256 mismatch")
    rows = [tuple(map(float, line.split())) for line in data.decode().splitlines()
            if line.strip() and not line.startswith("#")]
    return ([math.log(r[0]) for r in rows], [r[3] for r in rows], [r[4] for r in rows])


def photon_temperature(table, entropy, error_sign):
    log_axis, gs, err = table

    def log_entropy(log_T):
        i = min(bisect_right(log_axis, log_T) - 1, len(gs) - 2)
        weight = (log_T - log_axis[i]) / (log_axis[i+1] - log_axis[i])
        lower = gs[i] + error_sign * err[i]
        upper = gs[i+1] + error_sign * err[i+1]
        g = lower + weight * (upper - lower)
        return math.log(2 * math.pi**2 * g / 45) + 3 * log_T

    target = math.log(entropy)  # GeV^3
    low, high = log_axis[0], log_axis[-1]
    if not log_entropy(low) <= target <= log_entropy(high):
        raise ValueError("Temperature outside the SM table")
    for _ in range(70):
        middle = (low + high) / 2
        if log_entropy(middle) < target:
            low = middle
        else:
            high = middle
    return math.exp((low + high) / 2)


def compute(inputs, table):
    scale, mass, cold = (inputs["lattice"][key] for key in
                         ("r0_Tc", "r0_m0", "s_cold_over_Tc3"))
    ratio = scale["value"] / mass["value"]
    frac = math.sqrt((scale["sigma"] / scale["value"])**2 +
                     (mass["sigma_stat"] / mass["value"])**2 +
                     (mass["sigma_anisotropy"] / mass["value"])**2)
    points = []
    for point in inputs["preparations"]:
        m0 = point["m0_GeV"]
        R = point["R_post"]
        tx = m0 * ratio
        tg = photon_temperature(table, cold["value"] * tx**3 / R, 0)
        bounds = []
        for a, b, c, d, e in product((-1, 1), repeat=5):
            tx_corner = m0 * (scale["value"] + a * scale["sigma"]) / (
                mass["value"] + b * mass["sigma_stat"] + c * mass["sigma_anisotropy"])
            tg_corner = photon_temperature(table, (cold["value"] + d*cold["sigma"]) * tx_corner**3 / R, e)
            bounds.append((1000*tx_corner, 1000*tg_corner, tx_corner/tg_corner))
        quantities = ("T_X_MeV", "T_gamma_MeV", "xi")
        envelope = {key: [min(values), max(values)] for key, values in zip(quantities, zip(*bounds))}
        points.append(dict(point_id=point["point_id"], m0_GeV=m0, R_post=R,
                           T_X_MeV=1000*tx, T_gamma_MeV=1000*tg, xi=tx/tg,
                           input_shift_envelope=envelope))
    return {"Tc_over_m0": ratio, "linear_sigma_assuming_independent_errors": ratio*frac,
            "boundary": "confined equilibrium side at Tc; R=s_X/s_SM after confinement",
            "points": points}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sm_table", nargs="?", type=Path)
    parser.add_argument("--cache", type=Path, help="Retrieve the preparations, scales and SM table from donors")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    inputs = json.loads((HERE / "inputs.json").read_text())
    if args.cache:
        if args.sm_table:
            parser.error("Specify --cache or a local SM table")
        sys.path.insert(0, str(HERE.parent / "donors"))
        from fetch import acquire
        from extract import physics
        files = acquire(args.cache, {"physics"}, args.offline)
        donor = physics(files)
        inputs["preparations"] = donor["preparations"]
        inputs["lattice"] = {"r0_Tc": donor["r0_Tc"], "r0_m0": donor["r0_m0"],
                             "s_cold_over_Tc3": donor["phase_entropy"]["cold"]}
        args.sm_table = files["sm"]
    elif not args.sm_table or args.offline:
        parser.error("Specify --cache or a local SM table")
    table = entropy_table(args.sm_table, inputs["sources"]["SM_EOS"])
    result = compute(inputs, table)
    if args.verify:
        reference = json.loads((HERE / "coordinates.json").read_text())
        # Ignore only cross-libm rounding by comparing floats at 12 significant digits.
        def equal(a, b):
            if isinstance(a, dict):
                return isinstance(b, dict) and a.keys() == b.keys() and all(equal(a[k], b[k]) for k in a)
            if isinstance(a, list):
                return isinstance(b, list) and len(a) == len(b) and all(equal(x,y) for x,y in zip(a,b))
            if isinstance(a, float):
                return math.isclose(a, b, rel_tol=1e-12)
            return a == b
        if not equal(result, reference):
            raise ValueError("Published thermal coordinates differ")
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
