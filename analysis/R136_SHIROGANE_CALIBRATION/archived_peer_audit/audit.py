"""Reproduce the review. Arguments: R136 analysis directory, source tar 2021, source tar 2016, arXiv 2021v2 PDF, output directory."""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import sys
import numpy as np
import fitz
from numpy.polynomial import Polynomial
from scipy.optimize import brentq
from scipy.stats import norm


def pdf_cold(pdf):
    # Read the artists and the independent PDF tick geometry (Fig. 16, arXiv v2).
    with fitz.open(pdf) as paper:
        drawings = paper[22].get_drawings()
    black = [p for p in drawings if p['color'] == (0,0,0)]
    ys = sorted({p['rect'].y0 for p in black if p['rect'].width > 100 and p['rect'].height < .01}, reverse=True)
    xs = sorted({p['rect'].x0 for p in black if p['rect'].width < .01 and p['rect'].height > 100 and len(p['items']) == 2})
    assert len(xs) == 7 and len(ys) == 6, (xs,ys)
    tx = Polynomial.fit(xs, np.linspace(.988,1.012,7),1)
    ty = Polynomial.fit(ys, np.arange(6)*.5,1)
    circles = [p['rect'] for p in drawings if p['fill']==(0,0,1) and p['items'][0][0]=='c']
    points = sorted(((r.x0+r.x1)/2,(r.y0+r.y1)/2) for r in circles)
    rows = []
    for x,y in points[-2:]:
        bars = [abs(seg[1].y-seg[2].y)/2 for p in drawings if p['color']==(0,0,1)
                for seg in p['items'] if seg[0]=='l' and
                max(abs(seg[1].x-x),abs(seg[2].x-x))<.01 and
                abs((seg[1].y+seg[2].y)/2-y)<.02 and abs(seg[1].y-seg[2].y)>1]
        assert len(bars)==1
        rows.append([tx(x),ty(y),abs(ty.deriv()(y))*bars[0]])
    return rows


