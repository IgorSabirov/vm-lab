"""Static responses, source modulation, QRT and explicit Fano candidates."""
import time
import numpy as np
from scipy import sparse as sp
from scipy.sparse.linalg import splu, gmres, LinearOperator
from e002_exp.model import maxabs
from .space import dissipator_action
from .model import selective_difference
from .numerics import Bordered, FLOOR, values


def response_outputs(model, state, x):
    vals = values(model, x); base = values(model, state)
    if 'P_m6_N2' in vals:
        p = base['P_m6_N2'].real; h = base['h6'].real
        vals['j6'] = None if p <= FLOOR else (vals['h6']-(h/p)*vals['P_m6_N2'])/p
    return vals


def static_response(model, state, target, prepared):
    V = selective_difference(model['space'], target)
    x, checks = prepared.solve(-(V@state))
    return x, response_outputs(model, state, x), checks


def source_input(model, state):
    # The jump already includes sqrt(kappa_in); D[C] = kappa_in D[sigma+].
    C = dict(model['jumps'])['source_0']
    return model['space'].pack(dissipator_action(C, model['space'].unpack(state)))


def frequency_response(model, state, omega, prepared_zero=None, **solver_options):
    b = source_input(model, state)
    solver = prepared_zero if omega == 0 and prepared_zero is not None else Bordered(model['L'], model['space'], z=1j*omega, **solver_options)
    x, checks = solver.solve(-b if omega == 0 else b)
    return x, response_outputs(model, state, x), checks, solver.metrics()


def qrt_inputs(model, state, names=('J_h', 'P_m6_N2', 'K')):
    space = model['space']; rho = space.unpack(state); base = values(model, state)
    inputs = []; variances = []
    for name in names:
        B = model['observables'][name]; mean = base[name]
        if abs(mean.imag) > 1e-10:
            raise ArithmeticError('Hermitian mean is complex')
        y = space.pack(B@rho-mean*rho)
        if abs(space.trace(y)) > 1e-10:
            raise ArithmeticError('QRT input trace failed')
        var = complex(space.row(B@B)@state-mean**2)
        if abs(var.imag) > 1e-10 or var.real < -1e-10:
            raise ArithmeticError('Invalid variance')
        inputs.append(y); variances.append(max(0., var.real))
    return np.column_stack(inputs), np.array(variances)


def propagate_qrt(model, state, horizon, dt, sample_interval, names=('J_h', 'P_m6_N2', 'K'), checkpoint=None):
    if min(horizon, dt, sample_interval) <= 0:
        raise ValueError('Invalid QRT grid')
    steps = round(horizon/dt); stride = round(sample_interval/dt)
    if stride < 1 or abs(steps*dt-horizon) > 1e-9 or abs(stride*dt-sample_interval) > 1e-9 or steps % stride:
        raise ValueError('QRT grid must have integral steps and common final sample')
    y, var = qrt_inputs(model, state, names); L = model['L']; space = model['space']
    rows = np.vstack([space.row(model['observables'][name]) for name in names])
    times = [0.]; out = [rows@y]; trace_max = maxabs(space.trace(y)); start = time.perf_counter()
    for step in range(1, steps+1):
        a = L@y; b = L@(y+dt*a/2); c = L@(y+dt*b/2); d = L@(y+dt*c)
        y += dt*(a+2*b+2*c+d)/6
        if step % stride == 0:
            if not np.isfinite(y).all():
                raise ArithmeticError('QRT became nonfinite')
            t = step*dt; times.append(t); out.append(rows@y)
            trace_max = max(trace_max, maxabs(space.trace(y)))
            if checkpoint:
                checkpoint(step, t, y)
    if trace_max > 1e-8:
        raise ArithmeticError('QRT trace drift: '+str(trace_max))
    times = np.array(times); out = np.array(out); normalized = np.full_like(out, np.nan)
    den = np.sqrt(var[:, None]*var[None, :]); valid = den > FLOOR
    normalized[:, valid] = out[:, valid]/den[valid]
    integral = np.trapezoid(abs(out.diagonal(axis1=1, axis2=2)), times, axis=0)
    tau = [float(a/v) if v > FLOOR else None for a, v in zip(integral, var)]
    late = out[int(.8*len(out)):]
    summary = dict(steps=steps, block_rhs_calls=4*steps, scalar_rhs_equivalents=4*steps*len(names),
                   inputs=len(names), outputs_per_input=len(names), samples=len(times), trace_max=trace_max,
                   elapsed_seconds=time.perf_counter()-start, variances=var.tolist(), tau_int_truncated=tau,
                   late_window_abs_max=float(abs(late).max()), tail_status='TAIL_UNRESOLVED',
                   infinite_integral=None, input_convention='(B-mean_B)rho; ordered connected QRT',
                   positivity_test_applied=False)
    return dict(times=times, C=out, normalized=normalized, normalization_valid=valid, summary=summary, final=y)


