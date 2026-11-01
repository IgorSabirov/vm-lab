"""Fixed-marginal preparation, finite-window propagation and interval decisions.

No projection, clipping, renormalization, inferred infinite tail or Fano label.
The replacement channel has a fixed prepared edge state for each baseline.
"""
import hashlib
import time
import numpy as np
from e002_exp.model import maxabs
from e002e_exp.compat import trapezoid
from e002e_exp.numerics import ratio


def marginals(rho, dimensions):
    a, b = dimensions
    rho = np.asarray(rho, complex)
    if rho.shape != (a*b, a*b) or not np.isfinite(rho).all():
        raise ValueError('Invalid bipartite density matrix')
    tensor = rho.reshape(a, b, a, b)
    return np.trace(tensor, axis1=1, axis2=3), np.trace(tensor, axis1=0, axis2=2)


def replacement(rho, edge_reference, dimensions):
    """Linear CPTP only for a FIXED edge_reference.

    prepare chooses a target from its known baseline; the overall map from an
    arbitrary unknown baseline to its two marginals is not a universal channel.
    """
    nodes, _ = marginals(rho, dimensions)
    b = dimensions[1]
    edge_reference = np.asarray(edge_reference, complex)
    if (edge_reference.shape != (b, b) or not np.isfinite(edge_reference).all()
            or maxabs(edge_reference-edge_reference.conj().T) > 1e-10
            or abs(np.trace(edge_reference)-1) > 1e-10
            or np.linalg.eigvalsh(edge_reference).min() < -1e-10):
        raise ValueError('Invalid fixed reference state')
    return np.kron(nodes, edge_reference)


def physicality(space, state, tolerance):
    if not np.isfinite(state).all():
        raise ArithmeticError('Density matrix is nonfinite')
    rho = space.unpack(state)
    herm = maxabs(rho-rho.conj().T)
    minimum = float(np.linalg.eigvalsh((rho+rho.conj().T)/2).min())
    check = dict(trace_error=float(abs(space.trace(state)-1)), hermiticity=herm,
                 minimum_eigenvalue=minimum, psd_mode='FULL_HILBERT')
    if (not np.isfinite(state).all() or check['trace_error'] > tolerance
            or herm > tolerance or minimum < -tolerance):
        raise ArithmeticError('Density matrix physicality failed: '+str(check))
    return check


def array_hash(a):
    a = np.ascontiguousarray(a, dtype='<c16')
    return hashlib.sha256(str(a.shape).encode()+b'\0'+a.tobytes()).hexdigest()


def sector_check(space, rho, product, tolerance):
    """Certify this builder's complete q=0 block algebra, with no projection.

    The 216-state model has Q=N_nodes tensor I_edges. For [rho,Q]=0,
    [Tr_edges(rho),N_nodes]=0, hence [rho_nodes tensor rho_edges,Q]=0.
    No per-edge superselection rule from an older 512-state model is assumed.
    """
    joined = np.concatenate(space.groups)
    if not np.array_equal(np.sort(joined), np.arange(space.d)):
        raise ValueError('Charge groups do not partition full Hilbert space')
    outside = space.charges[:, None] != space.charges[None, :]
    errors = dict(input_off_sector=maxabs(np.where(outside, rho, 0)),
                  product_off_sector=maxabs(np.where(outside, product, 0)),
                  input_roundtrip=maxabs(space.unpack(space.pack(rho))-rho),
                  product_roundtrip=maxabs(space.unpack(space.pack(product))-product))
    if max(errors.values()) > tolerance:
        raise ArithmeticError('Preparation violates q=0 sector/roundtrip')
    return errors


