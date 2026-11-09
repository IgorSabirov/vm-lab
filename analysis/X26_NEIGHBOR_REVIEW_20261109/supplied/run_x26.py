#!/usr/bin/env python3
"""Run X26-A toy control and report X26-B blockers."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from x26_core import run_x26_a
from add_adapter import run_x26_b


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="x26_report.json", help="output JSON path")
    args = parser.parse_args()
    report = {"X26_A": run_x26_a(), "X26_B": run_x26_b()}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(out),
        "X26_A": report["X26_A"]["overall"],
        "X26_A_BIC_control": report["X26_A"]["T3_embedded_normalizable_state"]["status"],
        "X26_B": report["X26_B"]["status"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
