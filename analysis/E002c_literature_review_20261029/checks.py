"""Small algebraic counterexamples for the literature review; no trajectories/VM.

Run: python analysis/E002c_literature_review_20261029/checks.py
Only NumPy is used. The 8-state frozen control below is not the 216-state model.
"""
import json
import time
import numpy as np


def kron_all(factors):
    value = np.ones((1, 1), complex)
    for factor in factors:
        value = np.kron(value, factor)
    return value


def embedded(op, site):
    return kron_all([op if i == site else np.eye(2) for i in range(3)])


def liouvillian(h, jumps):
    eye = np.eye(len(h))
    result = -1j * (np.kron(eye, h) - np.kron(h.T, eye))
    for c in jumps:
        a = c.conj().T @ c
        result += np.kron(c.conj(), c)
        result -= (np.kron(eye, a) + np.kron(a.T, eye)) / 2
    return result


def pure(v):
    return np.outer(v, v.conj())


def alpha_gme(v):
    tensor = v.reshape(2, 2, 2)
    return max(float(np.linalg.svd(np.moveaxis(tensor, i, 0).reshape(2, 4),
                                   compute_uv=False)[0] ** 2) for i in range(3))


def main():
    started = time.perf_counter()
    basis = np.eye(8)
    vacuum = basis[0]
    dark = (basis[4] - basis[2]) / np.sqrt(2)
    w = (basis[4] + basis[2] + basis[1]) / np.sqrt(3)
    ghz = (basis[0] + basis[7]) / np.sqrt(2)
    alpha = alpha_gme(w)
    wrong = alpha * pure(w) - np.eye(8)
    correct = alpha * np.eye(8) - pure(w)
    witness = dict(
        wrong_on_product_vacuum=float(np.vdot(vacuum, wrong @ vacuum).real),
        correct_on_product_vacuum=float(np.vdot(vacuum, correct @ vacuum).real),
        correct_on_W_state=float(np.vdot(w, correct @ w).real),
        alpha_Bell_times_vacuum=alpha_gme(dark),
        alpha_W=alpha, alpha_GHZ=alpha_gme(ghz))
    assert np.isclose(witness['wrong_on_product_vacuum'], -1)
    assert witness['correct_on_product_vacuum'] >= 0
    assert witness['correct_on_W_state'] < 0
    assert np.allclose([witness['alpha_Bell_times_vacuum'], alpha,
                        witness['alpha_GHZ']], [1, 2/3, .5])

    up = [embedded(np.array([[0, 0], [1, 0]]), i) for i in range(3)]
    h = np.zeros((8, 8), complex)
    for i, j in ((0, 1), (1, 2), (0, 2)):
        a = up[i] @ up[j].conj().T
        h += a + a.conj().T
    sink, source = np.sqrt(.5)*up[2].conj().T, np.sqrt(.5)*up[0]
    unpumped = liouvillian(h, [sink])
    pumped = liouvillian(h, [sink, source])
    rd, rv = [pure(v).reshape(-1, order='F') for v in (dark, vacuum)]
    tolerance = 1e-10
    frozen = dict(
        hilbert_dimension=8, liouvillian_dimension=64,
        kappa_in=.5, kappa_out=.5, nullity_svd_tolerance=tolerance,
        no_source_nullity=int(np.sum(np.linalg.svd(unpumped, compute_uv=False) < tolerance)),
        with_source_nullity=int(np.sum(np.linalg.svd(pumped, compute_uv=False) < tolerance)),
        no_source_dark_residual=float(np.linalg.norm(unpumped @ rd)),
        no_source_vacuum_residual=float(np.linalg.norm(unpumped @ rv)),
        source_jump_weight_on_dark=float(np.linalg.norm(source @ dark)**2),
        with_source_dark_residual=float(np.linalg.norm(pumped @ rd)))
    assert frozen['no_source_nullity'] == 2
    assert frozen['with_source_nullity'] == 1
    assert frozen['no_source_dark_residual'] < tolerance
    assert frozen['no_source_vacuum_residual'] < tolerance
    assert np.isclose(frozen['source_jump_weight_on_dark'], .25)
    assert frozen['with_source_dark_residual'] > .01

    # Same stationary populations and aggregate jump turnover, different gaps.
    # This is a counterexample to identifying turnover with relaxation, not an
    # assertion that every edge-resolved rate in E002c has been matched here.
    chains = []
    for weights in ((1., 1., 1.), (2., .5, .5)):
        q = np.zeros((3, 3))
        for (i, j), rate in zip(((0, 1), (1, 2), (0, 2)), weights):
            q[i, j] = q[j, i] = rate
        q -= np.diag(q.sum(axis=1))
        pi = np.ones(3)/3
        values = np.linalg.eigvalsh(q)
        assert np.linalg.norm(pi @ q) < tolerance
        chains.append(dict(weights=weights, stationary_population=pi.tolist(),
                           turnover=float(-pi @ np.diag(q)),
                           spectrum=values.tolist(), gap=float(-values[-2])))
    assert np.allclose([x['turnover'] for x in chains], [2, 2])
    assert np.allclose([x['gap'] for x in chains], [3, 1.5])
    result = dict(status='PASS', scope='local_algebra_only_no_experiment_data',
                  numpy_version=np.__version__, witness=witness, frozen_control=frozen,
                  turnover_counterexample=chains,
                  full_model_dimensions=dict(hilbert=216, liouvillian=216**2),
                  elapsed_seconds=time.perf_counter()-started)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
