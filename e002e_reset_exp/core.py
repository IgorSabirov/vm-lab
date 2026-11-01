"""Fixed-target replacement and decisions. No state projection or clipping."""
import hashlib
import numpy as np
from scipy import sparse as sp
from e002_exp.model import maxabs
from e002e_corr_exp.core import marginals, array_hash, physicality, sector_check


def matrix_hash(matrix):
    a=sp.csr_matrix(matrix).copy();a.sum_duplicates();a.sort_indices();a.eliminate_zeros()
    h=hashlib.sha256(str(a.shape).encode())
    for x,dtype in ((a.indptr,'<i8'),(a.indices,'<i8'),(a.data,'<c16')):
        h.update(np.asarray(x,dtype=dtype).tobytes())
    return h.hexdigest()


def target_check(tau, tolerance=1e-10):
    a=np.asarray(tau,complex)
    if a.ndim!=2 or a.shape[0]!=a.shape[1] or not np.isfinite(a).all():
        raise ValueError('Invalid target dimensions/data')
    eig=np.linalg.eigvalsh((a+a.conj().T)/2)
    result=dict(trace_error=float(abs(np.trace(a)-1)),hermiticity=maxabs(a-a.conj().T),
                minimum_eigenvalue=float(eig.min()),spectrum=eig.tolist(),sha256=array_hash(a),
                psd_mode='FULL_EIGVALSH_DIAGNOSTIC_SYMMETRIZATION_ONLY',tolerance=tolerance)
    if max(result['trace_error'],result['hermiticity'],-result['minimum_eigenvalue'])>tolerance:
        raise ArithmeticError('Invalid fixed target')
    return result


class Reset:
    def __init__(self, space, tau, dimensions=(8,27)):
        self.space=space;self.dimensions=tuple(dimensions);a,b=self.dimensions
        if space.d!=a*b:raise ValueError('Reset dimension mismatch')
        self.tau=np.array(tau,complex,copy=True);self.target=target_check(self.tau)
        if self.tau.shape!=(b,b):raise ValueError('Wrong edge target size')
        self.tau.setflags(write=False)
        # This experiment's symmetry acts on nodes only. No edge charge is assumed.
        charge=space.charges.reshape(a,b)
        if not np.all(charge==charge[:,0,None]):raise ValueError('Expected Q=N_nodes tensor I_edges')
        pairs=[(i,j) for j in range(a) for i in range(a) if charge[i,0]==charge[j,0]]
        inverse=np.full(space.d**2,-1,int);inverse[space.indices]=np.arange(space.size)
        columns=[];rows=[];cols=[]
        for k,(i,j) in enumerate(pairs):
            node=np.zeros((a,a),complex);node[i,j]=1
            columns.append(space.pack(np.kron(node,self.tau)))
            for e in range(b):
                pos=inverse[(i*b+e)+space.d*(j*b+e)]
                if pos<0:raise ValueError('Partial trace outside q=0')
                rows.append(k);cols.append(pos)
        self.U=sp.csc_matrix(np.column_stack(columns))
        self.V=sp.csr_matrix((np.ones(len(rows)),(rows,cols)),shape=(len(pairs),space.size))
        self.rank=len(pairs)
        err=maxabs(self.V@self.U-sp.eye(self.rank))
        trace_err=maxabs((space.trace_row@self.U)@self.V-space.trace_row)
        if max(err,trace_err)>1e-10:raise ArithmeticError('Reset idempotence/trace identity failed')
        self.certificate=dict(rank=self.rank,rank_formula='sum squared node-charge multiplicities',
            idempotence_core_error=err,trace_preservation_error=trace_err,
            target=self.target,U_sha256=matrix_hash(self.U),V_sha256=matrix_hash(self.V),
            sector_operator='N_nodes tensor I_edges',edge_charge_constraint='NOT_PRESENT')

    def apply(self, x):
        return np.asarray(self.U@(self.V@x))

    def independent_action(self, x):
        rho=self.space.unpack(x);nodes,_=marginals(rho,self.dimensions)
        return self.space.pack(np.kron(nodes,self.tau))

    def certify_action(self, x, tolerance=1e-10):
        rho=self.space.unpack(x);y=self.apply(x);out=self.space.unpack(y)
        sector=sector_check(self.space,rho,out,tolerance)
        before,_=marginals(rho,self.dimensions);after,_=marginals(out,self.dimensions)
        errors=dict(independent_action=maxabs(y-self.independent_action(x)),
                    node_marginal=maxabs(before-after),trace=float(abs(self.space.trace(y-x))))
        if max(errors.values())>tolerance:raise ArithmeticError('Reset action certificate failed')
        return dict(**errors,**sector,target_sha256=self.target['sha256'],status='PASSED')


