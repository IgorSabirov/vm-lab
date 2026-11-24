"""Small, frozen donor benchmarks for R135. Run normally or against a saved cache."""
import argparse
import ast
import hashlib
import itertools
import json
import math
from pathlib import Path
from urllib.request import urlopen

import numpy as np
from scipy import integrate, interpolate, optimize


GRAPH = 'pirate/wolfram-gauge-physics/801ec5e0885e5870689352a1def3bff918711f2e'
TL = 'tasicarl/TransitionListener/2029102c05e7a2b34f348170d72a0c3fcaeac9be'
FIX = 'infinition/it-from-fix/407c0cc3ff0206a88116743880fde3ec8e282847'
GB = 'GambitBSM/gambit/3fc72d344ccb772f685fcc3426d8a239e33e6b11'
INPUTS = {
    'd4-loop-observer.json': (GRAPH + '/data/d4-loop-observer.json',
                             'a6aa43b4bfd5a9fd89d5e3271e5adc9740e334af8713278a5b657c65dfb7b76a'),
    'd4-fiber-mode-probe.json': (GRAPH + '/data/d4-fiber-mode-probe.json',
                                 'e81670b914b50cf75aaee02ce724eba241548fd9581b99de2b2a625b3c5a5c78'),
    'hard_control_results.json': (FIX + '/experiments/kernel_exchange_hard_controls/hard_control_results.json',
                                  '5d598d5ffa6d5af600ec78096e710041c86ef69af288e9fc1d54e0275dc53333'),
    'bubbledynamics.py': (TL + '/src/transitionlistener/bubbledynamics.py',
                          'ef4db325609dc897010f87153b616ec2949ccb7c0dd7966f9a3e3a35cd43af9f'),
    'BBN.cpp': (GB + '/CosmoBit/src/BBN.cpp',
                'f642fd003b8d6f50298c925c82b93ae13c94625b2df9676cbad117c6dd23afe0'),
}


def load_inputs(cache, offline):
    cache.mkdir(parents=True, exist_ok=True)
    contents = {}
    for name, (source, digest) in INPUTS.items():
        path = cache / name
        if path.exists() or offline:
            data = path.read_bytes()
        else:
            with urlopen('https://raw.githubusercontent.com/' + source, timeout=45) as response:
                data = response.read()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f'Unexpected SHA-256 for {name}')
        if not path.exists():
            path.write_bytes(data)
        contents[name] = data.decode()
    return contents


def fit_value(coefficients, x):
    return sum(coefficient / x**i for i, coefficient in enumerate(coefficients))


def plm():
    # Table 1 and eqs. 5-7, 13 in arXiv:2012.11614v4. x is T / tabulated Tc.
    b3, b4 = 2.36, 4.49
    poly = (3.78, -5.48, 8.47, -9.47, 0.222)
    log_coeff = (4.26, -6.53, 22.8, -4.10)

    def polynomial(x, ell):
        return -fit_value(poly, x) * ell**2 / 2 - 2*b3*ell**3 + b4*ell**4

    def logarithmic(x, ell):
        log_haar = 3 * math.log1p(-ell) + math.log1p(3*ell)
        return -fit_value(log_coeff, x)*ell**2/2 - 1.77*log_haar/x**3

    def poly_min(x):
        return (3*b3 + math.sqrt(9*b3**2 + 4*b4*fit_value(poly, x))) / (4*b4)

    def log_min(x):
        b_over_a = -1.77 / (x**3 * fit_value(log_coeff, x))
        return (1 + 2*math.sqrt(1 + 9*b_over_a)) / 3

    results = {}
    for name, potential, nonzero_min in [('polynomial', polynomial, poly_min),
                                          ('logarithmic', logarithmic, log_min)]:
        def vmin(x):
            return potential(x, nonzero_min(x))

        x = optimize.brentq(vmin, 0.999, 1.002, xtol=1e-14)
        ell = nonzero_min(x)
        step = 1e-5
        latent = -x * (vmin(x+step) - vmin(x-step)) / (2*step)
        tension = integrate.quad(lambda l: math.sqrt(max(0.0, 2*potential(x, l))),
                                 0, ell, epsabs=1e-12)[0]
        thin = 16*math.pi*tension**3 / (3*latent**2)
        if name == 'polynomial':
            d_b2 = sum(-i*value/x**(i+1) for i, value in enumerate(poly))
            assert math.isclose(ell, b3/b4, rel_tol=1e-10)
            assert math.isclose(latent, x*d_b2*ell**2/2, rel_tol=1e-7)
            assert math.isclose(tension, math.sqrt(2*b4)*ell**3/6, rel_tol=1e-9)
        assert abs(vmin(x)) < 1e-12 < potential(x, ell/2)
        results[name] = dict(T_over_input_Tc=x, ell_deconfined=ell, L_over_T4=latent,
                             sigma_over_T3_canonical=tension, thin_wall_delta2_S3_over_T=thin)
    return results


