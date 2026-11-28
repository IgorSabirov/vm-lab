"""R136.1 sensitivity audit. Run with the 2021 v2 and 2016 v1 arXiv source tarballs."""
import argparse
import itertools
import json
import re
from pathlib import Path

import numpy as np
from numpy.polynomial import Polynomial
from scipy.optimize import brentq

from extract import digitize, read_figure
from verify import BETA, HERE, jump_curve, run


def eps_axis_budget(eps, data, calibration, roots):
    ticks = re.findall(r'^(\d+) 704 M\n\[ \[\(Helvetica\).*?\(\s*([-\d.]+)\)\]', eps, re.M)
    pixels, labels = np.array(ticks, dtype=float).T
    assert len(pixels) == 7
    axis = Polynomial.fit(pixels, labels, 1)
    x_step = axis.deriv()(0)
    # Recover original integer EPS marker positions from the 9-decimal extraction.
    series = []
    for v, root in zip(BETA, roots):
        phases = []
        for name in ('hot', 'cold'):
            x, y, _ = np.array(data[v]['fig15_x_q_error'][name]).T
            positions = np.rint((x - axis(0)) / x_step)
            assert np.allclose(axis(positions), x, rtol=0, atol=5.1e-10)
            right = np.searchsorted(x, root)
            phases.append((positions[right-1:right+1], y[right-1:right+1]))
        series.append(phases)

    def rematch(transform, shifts):
        matched = []
        for v, phases, offsets in zip(BETA, series, shifts):
            lines = [(transform(p + offset), y) for (p, y), offset in zip(phases, offsets)]
            (xh, yh), (xc, yc) = lines
            target = data[v]['fig3_jump_error']['1.4'][0]
            def residual(x):
                return np.interp(x, xh, yh) - np.interp(x, xc, yc) - target
            matched.append(brentq(residual, max(xh[0], xc[0]), min(xh[1], xc[1]), xtol=1e-15))
        x48, x64 = matched
        return BETA['48'][0] - BETA['64'][0] + calibration(8*x64) - calibration(8*x48)

    zero = np.zeros((2, 2, 2))
    baseline = rematch(axis, zero)
    def span(values):
        changes = np.asarray(list(values)) - baseline
        return dict(min=float(changes.min()), max=float(changes.max()), cases=int(changes.size))

    half = (-0.5, 0.5)
    shared_ticks = span(rematch(Polynomial.fit(pixels + d, labels, 1), zero)
                        for d in itertools.product(half, repeat=len(pixels)))
    shared_translation = span(rematch(axis, zero + d) for d in half)
    volume_translations = span(rematch(axis, zero + np.array(d)[:, None, None])
                               for d in itertools.product(half, repeat=2))
    marker_offsets = span(rematch(axis, np.reshape(d, zero.shape))
                          for d in itertools.product(half, repeat=zero.size))
    # For a separate, explicitly stochastic model, propagate independent U(-0.5, 0.5)
    # coordinate rounding by the local Jacobian. The central differences span one unit.
    def uniform_sigma(size, evaluate):
        gradients = [evaluate(e*0.5)-evaluate(-e*0.5) for e in np.eye(size)]
        return np.linalg.norm(gradients) / np.sqrt(12)

    tick_sigma = uniform_sigma(len(pixels), lambda e: rematch(Polynomial.fit(pixels+e,labels,1), zero))
    marker_sigma = uniform_sigma(zero.size, lambda e: rematch(axis, e.reshape(zero.shape)))
    return dict(tick_eps_units=pixels.tolist(), tick_labels=labels.tolist(),
                x_per_eps_unit=x_step, max_tick_fit_residual_eps=float(max(abs(axis(pixels)-labels))/x_step),
                unrounded_marker_baseline=baseline,
                horizontal_derivatives=(-8*calibration.deriv()(8*roots)*np.array([1, -1])).tolist(),
                uniform_rounding_sigma=dict(ticks=tick_sigma, local_markers=marker_sigma,
                    combined_independent=np.hypot(tick_sigma, marker_sigma)),
                shared_axis_tick_refits=shared_ticks, common_marker_translation=shared_translation,
                separate_volume_translations=volume_translations, separate_local_markers=marker_offsets,
                interpretation="Half an integer EPS unit per input. Enumerated stress-test endpoints, not standard errors.")


