#!/usr/bin/env python3
"""Bounded engineering check of declared eigenvalue tolerance, not a physics run."""
import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from external_sources import digest, validate_contract

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = 'infra/external/contracts/NUMERICAL_ENV.json'


def run(output):
    c = json.loads((ROOT / CONTRACT).read_text())
    validate_contract(c)
    output.mkdir(parents=True, exist_ok=True)
    receipt = {'contract_sha256': digest(c), 'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
               'working_tree_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT)),
               'prepared_at_unix_ns': time.time_ns(), 'analysis_mode': c['analysis_mode'],
               'outcomes_already_inspected': c['outcomes_already_inspected'],
               'scientific_status_promoted': False}
    # Written before importing the numerical engine or constructing measured results.
    (output / 'PLAN_RECEIPT.json').write_text(json.dumps(receipt, indent=2) + '\n')
    import numpy as np
    import scipy
    from scipy.linalg import eigvalsh
    # Fixed orthogonal Hadamard matrix: no random input or selected seed.
    h = np.array([[1,1,1,1],[1,-1,1,-1],[1,1,-1,-1],[1,-1,-1,1]], dtype=float) / 2
    expected = np.array([-4., -1., 2., 8.])
    errors = []
    for scale in (2.**-20, 1., 2.**20):
        matrix = h @ np.diag(expected * scale) @ h.T
        for values in (np.linalg.eigvalsh(matrix), eigvalsh(matrix, driver='evr')):
            errors.append(float(np.max(np.abs(values / scale - expected))))
    tolerance = c['criteria'][0]['absolute_tolerance']
    with contextlib.redirect_stdout(io.StringIO()) as config:
        np.show_config()
    report = {'status': 'PASS' if max(errors) <= tolerance else 'FAIL',
              'normalized_max_eigenvalue_error': max(errors), 'absolute_tolerance': tolerance,
              'numpy': np.__version__, 'scipy': scipy.__version__, 'python': sys.version,
              'platform': platform.platform(), 'numpy_config': config.getvalue(),
              'threads': {k: os.environ.get(k) for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']},
              'contract_sha256': digest(c), 'finished_at_unix_ns': time.time_ns(),
              'interpretation': 'Two numerical paths may share LAPACK; not independent scientific replication.'}
    if digest(json.loads((ROOT / CONTRACT).read_text())) != receipt['contract_sha256']:
        raise ValueError('Contract changed after preparation')
    (output / 'RESULT.json').write_text(json.dumps(report, indent=2) + '\n')
    if report['status'] != 'PASS':
        raise SystemExit(1)
    print(json.dumps({k: report[k] for k in ['status','normalized_max_eigenvalue_error','absolute_tolerance','threads']}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, required=True)
    run(p.parse_args().output)
