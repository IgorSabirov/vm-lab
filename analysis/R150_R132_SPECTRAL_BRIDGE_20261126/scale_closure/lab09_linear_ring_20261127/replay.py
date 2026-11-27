"""Replay LAB09 or evaluate one supplied kit. Use --strict for the byte-level snapshot."""
import argparse
import json
import math
import sys
from pathlib import Path

import lab09


def compare_snapshot(saved, actual, path=()):
    """Keep categorical results exact; allow documented eigensolver roundoff."""
    if isinstance(saved, dict) and isinstance(actual, dict) and saved.keys() == actual.keys():
        for key in saved:
            compare_snapshot(saved[key], actual[key], (*path, key))
        return
    if isinstance(saved, list) and isinstance(actual, list) and len(saved) == len(actual):
        if path[-1] in ("site0_weights", "unperturbed_site0_weights") and len(saved) == 6:
            # At the two bare doublets only the projector trace is basis invariant.
            def groups(values):
                return [values[0], sum(values[1:3]), sum(values[3:5]), values[5]]
            if min(saved + actual) < -1e-14 or not all(map(math.isfinite, saved + actual)):
                raise ValueError("invalid bare projector weights")
            saved, actual = groups(saved), groups(actual)
        for i, (old, new) in enumerate(zip(saved, actual)):
            compare_snapshot(old, new, (*path, str(i)))
        return
    if isinstance(saved, float) and isinstance(actual, float):
        absolute, relative = 1e-9, 1e-10
        if "covariance" in path or path[-1] in ("denominator_sigma", "denominator_bias_bound"):
            absolute, relative = 1e-18, 1e-7
        elif path[-1] == "omit_largest_max_abs":
            absolute = 5e-6  # normalizing by the remaining ~0.0018 amplifies finite differences
        elif path[-1] in ("max_z", "weight_z"):
            absolute, relative = 1e-4, 1e-7  # residuals scaled by small input errors
        elif path[0] == "spectral_recovery":
            absolute = 3e-8  # GHz carrier differenced at sub-kHz to kHz steps
        if math.isclose(saved, actual, rel_tol=relative, abs_tol=absolute):
            return
    elif type(saved) is type(actual) and saved == actual:
        return
    raise ValueError(f"RESULTS.json differs at {'/'.join(path)}")


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kit", nargs="?")
    parser.add_argument("--strict", action="store_true", help="require byte-for-byte identical JSON")
    args = parser.parse_args(argv[1:])
    if args.kit:
        decision = lab09.evaluate_kit(lab09.load_kit(args.kit))
        print(json.dumps(decision, indent=2, ensure_ascii=False, allow_nan=False))
        return 0
    lab09.assert_reference()
    results = lab09.build_results()
    text = json.dumps(results, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    out = Path(__file__).with_name("RESULTS.json")
    if out.exists():
        old = out.read_text()
        if old != text:
            if args.strict:
                raise SystemExit("RESULTS.json does not match this byte-level replay")
            compare_snapshot(json.loads(old), results)
            print("RESULTS.json matches within numerical tolerances")
    else:
        out.write_text(text)
    for name, kit in results["kits"].items():
        print(name, kit["linear_decision"], kit["limit"])
    print("scientific_acceptance", results["scientific_acceptance"])
    print("physical_anchor", results["physical_anchor"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
