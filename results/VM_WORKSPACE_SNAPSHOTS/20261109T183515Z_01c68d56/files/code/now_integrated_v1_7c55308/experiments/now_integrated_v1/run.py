#!/usr/bin/env python3
"""No default phase and no automatic VM submission."""
import os
from pathlib import Path

for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[name] = "1"  # measured VM baseline; parallel trajectories are a separate calibration

if __name__ == "__main__":
    from nowexp.runner import run_cli
    run_cli(Path(__file__).resolve().parent)