def compare_qrt(fine, coarse, atol, rtol):
    if not np.array_equal(fine['times'], coarse['times']):
        raise ValueError('QRT comparison grids differ')
    err = abs(fine['C']-coarse['C']); scale = atol+rtol*np.maximum(abs(fine['C']), abs(coarse['C']))
    return dict(pass_gate=bool(np.all(err <= scale)), max_abs=float(err.max()),
                max_scaled=float((err/scale).max()), uncertainty_kind='EMPIRICAL_DT_DIFFERENCE_NOT_RIGOROUS_BOUND')


def schur_response(L, b, row, target, z, rtol=1e-10, maxiter=300):
    """Complete T/B partition; matrix-free Schur complement, no dense inverse.

    This candidate decomposition alone cannot certify Fano. z=0 is deliberately
    rejected here: stationary constraints need the separately validated border.
    """
    if z == 0:
        raise ValueError('Schur candidate at z=0 requires a separately declared constrained partition')
    L = sp.csr_matrix(L); n = L.shape[0]; target = np.asarray(target, dtype=int)
    if target.ndim != 1 or len(np.unique(target)) != len(target) or not 0 < len(target) < n or min(target) < 0 or max(target) >= n:
        raise ValueError('Invalid Schur partition')
    other = np.setdiff1d(np.arange(n), target); A = z*sp.eye(n, format='csr')-L
    tt = A[target][:, target]; tb = A[target][:, other]; bt = A[other][:, target]; bb = A[other][:, other]
    factor = splu(bb.tocsc()); rb_b = factor.solve(np.asarray(b)[other])
    eff = LinearOperator(tt.shape, matvec=lambda x: tt@x-tb@factor.solve(bt@x), dtype=complex)
    rhs = np.asarray(b)[target]-tb@rb_b
    xt, info = gmres(eff, rhs, rtol=rtol, atol=rtol*1e-2, maxiter=maxiter)
    if info:
        raise ArithmeticError('Schur GMRES did not converge')
    xb = factor.solve(np.asarray(b)[other]-bt@xt)
    x = np.empty(n, complex); x[target] = xt; x[other] = xb
    err = maxabs(A@x-b)
    if err > 10*rtol*max(1., np.linalg.norm(b)):
        raise ArithmeticError('Schur reconstruction residual failed')
    row = np.asarray(row); bg = complex(row[other]@rb_b)
    mediated = complex(row[target]@xt-row[other]@factor.solve(bt@xt))
    total = complex(row@x)
    return dict(x=x, background=bg, mediated=mediated, total=total,
                cross_intensity=float(2*np.real(bg.conjugate()*mediated)), reconstruction_error=float(abs(total-bg-mediated)),
                equation_residual=err, target_size=len(target), complement_size=len(other),
                interpretation='CANDIDATE_DECOMPOSITION_REQUIRES_PHYSICAL_PARTITION_AND_HELDOUT_CHECKS')


def g0(epsilon, v, J=1., kappa_left=.5, kappa_right=.5):
    A = J*J+kappa_left*kappa_right/4; width = kappa_left*v*v/(2*A)
    bg = -J*np.sqrt(kappa_left*kappa_right)/A
    if v == 0:
        amplitude, resonance = complex(bg), 0j
    else:
        amplitude = bg*epsilon/(epsilon-1j*width); resonance = amplitude-bg
    return dict(amplitude=amplitude, background=complex(bg), resonance=resonance,
                intensity=float(abs(amplitude)**2), width=width,
                cross=float(2*np.real(complex(bg).conjugate()*resonance)))