def prepare(model, state, dimensions=(8, 27), tolerance=1e-10):
    space = model['space']; rho = space.unpack(state)
    before = physicality(space, state, tolerance)
    nodes, edges = marginals(rho, dimensions)
    product = replacement(rho, edges, dimensions)
    sector = sector_check(space, rho, product, tolerance)
    cut = space.pack(product)
    after = physicality(space, cut, tolerance)
    # Verify the actual packed/unpacked state, not just the formal kron target.
    new_nodes, new_edges = marginals(space.unpack(cut), dimensions)
    errors = dict(nodes=maxabs(nodes-new_nodes), edges=maxabs(edges-new_edges))
    if max(errors.values()) > tolerance:
        raise ArithmeticError('Preparation changed a marginal')
    change = space.unpack(cut)-rho
    distance = .5*float(np.abs(np.linalg.eigvalsh((change+change.conj().T)/2)).sum())
    record = dict(marginal_errors=errors, sector_errors=sector,
                  sector_contract='COMPLETE_Q0_CHARGE_BLOCKS_NO_PROJECTION',
                  preparation_type='PRODUCT_OF_KNOWN_BASELINE_MARGINALS_FIXED_TARGET',
                  universal_cptp_channel=False,
                  hashes={n:array_hash(a) for n,a in (('state',state),('cut',cut),('nodes',nodes),('edges',edges))},
                  marginal_spectra=dict(nodes=np.linalg.eigvalsh((nodes+nodes.conj().T)/2).tolist(),
                                        edges=np.linalg.eigvalsh((edges+edges.conj().T)/2).tolist()),
                  sham_physicality=before, cut_physicality=after,
                  trace_distance=distance, frobenius_distance=float(np.linalg.norm(change)),
                  delta_energy=float(np.trace(model['H']@change).real),
                  external_preparation_cost='NOT_ASSUMED_ZERO_NOT_MEASURED',
                  removed_correlations='ALL_NODE_EDGE_CORRELATIONS_NOT_ONLY_ENTANGLEMENT')
    return np.column_stack((state, cut)), record


def grid_steps(horizon, dt, interval):
    if not np.isfinite([horizon, dt, interval]).all() or min(horizon, dt, interval) <= 0:
        raise ValueError('Invalid finite time grid')
    n, stride = round(horizon/dt), round(interval/dt)
    if n < 1 or stride < 1 or abs(n*dt-horizon) > 1e-10 or abs(stride*dt-interval) > 1e-10 or n % stride:
        raise ValueError('Grid must contain exact integral steps and endpoint')
    return n, stride


def propagate(model, initial, *, horizon, dt, sample_interval, physicality_interval,
              tolerance=1e-9, checkpoint=None, density_checks=True):
    """Two density columns (sham/cut), RK4; retain flux at EVERY step.

    Other observables are retained on the declared common grid. Physicality
    is checked at the declared checkpoints, not claimed between checkpoints.
    density_checks=False is reserved for synthetic calibration vectors.
    """
    steps, stride = grid_steps(horizon, dt, sample_interval)
    _, check_stride = grid_steps(horizon, dt, physicality_interval)
    space = model['space']; L = model['L']; y = np.asarray(initial, complex).copy()
    if y.shape != (space.size, 2) or not np.isfinite(y).all():
        raise ValueError('Expected two finite state columns')
    names = tuple(model['observables']); rows = np.vstack([space.row(model['observables'][n]) for n in names])
    frow = space.row(model['observables']['F'])
    times = np.arange(steps+1)*dt; flux = np.empty((steps+1, 2))
    output = []; checks = []; trace0 = space.trace(y)
    start = time.perf_counter()
    for step in range(steps+1):
        if step:
            a = L@y; b = L@(y+dt*a/2); c = L@(y+dt*b/2); d = L@(y+dt*c)
            y += dt*(a+2*b+2*c+d)/6
        f = frow@y
        if not np.isfinite(y).all() or maxabs(f.imag) > tolerance:
            raise ArithmeticError('Evolution is nonfinite or flux is complex')
        flux[step] = f.real
        if step % stride == 0:
            output.append(rows@y)
        if step % check_stride == 0:
            if maxabs(space.trace(y)-trace0) > tolerance:
                raise ArithmeticError('Evolution trace drift')
            if density_checks:
                checks.append(dict(time=float(times[step]), states=[physicality(space, y[:, k], tolerance) for k in range(2)]))
            if checkpoint:
                checkpoint(step, float(times[step]), y)
    return dict(time=times, flux=flux, sample_time=times[::stride], raw=np.asarray(output), names=names,
                time_index=np.arange(steps+1), sample_index=np.arange(steps+1)[::stride], dt=float(dt),
                final=y, checks=checks, steps=steps, checkpoint_calls=steps//check_stride+1,
                block_rhs_calls=4*steps,
                scalar_rhs_equivalents=8*steps, elapsed_seconds=time.perf_counter()-start)


def threshold_decision(value, uncertainty, threshold):
    if (not np.isfinite([value, uncertainty, threshold]).all()
            or value < 0 or uncertainty < 0 or threshold <= 0):
        raise ValueError('Invalid nonnegative interval')
    lo, hi = max(0., value-uncertainty), value+uncertainty
    status = ('MARGINAL_SUFFICIENCY_REJECTED_AT_DECLARED_RESOLUTION' if lo > threshold else
              'MARGINAL_SUFFICIENCY_NOT_REJECTED_IN_WINDOW' if hi < threshold else 'UNRESOLVED')
    return dict(value=value, uncertainty=uncertainty, interval=[lo, hi], threshold=threshold, status=status)


