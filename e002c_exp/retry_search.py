"""Bounded IC-1 search; six structural targets only, audited coordinate coverage."""
import numpy as np
import scipy
from scipy.optimize import least_squares

LOW, HIGH = 1e-4, 2.
FACTORS = (.25, 1., 4.)
MAX_CALLS_PER_START = 47  # 7 star points + <=10*(1+3) residual/Jacobian calls


def search(evaluate, target, seed):
    target = np.asarray(target, float)
    if target.shape != (6,) or np.any(target <= 0):
        raise ValueError('Exactly six positive structural targets required')
    cache, records, starts = {}, [], []
    computations = 0
    bounds = np.log([LOW, HIGH])
    for factor in FACTORS:
        calls = 0
        phase = 'star'

        def residual(x):
            nonlocal calls, computations
            if calls >= MAX_CALLS_PER_START:
                raise RuntimeError('IC retry callback budget exceeded')
            calls += 1
            alpha = np.clip(np.exp(x), LOW, HIGH)
            key = tuple(alpha)
            cached = key in cache
            if not cached:
                computations += 1
                values, valid, reason = evaluate(alpha, computations)
                values = np.asarray(values, float)
                if values.shape != (6,):
                    raise ValueError('Objective accepts six structural fields, never hop')
                err = (values-target)/target
                valid = bool(valid and np.isfinite(err).all())
                cache[key] = dict(alpha=alpha.tolist(), values=values.tolist() if np.isfinite(values).all() else None,
                    valid=valid, reason=reason, residual=err.tolist() if valid else [1000.]*6,
                    maximum_error=float(max(abs(err))) if valid else None,
                    objective=float(err@err) if valid else 6e6, computation=computations)
            r = cache[key]
            records.append(dict(r, call=len(records)+1, start_factor=factor, phase=phase, cache_hit=cached))
            return np.asarray(r['residual'])

        center = np.log(np.clip(np.asarray(seed)*factor, LOW, HIGH))
        residual(center)
        for axis in range(3):
            for direction in (-1., 1.):
                point = center.copy()
                point[axis] = np.clip(point[axis]+direction*np.log(2.), *bounds)
                residual(point)
        star = records[-7:]
        valid = [r for r in star if r['valid']]
        outcome = dict(success=False, status=None, message='No valid star point; optimizer skipped', nfev=0, njev=0)
        if valid:
            best = min(valid, key=lambda r: (r['maximum_error'], r['objective'], tuple(r['alpha'])))
            phase = 'optimizer'
            opt = least_squares(residual, np.log(best['alpha']), bounds=(np.full(3,bounds[0]), np.full(3,bounds[1])),
                method='trf', jac='2-point', diff_step=1e-3, max_nfev=10, ftol=1e-5, xtol=1e-5, gtol=1e-5)
            outcome = dict(success=bool(opt.success), status=int(opt.status), message=str(opt.message),
                nfev=int(opt.nfev), njev=int(opt.njev), optimality=float(opt.optimality), cost=float(opt.cost),
                x_log_alpha=opt.x.tolist(), active_mask=opt.active_mask.tolist())
        rows = [r for r in records if r['start_factor']==factor]
        coverage = [dict(axis=i, distinct=len({r['alpha'][i] for r in rows}),
            minimum=min(r['alpha'][i] for r in rows), maximum=max(r['alpha'][i] for r in rows),
            star_distinct=len({r['alpha'][i] for r in star})) for i in range(3)]
        if any(c['star_distinct'] < 2 for c in coverage):
            raise ValueError('Declared three-coordinate star coverage missing')
        starts.append(dict(factor=factor, calls=calls, coverage=coverage, optimizer=outcome))
    feasible = [r for r in cache.values() if r['valid']]
    selected = min(feasible, key=lambda r:(r['maximum_error'],r['objective'],tuple(r['alpha']))) if feasible else None
    return dict(records=records, starts=starts, selected=selected, calls=len(records), computations=computations,
        cache_hits=sum(r['cache_hit'] for r in records), scipy_version=scipy.__version__,
        bounds=[LOW,HIGH], hop_in_objective=False, coverage_pass=True,
        selection_fields=['maximum_error','objective','alpha_lexicographic'],
        limitation='Finite multi-start local search with explicit coordinate coverage; no global exclusion theorem.')
