"""Pinned VM entry point for E002c. Configuration lives beside this file."""
import os
# Set before NumPy/SciPy imports; one BLAS thread is part of calibration identity.
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[key]='1'
import json
from pathlib import Path
if __name__=='__main__':
    config=json.loads(Path(__file__).with_name('config.json').read_text())
    if config.get('mode')=='repair_report':
        from e002c_exp.repair import run
    else:
        from e002c_exp.task import run
    run(config)
