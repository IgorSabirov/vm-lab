#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: ./run_vm.sh MANIFEST.json OUTDIR [--preflight-only]" >&2
  exit 64
fi
MANIFEST="$1"
OUTDIR="$2"
shift 2

PYTHONPATH="$(dirname "$0")${PYTHONPATH:+:$PYTHONPATH}" \
  python -m x26r040.cli --manifest "$MANIFEST" --outdir "$OUTDIR" "$@"
