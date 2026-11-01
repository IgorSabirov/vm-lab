"""Physical operators for the approved geometry ladder and full model."""
import numpy as np
from scipy import sparse as sp
from e002_exp.model import build_model, clean, ketbra, tensor, maxabs, adjoint_jump
from e002c_exp.model import BASE, RR, EDGES, PAIRS, operators
from e002d_exp.plan import TARGETS, OPERATIONS
from .space import Space, liouvillian, charge_checks

IC_ALPHA = (.06489310345717117, .06489313511138023, .07065096360073866)


def node_ops():
    eye = sp.eye(8, dtype=complex, format='csr')
    def emb(x, at):
        return tensor([x if k == at else sp.eye(2, format='csr') for k in range(3)])
    up = [emb(ketbra(2, 1, 0), k) for k in range(3)]
    n = [x @ x.getH() for x in up]
    return eye, up, n


def make_small(case):
    d = int(case['dimension']); mask = int(case['mask'])
    if d not in (4, 8) or mask not in (6, 7):
        raise ValueError('Unsupported ladder case')
    source = float(case.get('source', .5)); sink = float(case.get('sink', .5))
    noise = float(case.get('node_noise', .05)); v = float(case.get('v_over_J', 1.))
    eps = float(case['epsilon']); phi = float(case['phi_over_pi'])*np.pi
    if min(source, sink) <= 0 or min(noise, v) < 0 or not np.isfinite([source, sink, noise, v, eps, phi]).all():
        raise ValueError('Invalid small-model parameters')
    eye, up8, n8 = node_ops()
    if d == 4:
        # Order g, node0, node1, node2; independent global N<=1 model.
        eye = sp.eye(4, format='csr', dtype=complex)
        up = [ketbra(4, i+1, 0) for i in range(3)]
        n = [ketbra(4, i+1, i+1) for i in range(3)]
        charges = np.array([0, 1, 1, 1])
        hops = [ketbra(4, i+1, j+1) for i, j in PAIRS]
    else:
        up, n = up8, n8
        charges = np.array([k.bit_count() for k in range(8)])
        hops = [up[i] @ up[j].getH() for i, j in PAIRS]
    H = eps*n[1]; currents = []
    for e, ((i, j), a, theta) in enumerate(zip(PAIRS, hops, (0., 0., -phi))):
        amp = v if e == (1 if mask == 6 else 0) else 1.
        h = amp*(np.exp(1j*theta)*a + np.exp(-1j*theta)*a.getH()) if mask & (1 << e) else 0*a
        H += h; currents.append(clean(1j*(h@n[j]-n[j]@h)))
    jumps = [('source_0', np.sqrt(source)*up[0]), ('sink_2', np.sqrt(sink)*up[2].getH())]
    convention = case.get('jump_convention', 'three_sqrt_phi_Z')
    if convention == 'sqrt(phi)*n1_only':
        jumps.append(('node_dephase_1', np.sqrt(noise)*n[1]))
    elif convention == 'three_sqrt_phi_Z':
        jumps += [(f'node_dephase_{i}', np.sqrt(noise)*(eye-2*x)) for i, x in enumerate(n)]
    else:
        raise ValueError('Unknown small noise convention')
    active = np.arange(d)
    branch = 'empty_initial_state_unique_stationary_candidate'
    if mask == 6 and v == 0:
        active = np.flatnonzero(abs(n[1].diagonal()) < .5)
        branch = 'n1_zero_invariant_from_empty_initial_state'
        outside = np.setdiff1d(np.arange(d), active)
        if maxabs(H[outside][:, active]) > 1e-12 or any(maxabs(c[outside][:, active]) > 1e-12 for _, c in jumps):
            raise ValueError('Declared physical branch is not invariant')
    restrict = lambda a: clean(a[active][:, active])
    H = restrict(H); jumps = [(name, restrict(c)) for name, c in jumps]
    n = [restrict(x) for x in n]; currents = [restrict(x) for x in currents]
    space = Space(charges[active]); charges = charges[active]
    obs = {'J_h': currents[1]+currents[2], 'F': sink*n[2], 'p_e': sp.diags((charges == 1).astype(float)),
           'P_N2': sp.diags((charges == 2).astype(float)), 'K': currents[1]-currents[2],
           'source': source*(sp.eye(len(active))-sum(n)) if d == 4 else source*(sp.eye(len(active))-n[0])}
    for N in range(4):
        p = sp.diags((charges == N).astype(float), format='csr')
        obs[f'p_N{N}'] = p; obs[f'h_N{N}'] = clean(p@obs['J_h'])
    return dict(H=H, jumps=jumps, space=space, observables=obs, currents=currents,
                n=n, case=case, original_dimension=d, active=active, branch=branch,
                L=liouvillian(H, jumps, space))


