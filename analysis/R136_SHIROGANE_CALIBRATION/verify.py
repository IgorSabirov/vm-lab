"""R136. Offline tests A–C from the two source archives' digitized curves."""
import argparse
import json
from pathlib import Path

import numpy as np
from numpy.polynomial import Polynomial
from scipy.optimize import brentq
from scipy.stats import chi2

HERE = Path(__file__).resolve().parent
# Shirogane 2021 Table 1 and Shirogane 2016 Table II and Sec. IV A.
BETA = {"48": (6.06160, .00018), "64": (6.06247, .00014)}
BETA_INF, E_INF, K = 6.06307, .00028, .6217


def interp(x, xp, fp):
    if not xp[0] <= x <= xp[-1]:
        raise ValueError("Outside the published data window")
    return np.interp(x, xp, fp)


def jump_curve(data):
    hot, cold = (np.array(data[k]).T for k in ("hot", "cold"))
    x = np.union1d(hot[0],cold[0])
    x = x[(x>=max(hot[0,0],cold[0,0])) & (x<=min(hot[0,-1],cold[0,-1]))]
    # A union knot grid also handles the shorter cold branch in Fig. 16.
    h,c = (np.interp(x,v[0],v[1]) for v in [hot,cold])
    eh,ec = (np.interp(x,v[0],v[2]) for v in [hot,cold])
    return x,h-c,eh,ec


def estimate(curve, x, target):
    xx,j,eh,ec = curve
    jx = interp(x,xx,j)
    interval = np.searchsorted(xx,x)-1
    slope = np.diff(j)[interval]/np.diff(xx)[interval]
    span_slopes = [slope]
    for half in [1,2]:
        cut = slice(max(0,interval-half),min(len(xx),interval+half+2))
        span_slopes.append(np.polyfit(xx[cut]-x,j[cut],1)[0])
    zeros = []
    for lo,hi,ja,jb in zip(xx,xx[1:],j,j[1:]):
        if (ja-target[0])*(jb-target[0]) < 0:
            zeros.append(lo+(hi-lo)*(target[0]-ja)/(jb-ja))
    assert len(zeros)==1
    return dict(x_beta_c=x, J_x1=interp(1,xx,j), J_at_beta_c=jx, J_reference=target[0],
                J_reference_error=target[1], residual=jx-target[0],
                removed_by_axis=interp(1,xx,j)-jx, x_matching_J=zeros[0],
                hot_error_at_x=interp(x,xx,eh), cold_error_at_x=interp(x,xx,ec),
                slopes_dJ_dx=span_slopes)


def run(data):
    nt,b = np.array(data["calibration_curve_Nt_beta"]).T
    assert len(nt)==100 and np.all(np.diff(b)>0)
    poly = Polynomial.fit(nt,b,5)
    anchor = poly(8)
    x_for = lambda beta: brentq(lambda x:poly(8*x)-beta,.98,1.02)
    out = {"test_A":dict(curve_beta_at_8=anchor, curve_8_derivative=8*poly.deriv()(8),
                         max_curve_digitization_residual=max(abs(poly(nt)-b)),
                         table_beta_at_8=BETA_INF, table_beta_error=E_INF,
                         published_8_derivative=K), "volumes":{}}
    slopes, finite_term, errors, errors3 = [], [], [], []
    implied = []
    for ns,(bc,ebc) in BETA.items():
        x_curve = x_for(bc)
        x_local = np.exp((bc-BETA_INF)/K)
        d = data[ns]
        target = d['fig3_jump_error']['1.4']
        assert abs(d['fig3_jump_error']['0'][0]-{'48':1.202,'64':1.132}[ns])<.001
        curve = jump_curve(d['fig15_x_q_error'])
        central = estimate(curve,x_curve,target)
        direct = estimate(curve,x_local,target)
        control = estimate(jump_curve(d['fig16_x_q_error']),x_curve,d['fig13_derivative_jump_error'])
        # If one common horizontal shift of the beta curve were all that changed,
        # each measured jump would imply this effective beta at x=1.
        implied_beta = bc + anchor - poly(8*central['x_matching_J'])
        implied.append(implied_beta)
        k_local = 8*poly.deriv()(8*x_curve)
        slope = central['slopes_dJ_dx'][0]/k_local
        slopes.append(slope)
        finite_term.append(ebc*slope)
        errors.append(np.hypot(central['hot_error_at_x'],central['cold_error_at_x']))
        errors3.append(target[1])
        assert central['removed_by_axis']>0 and slope>0 and x_curve<1
        out['volumes'][ns]=dict(fig15_fig3_curve=central,fig15_fig3_table_local=direct,
                                fig16_fig13_method_control=control,
                                beta_origin_implied_by_J=implied_beta,
                                dJ_dbeta_windows=np.array(central['slopes_dJ_dx'])/k_local)
    out['implied_origin_difference_48_minus_64']=implied[0]-implied[1]
    out['test_B_covariance_sensitivity']={}
    # Illustrative sensitivity only. Marginal errors interpolated across neighbouring
    # temperatures; hot/cold and separate volumes independent in the data part.
    # The reference-curve intercept is common to both predictions. Its error is
    # proxied by the published Nt=8 table error; the fit coefficient covariance
    # and cross-covariance with the finite-volume beta_c values are unpublished.
    residual=np.array([v['fig15_fig3_curve']['residual'] for v in out['volumes'].values()])
    for rho in (0,.5,.9):
        vj=np.square(errors)+np.square(errors3)-2*rho*np.array(errors)*errors3
        local_cov=np.diag(vj+np.square(finite_term))
        covariance=local_cov+E_INF**2*np.outer(slopes,slopes)
        stat=float(residual @ np.linalg.solve(covariance,residual))
        out['test_B_covariance_sensitivity'][str(rho)] = dict(
            residual_cov=covariance.tolist(), joint_chi2=stat, nominal_p_df2=chi2.sf(stat,2),
            residual_errors=np.sqrt(np.diag(covariance)).tolist())
    return out


def compact(value):
    if isinstance(value,dict):
        return {k:compact(v) for k,v in value.items()}
    if isinstance(value,(list,np.ndarray)):
        return [compact(v) for v in value]
    return float(f'{value:.8g}') if isinstance(value,(np.floating,float)) else value


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    result=compact(run(json.loads((HERE/'FIGURES.json').read_text())))
    if args.check:
        assert result==json.loads((HERE/'CHECKS.json').read_text()), "Numerical replay differed"
        print("R136 matched the archived numerical controls")
    else:
        print(json.dumps(result,indent=2,allow_nan=False))
