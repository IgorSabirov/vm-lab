"""Replay SU(3) phase and interface controls. Pass the arXiv:2011.10292v2 PDF."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import fitz
import numpy as np
from scipy.stats import chi2

from read_shirogane_fig15 import PDF_SHA
from xb_su3_eos.replay_eos import fits

HERE = Path(__file__).resolve().parent


def linear_fit(x, y, errors, target):
    x, y, errors = map(np.asarray, (x, y, errors))
    design = np.column_stack((np.ones(len(x)), x))
    norm = design / errors[:, None]
    cov = np.linalg.inv(norm.T @ norm)
    intercept, slope = cov @ norm.T @ (y / errors)
    v = np.array([1, target])
    stat = np.sum(((y - intercept - slope*x) / errors)**2)
    dof = len(y)-2
    return dict(value=intercept + slope*target, error=np.sqrt(v @ cov @ v), chi2=stat,
                dof=dof, diagonal_p=chi2.sf(stat, dof) if dof else None)


def fig3_marks(pdf):
    if hashlib.sha256(pdf.read_bytes()).hexdigest() != PDF_SHA:
        raise ValueError("Expected arXiv:2011.10292v2 PDF used for Fig. 15")
    with fitz.open(pdf) as doc:
        drawings = doc[10].get_drawings()
    result = {}
    for ns, base in ((48, 0), (64, 364)):
        y06, y16 = (drawings[base+j]['rect'].y0 for j in (0, 5))
        x0, x2 = (drawings[base+j]['rect'].x0 for j in (6, 10))
        def flow(x):
            return 2*(x-x0)/(x2-x0)
        def jump(y):
            return 0.6+(y06-y)/(y06-y16)
        for i in range(6):
            assert abs(jump(drawings[base+i]['rect'].y0) - (0.6+i*0.2)) < 0.001
        for i in range(5):
            assert abs(flow(drawings[base+6+i]['rect'].x0) - i/2) < 0.001
        marks = {}
        for mark in drawings[base+71:base+123]:
            assert mark['type']=='f' and mark['fill'][1] > 0 and mark['fill'][0] == mark['fill'][2] == 0
            box = mark['rect']
            x, y = (box.x0+box.x1)/2, (box.y0+box.y1)/2
            for t in (0, 1.4):
                if abs(flow(x)-t) > 0.0006:
                    continue
                bars = []
                for j in (68, 69, 70):
                    for kind, a, b in drawings[base+j]['items']:
                        if kind=='l' and abs(a.x-b.x)<0.01 and abs(a.x-x)<0.04:
                            bars.append(sorted([jump(a.y), jump(b.y)]))
                assert len(bars)==1 and abs(np.mean(bars[0])-jump(y)) < 0.001 and str(t) not in marks
                marks[str(t)] = dict(jump=jump(y), drawn_bounds=bars[0])
        assert set(marks)=={'0','1.4'}
        result[ns] = marks
    return result


def cold_model(x, cold, hot, errors, ref, rho):
    """GLS in measured q. Reference and hot series fixed, rho is a stress setting."""
    distances = np.abs(np.subtract.outer(np.arange(len(x)), np.arange(len(x))))
    cov = np.outer(errors, errors)*rho**distances
    offset = cold-ref
    out = {}
    for name, shape in [('offset', np.ones(len(x))), ('hot_fraction', hot-ref)]:
        precision_shape = np.linalg.solve(cov, shape)
        value = (offset @ precision_shape)/(shape @ precision_shape)
        residual = offset-value*shape
        stat = residual @ np.linalg.solve(cov, residual)
        out[name] = dict(value=value, chi2=stat, dof=len(x)-1, nominal_p=chi2.sf(stat,len(x)-1))
    return out


def run(pdf):
    marks = fig3_marks(pdf)
    donor = json.loads((HERE/'xb_su3_eos/donor_inputs.json').read_text())
    with (HERE/'SHIROGANE_FIG15_DIGITIZED.csv').open() as stream:
        rows = list(csv.DictReader(stream))
    # Giusti et al., arXiv:2501.10284v1, Table 1 (shift vector (1,0,0)).
    a2 = 1/(2*np.arange(5,10)**2)
    ref = {}
    for phase, y, err in [
        ('cold', [.2878,.2894,.2916,.2908,.288], [.0022,.0024,.0026,.0034,.005]),
        ('hot', [1.556,1.523,1.510,1.504,1.510], [.012,.011,.011,.012,.021])]:
        ref[phase] = {name:linear_fit(a2[:n], y[:n], err[:n], 1/64) for name,n in [('adjacent',2),('all',5)]}
    # Shirogane Table 2, NNLO mu0, enthalpy discontinuity after t->0.
    shiro = {6:([1.202,1.257,1.309],[.026,.046,.045]), 8:([1.132,1.120,1.118],[.020,.034,.041])}
    continuum = {lt:linear_fit(1/np.array([8,12,16])**2, y, e, 0) for lt,(y,e) in shiro.items()}
    # Shirogane (2021), Table 1, and the Nt=8 infinite-volume local scale
    # derivative |a d beta/da| from Shirogane (2016), Eq. (42) and following text.
    beta_c = {48: (6.06160, .00018), 64: (6.06247, .00014)}
    scale = .6217
    phases = {}
    for ns, lt in [(48,6),(64,8)]:
        series = {}
        for phase in ('hot','cold','all'):
            group = [r for r in rows if int(r['Ns'])==ns and r['series']==phase]
            x = np.array([float(r['T_over_Tc']) for r in group])
            q = np.array([float(r['w_over_T4']) for r in group])
            e = np.array([0.5*(float(r['drawn_error_plus'])+float(r['drawn_error_minus'])) for r in group])
            series[phase] = x,q,e
        x, cold, ec = series['cold']
        assert all(np.array_equal(x,s[0]) for s in series.values()) and np.all(np.diff(x)>0)
        hot, allq = series['hot'][1], series['all'][1]
        gap = hot-cold
        assert np.all(np.diff(gap)>0)
        j15 = np.interp(1,x,gap)
        j3 = marks[ns]['1.4']['jump']
        j0 = shiro[lt][0][0]
        assert abs(marks[ns]['0']['jump']-j0)<0.001 and gap[0]<j3<gap[-1]
        xr = np.interp(j3,gap,x)
        vals = {k:np.interp(1,x,s[1]) for k,s in series.items()}
        models = {}
        for window, mask in [('full', x<1), ('common', (x>=.992776) & (x<1))]:
            xx = x[mask]
            published = fits(donor,'cold',xx)[0]
            anchored = published*ref['cold']['all']['value']/fits(donor,'cold',1)[0]
            for label, r in [('aligned_q',anchored), ('continuum_q',published),
                             ('peer_mixed_units',xx**3 * published*(.28905/.2927))]:
                for rho in ([0,.5,.9] if label=='aligned_q' else [0]):
                    models[f'{window}/{label}/rho={rho}'] = cold_model(xx,cold[mask],hot[mask],ec[mask],r,rho)
        phases[ns] = dict(q_at_plot_one=vals, matched_a_percent={k:100*(vals[k]/ref[k]['all']['value']-1) for k in ref},
                          window=[x[0],x[-1]], mixture_at_plot_one=(vals['all']-vals['cold'])/j15,
                          fig15_jump_at_plot_one=j15, fig3=marks[ns], table2_t0=j0,
                          fig15_minus_fig3_same_flow=j15-j3, fig3_finite_minus_table2=j3-j0,
                          fig15_minus_table2=j15-j0, fig15_x_at_fig3_jump=xr,
                          beta_c=beta_c[ns][0], beta_c_error=beta_c[ns][1],
                          local_sigma_log_T_from_beta_c=beta_c[ns][1]/scale, cold_models=models)
    # Iwasaki et al. PRD 49, 3540, Nt=4,6. LTW hep-lat/0502003 Table 15, Nt=5.
    nt = np.array([4,5,6])
    s, e = np.array([.0292,.0200,.0218]),np.array([.0022,.0006,.0033])
    sigma = {}
    for ix in ([0,1,2],[0,2],[1,2],[0,1]):
        n = nt[ix]
        sigma[','.join(map(str,n))] = linear_fit(1/n**2,s[ix],e[ix],0)
    pred = linear_fit(1/nt[[0,2]]**2,s[[0,2]],e[[0,2]],1/25)
    pred['pull_vs_LTW'] = (pred['value']-s[1])/np.hypot(e[1],pred['error'])
    cases = {k:v for k,v in sigma.items() if k in ('4,5,6','4,6')}
    cases.update(BKP=dict(value=.0155,error=.0016), LTW=dict(value=.0200,error=.0006))
    scaling = {}
    for k,v in cases.items():
        s0,se = v['value'],v['error']
        points = np.array([s0-se,s0,s0+se])/.0200
        scaling[k]=dict(C_over_Cref=list(points**3), eps_over_eps_ref=list(points**1.5))
    return dict(matched_a_giusti=ref, fixed_LT_table2_continuum=continuum, phases=phases,
                delta_log_T_between_pseudocritical_betas_linear=(beta_c[64][0]-beta_c[48][0])/scale,
                wilson_sigma_intercepts=sigma, held_out_Nt5=pred, conditional_thin_wall_scaling=scaling)


def round_floats(obj):
    if isinstance(obj,dict):
        return {k:round_floats(v) for k,v in obj.items()}
    if isinstance(obj,list):
        return [round_floats(v) for v in obj]
    return float(f'{obj:.9g}') if isinstance(obj,float) else obj


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf',type=Path)
    print(json.dumps(round_floats(run(parser.parse_args().pdf)), indent=2, allow_nan=False))
