"""Audit the active seam and the archived network response. No network integration."""
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
from scipy.integrate import quad
from scipy.linalg import expm, null_space
from scipy.optimize import brentq, linprog
from scipy.special import expit, iv, zeta

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent / 'network_bench'
FORMATION = HERE.parent / 'formation'
sys.path.insert(0, str(BENCH))
sys.path.insert(0, str(FORMATION))
from check import graph, chemical_control, log_partition
from word_rule import F_word, state_to_word, word_to_state
from graph import contrast, target_x, relic

OBS = ['Yp', 'D_H', 'He3_H_late', 'Li7_H_late']
LENGTHS = (3, 5, 7, 9, 15)
REGISTRY = json.loads((HERE / 'registry.json').read_text())
CHECKED = set()


def close(key, observed, expected):
    err = np.max(np.abs(np.asarray(observed) - np.asarray(expected)))
    if not err <= REGISTRY[key]['tolerance']:
        raise ArithmeticError(f'{key}: residual {err}')
    CHECKED.add(key)


def spectral():
    ratios = json.loads((FORMATION / 'results.json').read_text())['partition_ratios']
    for key, ratio in ratios.items():
        length, x = [int(s[1:]) for s in key.split('_')]
        close('partition', 1 - contrast(length, x), ratio)
    parity = {}
    for length in range(3, 17):
        n = length - 1
        dims = []
        for phi in (0, np.pi):
            if length % 2:
                step = graph(length, phi)[0]
            else:  # abstract cyclic control only
                step = np.zeros((length, length))
                step[0, 0] = 1
                step[2:, 1:-1] = np.eye(n - 1)
                step[1, -1] = 1 if phi == 0 else -1
            dims.append(int(np.sum(abs(np.linalg.eigvalsh(1j*(step-step.conj().T))) < 1.e-10)))
        close('parity', dims, [3, 1] if length % 2 else [2, 2])
        parity[length] = dims
    rows = []
    for length in LENGTHS:
        n = length - 1
        f, v, phase = graph(length, 0)
        g, w, twist = graph(length, np.pi)
        z = np.eye(length)
        z[-1, -1] = -1
        close('factor', g, f @ z)
        u = w.conj().T @ v
        close('overlap', w.conj().T @ z @ v,
              np.exp(-1j*twist[:, None]) * u * np.exp(1j*phase))
        for x in (1,4,8):
            eps = contrast(length,x)
            if not 0 < eps < .5:
                raise ArithmeticError('Finite active-layer contrast outside (0,1/2)')
        close('ceiling', contrast(length, 500*n*n), .5)
        weights = abs(v.conj().T @ g @ v[:, 1])**2
        close('channels', weights, np.r_[0., (1-2/n)**2, np.full(n-1, 4/n**2)])
        rows.append(dict(L=length, coherent_leak=4*(n-2)/n**2,
                         thermal_epsilon_x4=contrast(length, 4),
                         I_N_over_leading_x4=iv(n, 4)/(2**n/math.factorial(n))))
    return dict(parity=parity, channels=rows, partition_points=len(ratios))


def order_sign(word):
    """Parity from permanent bit-label order to (site, bit) order."""
    sites = [next(i for i, mask in enumerate(word) if mask & bit) for bit in (1,2,4,8)]
    return (-1)**sum(a > b for i, a in enumerate(sites) for b in sites[i+1:])