def run(source_dir, tar21, tar16, pdf, outdir):
    sys.path.insert(0,str(source_dir.resolve()))
    import extract
    import verify
    data = extract.digitize(tar21,tar16)
    assert data==json.loads((source_dir/'FIGURES.json').read_text())
    archive = verify.run(data)
    assert verify.compact(archive)==json.loads((source_dir/'CHECKS.json').read_text())
    n,b = np.array(data['calibration_curve_Nt_beta']).T
    f = Polynomial.fit(n,b,5)
    rows, contrasts, tests, curves, flows = {}, {}, {}, {}, {}
    BC = np.array([6.06160,6.06247])
    EB = np.array([.00018,.00014])
    for i,v in enumerate(('48','64')):
        entries=archive['volumes'][v]
        root=entries['fig15_fig3_curve']['x_matching_J']
        c=verify.jump_curve(data[v]['fig15_x_q_error'])
        j3=data[v]['fig3_jump_error']['1.4']
        match=verify.estimate(c,root,j3)
        rows[v]=[root,match['slopes_dJ_dx'][0]/(8*f.deriv()(8*root)),
                 match['hot_error_at_x'],match['cold_error_at_x'],j3[1]]
        curves[v]=(c,j3)
        flows[v]=extract.points(extract.read_figure(tar21,'fig3_'+v),'0.00 0.39 0.00','CircleF',51)
        j13,e13=data[v]['fig13_derivative_jump_error']
        tests[v]={}
        for t,(value,err) in data[v]['fig3_jump_error'].items():
            delta=j13-value
            tests[v][t]=[delta,np.hypot(e13,err),delta/np.hypot(e13,err)]
    roots,s,eh,ec,e3=np.array(list(rows.values())).T
    D=BC[0]-BC[1]+f(8*roots[1])-f(8*roots[0])
    output={'D':D,'fit_vertices':len(b),'distinct_vertical_values':len(set(b)),'root_local_parameters':rows,
            'axis_free_comparison_fig13_minus_fig3_independent_errors':tests,'cold64_last_two_PDF':pdf_cold(pdf)}
    # The journal's Fig. 13 caption distinguishes open and filled symbols.
    # The color, shape, centers and error bars come from the plotted vector objects.
    fig13 = extract.read_figure(tar21, 'fig13')
    output['fig13_Nt8_green_triangles'] = {}
    for name, marker in [('derivative_open', 'TriU'), ('SFtX_filled', 'TriUF')]:
        values = extract.points(fig13, '0.00 0.39 0.00', marker, 2)
        output['fig13_Nt8_green_triangles'][name] = {
            v: dict(aspect_drawn=x, J=y, error=e)
            for v, (x,y,e) in zip(('48','64'), values)
        }
    output['root_parameter_order'] = ['x_matching', 'dJ_dbeta', 'hot_error', 'cold_error', 'Fig3_error']
    output['jump_residuals'] = {}
    for v, entry in archive['volumes'].items():
        curve = entry['fig15_fig3_curve']
        table = entry['fig15_fig3_table_local']
        output['jump_residuals'][v] = {
            'raw_at_x1': curve['J_x1'] - curve['J_reference'],
            'curve_at_beta_c': curve['residual'],
            'table_at_beta_c': table['residual'],
            'x_beta_c_from_curve': curve['x_beta_c'],
        }
    # Two fixed propagation conventions, all conditional on independent beta_c errors and volumes.
    # ARCH uses the script's rounded inputs; ROOT applies the delta method at the implicit roots.
    A=np.array([[68.96,.021046414,.0092617872,.022559457],[106.78,.016605519,.0071178013,.014992044]]).T
    variants={'archive':(.0006229,*A), 'root':(D,s,eh,ec,e3)}
    def significance(rhc,r153,params):
        d,m,h,c,ref=params
        err15=np.sqrt(h*h+c*c-2*rhc*h*c)
        var=(err15**2+ref**2-2*r153*err15*ref)/m**2+EB**2
        return d/np.sqrt(var.sum())
    with (outdir/'covariance_grid.csv').open('w') as stream:
        w=csv.writer(stream);w.writerow(['rho_hc','rho_153','rho_x','z_archived_convention','z_root_local'])
        for h in np.linspace(0,1,21):
            for j in np.linspace(0,1,21):
                w.writerow([round(h,3),round(j,3),0,*[significance(h,j,q) for q in variants.values()]])
    for key,q in variants.items():
        contrasts[key]={'diagonal':{str(h):significance(h,h,q) for h in (0,.5,.7,.9)},
                         'critical_diagonal':brentq(lambda h:significance(h,h,q)-1.96,0,.99),
                         'critical_rho_153_given_rho_hc':{str(h):brentq(lambda j:significance(h,j,q)-1.96,0,1) for h in (0,.5,.9)}}
    output['conditional_correlation_sensitivity']=contrasts
    residual=np.array([archive['volumes'][v]['fig15_fig3_curve']['residual'] for v in rows])
    slope,h,c,ref=A
    dl=residual[0]/slope[0]-residual[1]/slope[1]
    output['linearized_residual_contrast']=dl
    for rho in (0,.9):
        f15=np.sqrt(h**2+c**2-2*rho*h*c)
        C=np.diag(f15**2+ref**2-2*rho*f15*ref+(slope*EB)**2)+.00028**2*np.outer(slope,slope)
        ci=np.linalg.inv(C)
        fit=slope@ci@residual/(slope@ci@slope)
        chi=(residual-fit*slope)@ci@(residual-fit*slope)
        w=np.array([1/slope[0],-1/slope[1]])
        assert abs(chi-dl**2/(w@C@w))<1e-10
        output.setdefault('gls',{})[str(rho)]=dict(shift=fit,chi_min=chi,p_df1=2*norm.sf(np.sqrt(chi)))
    def fixed15(targets):
        r=[brentq(lambda x: np.interp(x,c[0],c[1])-j,c[0][0],c[0][-1]) for (c,_),j in zip(curves.values(),targets)]
        return BC[0]-BC[1]+f(8*r[1])-f(8*r[0])
    selected=[]
    with (outdir/'fig3_flow.csv').open('w') as stream:
        w=csv.writer(stream);w.writerow(['t_over_a2_nominal','point_kind','J48','error48','J64','error64','D_with_Fig15_frozen_if_in_published_fit_window'])
        for x,y in zip(sorted(flows['48'],key=lambda p:p[0]),sorted(flows['64'],key=lambda p:p[0])):
            assert abs(x[0]-y[0])<1e-6
            t=round(float(x[0]),2) or 0.0
            d=fixed15([x[1],y[1]]) if 1<=t<=1.6 else None
            if d is not None:selected.append([t,d])
            w.writerow([t,'extrapolated' if t==0 else 'finite',*x[1:],*y[1:],d])
    output['conditional_fixed_Fig15_range_1_to_1p6']=[min(selected,key=lambda z:z[1]),max(selected,key=lambda z:z[1])]
    output['file_hashes_sha256']={str(p.name):hashlib.sha256(p.read_bytes()).hexdigest() for p in [tar21,tar16,pdf]}
    (outdir/'results.json').write_text(json.dumps(output,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__)
    for key in ('source_dir','tar21','tar16','pdf','outdir'):a.add_argument(key,type=Path)
    args=a.parse_args()
    args.outdir.mkdir(parents=True,exist_ok=True)
    run(**vars(args))
