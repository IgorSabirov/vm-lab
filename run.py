"""Pinned E002d entry point; no Copilot or network access."""
import os
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[key]='1'
import json
from pathlib import Path
from e002d_exp.task import run
if __name__=='__main__':run(json.loads(Path(__file__).with_name('config.json').read_text()))
