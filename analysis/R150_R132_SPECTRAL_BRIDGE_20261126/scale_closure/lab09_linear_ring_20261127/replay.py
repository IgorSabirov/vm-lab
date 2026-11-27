"""Replay the 09-LAB linear 6+1 acceptance. Prints decisions; does not promote them."""
import json
import sys
from pathlib import Path

import lab09


def main(argv):
    if len(argv) > 1:
        decision = lab09.evaluate_kit(lab09.load_kit(argv[1]))
        print(json.dumps(decision, indent=2, ensure_ascii=False))
        return 0
    lab09.assert_reference()
    results = lab09.build_results()
    text = json.dumps(results, indent=2, ensure_ascii=False) + "\n"
    out = Path(__file__).with_name("RESULTS.json")
    if out.exists() and out.read_text() != text:
        raise SystemExit("RESULTS.json does not match this replay")
    if not out.exists():
        out.write_text(text)
    for name, kit in results["kits"].items():
        print(name, kit["linear_decision"], kit["limit"])
    print("scientific_acceptance", results["scientific_acceptance"])
    print("physical_anchor", results["physical_anchor"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
