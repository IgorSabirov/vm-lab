"""E002c changes around the byte-for-byte pinned E002b operator builder."""
from functools import lru_cache
import numpy as np
from scipy import sparse as sp
from e002_exp.model import (build_model, build_liouvillian, tensor, ketbra,
                            clean, maxabs, adjoint_jump)

EDGES = ('01', '12', '02')
PAIRS = ((0, 1), (1, 2), (0, 2))
BASE = dict(J=1., g=.5, eta=.25, delta=.1, gamma_bg=.01, gamma_r=.05,
            kappa_in=.5, kappa_out=.5, phi_e=.05, phi_n=.05,
            gate_form='Q', gate_idle='S')
RR = dict(zip(EDGES, ((.034391922002445986, .03673596724712181),
                     (.0343919220002473, .03673596724703888),
                     (.06080323306206624, .03505876323286412))))
ONE = np.array([4, 2, 1])
TWO = np.array([6, 5, 3])

@lru_cache(None)
def operators():
    dims = [2, 2, 2, 3, 3, 3]
    def emb(a, k):
        fs = [sp.eye(d, dtype=complex, format='csr') for d in dims]
        fs[k] = a
        return tensor(fs)
    eye = sp.eye(216, dtype=complex, format='csr')
    n = [emb(ketbra(2, 1, 1), i) for i in range(3)]
    up = [emb(ketbra(2, 1, 0), i) for i in range(3)]
    pl = [emb(ketbra(3, 2, 2), i+3) for i in range(3)]
    pr = [emb(ketbra(3, 1, 1), i+3) for i in range(3)]
    bp = [emb(ketbra(3, 2, 1), i+3) for i in range(3)]
    c = [(eye-n[i])@n[j]+n[i]@(eye-n[j]) for i, j in PAIRS]
    edge_states = np.array(list(np.ndindex(3, 3, 3)))
    mask_id = ((edge_states == 2) * [1, 2, 4]).sum(axis=1)
    masks = [sp.diags((mask_id == m).astype(float), format='csr') for m in range(8)]
    return dict(eye=eye, n=n, up=up, pl=pl, pr=pr, bp=bp, c=c,
                mask_id=mask_id, masks=masks)

def initial():
    r = np.zeros((216, 216), complex)
    for node in (4, 2):
        k = node*27+13  # RRR = ternary 111
        r[k, k] = .5
    return r.reshape(-1, order='F')

def sector_hamiltonian(mask, phi=0., epsilon=0., amplitudes=(1., 1., 1.), theta=None):
    theta = [0., 0., -phi] if theta is None else theta
    h = np.diag([0., epsilon, 0.]).astype(complex)
    for e, (i, j) in enumerate(PAIRS):
        if mask & (1 << e):
            h[i, j] = amplitudes[e]*np.exp(1j*theta[e])
            h[j, i] = h[i, j].conjugate()
    return h

def null_projector(a):
    _, s, vh = np.linalg.svd(a, full_matrices=True)
    tol = 1e-10*max(1., s[0] if len(s) else 0.)
    v = vh[int(np.sum(s > tol)):].conj().T
    p = v@v.conj().T
    return p, dict(singular_values=s.tolist(), tolerance=tol,
                   dimension=v.shape[1], residual=float(np.linalg.norm(a@p)))

def dark_projectors(h):
    c = np.array([[0., 0., 1.]])
    k, ki = null_projector(np.vstack([c, c@h]))
    d, di = null_projector(np.vstack([c, c@h, c@h@h]))
    connected = {2}
    for _ in range(3):
        connected |= {j for i in list(connected) for j in range(3)
                      if i != j and abs(h[i, j]) > 1e-12}
    isolated = np.diag([float(i not in connected) for i in range(3)])
    # Every sink-disconnected component is invariant; separate it from interference.
    return k, d, isolated, d-isolated, dict(K=ki, D=di)

