"""Bounded code checks. Run via Python with this script; no production suite."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import unittest

START = time.perf_counter()
for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[key] = '1'
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT/'tests'))


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--suite', choices=('pilot', 'all', 'integration'), required=True)
    parser.add_argument('--output', type=Path, required=True); args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    from e002e_exp.runtime import environment, kernel_hash
    from e002_exp.model import save_json
    before = environment()
    names = ['test_e002e.ReducedAlgebra.test_small_generators_against_full_kron_all_columns',
             'test_e002e.FullOperators.test_pinned_builder_and_reduction'] if args.suite == 'pilot' else (['test_e002e_integration'] if args.suite == 'integration' else ['test_e002e', 'test_e002e_integration'])
    suite = unittest.defaultTestLoader.loadTestsFromNames(names); count = suite.countTestCases()
    class TimedResult(unittest.TextTestResult):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw); self.timings = []
        def startTest(self, test):
            self.t0 = time.perf_counter(); super().startTest(test)
        def stopTest(self, test):
            self.timings.append(dict(id=test.id(), seconds=time.perf_counter()-self.t0)); super().stopTest(test)
    with (args.output/'tests.log').open('w') as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2, resultclass=TimedResult).run(suite)
    data = dict(suite=args.suite, declared_tests=count, executed_tests=result.testsRun,
                successful=result.wasSuccessful(), failures=len(result.failures), errors=len(result.errors),
                test_timings=result.timings, source_commit=os.environ.get('E002E_SOURCE_COMMIT'), kernel_sha256=kernel_hash(),
                environment_before=before, environment_after=environment(),
                internal_seconds_to_report=time.perf_counter()-START,
                scope='Code validation only; no production full-model NESS or E002e run')
    save_json(args.output/'checks.json', data)
    print(json.dumps(dict(tests=result.testsRun, success=result.wasSuccessful(), seconds=data['internal_seconds_to_report'])))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