def local_inputs(data, calibration, roots):
    rows = []
    for (v, (_, ebc)), root in zip(BETA.items(), roots):
        x, j, h, c = jump_curve(data[v]['fig15_x_q_error'])
        i = np.searchsorted(x, root) - 1
        s = (j[i+1]-j[i]) / (x[i+1]-x[i]) / (8*calibration.deriv()(8*root))
        rows.append(dict(volume=v, x=root, slope=s, hot=np.interp(root,x,h),
                         cold=np.interp(root,x,c), fig3=data[v]['fig3_jump_error']['1.4'][1], beta_c=ebc))
    return rows


def variance_terms(rows, rho_hc, rho_beta):
    # rho_153 refers to hot-minus-cold and Fig. 3, not to either phase on its own.
    a, b = 0., 0.
    for row in rows:
        h, c, e, s = (row[k] for k in ('hot','cold','fig3','slope'))
        gap = np.sqrt(h*h + c*c - 2*rho_hc*h*c)
        a += (gap**2 + e**2 + (s*row['beta_c'])**2) / s**2
        b += 2*gap*e / s**2
    a -= 2*rho_beta*rows[0]['beta_c']*rows[1]['beta_c']
    return a, b


def zscore(rows, d, hc, r153, rb):
    a, b = variance_terms(rows, hc, rb)
    return abs(d) / np.sqrt(a-b*r153)


def contour(rows, d, hc, rb, level=1.96):
    a, b = variance_terms(rows, hc, rb)
    return (a-(d/level)**2)/b


