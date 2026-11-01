"""One timed local development attempt; never a production physics run."""
import time
START = time.perf_counter()
import contextlib
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from e002e_exp.runtime import environment, kernel_hash
from e002e_corr_exp.evidence import build
from e002e_corr_exp.plan import implementation_hash, protocol_hash

DEST = Path(__file__).resolve().parent
attempt = sys.argv[1] if len(sys.argv) > 1 else '001'
if not attempt.isdigit():
    raise ValueError('Numeric attempt ID required')
path = DEST/('development_attempt_'+attempt+'.json')
if path.exists():
    raise FileExistsError('Attempt is immutable')
env = environment()
(DEST/('environment_local_'+attempt+'.json')).write_text(json.dumps(env, indent=2)+'\n')
if attempt == '001':
    forecast = dict(expected_seconds=6.,lower_seconds=1.,upper_seconds=20.,calibrated=False)
    environment_match = False
else:
    forecast = json.loads((DEST/('development_forecast_'+attempt+'.json')).read_text())
    reference = json.loads((DEST/forecast['environment_reference']).read_text())
    keys = ('python','platform','machine','cpu_model','affinity','numpy','scipy',
            'threadpools','requested_threads','blas_library_identity','cpu_quota','memory_limit')
    environment_match = all(env[k] == reference[k] for k in keys)
failure = None; test_result = None
with (DEST/('development_attempt_'+attempt+'.log')).open('w') as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
    try:
        evidence = build(DEST)
        suite = unittest.defaultTestLoader.discover(str(ROOT/'tests'), pattern='test_e002e*.py')
        test_result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    except Exception as exc:
        import traceback
        traceback.print_exc(file=log); failure = type(exc).__name__+': '+str(exc)
elapsed = time.perf_counter()-START
within = forecast['lower_seconds'] <= elapsed <= forecast['upper_seconds']
runtime_status = ('NOT_EVALUABLE_FIRST_SUITE_CALIBRATION' if not forecast['calibrated'] else
                  'NOT_EVALUABLE_ENVIRONMENT_CHANGED' if not environment_match else
                  'PASS' if within and test_result and test_result.wasSuccessful() else 'REVIEW_REQUIRED')
out = dict(attempt=attempt, source_commit=os.environ.get('DEVELOPMENT_SOURCE_COMMIT'),
           forecast=forecast, internal_elapsed_seconds=elapsed,
           deviation_seconds=elapsed-forecast['expected_seconds'], runtime_status=runtime_status,
           forecast_range_contains_time=within, environment_match=environment_match,
           tests_run=test_result.testsRun if test_result else 0,
           failures=len(test_result.failures) if test_result else None,
           errors=len(test_result.errors) if test_result else None,
           skipped=len(test_result.skipped) if test_result else None,
           tests_passed=bool(test_result and test_result.wasSuccessful()), failure=failure,
           old_kernel_sha256=kernel_hash(), implementation_sha256=implementation_hash(), protocol_sha256=protocol_hash(),
           new_full_NESS=0, new_full_time_propagations=0,
           timing_scope='Python body including imports/environment/evidence/tests; interpreter startup excluded')
path.write_text(json.dumps(out, indent=2)+'\n');print(json.dumps(out))
sys.exit(0 if out['tests_passed'] and not failure else 1)
