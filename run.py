"""Pinned experiment entry point; no Copilot or network access in VM jobs."""
import os
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[key]='1'
import json
from pathlib import Path
if __name__=='__main__':
    config=json.loads(Path(__file__).with_name('config.json').read_text())
    if config.get('experiment')=='E002e':
        from e002e_exp.task import run
    else:
        from e002d_exp.task import run
    run(config)
