#!/usr/bin/env python3
"""Replay the uploaded notebook cells with explicitly reconstructed missing context.

The attachment contains code AND recorded outputs. Only the listed code ranges
are executed. Missing initial definitions are loaded from the supplied R130
reference, and the three aliases used before their definitions are explicit.
This does not claim to reconstruct Quinn's unprovided kernel state.
"""
from pathlib import Path
import ast
from collections import Counter
from contextlib import redirect_stdout, redirect_stderr
import hashlib
import importlib.util
import io
import itertools
import json
import platform
import time
import traceback

import numpy as np

ROOT = Path(__file__).resolve().parent
ATTACHMENT = ROOT / "original_quinn.txt"
REFERENCE = ROOT / "dynamics/source_engine.py"
RANGES = [(1,53), (83,153), (159,217), (223,266), (272,309),
          (318,381), (387,416), (425,458), (464,509), (523,539),
          (548,574), (584,609), (615,630)]

def main():
    spec = importlib.util.spec_from_file_location("r130_reference", REFERENCE)
    ref = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ref)
    namespace = {name: getattr(ref, name) for name in
                 ("named", "equal", "word", "forward", "backward",
                  "transport", "interact", "mirror_name", "swap_bits",
                  "reflected_swap", "r2")}
    namespace.update(np=np, itertools=itertools, Counter=Counter)
    exec("def mirror_only(x):\n"
         "    return tuple((mirror_name(u), s) for u,s in reversed(x))\n"
         "C1 = reflected_swap\n"
         "def C2(x):\n"
         "    return mirror_only(r2(x))\n", namespace)
    raw = ATTACHMENT.read_text(encoding="utf-8")
    lines = raw.splitlines()
    records = []
    for number, (start, end) in enumerate(RANGES, 1):
        code = "\n" * (start-1) + "\n".join(lines[start-1:end]) + "\n"
        stdout, stderr = io.StringIO(), io.StringIO()
        record = dict(cell=number, start_line=start, end_line=end)
        tick = time.perf_counter()
        try:
            compiled = compile(code, str(ATTACHMENT), "exec")
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exec(compiled, namespace)
            record["status"] = "completed"
        except Exception as exc:
            record.update(status="error", exception_type=type(exc).__name__,
                          message=str(exc), traceback=traceback.format_exc())
        record.update(elapsed_seconds=time.perf_counter()-tick,
                      stdout=stdout.getvalue(), stderr=stderr.getvalue())
        records.append(record)
        print(f"cell {number:02d}, lines {start}-{end}: {record['status']}"
              + (f" ({record['exception_type']}: {record['message']})"
                 if record['status'] == 'error' else ''), flush=True)
    result = {
        "scope": "Original code cells with explicit reconstructed initial context; captured outputs are not executed.",
        "original_sha256": hashlib.sha256(ATTACHMENT.read_bytes()).hexdigest(),
        "r130_reference_sha256": hashlib.sha256(REFERENCE.read_bytes()).hexdigest(),
        "python": platform.python_version(), "numpy": np.__version__,
        "initial_context": ["numpy as np", "itertools", "collections.Counter",
                            "R130 reference functions", "mirror_only = M", "C1 = M B", "C2 = M R"],
        "cells": records,
    }
    (ROOT / "original_cells_replay.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "original_cells_replay.txt").write_text(
        "\n\n".join(f"CELL {r['cell']} ({r['start_line']}-{r['end_line']}): {r['status']}\n"
                    + r['stdout'] + r['stderr'] + r.get('traceback', '') for r in records), encoding="utf-8")

if __name__ == "__main__":
    main()