def word_sign_tests():
    rows = []
    for length in LENGTHS:
        signs = dict(unsigned=[], canonical_order=[], split=[], merge=[], reciprocal=[])
        for t in range(length):
            word = state_to_word((t, (length+1)//2, (t+(length-1)//2)%length), length)
            target = word_to_state(F_word(word))
            # Compare in the same canonical representative with bit 1 at site zero.
            dest = state_to_word(target, length)
            split = word.count(12)
            merge = sum((m, word[(i+1)%length]) == (8,4) for i,m in enumerate(word))
            signs['unsigned'].append(1)
            signs['canonical_order'].append(order_sign(dest) * order_sign(word))
            signs['split'].append((-1)**split)
            signs['merge'].append((-1)**merge)
            signs['reciprocal'].append((-1)**(split+merge))
        products = {k: [s[1], math.prod(s[:1]+s[2:])] for k,s in signs.items()}
        expected = [[1,1], [1,1], [-1,1], [1,-1], [-1,-1]]
        close('sign_controls', list(products.values()), expected)
        rows.append(dict(L=length, fixed_loop_and_long_cycle=products))
    return rows


def mutual_response(length, x, coupling):
    """Simultaneously open both gates for one dimensionless time unit, from (0,0)."""
    gb = -math.log1p(-contrast(length,x))
    q = np.zeros((4,4))
    for i in range(4):
        r,d = divmod(i,2)
        q[i^2,i] = expit((1-2*r)*(gb+coupling*d))
        q[i^1,i] = expit((1-2*d)*coupling*r)
    q[np.diag_indices(4)] = -q.sum(axis=0)
    return expm(q)[-1,0]


def kinetics():
    length, x = 7, 4
    f, v, a = graph(length, 0)
    _, w, b = graph(length, np.pi)
    eye = np.eye(length)
    z = np.diag([1.]*(length-1)+[-1.])
    s01, s06 = eye.copy(), eye.copy()
    s01[[0,1]] = s01[[1,0]]
    s06[[0,6]] = s06[[6,0]]
    hop = np.zeros_like(eye)
    hop[0,-1] = hop[-1,0] = 1
    close('commutation', s01 @ z - z @ s01, 0)
    close('commutation', hop @ z + z @ hop, 0)
    operators = dict(I=eye, Z=z, S01=s01, S06=s06, edge=hop)
    def hazards(op, drive):
        strengths = abs(w.conj().T @ op @ v)**2
        return (strengths * expit(-x*np.cos(a) + x*np.cos(b[:,None]) + drive)).sum(axis=0)
    values = {}
    for name, op in operators.items():
        h = hazards(op, 0)
        values[name] = dict(selected=h[[0,1,4]].tolist(), total=float(h.sum()))
    close('hazard_controls', [values[k]['total'] for k in ('I','Z','edge')], [3.5,3.5,1])
    close('hazard_controls', values['edge']['selected'][0], 0)
    close('hazard_controls', values['I']['selected'], values['Z']['selected'])
    if abs(values['S01']['total'] - 3.5) < .001:
        raise ArithmeticError('Missing unitary counterexample')
    sum_b1 = float(hazards(eye, 1).sum())
    if abs(sum_b1 - length*expit(1)) < .01:
        raise ArithmeticError('Missing b=1 counterexample')
    p0, pp = [chemical_control(length,x,phi,0)['P_bound_after_one_unit'] for phi in (0,np.pi)]
    ratio = math.exp(log_partition(length,np.pi,x) - log_partition(length,0,x))
    gap = .5 - ratio/(1+ratio)
    amplification = (p0-pp)/gap
    close('transient', amplification, 5.9200615711)
    deltas = []
    for L in (7,9,15):
        g = -math.log1p(-contrast(L,x))
        base = mutual_response(L,x,0)
        deltas.append(dict(L=L,g_bias=g, delta_joint_g_bias=mutual_response(L,x,g)-base,
                           delta_joint_g_ln2=mutual_response(L,x,math.log(2))-base))
    return dict(hazards=values, joint_probabilities=deltas, identity_sum_b1=sum_b1, proposed_sum_b1=length*expit(1),
                transient_gap=p0-pp, equilibrium_gap=gap, amplification=amplification)


def response():
    folder = BENCH / 'results'
    rows = np.loadtxt(folder/'binding_response.csv', delimiter=',', skiprows=1)
    M = rows[:,1:].T
    runs = json.loads((folder/'paired_runs.json').read_text())
    def yields(case):
        return np.array([runs[case]['result'][k] for k in OBS])
    # Check ordering and units against independent reconstruction from all 20 stored perturbations.
    check = np.stack([np.log(yields(f'kernel_{i}_1')/yields(f'kernel_{i}_-1'))/.0006
                      for i in range(10)], axis=1)
    close('response_input', M, check)
    d = M[1:2]
    Q = null_space(d)
    held = M[[0,2,3]] @ Q
    close('response_rank', [np.linalg.matrix_rank(M), np.linalg.matrix_rank(held)], [4,3])
    bases = rows[:,0]
    window = (bases >= .06) & (bases <= .08)
    abs_share = np.sum(abs(M[:,window]),axis=1) / np.sum(abs(M),axis=1)
    diff = yields('coupled') - yields('refit_direct')
    # Largest helium contrast at fixed D/H in the measured linear response, infinity-norm box.
    radius = .00030
    optimum = linprog(-M[0], A_eq=d, b_eq=[0.], bounds=(-radius, radius), method='highs')
    if not optimum.success:
        raise ArithmeticError(optimum.message)
    close('local_box', d @ optimum.x, 0)
    # Dual certificate: optimise the free D/H multiplier, check it bounds the attainable contrast.
    multiplier = optimum.eqlin.marginals[0]
    close('local_box', -optimum.fun, radius*np.abs(M[0]+multiplier*d[0]).sum())
    sigmas = (.0013, .004)
    return dict(observables=OBS, scenario_count=len(runs), rhs_sum=sum(v['result']['nfev'] for v in runs.values()),
                singular_values_per_MeV=np.linalg.svd(M,compute_uv=False).tolist(),
                restricted_singular_values_per_MeV=np.linalg.svd(held,compute_uv=False).tolist(),
                tangent_input_dimension=Q.shape[1], tangent_null_dimension=Q.shape[1]-np.linalg.matrix_rank(held).item(),
                abs_row_share_60_70_80_keV=abs_share.tolist(), absolute_matched_difference=diff.tolist(),
                relative_percent=(100*diff/yields('refit_direct')).tolist(),
                local_box=dict(max_knot_difference_MeV=radius, max_delta_ln_Yp=-optimum.fun,
                               max_sigma_helium=yields('off')[0]*(-optimum.fun)/sigmas[0]),
                helium_separation={str(s):abs(diff[0])/s for s in sigmas},
                coupled_to_tight=(yields('coupled')-yields('tight')).tolist())


def cosmology():
    T = .08
    tn = (4/11)**(1/3)*T
    ref = 7*np.pi**2/120*tn**4
    rows = []
    for gd in (28,106.75,202):
        tx = tn*(10.75/gd)**(1/3)
        for gx in (1,7,126):
            def ratio(j):
                return float(relic(tx,2*j,gx)[0]/ref)
            cap = brentq(lambda j:ratio(j)-.17,0,2) if ratio(0)<.17 else None
            jr = {L:target_x(L,.01)*T/2 for L in (3,7,9,15)}
            rows.append(dict(g_dec=gd, g_X=gx, J_max_MeV=cap,
                             density_at_visibility={L:ratio(j) for L,j in jr.items()}))
    close('relic_control', [rows[i]['J_max_MeV'] for i in (0,3,6)],
          [.0170770621,.2238488586,.4297378729])
    me = .51099895
    a = me/T
    theta = 2*me**2*T**2/np.pi**2*quad(lambda y: np.sqrt(y*y-a*a)*expit(-y),a,np.inf)[0]
    nb = 6.1e-10*2*zeta(3)/np.pi**2*T**3
    return dict(T_MeV=T, rho_one_nu_MeV4=ref, relic_screen=rows,
                final_He_binding_budget_over_electron_trace=.247*7.07*nb/theta)


def main():
    results = dict(spectral=spectral(), sign_interpretations=word_sign_tests(), kinetics=kinetics(),
                   archived_response=response(), cosmology=cosmology())
    needed = {k for k,v in REGISTRY.items() if 'tolerance' in v}
    if CHECKED != needed:
        raise RuntimeError(f'Missing coverage: {needed ^ CHECKED}')
    paths = [FORMATION/'check.py', FORMATION/'results.json', HERE.parent.parent/'word_rule.py',
             BENCH/'graph.py', BENCH/'results/binding_response.csv', BENCH/'results/paired_runs.json']
    results['input_sha256'] = {str(p.relative_to(HERE.parents[2])): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    return results


if __name__ == '__main__':
    print(json.dumps(main(), indent=2, allow_nan=False))
