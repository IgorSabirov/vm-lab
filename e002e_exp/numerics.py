"""Bordered sparse solves; state and response checks deliberately differ."""
import time
import numpy as np
from scipy import sparse as sp
from scipy.sparse.linalg import splu, spilu, gmres, LinearOperator, onenormest
from e002_exp.model import maxabs

FLOOR = 1e-6


def refinement_check(primary, reference, values_primary, values_reference, limits):
    """Calibrated engineering acceptance thresholds; not a rigorous error bound."""
    state_difference = maxabs(np.asarray(primary)-np.asarray(reference))
    errors = {name: float(abs(value-values_reference[name])) for name, value in values_primary.items()
              if value is not None and values_reference.get(name) is not None}
    failed = [name for name, error in errors.items() if error > limits['observable_absolute']+
              limits['observable_relative']*max(abs(values_primary[name]), abs(values_reference[name]))]
    passed = state_difference <= limits['vector_inf'] and not failed
    return dict(pass_gate=bool(passed), vector_difference_inf=state_difference, observable_differences=errors,
                failed_observables=failed, limits=limits, status='PASS' if passed else 'NUMERICALLY_UNRESOLVED')


def residual(A, x, b):
    r = A@x-b
    return dict(absolute_inf=maxabs(r), relative_2=float(np.linalg.norm(r)/max(np.linalg.norm(b), 1.)))


class Bordered:
    def __init__(self, L, space, z=0j, method='lu', rtol=1e-11, atol=1e-13,
                 maxiter=400, restart=100, ilu_drop_tol=1e-5, ilu_fill_factor=10.):
        self.space = space; self.L = sp.csr_matrix(L); self.z = complex(z)
        self.A = self.L if z == 0 else (z*sp.eye(space.size, format='csr')-self.L)
        r = space.trace_row.T/space.d
        self.matrix = sp.bmat([[self.A, r], [space.trace_row, None]], format='csc')
        self.rtol, self.atol, self.maxiter, self.restart = rtol, atol, maxiter, restart
        self.method = method; self.factor = None; self.preconditioner = None
        self.iterations = 0; self.solves = 0; self.solve_seconds = 0.
        start = time.perf_counter()
        if method == 'lu':
            self.factor = splu(self.matrix)
        elif method == 'gmres_ilu':
            self.factor = spilu(self.matrix, drop_tol=ilu_drop_tol, fill_factor=ilu_fill_factor)
            self.preconditioner = LinearOperator(self.matrix.shape, matvec=self.factor.solve, dtype=complex)
        else:
            raise ValueError('Unsupported solver')
        self.factor_seconds = time.perf_counter()-start
        self.factor_nnz = int(self.factor.L.nnz+self.factor.U.nnz)
        self.factor_storage_bytes = int(sum(a.data.nbytes+a.indices.nbytes+a.indptr.nbytes for a in (self.factor.L, self.factor.U)))

    def solve(self, b=None, trace=0.):
        b = np.zeros(self.space.size, complex) if b is None else np.asarray(b, complex)
        if b.shape != (self.space.size,) or not np.isfinite(b).all():
            raise ValueError('Invalid RHS')
        if abs(self.space.trace(b)) > max(1e-11, 10*self.atol):
            raise ValueError('RHS must have zero trace')
        if self.z != 0 and trace != 0:
            raise ValueError('Nonzero frequency expects traceless response')
        rhs = np.r_[b, trace]; start = time.perf_counter(); iterations = 0
        if self.method == 'lu':
            x = self.factor.solve(rhs)
            # Residual correction, never a state projection or renormalization.
            for _ in range(2):
                correction = self.factor.solve(rhs-self.matrix@x)
                x += correction
        else:
            def count(_):
                nonlocal iterations
                iterations += 1
            x, info = gmres(self.matrix, rhs, M=self.preconditioner, rtol=self.rtol,
                            atol=self.atol, maxiter=self.maxiter, restart=self.restart,
                            callback=count, callback_type='pr_norm')
            if info != 0:
                raise ArithmeticError('GMRES did not converge: '+str(info))
        self.solve_seconds += time.perf_counter()-start; self.solves += 1; self.iterations += iterations
        checks = residual(self.A, x[:-1], b)
        checks.update(trace_error=float(abs(self.space.trace(x[:-1])-trace)), border_multiplier=float(abs(x[-1])), iterations=iterations)
        limit = max(10*self.atol, 10*self.rtol*max(1., np.linalg.norm(b)))
        if not np.isfinite(x).all() or max(checks['absolute_inf'], checks['trace_error'], checks['border_multiplier']) > limit:
            raise ArithmeticError('Original equation/trace residual failed: '+str(checks))
        return x[:-1], checks

    def condition_estimate(self):
        if self.method != 'lu':
            return dict(value=None, status='NOT_ESTIMATED_FOR_ITERATIVE_SOLVER')
        inverse = LinearOperator(self.matrix.shape, matvec=self.factor.solve,
                                 rmatvec=lambda x: self.factor.solve(x, trans='H'), dtype=complex)
        estimate = float(sp.linalg.norm(self.matrix, 1)*onenormest(inverse))
        return dict(value=estimate, status='ONE_NORM_ESTIMATE_NOT_RIGOROUS_ERROR_BOUND')

    def metrics(self):
        return dict(method=self.method, matrix_nnz=int(self.matrix.nnz), factor_nnz=self.factor_nnz,
                    factor_storage_bytes=self.factor_storage_bytes, factor_seconds=self.factor_seconds,
                    solves=self.solves, solve_seconds=self.solve_seconds, iterations=self.iterations)


