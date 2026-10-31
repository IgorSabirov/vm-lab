"""Pinned experiment entry point; no Copilot or network access in VM jobs."""
import os
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[key]='1'
import json
import re
from pathlib import Path

def bind_source(config):
    """Resolve the source SHA supplied by the hash-checking VM launcher.

    A config cannot contain the hash of its own containing commit. The immutable
    queue request pins that commit; the launcher checks FETCH_HEAD and every blob.
    Explicit SHA configurations remain supported and must match the launcher.
    """
    actual = os.environ.get('VM_SOURCE_COMMIT', '')
    if not re.fullmatch('[0-9a-f]{40}', actual):
        raise ValueError('Verified VM launcher source SHA is missing')
    requested = config.get('source_commit')
    if requested != 'FROM_VERIFIED_VM_LAUNCHER' and requested != actual:
        raise ValueError('Configured source SHA differs from VM launcher')
    result = dict(config)
    result['source_commit_binding'] = requested
    result['source_commit'] = actual
    return result

if __name__=='__main__':
    config=json.loads(Path(__file__).with_name('config.json').read_text())
    if config.get('experiment')=='E002e':
        config=bind_source(config)
        from e002e_exp.task import run
    elif config.get('experiment')=='E002e_CALIBRATION':
        config=bind_source(config)
        from experiments.e002e.calibration import run
    else:
        from e002d_exp.task import run
    run(config)