def sign_decision(value, uncertainty):
    validate_numbers(value,uncertainty)
    return dict(value=float(value),uncertainty=float(uncertainty),interval=[float(value-uncertainty),float(value+uncertainty)],
                status='SUPPORTED' if value-uncertainty>0 else 'REFUTED' if value+uncertainty<0 else 'UNRESOLVED')


def validate_numbers(value,uncertainty):
    if not np.isfinite([value,uncertainty]).all() or uncertainty<0:raise ValueError('Invalid interval')


def relative_decision(x,ux,y,uy,z,uz,alpha,floor=1e-6):
    for v,u in ((x,ux),(y,uy),(z,uz)):validate_numbers(v,u)
    if not np.isfinite([alpha,floor]).all() or min(alpha,floor)<=0:raise ValueError('Invalid rule')
    guard=max(10*uz,floor);d=abs(x-y);u=ux+uy
    lower=max(0.,d-u);upper=d+u;band_lower=alpha*max(0.,abs(z)-uz);band_upper=alpha*(abs(z)+uz)
    if abs(z)<=guard:status='NOT_ASSESSED_SMALL_SIGNAL'
    elif upper<=band_lower:status='SUPPORTED'
    elif lower>band_upper:status='REFUTED'
    else:status='UNRESOLVED'
    return dict(status=status,difference=float(x-y),uncertainty=float(u),absolute_interval=[lower,upper],
                band_interval=[band_lower,band_upper],guard=guard,alpha=alpha)


def analyze(primary, reference, area, area_uncertainty, gammas=(.001,.002)):
    S=primary['S'];uS=max(1e-10,3*abs(S-reference['S']))
    if uS>1e-6:raise ArithmeticError('Reset derivative uncertainty cap failed')
    sign=sign_decision(S,uS);window=relative_decision(S,uS,area,area_uncertainty,area,area_uncertainty,.20)
    finite=[]
    for gamma in gammas:
        key=str(gamma);p=primary['flux'][key];r=reference['flux'][key]
        delta=p-primary['flux']['0.0'];u=max(1e-10,3*(abs(p-r)+abs(primary['flux']['0.0']-reference['flux']['0.0'])))
        if u>1e-8:raise ArithmeticError('Finite reset uncertainty cap failed')
        q=delta/gamma;uq=u/gamma
        finite.append(dict(gamma=gamma,delta_F=delta,u_delta_F=u,Q=q,u_Q=uq,
                           linearity=relative_decision(q,uq,S,uS,S,uS,.10)))
    pair=relative_decision(finite[1]['Q'],finite[1]['u_Q'],finite[0]['Q'],finite[0]['u_Q'],S,uS,.10)
    statuses=[r['linearity']['status'] for r in finite]+[pair['status']]
    overall=('NOT_ASSESSED_SMALL_SIGNAL' if 'NOT_ASSESSED_SMALL_SIGNAL' in statuses else
             'REFUTED' if 'REFUTED' in statuses else 'SUPPORTED' if all(x=='SUPPORTED' for x in statuses) else 'UNRESOLVED')
    return dict(sign=sign,window=window,finite=finite,linearity_pair=pair,linearity_status=overall,
                tail=sign_decision(S-area,uS+area_uncertainty),
                tail_meaning='SIGNED_AREA_NOT_LIFETIME_OR_SPECTRAL_WIDTH',
                uncertainty_kind='ENGINEERING_SOLVER_AND_BASELINE_SENSITIVITY_NOT_RIGOROUS_BOUND')


def entropy(rho,tolerance=1e-9):
    vals=np.linalg.eigvalsh((rho+rho.conj().T)/2)
    if vals.min() < -tolerance:raise ArithmeticError('Entropy requires PSD input')
    # Only this diagnostic uses the positive part of eigenvalues; state is not altered.
    pos=vals[vals>0]
    return dict(value=float(-np.sum(pos*np.log(pos))),negative_mass=float(-vals[vals<0].sum()),
                convention='NATURAL_LOG_POSITIVE_EIGENVALUES_ONLY_STATE_UNCHANGED')
