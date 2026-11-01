"""Bordered shifted sparse factors + rank-20 Woodbury; independent GMRES/ILU.

Every factor application is counted, including columns, residual corrections,
preconditioner applications and inverse-norm estimation. No eigenspectrum repair.
"""
import time,warnings
import numpy as np
from scipy import sparse as sp
from scipy import linalg
from scipy.sparse.linalg import splu,spilu,LinearOperator,onenormest
from e002e_exp.compat import gmres
from e002_exp.model import maxabs


class Solver:
    def __init__(self,L,space,gamma=0.,reset=None,method='lu',rtol=1e-11,atol=1e-13,
                 ilu_drop_tol=1e-5,ilu_fill_factor=10.,restart=100,maxiter=400):
        self.L=sp.csr_matrix(L);self.space=space;self.gamma=float(gamma);self.reset=reset
        if not np.isfinite(gamma) or gamma<0 or (gamma and reset is None):raise ValueError('Invalid reset solve')
        if method not in ('lu','gmres_ilu'):raise ValueError('Unknown method')
        self.method=method;self.rtol=rtol;self.atol=atol;self.restart=restart;self.maxiter=maxiter
        self.counts=dict(task_solves=0,factor_calls=0,factor_rhs_columns=0,preconditioner_calls=0,
                         residual_corrections=0,gmres_iterations=0,condition_estimates=0)
        self.times=dict(factor_seconds=0.,low_rank_setup_seconds=0.,factor_application_seconds=0.,solve_seconds=0.,condition_seconds=0.)
        n=space.size;r=space.trace_row.T/space.d
        self.base=sp.bmat([[self.L-gamma*sp.eye(n),r],[space.trace_row,None]],format='csc')
        tick=time.perf_counter()
        self.factor=splu(self.base) if method=='lu' else spilu(self.base,drop_tol=ilu_drop_tol,fill_factor=ilu_fill_factor)
        self.times['factor_seconds']=time.perf_counter()-tick
        self.U=sp.csc_matrix((n+1,0));self.V=sp.csr_matrix((0,n+1));self.W=None;self.small=None
        tick=time.perf_counter()
        if gamma:
            self.U=sp.vstack([reset.U,sp.csr_matrix((1,reset.rank))],format='csc')
            self.V=sp.hstack([reset.V,sp.csr_matrix((reset.rank,1))],format='csr')
            self.W=self.factor_apply(self.U.toarray())
            self.small=np.eye(reset.rank)+gamma*(self.V@self.W)
            if not np.isfinite(self.small).all():raise ArithmeticError('Invalid Woodbury core')
            with warnings.catch_warnings():
                warnings.simplefilter('error',linalg.LinAlgWarning)
                self.small_factor=linalg.lu_factor(self.small)
            if not np.isfinite(self.small_factor[0]).all():raise ArithmeticError('Invalid Woodbury factor')
        self.times['low_rank_setup_seconds']=time.perf_counter()-tick
        self.operator=LinearOperator(self.base.shape,matvec=self.apply,matmat=self.apply,dtype=complex)
        self.preconditioner=LinearOperator(self.base.shape,matvec=self.precondition,dtype=complex)

    def factor_apply(self,rhs,trans='N'):
        tick=time.perf_counter();self.counts['factor_calls']+=1
        self.counts['factor_rhs_columns']+=1 if np.ndim(rhs)==1 else rhs.shape[1]
        out=self.factor.solve(np.asarray(rhs,complex),trans=trans)
        self.times['factor_application_seconds']+=time.perf_counter()-tick
        return out

    def inverse(self,rhs,adjoint=False):
        z=self.factor_apply(rhs,'H' if adjoint else 'N')
        if self.gamma:
            if adjoint:
                c=linalg.lu_solve(self.small_factor,self.U.getH()@z,trans=2)
                z-=self.gamma*self.factor_apply(self.V.getH()@c,'H')
            else:
                c=linalg.lu_solve(self.small_factor,self.V@z)
                z-=self.gamma*(self.W@c)
        if not np.isfinite(z).all():raise ArithmeticError('Nonfinite inverse application')
        return z

    def precondition(self,rhs):
        self.counts['preconditioner_calls']+=1
        return self.inverse(rhs)

    def apply(self,x):
        return self.base@x+self.gamma*(self.U@(self.V@x))

    def equation(self,x):
        return self.L@x+(self.gamma*(self.reset.apply(x)-x) if self.gamma else 0)

    def solve(self,b=None,trace=0.):
        b=np.zeros(self.space.size,complex) if b is None else np.asarray(b,complex)
        if b.shape!=(self.space.size,) or not np.isfinite(b).all():raise ValueError('Invalid RHS')
        if abs(self.space.trace(b))>1e-11:raise ValueError('RHS is not traceless')
        rhs=np.r_[b,trace];tick=time.perf_counter();self.counts['task_solves']+=1
        if self.method=='lu':
            x=self.inverse(rhs)
            for _ in range(2):
                x+=self.inverse(rhs-self.apply(x));self.counts['residual_corrections']+=1
        else:
            def count(_):self.counts['gmres_iterations']+=1
            x,info=gmres(self.operator,rhs,M=self.preconditioner,rtol=self.rtol,atol=self.atol,
                         restart=self.restart,maxiter=self.maxiter,callback=count,callback_type='pr_norm')
            if info!=0:raise ArithmeticError('Reset GMRES did not converge: '+str(info))
        self.times['solve_seconds']+=time.perf_counter()-tick
        residual=self.equation(x[:-1])-b;bnorm=float(np.linalg.norm(b));rnorm=float(np.linalg.norm(residual))
        checks=dict(absolute_inf=maxabs(residual),absolute_2=rnorm,
                    relative_true=None if bnorm==0 else rnorm/bnorm,
                    relative_true_status='ZERO_RHS' if bnorm==0 else 'DEFINED',
                    relative_normalized=rnorm/max(bnorm,1.),trace_error=float(abs(self.space.trace(x[:-1])-trace)),
                    border_multiplier=float(abs(x[-1])))
        if (not np.isfinite(x).all() or max(checks['absolute_inf'],checks['trace_error'],checks['border_multiplier'])>1e-9):
            raise ArithmeticError('Original reset equation/trace failed: '+str(checks))
        return x[:-1],checks

    def condition_estimate(self):
        if self.method!='lu':return dict(value=None,status='NOT_ESTIMATED_FOR_ILU')
        tick=time.perf_counter();self.counts['condition_estimates']+=1
        inverse=LinearOperator(self.base.shape,matvec=self.inverse,
            rmatvec=lambda x:self.inverse(x,adjoint=True),matmat=self.inverse,dtype=complex)
        # Forming rank-20 update for a norm is cheap; it is never factorized.
        matrix=self.base+self.gamma*(self.U@self.V)
        value=float(sp.linalg.norm(matrix,1)*onenormest(inverse))
        self.times['condition_seconds']+=time.perf_counter()-tick
        if not np.isfinite(value):raise ArithmeticError('Nonfinite condition diagnostic')
        return dict(value=value,status='ONE_NORM_ESTIMATE_NOT_RIGOROUS_BOUND')

    def metrics(self):
        factor_bytes=sum(a.data.nbytes+a.indices.nbytes+a.indptr.nbytes for a in (self.factor.L,self.factor.U))
        return dict(method=self.method,gamma=self.gamma,base_nnz=int(self.base.nnz),
                    factor_nnz=int(self.factor.L.nnz+self.factor.U.nnz),factor_storage_bytes=int(factor_bytes),
                    woodbury_rank=0 if self.reset is None or not self.gamma else self.reset.rank,
                    low_rank_dense_bytes=0 if self.W is None else self.W.nbytes,
                    counts=dict(self.counts),timing=dict(self.times),
                    timing_note='Factor-application time is a subcomponent; do not add twice.')
