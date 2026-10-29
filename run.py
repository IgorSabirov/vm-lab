"""Pinned VM entry point for E002c. Configuration lives beside this file."""
import os
# Set before NumPy/SciPy imports; one BLAS thread is part of calibration identity.
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[key]='1'
import json
from pathlib import Path
from e002c_exp.task import run
if __name__=='__main__':
    run(json.loads(Path(__file__).with_name('config.json').read_text()))
