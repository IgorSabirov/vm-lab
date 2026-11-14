"""Deterministic source/matrix/algebra audit; no BBN, GP fit, or BH1 run.

Python 3, NumPy and SymPy. From a repository checkout, run this script;
--parent-result overrides only the location, never the required parent hash.
Outputs JSON to stdout. All covariance calculations are local linearizations.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import time

import numpy as np
import sympy as sp

started = time.perf_counter()
here = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--parent-result', type=Path,
    default=here.parents[1] / 's3_input_audit/results/RESULT.json')
args = parser.parse_args()
data_bytes = (here / 'LEONARD_INPUT.json').read_bytes()
data = json.loads(data_bytes)
M = np.asarray(data['covariance_a0'], dtype=float)
mu = np.asarray(data['cross_section_mb'], dtype=float)
published_sd = np.asarray(data['published_cross_section_sd_mb'], dtype=float)
assert M.shape == (16, 16) and mu.shape == (16,)
assert np.array_equal(M, M.T)
eig = np.linalg.eigvalsh(M)
assert eig[0] > 0
cov = (4 * np.pi)**2 * M
reconstructed_sd = np.sqrt(np.diag(cov))
rounding_error = np.max(np.abs(reconstructed_sd - published_sd))
assert rounding_error <= 0.005  # Half of Table III's printed 0.01 mb unit.
corr = cov / np.sqrt(np.outer(np.diag(cov), np.diag(cov)))
cross = corr[:8, 8:]
independent = cov.copy()
independent[:8, 8:] = 0
independent[8:, :8] = 0
assert np.array_equal(independent[:8, :8], cov[:8, :8])
assert np.array_equal(independent[8:, 8:], cov[8:, 8:])
assert np.linalg.eigvalsh(independent)[0] > 0
delta_eig = np.linalg.eigvalsh(cov - independent)
assert delta_eig[0] < 0 < delta_eig[-1]
# Delta-method covariance of logarithmic cross sections, NOT reaction rates.
log_cov = cov / np.outer(mu, mu)
mode_rows = []
for i, energy in enumerate(data['lab_energy_keV']):
    j = i + 8
    v0 = log_cov[i, i] + log_cov[j, j]
    cross_term = 2 * log_cov[i, j]
    mode_rows.append({
        'lab_energy_keV': energy,
        'cm_energy_keV_nonrelativistic': energy / 2,
        'same_energy_correlation': float(cross[i, i]),
        'sd_geometric_mean_log_full_over_independent': float(np.sqrt((v0 + cross_term) / v0)),
        'sd_channel_ratio_log_full_over_independent': float(np.sqrt((v0 - cross_term) / v0)),
    })

# Optional common 1% scale: explicitly a first-order, shared-scalar model.
scale_cov = 0.01**2 * np.outer(mu, mu)
scale_growth = np.sqrt(np.diag(cov + scale_cov) / np.diag(cov)) - 1
parent_bytes = args.parent_result.read_bytes()
parent_hash = hashlib.sha256(parent_bytes).hexdigest()
assert parent_hash == '48a81ecf8734e04426d4b3463a0e68deb20c12e8865459272fcdbae4d9858f02'
parent = json.loads(parent_bytes)
a = parent['rows']['YPBBN']['J_dY_dlneta_secant']
b = parent['rows']['DoH']['J_dY_dlneta_secant'] / parent['rows']['DoH']['baseline']

aa, bb, e, d = sp.symbols('a b e d', nonzero=True)
# e = delta ln eta_CMB, d = ln D_gamma. Conditional eta-component model.
delta_y, delta_d, delta_n = aa * (e + d), bb * (e + d), -sp.Rational(4, 3) * d
identities = {
    'helium_entropy_consistency': sp.simplify(delta_y - aa*e + sp.Rational(3, 4)*aa*delta_n),
    'deuterium_entropy_consistency': sp.simplify(delta_d - bb*e + sp.Rational(3, 4)*bb*delta_n),
    'bbn_eta_null_also_erases_entropy_component': sp.simplify(bb*delta_y - aa*delta_d),
}
assert all(value == 0 for value in identities.values())
bbn_design = sp.Matrix([[aa, aa], [bb, bb]])
joint_design = sp.Matrix([[aa, aa], [bb, bb], [0, -sp.Rational(4, 3)]])
assert bbn_design.rank() == 1 and joint_design.rank() == 2
# A shared additive log-scale has zero response in a channel log-ratio.
unit = np.ones(16)
w = np.zeros(16)
w[7], w[15] = -1, 1
assert w @ unit == 0

result = {
    'status': 'SOURCE_MATRIX_AND_CONDITIONAL_IDENTITIES_VERIFIED',
    'scope': 'Laboratory covariance modes and local entropy identifiability; not a BBN uncertainty or Anthropic likelihood',
    'BBN_executed': False, 'BH1_executed': False,
    'GP_fitted': False, 'scientific_acceptance': False,
    'source_commit': data['repository_parent_sha'],
    'input_sha256': hashlib.sha256(data_bytes).hexdigest(),
    'parent_result_sha256': parent_hash,
    'environment': {'python': platform.python_version(), 'numpy': np.__version__, 'sympy': sp.__version__},
    'table_v': {
        'dimension': list(M.shape), 'symmetry_max_abs': float(np.max(np.abs(M-M.T))),
        'min_eigenvalue_a0_units_squared': float(eig[0]),
        'max_eigenvalue_a0_units_squared': float(eig[-1]),
        'condition_number': float(eig[-1] / eig[0]),
        'table_iii_max_sd_rounding_difference_mb': float(rounding_error),
        'cross_correlation_range': [float(cross.min()), float(cross.max())],
        'full_minus_independent_eigenvalue_range_mb2': [float(delta_eig[0]), float(delta_eig[-1])],
    },
    'laboratory_modes_without_extra_1pct_scale': mode_rows,
    'conditional_common_1pct_scale_sd_increase_fraction': [float(scale_growth.min()), float(scale_growth.max())],
    'entropy_component_only': {
        'a_dYp_dlneta': a, 'b_dlnDoH_dlneta': b,
        'bbn_design_rank': int(bbn_design.rank()),
        'with_known_neutrino_component_design_rank': int(joint_design.rank()),
        'RY_coefficient_of_delta_ln_Neff_nu': 0.75*a,
        'RD_coefficient_of_delta_ln_Neff_nu': 0.75*b,
        'identities': {name: str(value) for name, value in identities.items()},
        'requires': 'Late blackbody photon heating, conserved baryons, unchanged neutrinos, known initial Neff_nu, no residual-X contamination, no earlier background/weak or photodissociation effects',
    },
    'wall_seconds': time.perf_counter() - started,
}
print(json.dumps(result, ensure_ascii=False, indent=2))