def state_checks(L, space, x, tolerance=1e-10):
    rho = space.unpack(x)
    eigmin = min(float(np.linalg.eigvalsh((rho[np.ix_(g, g)]+rho[np.ix_(g, g)].conj().T)/2).min()) for g in space.groups)
    result = dict(trace_error=float(abs(space.trace(x)-1)), hermiticity=maxabs(rho-rho.conj().T),
                  minimum_eigenvalue=eigmin, Lrho_inf=maxabs(L@x), Lrho_2=float(np.linalg.norm(L@x)))
    result['pass'] = bool(result['trace_error'] <= tolerance and result['hermiticity'] <= tolerance
                          and eigmin >= -tolerance and result['Lrho_inf'] <= tolerance)
    return result


def values(model, vector):
    return {name: complex(model['space'].row(op)@vector) for name, op in model['observables'].items()}


def ratio(h, p, uh=None, up=None):
    if not np.isfinite([h, p]).all() or p <= FLOOR:
        return dict(value=None, uncertainty=None, status='SMALL_DENOMINATOR')
    j = h/p
    if uh is None or up is None:
        return dict(value=float(j), uncertainty=None, status='ERROR_UNRESOLVED')
    if min(uh, up) < 0 or not np.isfinite([uh, up]).all():
        raise ValueError('Invalid error estimates')
    if p-up <= FLOOR:
        return dict(value=None, uncertainty=None, status='DENOMINATOR_UNRESOLVED')
    return dict(value=float(j), uncertainty=float((uh+abs(j)*up)/(p-up)), status='PROPAGATED_ESTIMATE')


def contrast(left, center, right, delta):
    if delta <= 0:
        raise ValueError('delta must be positive')
    if any(x['value'] is None for x in (left, center, right)):
        return dict(D=None, d=None, curvature=None, uncertainty_D=None, status='UNDEFINED')
    D = center['value']-(left['value']+right['value'])/2
    u = None if any(x['uncertainty'] is None for x in (left, center, right)) else center['uncertainty']+(left['uncertainty']+right['uncertainty'])/2
    return dict(D=float(D), d=None if abs(center['value']) <= FLOOR else float(-D/center['value']),
                curvature=float(-2*D/delta**2), uncertainty_D=u,
                center_below_both=bool(center['value'] < min(left['value'], right['value'])),
                status='ERROR_UNRESOLVED' if u is None else 'PROPAGATED_ESTIMATE')
