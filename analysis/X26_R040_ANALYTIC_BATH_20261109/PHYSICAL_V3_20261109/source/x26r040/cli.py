from __future__ import annotations
import argparse
import json
from pathlib import Path
from .provenance import preflight, canonical_digest
from .runner import run_spectral
from .workload import workload_inventory


def main() -> int:
    ap = argparse.ArgumentParser(description="X26 conditional R040 + analytic 1D tight-binding bath")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--preflight-only", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        import unittest
        suite = unittest.defaultTestLoader.discover(str(Path(__file__).resolve().parents[1] / "tests"))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1
    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    gate = preflight(manifest)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "PREFLIGHT.json").write_text(json.dumps(gate,indent=2,ensure_ascii=False),encoding="utf-8")
    (outdir / "WORKLOAD_VOLUME.json").write_text(
        json.dumps(workload_inventory(manifest),indent=2,ensure_ascii=False),encoding="utf-8")
    if args.preflight_only:
        print(json.dumps(gate,indent=2,ensure_ascii=False))
        return 0 if gate["submit_allowed"] else 2
    if not gate["submit_allowed"]:
        print(json.dumps(gate,indent=2,ensure_ascii=False))
        return 2
    report = run_spectral(manifest)
    digest = canonical_digest(manifest_path, Path(__file__).resolve().parents[1])
    report["source_digest"] = digest
    (outdir / "X26_REPORT.json").write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps({"status":report["status"],"outdir":str(outdir)},ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
