"""Replay the averaging, marked-spectrum, finite-size and second-order audit."""
import argparse
import json
from pathlib import Path
import tempfile

import mpmath
import numpy as np
from scipy import constants

from averaging import independent_temperature_control, width_controls
from curvature import second_order
from finite_controls import controls
from replay import BASE, MAP, MOSSA, archive_baseline, compare_saved, ensemble_covariance, git, pinned_files


def review_filter():
    spacing=10.
    e=np.linspace(.5,1500,3000)
    de=e[1]-e[0]
    w=np.exp(-e/(86.1733*.5)-31.29*np.sqrt(.6717112347483052/e))
    w /= np.trapezoid(w,e)
    padded=[]
    for field in (1500,6000,24000):
        variance=[ensemble_covariance(w[None,:],de,spacing,law,field)[0,0] for law in ('GOE','GUE','Poisson')]
        padded.append([np.sqrt(variance[0]/variance[1]),np.sqrt(variance[2]/variance[0])])
    # Reproduce the attached proxy's trapezoid over wrapped fftfreq coordinates.
    k=np.fft.fftfreq(len(e),de)
    power=abs(de*np.fft.fft(w))**2
    tau=spacing*abs(k)
    goe=np.empty_like(tau)
    lo=tau<=1
    goe[lo]=2*tau[lo]-tau[lo]*np.log1p(2*tau[lo])
    goe[~lo]=2-tau[~lo]*np.log1p(2/(2*tau[~lo]-1))
    vals=[np.trapezoid(power*form,k) for form in [goe,np.minimum(tau,1),np.ones_like(k)]]
    # Same high-accuracy quadrature and bare masses for constant S and Mossa's polynomial.
    energy=np.arange(2.25,2000,.5)
    mu_p,mu_d=[constants.physical_constants[s+' mass energy equivalent in MeV'][0]*1000 for s in ('proton','deuteron')]
    mu=mu_p*mu_d/(mu_p+mu_d)
    kt=constants.Boltzmann/constants.electron_volt*1e6*.5
    weight=np.exp(-energy/kt-2*np.pi*constants.alpha*np.sqrt(mu/(2*energy)))
    S=np.polynomial.polynomial.polyval(energy,MOSSA['coefficients_ascending'])
    conversion=constants.Avogadro*1e-25*constants.c*np.sqrt(8/(np.pi*mu))/kt**1.5*.5
    return dict(wrapped_trapezoid_ratios=[np.sqrt(vals[0]/vals[1]),np.sqrt(vals[2]/vals[0])],
                correct_fft_field_1500_6000_24000=padded,constant_S_rate=conversion*.214*sum(weight),
                Mossa_rate=conversion*(weight@S),effective_S_eV_b=(weight@S)/sum(weight))


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--primat',required=True,type=Path)
    p.add_argument('--vm_lab',required=True,type=Path)
    p.add_argument('--check',action='store_true')
    a=p.parse_args()
    assert git(a.primat,'rev-parse','HEAD').decode().strip()==MAP['sources']['primat']['commit']
    pinned_files(a.primat,'primat/network_builder.py')
    here=Path(__file__).resolve().parent
    ref=json.loads((here/'CHECKS.json').read_text())
    from response import trajectory_response
    redraw={}
    curve={}
    with tempfile.TemporaryDirectory() as tmp:
        archive=Path(tmp)
        archive_baseline(a.vm_lab,archive)
        for n in (1,2,4,8):
            t,j,_=trajectory_response(a.primat,archive,n,2.)
            redraw[str(n)]=independent_temperature_control(t,j)
            if n==4:
                variance=width_controls(t,j,ref)
            if n>=2:
                curve[str(n)]=second_order(a.primat,archive,n)
    for law in ('GOE','GUE','Poisson'):
        np.testing.assert_allclose(curve['4']['sd_fractional_coefficient'][law],
                                   ref['projected']['10'][law]['sd_unit_fraction'][2:],rtol=1e-7)
        np.testing.assert_allclose(curve['4']['mean_fractional_coefficient'][law],
                                   curve['8']['mean_fractional_coefficient'][law],rtol=.001)
    curvature_rows={}
    for law,v in [('GOE',2),('GUE',1)]:
        m=curve['8']['mean_fractional_coefficient']
        for label,var,model in [('equal',0,'equal'),('one_width',v,'one_width')]:
            shift=.1**2*(np.array(m[law])+var*np.array(m['Poisson']))
            obs=shift*np.array(ref['baseline'])/ref['observational_sigma']
            sd=np.array(variance['marks'][law][model]['obs_sd'])
            curvature_rows[law+'_'+label]=dict(relative_mean_shift=shift.tolist(),mean_in_obs_sigma=obs.tolist(),
                                                mean_over_first_order_sd=(obs/sd).tolist())
    with mpmath.workdps(20):
        count=int(mpmath.nzeros(1010))
        assert count==657
    result=dict(trajectory_commit=BASE, spacing_keV=10, line_fraction=.1, output_order=['D/H','Yp'],
                filter_audit=review_filter(), zero_count_below_1010=count,
                spectrum_tests=variance, wrong_independent_time_sd_over_coherent=redraw,
                quadratic_response=curve, mean_at_example=curvature_rows, finite_controls=controls())
    if a.check:
        compare_saved(result,json.loads((here/'SIGNAL_CHECKS.json').read_text()))
        print('R141 averaging audit passed')
    else:
        print(json.dumps(result,indent=2,allow_nan=False))


if __name__=='__main__':
    main()
