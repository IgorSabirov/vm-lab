"""Independent continuity diagnostic on the archived expansion history; no fitted pressures."""
from pathlib import Path
import numpy as np
from scipy.special import roots_laguerre
from graph import relic,TREF,HBAR,MPL

def ideal_sm(T,tn):
    # Thermal gamma,e-,e+, and three neutrino species with fitted temperature.
    q,w=roots_laguerre(96)
    z=.51099895/T[:,None]
    e=np.hypot(q,z)
    weights=w*q**2*np.exp(q-e)/(1+np.exp(-e))
    norm=4*T**4/(2*np.pi**2)
    rho_e=norm*np.sum(weights*e,axis=1)
    p_e=norm*np.sum(weights*q**2/(3*e),axis=1)
    rho_rad=np.pi**2/15*T**4+3*7*np.pi**2/120*tn**4
    return rho_rad+rho_e,rho_rad/3+p_e


def energy_audit(h,out):
    config=__import__('json').loads((out/'paired_runs.json').read_text())['both_channels']['config']
    T,tn=h.T,h.Tnu
    a_ref=np.exp(np.interp(np.log(TREF),h.logT[::-1],np.log(h.a[::-1])))
    tn_ref=np.interp(np.log(TREF),h.logT[::-1],tn[::-1])
    tx=tn_ref*(10.75/config['gdec'])**(1/3)*a_ref/h.a
    rx,px=relic(tx,2*config['J'],config['gx'])
    rho,p=ideal_sm(T,tn)
    loga=np.log(h.a)
    def trace(rho,p):
        # R_E/(H rho), so a change of time coordinate drops out.
        return np.gradient(np.log(rho),loga,edge_order=2)+3*(1+p/rho)
    xonly=trace(rx,px)
    sm=trace(rho,p)
    total=trace(rho+rx,p+px)
    quantities=np.c_[T,tx,rx,px,sm,xonly,total]
    np.savetxt(out/'energy_history.csv',quantities,delimiter=',',header='T_MeV,TX_MeV,rhoX,pX,R_SM_over_HrhoSM,R_X_over_HrhoX,R_tot_over_Hrho',comments='')
    mask=(T>.02)&(T<2.)
    formation=(T>.06)&(T<.085)
    return dict(denominator='H rho of each selected component; standard photon/electron/3nu ideal-gas reference',
                window_MeV=[.02,2.],SM_max_abs=float(max(abs(sm[mask]))),X_max_abs=float(max(abs(xonly[mask]))),
                total_max_abs=float(max(abs(total[mask]))),formation_total_max_abs=float(max(abs(total[formation]))),
                Qgamma=0,Qnu=0,portal_work_in_background=False)
