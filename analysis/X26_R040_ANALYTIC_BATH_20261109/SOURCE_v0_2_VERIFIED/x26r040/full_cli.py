from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from .integrated import preflight_full_pipeline, run_full_pipeline


def main() -> int:
    ap = argparse.ArgumentParser(description="X26 conditional ADD-Phi-R040-Psi integrated runner")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--preflight-only", action="store_true")
    args = ap.parse_args()
    manifest_path = Path(args.manifest)
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    gate = preflight_full_pipeline(manifest)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "BLOCKERS.json").write_text(
        json.dumps({"manifest_sha256": hashlib.sha256(raw).hexdigest(), **gate},
                   indent=2, allow_nan=False) + "\n", encoding="utf-8")
    if args.preflight_only:
        print(json.dumps(gate, indent=2, ensure_ascii=False))
        return 0 if gate["submit_allowed"] else 2
    if not gate["submit_allowed"]:
        print(json.dumps(gate, indent=2, ensure_ascii=False))
        return 2
    report = run_full_pipeline(manifest)
    report["manifest_sha256"] = hashlib.sha256(raw).hexdigest()
    (outdir / "X26_INTEGRATED_REPORT.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["experiment"], "outdir": str(outdir)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
