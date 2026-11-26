"""Finite R150 graph, exact isocontrast roots and hot-relic diagnostic."""
import math
import numpy as np
from scipy.optimize import brentq
from scipy.special import ive, logsumexp, roots_laguerre
from upstream.contact import detector_contact

TREF = 0.07251310823341744
HBAR = 6.582119569e-22  # MeV s
MPL = 1.22089e22        # MeV, unreduced
Q, W = roots_laguerre(72)


def contrast(length, x):
    if length < 3 or length % 2 != 1 or x < 0:
        raise ValueError("Need odd L >= 3 and x >= 0")
    n = length - 1
    angles = 2 * np.pi * np.arange(n) / n
    z0 = 1 + np.exp(-2*x*np.sin(angles/2)**2).sum()
    # Positive series with exp(-x) removed, including the first omitted-order check.
    total = 0.
    for m in range(1, 10000, 2):
        term = ive(m*n, x)
        total += term
        if term <= 1e-15 * total:
            return 4*n*total/z0
    raise ArithmeticError("Bessel series did not converge")


def target_x(length, target):
    if not 0 < target < .5:
        raise ValueError("Finite contrast for active B must lie between zero and one half")
    return brentq(lambda x: contrast(length, x)-target, 0, max(1e3,20*(length-1)**2))


def contacts(length, J, lam, temperatures, layer="B"):
    """Return bare graph log-odds, diagonal and mixed shifts in MeV, C at 0 and pi.
    With fixed J and lambda, the Hermitian matrices need diagonalising only once."""
    n = length-1
    if length < 3 or length % 2 == 0:
        raise ValueError("Need odd L >= 3")
    T = np.atleast_1d(temperatures)
    if np.min(T)<=0 or J<0:
        raise ValueError("Need T>0 and J>=0")
    if layer=="A":
        phases=2*np.pi*np.arange(length)/length
        def cycle_log(phi):
            return logsumexp(2*J*np.cos(phases+phi/length)[:,None]/T,axis=0)
        return np.array([cycle_log(0.)-cycle_log(np.pi),*[np.zeros_like(T)]*4])
    if layer!="B": raise ValueError("Layer must be A or B")
    logs, shifts, means = [], [], []
    c = np.diag([1.,1.]+[0.]*(length-2))
    for sign in (1.,-1.):
        step=np.zeros((length,length))
        step[1,1]=1
        cycle=[0,*range(2,length)]
        for a,b in zip(cycle,cycle[1:]+cycle[:1]):
            step[b,a]=sign if b==0 else 1.
        h=J*(step+step.T)
        def log_z(matrix):
            return logsumexp(np.linalg.eigvalsh(matrix)[:,None]/T,axis=0)
        z=log_z(h)
        logs.append(z)
        shifts.append(T*(log_z(h+lam*c)-z))
        means.append(1/n+(1-1/n)*np.exp(2*J/T-z))
    return np.array([logs[0]-logs[1],shifts[1],shifts[0]-shifts[1],*means])


def relic(tx, mass, dof=1):
    """Collisionless Bose distribution set while relativistic, zero chemical potential.
    tx is momentum temperature, not the equilibrium temperature of a massive gas."""
    t=np.asarray(tx)[...,None]
    e=np.hypot(Q,mass/t)
    weight=W*Q**2/(-np.expm1(-Q))
    norm=dof*t[...,0]**4/(2*np.pi**2)
    return norm*(e@weight), norm*((Q**2/(3*e))@weight)


def screen(length, eps, gdec, gx, graph_bath="photon"):
    tn=(4/11)**(1/3)*TREF
    tx=(10.75/gdec)**(1/3)*tn
    reference=7*np.pi**2/120*tn**4
    temperature={"photon":TREF,"relic":tx}[graph_bath]
    J=target_x(length,eps)*temperature/2
    ratio=float(relic(tx,2*J,gx)[0]/reference)
    def residual(j):
        return float(relic(tx,2*j,gx)[0]/reference)-.17
    cap=brentq(residual,0,100) if residual(0)<0 else None
    # Optional extension to today: stable nonrelativistic particles, no dilution.
    number_today=410.73*gx/2*(10.75/gdec)*(4/11)
    rho_crit_over_h2_eV_cm3=1.053672e4
    omega_h2=(2*J*1e6)*number_today/rho_crit_over_h2_eV_cm3
    return dict(L=length,epsilon=eps,g_dec=gdec,g_X=gx,graph_bath=graph_bath,
                stable_n_today_cm3=number_today,stable_Omega_h2=omega_h2,
                stable_fraction_of_DM=omega_h2/.1200,
                max_surviving_comoving_number_fraction=min(1.,.1200/omega_h2),
                J_MeV=J,J_max_MeV=cap,rho_over_one_nu=ratio,passes_at_Tref=ratio<=.17)


def spectral_audit():
    rows=[]
    for length in (3,5,7,9,15,31,61):
        for eps in (.01,.1,.4):
            x=target_x(length,eps)
            for s in (-.1,.1):
                out=detector_contact(length,x,s)
                rows.append(dict(L=length,epsilon=eps,x=x,J_MeV=x*TREF/2,
                                 lambda_over_T=s,mixed_keV=1000*TREF*out['g_eff'],**out))
    return rows


def diagonal_caps():
    rows=[]
    for length in (3,5,7,15):
        J=target_x(length,.4)*TREF/2
        for cap in (-32.09,7.70):
            def shifts(s):
                return contacts(length,J,s*TREF,[TREF])[1:3,0]*1000
            s=brentq(lambda v: shifts(v)[0]-cap,-2.,2.)
            rows.append(dict(L=length,cap_keV=cap,lambda_over_T=s,
                             diagonal_keV=shifts(s)[0],mixed_keV=shifts(s)[1]))
    return rows