def build(case, alpha=None):
    o = operators(); p = dict(BASE, phi_n=float(case['dephasing']))
    variant = case['model']
    if variant == 'RR_QS':
        p.update(g=0., gamma_r=0., rr_rates=RR)
    elif variant == 'IC1_QS':
        if alpha is None or np.shape(alpha) != (3,) or not np.isfinite(alpha).all() or min(alpha)<1e-4 or max(alpha)>2:
            raise ValueError('IC requires three declared rates in [1e-4,2]')
        p['g'] = 0.
    elif variant != 'QS':
        raise ValueError('Unknown model')
    h, jumps, inventory, resource, _ = build_model(p)
    theta = [0., 0., -float(case['phi_over_pi'])*np.pi]
    currents = []; hh_total = 0*h
    for e, (i, j) in enumerate(PAIRS):
        a = o['up'][i]@o['up'][j].getH()
        old = p['J']*o['pl'][e]@(a+a.getH())
        hh = p['J']*o['pl'][e]@(np.exp(1j*theta[e])*a+np.exp(-1j*theta[e])*a.getH())
        h += hh-old; hh_total += hh
        currents.append(clean(1j*(hh@o['n'][j]-o['n'][j]@hh)))
        if variant == 'IC1_QS':
            jumps.append(('feed_'+EDGES[e], clean(np.sqrt(alpha[e])*o['bp'][e]@o['c'][e])))
    h = clean(h+float(case['detuning'])*o['n'][1])
    L = build_liouvillian(h, jumps)
    jd = dict(jumps)
    ell = [clean(sum(jd[k+'_'+e].getH()@jd[k+'_'+e] for k in ('break', 'background', 'idle'))) for e in EDGES]
    feed = [clean(jd[('feed_' if variant == 'IC1_QS' else 'renew_')+e].getH()@
                  jd[('feed_' if variant == 'IC1_QS' else 'renew_')+e])
            if variant != 'QS' else 0*o['eye'] for e in EDGES]
    ops = [*currents, currents[1]+currents[2], .5*o['n'][2], *o['n'],
           *o['pl'], *ell, .25*(3*o['eye']-inventory), .1*sum(o['pl']), inventory,
           .5*(o['eye']-o['n'][0]), *feed]
    names = ['I01','I12','I02','h','F','n0','n1','n2',
             'pL01','pL12','pL02','ell01','ell12','ell02','pump','break','inventory',
             'source','feed01','feed12','feed02']
    dark=[]; masks=o['masks']; p1=np.zeros((8,8));p1[ONE,ONE]=1
    def embed_node(a):
        v=np.zeros((8,8),complex);v[np.ix_(ONE,ONE)]=a;return v
    for m in range(8):
        hm=sector_hamiltonian(m, float(case['phi_over_pi'])*np.pi, case['detuning'])
        k,d,iso,inter,info=dark_projectors(hm)
        dark.append(dict(k=embed_node(k),d=embed_node(d),isolated=embed_node(iso),
                         interference=embed_node(inter),info=info))
        for tag,op in [('p',np.eye(8)),('w1',p1),('k',embed_node(k)),('d',embed_node(d))]:
            names.append(f'{tag}_m{m}');ops.append(sp.kron(op,masks[m],format='csr'))
    rows=sp.vstack([sp.csr_matrix(op.T.toarray().reshape(1,-1,order='F')) for op in ops],format='csr')
    def adj(op):
        return clean(1j*(h@op-op@h)+sum(adjoint_jump(c,op) for _,c in jumps))
    checks={'H_hermiticity':maxabs(h-h.getH()),
            'trace':maxabs(adj(o['eye'])), 'resource':maxabs(adj(inventory)-resource)}
    checks['node0']=maxabs(adj(o['n'][0])-(-currents[0]-currents[2]+.5*(o['eye']-o['n'][0])))
    checks['node1']=maxabs(adj(o['n'][1])-(currents[0]-currents[1]))
    checks['node2']=maxabs(adj(o['n'][2])-(currents[1]+currents[2]-.5*o['n'][2]))
    hf=clean(h-hh_total-case['detuning']*o['n'][1])
    for i in range(3):
        checks[f'form_current{i}']=maxabs(hf@o['n'][i]-o['n'][i]@hf)
        checks[f'idle_current{i}']=maxabs(sum(adjoint_jump(jd['idle_'+e],o['n'][i]) for e in EDGES))
    if variant == 'IC1_QS':
        checks['IC_form_zero']=maxabs(hf)
        for e in range(3):
            checks[f'IC_feed{e}']=maxabs(adjoint_jump(jd['feed_'+EDGES[e]],o['pl'][e])-alpha[e]*o['pr'][e]@o['c'][e])
            checks[f'IC_balance{e}']=maxabs(adj(o['pl'][e])-feed[e]+ell[e])
    if variant in ('QS','IC1_QS'):
        for e in range(3):
            checks[f'loss{e}']=maxabs(ell[e]-(.16*o['pl'][e]-.025*o['pl'][e]@o['c'][e]))
    if max(checks.values()) > 1e-10:
        raise ValueError('Operator identity failed: '+str(checks))
    return dict(H=h,jumps=jumps,L=L,rows=rows,names=names,dark=dark,checks=checks,
                case=case,currents=currents,alpha=alpha)
