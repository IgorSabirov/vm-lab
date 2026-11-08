"""SPDX-License-Identifier: GPL-3.0-or-later. Engineering checks, not a QG simulation."""
import argparse
import json
import statistics
import time
from pathlib import Path
import numpy as np
from signature_kernel import SignatureKernel

p = argparse.ArgumentParser()
p.add_argument('--library', required=True)
p.add_argument('--output', required=True)
a = p.parse_args()
start = time.perf_counter()
kernel = SignatureKernel(a.library)
checks = {}
examples = np.array([np.diag([1., 2., 3., 4.]), np.diag([1., 2., 3., -4.]),
                     np.diag([1., 2., -3., -4.]), np.diag([1., 2., 3., 0.])])
checks['known_inertias'] = np.array_equal(kernel.classify(examples)['counts'],
                                         [[4, 0, 0], [3, 1, 0], [2, 2, 0], [3, 0, 1]])
checks['single_matrix'] = np.array_equal(kernel.classify(examples[1])['counts'], [[3, 1, 0]])
near = np.diag([1., 1., 1., 1e-14])
diagnostic = kernel.classify(near, strict=False)
checks['near_threshold_flag'] = bool(diagnostic['numerically_ambiguous'][0])
try:
    kernel.classify(near)
    checks['strict_rejects_ambiguous'] = False
except ValueError:
    checks['strict_rejects_ambiguous'] = True
bad = examples[0].copy(); bad[0, 0] = np.nan
checks['nonfinite_rejected'] = bool(kernel.classify(bad, strict=False)['status'][0] != 0)
bad = examples[0].copy(); bad[0, 1] = 1.
checks['asymmetry_rejected'] = bool(kernel.classify(bad, strict=False)['status'][0] != 0)
for name, matrix in [('nonsquare', np.ones((2, 3))), ('empty', np.empty((0, 4, 4)))]:
    try:
        kernel.classify(matrix)
        checks[name+'_rejected'] = False
    except ValueError:
        checks[name+'_rejected'] = True
rng = np.random.default_rng(20261108)
q, _ = np.linalg.qr(rng.normal(size=(4096, 4, 4)))
eigenvalues = rng.uniform(.25, 4., size=(4096, 4)) * rng.choice([-1., 1.], size=(4096, 4))
raw_matrices = (q * eigenvalues[:, None, :]) @ np.swapaxes(q, 1, 2)
# Construct exactly symmetric test inputs explicitly. The runtime adapter never
# silently repairs a user's matrix; the upstream API rejects adjusted symmetry.
matrices = (raw_matrices + np.swapaxes(raw_matrices, 1, 2)) / 2
fixture_adjustment = float(np.max(np.abs(matrices-raw_matrices)))
expected = np.stack([(eigenvalues > 0).sum(1), (eigenvalues < 0).sum(1), np.zeros(4096)], axis=1)
checks['4096_known_congruences'] = np.array_equal(kernel.classify(matrices)['counts'], expected)
for power in [-500, 500]:
    checks['scale_'+str(power)] = np.array_equal(kernel.classify(matrices[:16]*2.**power)['counts'], expected[:16])
kernel.classify(matrices); np.linalg.eigvalsh(matrices)
timings = {'cpp_batch': [], 'numpy_eigvalsh_batch': [], 'numpy_eigvalsh_python_loop': []}
for _ in range(3):
    t = time.perf_counter(); kernel.classify(matrices)
    timings['cpp_batch'].append(time.perf_counter()-t)
    t = time.perf_counter(); values = np.linalg.eigvalsh(matrices)
    numpy_counts = np.stack([(values > 0).sum(1), (values < 0).sum(1), np.zeros(4096)], axis=1)
    timings['numpy_eigvalsh_batch'].append(time.perf_counter()-t)
    t = time.perf_counter(); loop_counts = [((v > 0).sum(), (v < 0).sum(), 0) for v in map(np.linalg.eigvalsh, matrices)]
    timings['numpy_eigvalsh_python_loop'].append(time.perf_counter()-t)
checks['numpy_agrees_on_well_conditioned_inputs'] = np.array_equal(numpy_counts, expected) and np.array_equal(loop_counts, expected)
result = dict(passed=all(checks.values()), checks=checks, matrices=4096, dimension=4, repetitions=3,
              seed=20261108, fixture_symmetry_adjustment=fixture_adjustment,
              fixture_minimum_absolute_eigenvalue=.25, timings_seconds=timings,
              medians_seconds={k:statistics.median(v) for k,v in timings.items()},
              benchmark_scope='Well-conditioned matrices; C++ performs extra reliability/threshold diagnostics; not equal work per matrix.',
              no_quantum_gravity_sampling=True, elapsed_seconds=time.perf_counter()-start)
Path(a.output).write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result), flush=True)
raise SystemExit(0 if result['passed'] else 1)