def make_full(case, assemble=True):
    from .plan import full_physical_key
    full_physical_key(case)
    o = operators(); model = case['model']; p = dict(BASE, phi_n=float(case['node_noise']))
    if model == 'RR_QS':
        p.update(g=0., gamma_r=0., rr_rates=RR)
    elif model == 'IC1_QS':
        p['g'] = 0.
    elif model != 'QS':
        raise ValueError('Unknown full model')
    phi = float(case['phi_over_pi'])*np.pi; eps = float(case['epsilon']); v = float(case['m6_v_over_J'])
    if not np.isfinite([phi, eps, v, p['phi_n']]).all() or min(v, p['phi_n']) < 0:
        raise ValueError('Invalid full parameters')
    H, jumps, inventory, resource, _ = build_model(p)
    Q = sp.kron(sp.eye(8), o['masks'][6], format='csr')
    currents = []; deformation = 0*H; hop_terms = []
    for e, ((i, j), theta) in enumerate(zip(PAIRS, (0., 0., -phi))):
        a = o['up'][i] @ o['up'][j].getH()
        old = p['J']*o['pl'][e]@(a+a.getH())
        h = p['J']*o['pl'][e]@(np.exp(1j*theta)*a+np.exp(-1j*theta)*a.getH())
        if e == 1:
            deformation = clean((v-1.)*Q@h); h += deformation
        H += h-old; hop_terms.append(clean(h))
        currents.append(clean(1j*(h@o['n'][j]-o['n'][j]@h)))
        if model == 'IC1_QS':
            jumps.append(('feed_'+EDGES[e], clean(np.sqrt(IC_ALPHA[e])*o['bp'][e]@o['c'][e])))
    H = clean(H+eps*o['n'][1]); N = np.array([(k//27).bit_count() for k in range(216)])
    space = Space(N)
    obs = {'J_h': currents[1]+currents[2], 'K': currents[1]-currents[2], 'F': .5*o['n'][2],
           'source': .5*(o['eye']-o['n'][0]), 'inventory': inventory}
    for m in range(8):
        for n in range(4):
            pmn = sp.diags(((N == n) & np.tile(o['mask_id'] == m, 8)).astype(float), format='csr')
            obs[f'p_m{m}_N{n}'] = pmn
            obs[f'h_m{m}_N{n}'] = clean(pmn@obs['J_h'])
            for tag, I in zip(('I01', 'I12', 'I02'), currents):
                obs[f'{tag}_m{m}_N{n}'] = clean(pmn@I)
    obs['P_m6_N2'] = obs['p_m6_N2']; obs['h6'] = obs['h_m6_N2']
    for name, (m, a, b) in TARGETS.items():
        # Tr(|b><a| rho) = rho[a,b], preserving the declared sign convention.
        obs['C_'+name] = sp.kron(ketbra(8, b, a), o['masks'][m], format='csr')
    adj = lambda a: clean(1j*(H@a-a@H)+sum(adjoint_jump(c, a) for _, c in jumps))
    checks = dict(H_hermiticity=maxabs(H-H.getH()), trace=maxabs(adj(o['eye'])),
                  node0=maxabs(adj(o['n'][0])+currents[0]+currents[2]-obs['source']),
                  node1=maxabs(adj(o['n'][1])-currents[0]+currents[1]),
                  node2=maxabs(adj(o['n'][2])-obs['J_h']+obs['F']),
                  resource=maxabs(adj(inventory)-resource),
                  deformation_support=maxabs((o['eye']-Q)@deformation),
                  deformation_commutator=maxabs(Q@deformation-deformation@Q))
    for m in range(8):
        pm = sp.kron(sp.eye(8), o['masks'][m], format='csr')
        obs[f'mask_balance_m{m}'] = adj(pm)
    if max(checks.values()) > 1e-11:
        raise ValueError('Full operator checks failed: '+str(checks))
    result = dict(H=H, jumps=jumps, space=space, observables=obs, currents=currents,
                  n=o['n'], case=case, checks=checks, deformation=deformation, hop_terms=hop_terms,
                  charge_checks=charge_checks(H, jumps, space))
    if assemble:
        result['L'] = liouvillian(H, jumps, space)
    return result


def selective_difference(space, target):
    if target not in OPERATIONS or space.d != 216:
        raise ValueError('Unknown selective target or space')
    rates = np.zeros((216, 216))
    masks = operators()['mask_id']
    for name in OPERATIONS[target]:
        m, a, b = TARGETS[name]
        ds = []
        for sign in (-1., 1.):
            x = np.zeros(8); x[a] = 1.; x[b] = sign
            ds.append(np.kron(x, (masks == m).astype(float)))
        rates += -.5*((ds[0][:, None]-ds[0][None, :])**2 - (ds[1][:, None]-ds[1][None, :])**2)
    return sp.diags(rates.ravel(order='F')[space.indices], format='csr')