def analyze(fine, coarse, reference, *, baseline_flux, reference_flux, policy):
    for run in (fine, coarse, reference):
        if not np.isfinite(run['flux']).all():
            raise ValueError('Nonfinite trajectory')
    def same_grid(a,b):
        return a.shape == b.shape and np.allclose(a,b,rtol=0.,atol=1e-12)
    if (not same_grid(fine['time'], reference['time'])
            or not same_grid(fine['sample_time'], coarse['sample_time'])
            or not same_grid(fine['sample_time'], reference['sample_time'])
            or fine['names'] != coarse['names'] or fine['names'] != reference['names']):
        raise ValueError('Comparison grids or observables differ')
    if abs(fine['time'][-1]-coarse['time'][-1]) > 1e-12:
        raise ValueError('Comparison horizons differ')
    if baseline_flux <= 1e-6 or reference_flux <= 1e-6:
        raise ValueError('Unresolved normalization flux')
    # Fixed numerical caps are independent of the scientific threshold.
    comparisons = {}
    for name, other in (('dt', coarse), ('initial_condition_and_solver_sensitivity', reference)):
        err = abs(fine['raw']-other['raw'])
        scale = policy['raw_absolute_tolerance']+policy['raw_relative_tolerance']*np.maximum(abs(fine['raw']), abs(other['raw']))
        comparisons[name] = dict(max_abs=float(err.max()), max_scaled=float((err/scale).max()), passed=bool(np.all(err <= scale)))
    if not all(x['passed'] for x in comparisons.values()):
        raise ArithmeticError('Trajectory refinement failed: '+str(comparisons))
    t = fine['time']; H = float(t[-1]); delta = fine['flux'][:, 1]-fine['flux'][:, 0]
    dc = coarse['flux'][:, 1]-coarse['flux'][:, 0]; dr = reference['flux'][:, 1]-reference['flux'][:, 0]
    u = policy['absolute_floor']+policy['safety']*(abs(delta-np.interp(t, coarse['time'], dc))+abs(delta-dr))
    area = float(trapezoid(abs(delta), t)); u_area = float(trapezoid(u, t))
    uf = policy['absolute_floor']+policy['safety']*abs(baseline_flux-reference_flux)
    R = ratio(area, H*baseline_flux, u_area, H*uf)
    if R['value'] is None or R['uncertainty'] is None or R['uncertainty'] > policy['maximum_metric_uncertainty']:
        raise ArithmeticError('Primary uncertainty is unresolved or exceeds fixed cap')
    verdict = threshold_decision(R['value'], R['uncertainty'], policy['primary_threshold'])
    raw_error = policy['absolute_floor']+policy['safety']*(abs(fine['raw']-coarse['raw'])+abs(fine['raw']-reference['raw']))
    h = fine['names'].index('h6'); p = fine['names'].index('P_m6_N2')
    conditional = []
    for i, ti in enumerate(fine['sample_time']):
        row = []
        for k in range(2):
            hh, pp = fine['raw'][i, h, k], fine['raw'][i, p, k]
            if max(abs(hh.imag), abs(pp.imag)) > policy['raw_absolute_tolerance']:
                raise ArithmeticError('Conditional primitive is complex')
            row.append(ratio(float(hh.real), float(pp.real), float(raw_error[i, h, k]), float(raw_error[i, p, k])))
        conditional.append(dict(time=float(ti), sham=row[0], cut=row[1]))
    peak = int(np.argmax(abs(delta)))
    sham_drift = float(np.max(abs(fine['flux'][:, 0]-baseline_flux)))
    reference_sham_drift = float(np.max(abs(reference['flux'][:,0]-reference_flux)))
    coarse_sham_drift = float(np.max(abs(coarse['flux'][:,0]-baseline_flux)))
    if max(sham_drift, reference_sham_drift, coarse_sham_drift) > policy['maximum_sham_drift']:
        raise ArithmeticError('Sham stationary drift exceeds fixed cap')
    return dict(primary=verdict, area_absolute=area, area_uncertainty=u_area,
                signed_area=float(trapezoid(delta, t)), peak_relative=float(abs(delta[peak])/baseline_flux),
                time_peak=float(t[peak]), final_delta_flux=float(delta[-1]), sham_drift=sham_drift,
                reference_sham_drift=reference_sham_drift, coarse_sham_drift=coarse_sham_drift,
                refinement=comparisons,
                uncertainty_kind='ENGINEERING_DT_AND_INITIAL_CONDITION_SOLVER_SENSITIVITY_NOT_RIGOROUS_TOTAL_BOUND',
                tail_status='FINITE_WINDOW_ONLY', conditional=conditional, raw_uncertainty=raw_error)
