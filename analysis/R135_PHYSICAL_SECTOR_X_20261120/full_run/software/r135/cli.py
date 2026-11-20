"""The P0--P10 executable interface, independent of any job service."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .common import InputError, OpenInput, read_json
from .contracts import execute, seal, source_inventory, verify_result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=[f"P{i}" for i in range(11)])
    parser.add_argument("--request", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--seal", action="store_true", help="freeze config and explicit input checksums")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--template", type=Path)
    parser.add_argument("--verify", type=Path, metavar="RESULT_DIR")
    parser.add_argument("--source-digest", action="store_true")
    parser.add_argument("--pipeline", type=Path, help="execute a frozen explicit stage DAG")
    args = parser.parse_args(argv)
    try:
        if args.source_digest:
            print(json.dumps(source_inventory(), indent=2))
            return 0
        if args.pipeline:
            if not args.out:
                parser.error("--pipeline requires --out")
            from .pipeline import run_pipeline
            result = run_pipeline(args.pipeline, args.out)
            print(json.dumps(result, ensure_ascii=False))
            return 0 if result["all_requested_software_completed"] else 3
        if args.verify:
            receipt = verify_result(args.verify)
        elif args.seal:
            if not all((args.stage, args.config, args.template, args.out)):
                parser.error("--seal requires --stage, --config, --template, --out")
            request = seal(args.stage, args.config, args.template, args.out)
            print(json.dumps({"state": "REQUEST_FROZEN", "stage": request["stage"],
                              "source_sha256": request["source_sha256"]}))
            return 0
        else:
            if not all((args.stage, args.request, args.out)):
                parser.error("execution requires --stage, --request and --out")
            receipt = execute(args.stage, args.request, args.out)
        print(json.dumps({"stage": receipt["stage"], "key": receipt["key"],
                          **receipt["result"]}, ensure_ascii=False, default=str))
        status = receipt["result"]["software_status"]
        return 0 if status == "PASS" else (3 if status == "NOT_EVALUATED" else 2)
    except OpenInput as exc:
        print(json.dumps({"status": "OPEN_INPUT", "reason": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 3
    except (InputError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({"status": "INVALID_REQUEST", "reason": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
