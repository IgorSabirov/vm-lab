"""E001X operators plus explicit sqrt(I-Q) idle control; P/Q definitions retained."""
import hashlib,json,os
from pathlib import Path
import numpy as np
from scipy import sparse as sp
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save_json(path, obj):
    path = Path(path)
    temp = path.with_name(path.name + '.tmp')
    with temp.open('w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)

def maxabs(a):
    values = a.data if sp.issparse(a) else np.asarray(a)
    return float(np.max(np.abs(values), initial=0.0))

def clean(a):
    a = a.tocsr()
    a.sum_duplicates()
    a.eliminate_zeros()
    a.sort_indices()
    return a

def ketbra(d, a, b):
    return sp.csr_matrix(([1.0 + 0j], ([a], [b])), shape=(d, d))

def tensor(factors):
    out = sp.csr_matrix([[1.0 + 0j]])
    for a in factors:
        out = sp.kron(out, a, format='csr')
    return out

def build_model(p):
    if 'rr_rates' in p:
        if p['g'] != 0:
            raise ValueError('RR requires g=0: coherent H_form is forbidden')
        if set(p['rr_rates']) != {'01','12','02'}:
            raise ValueError('RR rates must specify edges 01,12,02')
        for rates in p['rr_rates'].values():
            if len(rates)!=2 or not np.isfinite(rates).all() or min(rates)<0:
                raise ValueError('Invalid RR rates')
    if p['gate_form'] not in {'Pi', 'Q'} or p['gate_idle'] not in {'Pi', 'Q', 'S'}:
        raise ValueError('Unknown gate')
    dims = [2, 2, 2, 3, 3, 3]
    identities = [sp.eye(d, format='csr', dtype=complex) for d in dims]
    size = int(np.prod(dims))
    eye = sp.eye(size, format='csr', dtype=complex)

    def embed(a, at):
        factors = identities.copy()
        factors[at] = a
        return tensor(factors)

    plus = [embed(ketbra(2, 1, 0), i) for i in range(3)]
    minus = [a.getH().tocsr() for a in plus]
    n = [clean(a @ b) for a, b in zip(plus, minus)]
    z = [eye - 2 * a for a in n]
    edge_pairs = [(0, 1), (1, 2), (0, 2)]
    h_hop = sp.csr_matrix((size, size), dtype=complex)
    h_form = h_hop.copy()
    jumps = []
    p0s, prs, pls = [], [], []
    for e, (i, j) in enumerate(edge_pairs):
        at = e + 3
        p0, pr, pl = [embed(ketbra(3, k, k), at) for k in range(3)]
        bplus = embed(ketbra(3, 2, 1), at)
        bminus = bplus.getH().tocsr()
        pump = embed(ketbra(3, 1, 0), at)
        broken = embed(ketbra(3, 0, 2), at)
        hop = plus[i] @ minus[j] + plus[j] @ minus[i]
        p_single = (eye - z[i] @ z[j]) / 2
        pi_plus = (p_single + hop) / 2
        q = p_single / 2
        g_form = pi_plus if p["gate_form"] == "Pi" else q
        # Q has eigenvalues 0 and 1/2; this is sqrt(I-Q), NOT I-sqrt(I-Q).
        idle_factor = (eye - pi_plus if p['gate_idle'] == 'Pi' else
                       eye - q if p['gate_idle'] == 'Q' else
                       eye - (2 - np.sqrt(2))*q)
        h_hop += p['J'] * (pl @ hop)
        h_form += p['g'] * ((bplus + bminus) @ g_form)
        channels = [
            ('pump', p['eta'], pump),
            ('break', p['delta'], broken),
            ('idle', p['gamma_r'], bminus @ idle_factor),
            ('background', p['gamma_bg'], bminus),
            ('edge_dephase', p['phi_e'], pr - pl),
        ]
        if 'rr_rates' in p:
            channels=[x for x in channels if x[0]!='idle']
            alpha,beta=p['rr_rates'][f'{i}{j}']
            channels += [('idle',beta,bminus),('renew',alpha,bplus)]
        for label, rate, op in channels:
            jumps.append((f'{label}_{i}{j}', clean(np.sqrt(rate) * op)))
        p0s.append(p0)
        prs.append(pr)
        pls.append(pl)
    jumps.append(('source_0', clean(np.sqrt(p['kappa_in']) * plus[0])))
    jumps.append(('sink_2', clean(np.sqrt(p['kappa_out']) * minus[2])))
    jumps.extend((f'node_dephase_{i}', clean(np.sqrt(p['phi_n']) * z[i])) for i in range(3))
    return clean(h_hop + h_form), jumps, clean(sum(prs) + sum(pls)), clean(p['eta'] * sum(p0s) - p['delta'] * sum(pls)), dims

def build_liouvillian(h, jumps):
    eye = sp.eye(h.shape[0], format='csr', dtype=complex)
    result = -1j * (sp.kron(eye, h, format='csr') - sp.kron(h.T, eye, format='csr'))
    for _, c in jumps:
        a = clean(c.getH() @ c)
        result += sp.kron(c.conjugate(), c, format='csr')
        result -= 0.5 * sp.kron(eye, a, format='csr')
        result -= 0.5 * sp.kron(a.T, eye, format='csr')
    return clean(result)

def right(rho, a):
    return (a.T @ rho.T).T

def make_direct_rhs(h, jumps):
    products = [(c, c.getH().tocsr(), clean(c.getH() @ c)) for _, c in jumps]

    def rhs(v):
        rho = v.reshape(h.shape, order='F')
        out = -1j * (h @ rho - right(rho, h))
        for c, ch, a in products:
            out += right(c @ rho, ch) - 0.5 * (a @ rho + right(rho, a))
        return out.reshape(-1, order='F')
    return rhs

def rk4(rhs, v, dt):
    a = rhs(v)
    b = rhs(v + dt * a / 2)
    c = rhs(v + dt * b / 2)
    d = rhs(v + dt * c)
    return v + dt * (a + 2*b + 2*c + d) / 6

def measurement_operators(p,h,jumps,L):
    dims=[2,2,2,3,3,3];I=sp.eye(216,format='csr',dtype=complex)
    def emb(a,k):
        fs=[sp.eye(d,format='csr',dtype=complex) for d in dims];fs[k]=a;return tensor(fs)
    n=[emb(ketbra(2,1,1),i) for i in range(3)];z=[I-2*x for x in n]
    up=[emb(ketbra(2,1,0),i) for i in range(3)]
    p0=[emb(ketbra(3,0,0),i+3) for i in range(3)]
    pr=[emb(ketbra(3,1,1),i+3) for i in range(3)]
    pl=[emb(ketbra(3,2,2),i+3) for i in range(3)]
    names=[];ops=[]
    def add(name,op):names.append(name);ops.append(clean(op))
    pairs=[(0,1),(1,2),(0,2)]
    for e,(i,j) in enumerate(pairs):
        en=f'{i}{j}'
        for label,arr in [('p0',p0),('pR',pr),('pL',pl)]:add(label+en,arr[e])
        bp=emb(ketbra(3,2,1),e+3);bm=bp.getH();hop=up[i]@up[j].getH()+up[j]@up[i].getH()
        q=(I-z[i]@z[j])/4;pi=q+hop/2;G=pi if p['gate_form']=='Pi' else q
        add('gate_Pi'+en,pi);add('gate_Q'+en,q)
        add('edge_coherence_Re'+en,(bp+bm)/2);add('edge_coherence_Im'+en,(bp-bm)/(2j))
        add('formation_current'+en,1j*p['g']*((bm-bp)@G))
        add('dPL_H_'+en,1j*(h@pl[e]-pl[e]@h))
        for name,c in jumps:
            ch=c.getH();a=ch@c;add('dPL_'+en+'__'+name,ch@pl[e]@c-(a@pl[e]+pl[e]@a)/2)
    for i,x in enumerate(n):add('n'+str(i),x)
    add('sum_pL',sum(pl));add('sum_pR',sum(pr));add('inventory',sum(pl)+sum(pr))
    add('sink_flux',p['kappa_out']*n[2]);add('source_flux',p['kappa_in']*(I-n[0]))
    add('pump_flux',p['eta']*sum(p0));add('break_flux',p['delta']*sum(pl))
    add('path_probability',pl[2]+(I-pl[2])@pl[0]@pl[1])
    for name,c in jumps:add('event_rate__'+name,c.getH()@c)
    rows=sp.vstack([sp.csr_matrix(op.T.toarray().reshape(1,-1,order='F')) for op in ops],format='csr')
    idx={name:i for i,name in enumerate(names)}
    balance=0.
    for i,j in pairs:
        en=f'{i}{j}';row=rows[idx['dPL_H_'+en]].copy()
        for name,_ in jumps:row+=rows[idx['dPL_'+en+'__'+name]]
        balance=max(balance,maxabs(rows[idx['pL'+en]]@L-row))
    return rows,names,balance

def validate(v,tol,eigen=False):
    rho=v.reshape((216,216),order='F');x={'trace_error':float(abs(np.trace(rho)-1)),'hermiticity_error':maxabs(rho-rho.conj().T),'finite':bool(np.isfinite(v).all())}
    if eigen:x['min_eigenvalue']=float(np.linalg.eigvalsh((rho+rho.conj().T)/2)[0])
    good=x['finite'] and x['trace_error']<=tol['trace'] and x['hermiticity_error']<=tol['hermiticity'] and x.get('min_eigenvalue',0)>=-tol['positivity']
    if not good:raise RuntimeError('Invalid state: '+json.dumps(x))
    return x

def adjoint_jump(c, observable):
    a = c.getH() @ c
    return clean(c.getH() @ observable @ c - (a @ observable + observable @ a) / 2)

def measurement_model(parameters, acceptance):
    h, jumps, inventory, resource_rhs, dims = build_model(parameters)
    generator = build_liouvillian(h, jumps)
    old_rows, names, edge_balance = measurement_operators(parameters, h, jumps, generator)
    names = list(names)
    extra = []
    eye = sp.eye(216, format='csr', dtype=complex)
    def emb(a, at):
        fs = [sp.eye(d, format='csr', dtype=complex) for d in dims]
        fs[at] = a
        return tensor(fs)
    def add(name, op):
        names.append(name)
        extra.append(clean(op))
    n = [emb(ketbra(2, 1, 1), i) for i in range(3)]
    up = [emb(ketbra(2, 1, 0), i) for i in range(3)]
    jd = dict(jumps)
    checks = {
        'H_hermiticity': maxabs(h - h.getH()),
        'trace_generator': maxabs(generator.getH() @ np.eye(216).reshape(-1, order='F')),
        'resource_identity': maxabs(generator.getH() @ inventory.toarray().reshape(-1, order='F') - resource_rhs.toarray().reshape(-1, order='F')),
        'edge_balance': edge_balance,
    }
    node_currents = {k: [sp.csr_matrix((216,216), dtype=complex) for _ in range(3)] for k in ['hop','form','idle']}
    protected_totals = {k:sp.csr_matrix((216,216),dtype=complex) for k in ['B_L','B_R','M_L','E_L']}
    for e, (i,j) in enumerate([(0,1),(1,2),(0,2)]):
        en = f'{i}{j}'
        pl = emb(ketbra(3,2,2), e+3)
        pr = emb(ketbra(3,1,1), e+3)
        bp = emb(ketbra(3,2,1), e+3)
        bm = bp.getH()
        hop = up[i] @ up[j].getH() + up[j] @ up[i].getH()
        q = ((eye-n[i]) @ n[j] + n[i] @ (eye-n[j])) / 2
        pi = q + hop/2
        pm = q - hop/2
        even = eye - 2*q
        gf = pi if parameters['gate_form'] == 'Pi' else q
        hf = parameters['g'] * (bp+bm) @ gf
        if 'rr_rates' in parameters:
            checks['rr_H_form_zero_'+en] = maxabs(hf)
        hh = parameters['J'] * pl @ hop
        bl, ml, el = pl @ pi, pl @ pm, pl @ even
        for label, op in [('B_L', bl), ('B_R', pr@pi), ('M_L',ml), ('E_L',el)]:
            add(label+en, op)
            protected_totals[label] += op
        checks['partition_'+en] = maxabs(bl+ml+el-pl)
        own_idle = adjoint_jump(jd['idle_'+en], n[j])
        conditional_pi = 'rr_rates' not in parameters and parameters['gate_idle']=='Pi'
        target_idle = parameters['gamma_r']/4 * pl @ (n[i]-n[j]) if conditional_pi else 0*pl
        checks['idle_current_'+en] = maxabs(own_idle-target_idle)
        pieces = {'hop':1j*(hh@n[j]-n[j]@hh), 'form':1j*(hf@n[j]-n[j]@hf), 'idle':own_idle}
        for label, op in pieces.items():
            add('I_'+label+en, op)
            node_currents[label][i] -= op
            node_currents[label][j] += op
        add('I_total'+en, sum(pieces.values()))
        deph = adjoint_jump(jd['node_dephase_'+str(i)],bl)+adjoint_jump(jd['node_dephase_'+str(j)],bl)
        ed = adjoint_jump(jd['edge_dephase_'+en],bl)
        own_idle_bl = adjoint_jump(jd['idle_'+en],bl)
        for label, op in [('node_dephase',deph),('edge_dephase',ed),('break',adjoint_jump(jd['break_'+en],bl)),('idle',own_idle_bl)]:
            add('dBL_'+label+en,op)
        checks['bright_node_dephase_'+en]=maxabs(deph-2*parameters['phi_n']*(ml-bl))
        checks['bright_edge_dephase_'+en]=maxabs(ed)
        idle_bl_target=0*bl if parameters['gate_idle']=='Pi' else -parameters['gamma_r']*(0.5 if parameters['gate_idle']=='S' else 0.25)*bl
        if 'rr_rates' in parameters:
            idle_bl_target=-parameters['rr_rates'][en][1]*bl
        checks['bright_idle_'+en]=maxabs(own_idle_bl-idle_bl_target)
        idle_rate_target=parameters['gamma_r']*(ml+el if parameters['gate_idle']=='Pi' else (bl+ml)*(0.5 if parameters['gate_idle']=='S' else 0.25)+el)
        if 'rr_rates' in parameters:
            idle_rate_target=parameters['rr_rates'][en][1]*pl
        checks['idle_rate_'+en]=maxabs(jd['idle_'+en].getH()@jd['idle_'+en]-idle_rate_target)
    for label, op in protected_totals.items():
        add(label+'_total',op)
    for label in node_currents:
        add('I_'+label+'_sink',node_currents[label][2])
    for i in range(3):
        full=clean(1j*(h@n[i]-n[i]@h)+sum(adjoint_jump(c,n[i]) for _,c in jumps))
        transport=sum(node_currents[k][i] for k in node_currents)
        external=parameters['kappa_in']*(eye-n[0]) if i==0 else (-parameters['kappa_out']*n[2] if i==2 else 0*eye)
        checks['node_balance_'+str(i)]=maxabs(full-transport-external)
        add('dn'+str(i)+'_dt',full)
    extra_rows=sp.vstack([sp.csr_matrix(op.T.toarray().reshape(1,-1,order='F')) for op in extra],format='csr')
    rows=sp.vstack([old_rows,extra_rows],format='csr')
    if max(checks.values())>acceptance['algebra']:
        raise RuntimeError('Operator checks failed: '+json.dumps(checks))
    return {'H':h,'jumps':jumps,'L':generator,'rows':rows,'names':names,'index':{n:i for i,n in enumerate(names)},'checks':checks}