def loop_checks(inputs):
    loops = json.loads(inputs['d4-loop-observer.json'])
    modes = json.loads(inputs['d4-fiber-mode-probe.json'])
    coords = [tuple(c) for c in loops['coordinates']]
    group = range(len(coords))

    def mul(i, j):
        a, b, c = coords[i]
        d, f, h = coords[j]
        return coords.index((a^d, b^f, c^h^(b&d)))

    inv = [next(j for j in group if mul(i,j) == 0) for i in group]
    action = [[mul(mul(g, i), inv[g]) for i in group] for g in group]

    def canonical(indices):
        return min(tuple(row[i] for i in indices) for row in action)

    census = []
    for size in range(5):
        orbits = {canonical(word) for word in itertools.product(group, repeat=size)}
        assert len(orbits) == (8**size + 3*4**size)//4 == loops['census'][size]['gauge_orbits']
        census.append(len(orbits))

    def marginals(word):
        pairs = [mul(i,j) for i,j in itertools.combinations(word, 2)]
        return tuple(canonical((i,)) for i in (*word, *pairs))

    triples = [(1,2,3), (1,2,6)]
    relations = [mul(mul(i,j), inv[k]) for i,j,k in triples]
    assert marginals(triples[0]) == marginals(triples[1])
    assert set(relations) == {0, loops['generators']['z']}

    # Faithful embedding O(2) -> SO(3) inside SU(3). Exact for these integer matrices.
    lifted = []
    for matrix in modes['representation']['matrices']:
        rep = np.asarray(matrix, dtype=int)
        lift = np.zeros((3,3), dtype=int)
        lift[:2,:2] = rep
        lift[2,2] = rep[0,0]*rep[1,1] - rep[0,1]*rep[1,0]
        assert np.array_equal(lift.T @ lift, np.eye(3)) and round(np.linalg.det(lift)) == 1
        lifted.append(lift)
    for i,j in itertools.product(group, repeat=2):
        assert np.array_equal(lifted[i] @ lifted[j], lifted[mul(i,j)])
    word_traces = [int(np.trace(lifted[i] @ lifted[j] @ lifted[k].T)) for i,j,k in triples]
    assert word_traces == [-1, 3]

    traces = {}
    for branch in modes['branches']:
        matrix = np.asarray(branch['mode_laplacian'], dtype=np.int64)
        moments = [int(np.trace(np.linalg.matrix_power(matrix, k))) for k in range(1, 5)]
        assert moments == branch['mode_trace_powers_1_through_8'][:4]
        traces[str(branch['rule'])] = moments
    assert traces['33'][:3] == traces['34'][:3] and traces['33'][3] != traces['34'][3]
    witness = loops['conversion_witness']
    assert witness['branches'][0]['face_classes'] == witness['branches'][1]['face_classes']
    specified = witness['specified_rule_responses']
    assert specified[0]['face_classes'] != specified[1]['face_classes']
    uniform = witness['uniform_next_class_counts']
    assert sum(count for _, count in uniform) == 48 and witness['uniform_next_class_distribution_identical']
    return dict(orbits=census, three_loop_relations=relations, mode_moments=traces,
                su3_embedding_word_traces=word_traces, checked_group_products=64,
                specified_next_face_classes_differ=True, uniform_next_class_counts_equal_reported=True)


def completion(source):
    # Isolate the reviewed, checksum-pinned donor function; do not import its simulation stack.
    fn = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)
              and n.name == 'falseVacuumVolumeGrowthRate')
    environment = {'np': np, 'interpolate': interpolate}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), 'bubbledynamics.py', 'exec'), environment)
    growth = environment[fn.name]
    i_perc = -math.log1p(-0.29)
    outputs = []
    for n, amplitude, cold in [(2, .01, .1), (20, .001, .65)]:
        ts = np.linspace(1, cold, 400)
        fractions = -np.expm1(-amplitude/ts**n)
        tp = (amplitude/i_perc)**(1/n)
        observed = growth(ts, fractions, tp)
        expected = 1 - n*i_perc/3
        assert abs(observed - expected) < 1e-3
        outputs.append(dict(power=n, true_fraction=.29, growth_over_3H=observed, exact=expected))
    return outputs


def covariance(source):
    # The compared line updates the diagonal in compute_BBN_LogLike. r already means He3/D here.
    assert 'double YD = BBN_res.get_BBN_abund("D"), YHe3 = BBN_res.get_BBN_abund("He3")/BBN_res.get_BBN_abund("D");' in source
    assert '(YHe3*YHe3)/(YD*YD) * (BBN_res.get_BBN_covmat(He3,He3)/pow(YHe3,2) + BBN_res.get_BBN_covmat(D,D)/pow(YD,2) - 2*old_covmat_He3_D/YD/YHe3)' in source
    d, r, common_sd = 2.5e-5, .8, .01
    h = d*r
    cov = np.outer([h,d], [h,d]) * common_sd**2
    jac = np.array([1/d, -r/d])
    correct = float(jac @ cov @ jac)
    cpp = r**2/d**2*(cov[0,0]/r**2 + cov[1,1]/d**2 - 2*cov[0,1]/(d*r))
    assert abs(correct) < 1e-15 and cpp > 1
    return dict(h=h, d=d, r=r, common_fractional_sd=common_sd,
                exact_ratio_variance=0, jacobian_variance=correct, cpp_line_variance=float(cpp))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', required=True, type=Path)
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    inputs = load_inputs(args.cache, args.offline)
    controls = json.loads(inputs['hard_control_results.json'])
    delta = controls['persistence']['mean_drift'] - max(controls[k]['mean_drift']
                                                       for k in ('random', 'degree', 'anti_persistence'))
    assert math.isclose(delta, controls['specificity']['target_minus_best_control'])
    result = dict(plm=plm(), graph=loop_checks(inputs), transition_listener=completion(inputs['bubbledynamics.py']),
                  ratio_covariance=covariance(inputs['BBN.cpp']), equal_budget=dict(
                      target_minus_best_mean_drift=delta, target_gain=controls['persistence']['persistence_gain'],
                      random_gain=controls['random']['persistence_gain']))
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
