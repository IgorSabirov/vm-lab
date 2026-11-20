"""Propagate a one-reaction sensitivity or the published independent LINX prior through both native solvers."""
import argparse
import math
from pathlib import Path
import sys

SOFTWARE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOFTWARE))

from r135.backends import CORNERS, NativePair
from r135.common import read_json, sha256, write_json
from r135.nuclear_covariance import propagate, reconstruct


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=SOFTWARE/"extensions_reference/p7_bbn_control/BBN_input.json")
    parser.add_argument("--design", choices=("dpHe3g","linx-12"), default="dpHe3g")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    pair = NativePair()
    history = read_json(args.input)
    q = [float(name == "dpHe3g") for name in pair.names]
    spec = {"source": "LINX key_PRIMAT_2023 dpHe3g uncertainty, symmetric two-node sensitivity control",
            "reaction_order": pair.names, "nodes": [{"q": q, "weight": 0.5},
            {"q": [-x for x in q], "weight": 0.5}]}
    if args.design == "linx-12":
        source = Path(pair.sources["linx"]["source_root"])/"scripts/run_numpyro.py"
        digest = "2bf0079efc77158421d106f5eca94e138ba5a916f59b1b340d859868b7da7489"
        if len(q) != 12 or sha256(source) != digest:
            raise ValueError("unexpected LINX prior version")
        # Equal weights at +/-sqrt(d) along each axis integrate moments through degree three.
        d = len(q)
        nodes = []
        for axis in range(d):
            for sign in (-1,1):
                point = [0.]*d
                point[axis] = sign*math.sqrt(d)
                nodes.append({"q":point,"weight":1/(2*d)})
        spec.update(source="LINX run_numpyro.py independent N(0,1) prior for 12 nuclear rate shifts",
                    prior_source_sha256=digest, prior_source_commit=pair.sources["linx"]["source_commit"],
                    quadrature="third-degree spherical-radial cubature", nodes=nodes)
    histories = dict.fromkeys(CORNERS, history)
    tolerance = {"rtol": 1e-7, "atol": 1e-11}
    write_json(args.out/"ensemble.json", spec)
    propagate(spec, histories, pair, tolerance, args.out)
    matrices = reconstruct(spec, histories, tolerance, args.out)
    report = read_json(args.out/"nuclear_covariance.json")
    result = {"status": "RECONSTRUCTED", "physical_point": False, "independent_histories": 1,
              "input_sha256": sha256(args.input), "tolerance": tolerance,
              "unique_native_solves": report["unique_native_solves"], "slots": len(report["slots"]),
              "covariance_at_00": {e: matrices[e+"/00"] for e in ("linx", "primat")},
              "coordinate_order": report["coordinate_order"], "design": args.design,
              "varied_reactions": pair.names if args.design=="linx-12" else ["dpHe3g"],
              "scope": "finite quadrature on one diagnostic history; experimental cross-channel correlations outside prior",
              "ensemble_sha256": sha256(args.out/"ensemble.json"),
              "nuclear_covariance_sha256": sha256(args.out/"nuclear_covariance.json")}
    write_json(args.out/"VALIDATION.json", result)
    print(result)


if __name__ == "__main__":
    main()
