"""Independent direct-matrix check; no model evolution or external access."""
import json
import numpy as np

gamma = 0.1
target_vectors = [np.array([1., -1., 0., 0., 0.]), np.array([0., 0., 1., -1., 0.])]
control_vectors = [abs(v) for v in target_vectors]

def dissipator(v, rho):
    jump = np.sqrt(gamma) * np.diag(v)
    square = jump.conj().T @ jump
    return jump @ rho @ jump.conj().T - (square @ rho + rho @ square) / 2

def measured_rate(vectors, i, j):
    basis = np.zeros((5, 5), complex)
    basis[i, j] = 1
    return float(-sum(dissipator(v, basis) for v in vectors)[i, j].real)

rng = np.random.default_rng(20261030)
matrix = rng.normal(size=(5, 5)) + 1j*rng.normal(size=(5, 5))
rho = matrix @ matrix.conj().T
rho /= np.trace(rho)
d_target = sum(dissipator(v, rho) for v in target_vectors)
d_control = sum(dissipator(v, rho) for v in control_vectors)
expected = np.zeros_like(rho)
for i, j in [(0, 1), (1, 0), (2, 3), (3, 2)]:
    expected[i, j] = -2*gamma*rho[i, j]
error = float(np.max(abs(d_target-d_control-expected)))
assert error < 1e-15
cross = [measured_rate(target_vectors, 0, 3), measured_rate(control_vectors, 0, 3)]
target_pair = [measured_rate(target_vectors, 0, 1), measured_rate(control_vectors, 0, 1)]
combined = [measured_rate([sum(target_vectors)], 0, 3), measured_rate([sum(control_vectors)], 0, 3)]
assert np.allclose(cross, [gamma, gamma], atol=1e-15, rtol=0)
assert np.allclose(target_pair, [2*gamma, 0], atol=1e-15, rtol=0)
assert np.allclose(combined, [2*gamma, 0], atol=1e-15, rtol=0)
print(json.dumps(dict(gamma=gamma, independent_cross_rates=cross,
    independent_target_pair_rates=target_pair, combined_cross_rates=combined,
    direct_density_matrix_residual=error,
    direct_population_change_max=float(max(np.max(abs(np.diag(d_target))), np.max(abs(np.diag(d_control))))),
    status='PASS'), indent=2))