def plot(rows, d, destination):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FormatStrFormatter
    from matplotlib.colors import ListedColormap, BoundaryNorm

    fig, axs = plt.subplots(1, 2, figsize=(9.5, 5.0), sharey=True, layout='constrained')
    h = np.linspace(-1, 1, 121)
    col = ListedColormap(['#f3f5f4','#d9e9ef','#a5cbdb','#74aabf','#43819b','#26596f'])
    levels = [0, 1, 1.5, 1.96, 2.5, 3, 20]
    norm = BoundaryNorm(levels, col.N)
    for ax, rb in zip(axs, (0, 1)):
        bands = [np.full_like(h,-1)] + [np.clip(contour(rows,d,h,rb,v),-1,1) for v in levels[1:-1]] + [np.full_like(h,1)]
        for lo, hi, color in zip(bands, bands[1:], col.colors):
            ax.fill_between(h, lo, hi, color=color, linewidth=0)
        ax.plot(h, contour(rows,d,h,rb), color='#99392e', lw=2.4, label='z = 1.96')
        ax.axhline(0, linestyle=':', lw=.8, color='0.4')
        ax.axvline(0, linestyle=':', lw=.8, color='0.4')
        ax.set(xlim=(-1,1), ylim=(-1,1), xlabel=r'$\rho_{hc}$', title=rf'$\rho_{{\beta_c}}={rb}$', aspect='equal')
        ax.set_xticks([-1,-.5,0,.5,1])
        ax.set_yticks([-1,-.5,0,.5,1])
        ax.yaxis.set_major_formatter(FormatStrFormatter('%g'))
        ax.xaxis.set_major_formatter(FormatStrFormatter('%g'))
        ax.legend(loc='lower left')
    axs[0].set_ylabel(r'$\rho_{15,3}$')
    fig.suptitle('R136.1  |  Корреляционная чувствительность D', fontsize=15)
    bar=fig.colorbar(matplotlib.cm.ScalarMappable(norm=norm, cmap=col), ax=axs, orientation='horizontal',
                     ticks=[], fraction=.08, pad=.1, spacing='uniform')
    bar.set_ticks([.5,1.25,1.73,2.23,2.75,11.5],labels=['< 1','1–1.5','1.5–1.96','1.96–2.5','2.5–3','≥ 3'])
    bar.set_label('Условная значимость z  ·  вся область сценарная')
    with matplotlib.rc_context({'svg.hashsalt':'R136.1','svg.fonttype':'none'}):
        fig.savefig(destination, metadata={'Date':None})
    plt.close(fig)
    if destination.suffix == '.svg':
        destination.write_text('\n'.join(line.rstrip() for line in destination.read_text().splitlines())+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('paper', type=Path)
    parser.add_argument('scale_paper', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--plot', type=Path)
    args = parser.parse_args()
    data = digitize(args.paper, args.scale_paper)
    assert data == json.loads((HERE/'FIGURES.json').read_text())
    base = run(data)
    d = base['implied_origin_difference_48_minus_64']
    roots = np.array([base['volumes'][v]['fig15_fig3_curve']['x_matching_J'] for v in BETA])
    fit = Polynomial.fit(*np.array(data['calibration_curve_Nt_beta']).T, 5)
    rows = local_inputs(data, fit, roots)
    axis = eps_axis_budget(read_figure(args.paper,'fig15'), data, fit, roots)
    assert abs(axis['unrounded_marker_baseline']-d) < 1e-9
    pairs = [(0,0),(.5,.5),(.7,.7),(.9,.9),(.5,.9),(.9,.5)]
    beta = [r['beta_c'] for r in rows]
    scenarios=[]
    for rb in (-1,0,1):
        rcrit=brentq(lambda r:zscore(rows,d,r,r,rb)-1.96, -.999, .999) if zscore(rows,d,.999,.999,rb)>1.96 else None
        sig_beta=np.sqrt(beta[0]**2+beta[1]**2-2*rb*beta[0]*beta[1])
        scenarios.append(dict(rho_beta=rb, sigma_beta_difference=sig_beta, common_rho_threshold=rcrit,
            pairs=[dict(hc=h,r153=r,z=zscore(rows,d,h,r,rb)) for h,r in pairs],
            contour_at_hc={str(h):contour(rows,d,h,rb) for h in (-1,0,.5,.9,1)}))
    archived=json.loads((HERE/'CHECKS.json').read_text())
    rounded=[archived['volumes'][v]['beta_origin_implied_by_J'] for v in BETA]
    curve=[archived['volumes'][v]['fig15_fig3_curve']['residual'] for v in BETA]
    table=[archived['volumes'][v]['fig15_fig3_table_local']['residual'] for v in BETA]
    def secant(r):
        return r[0]/68.96-r[1]/106.78
    provenance=dict(canonical_curve_reconstruction=dict(value=d, source="verify.run(FIGURES.json): implied_origin_difference_48_minus_64"),
        rounded_anchor_replay=dict(value=rounded[0]-rounded[1], inputs=rounded, source="CHECKS.json: per-volume beta_origin_implied_by_J; rounded before subtraction"),
        curve_secant_proxy=dict(value=secant(curve), inputs=curve, source="CHECKS.json: fig15_fig3_curve.residual and archived secants"),
        table_secant_proxy=dict(value=secant(table), inputs=table, source="CHECKS.json: fig15_fig3_table_local.residual and archived secants"))
    budget=dict(question="U013", status="OPEN", provenance=provenance, axis=axis, local_inputs=rows,
                assumptions="Interpolated marginal errors at matching roots; zero cross-volume J covariance, zero beta_c/J covariance; fixed local F and piecewise slopes; correlations illustrative.",
                scenarios=scenarios)
    args.output.write_text(json.dumps(budget,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    if args.plot:
        plot(rows,d,args.plot)


if __name__=='__main__':
    main()
