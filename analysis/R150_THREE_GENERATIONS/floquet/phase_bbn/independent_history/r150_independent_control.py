import numpy as np
from scipy.special import roots_laguerre, logsumexp, expit
from scipy.integrate import cumulative_trapezoid
from scipy.optimize import minimize_scalar
from scipy.interpolate import PchipInterpolator

ME=.51099895
ALPHA=1/137.035999177
HBAR=6.582119569e-22
MPL=1.22089e22
J=ME/2
LAM=ALPHA*ME
L=7
q,w=roots_laguerre(128)

# Independent thermal history: gamma, electron/positron and 3 neutrino species.
# No nuclear abundance, reaction network, or target reference temperature read.
def em(T):
    T=np.asarray(T); E=np.hypot(q,ME/T[...,None]); wt=w*q**2*np.exp(q-E)/(1+np.exp(-E)); norm=4*T**4/(2*np.pi**2)
    r=np.pi**2/15*T**4+norm*np.sum(wt*E,axis=-1)
    p=np.pi**2/45*T**4+norm*np.sum(wt*q**2/(3*E),axis=-1)
    return r,p,(r+p)/T

def eos(T):
    r,p,s=em(T)
    rd,pd,sd=em(2.)
    sn=3*7*np.pi**2/90*T**3
    sn_dec=3*7*np.pi**2/90*2.**3
    a=np.where(T>=2.,((sd+sn_dec)/(s+sn))**(1/3),(sd/s)**(1/3))
    tn=np.where(T>=2.,T,2./a)
    rsm=r+3*7*np.pi**2/120*tn**4
    tx=2.*(10.75/106.75)**(1/3)/a
    e=np.hypot(q,2*J/tx[...,None]); wt=w*q**2/(-np.expm1(-q))
    rx=tx**4/(2*np.pi**2)*np.sum(e*wt,axis=-1)
    px=tx**4/(2*np.pi**2)*np.sum(q**2/(3*e)*wt,axis=-1)
    h0=np.sqrt(8*np.pi/3*rsm)/(HBAR*MPL)
    hx=h0*np.sqrt(1+rx/rsm)
    return a,tn,tx,rx,px,h0,hx

def graph(T,J,L=7,lam=0):
    n=L-1; T=np.atleast_1d(T); logs=[]; shifts=[]
    c=np.diag([1.,1.]+[0.]*(L-2))
    for sign in (1.,-1.):
        F=np.zeros((L,L)); F[1,1]=1.; cyc=[0,*range(2,L)]
        for a,b in zip(cyc,cyc[1:]+cyc[:1]): F[b,a]=sign if b==0 else 1.
        h=J*(F+F.T)
        log=lambda H:logsumexp(np.linalg.eigvalsh(H)[:,None]/T,axis=0)
        z=log(h); logs.append(z); shifts.append(T*(log(h+lam*c)-z))
    b=logs[0]-logs[1]; m=shifts[0]-shifts[1]; u=shifts[1]+expit(b)*m
    return b,m,u,shifts[1]

T=np.unique(np.r_[np.geomspace(.01,10,10001),2.,1.,.8,.3,.1,.08,.05,.03,.02])[::-1]
a,tn,tx,rx,px,h0,hx=eos(T)
# at the upper endpoint use radiation-dominated age approximation.
t0=1/(2*h0[0])+cumulative_trapezoid(1/h0,np.log(a),initial=0)
tx_time=1/(2*hx[0])+cumulative_trapezoid(1/hx,np.log(a),initial=0)
# Exact relative-scale extremum, no dimensionful fit.
for l in [3,5,7,9,15]:
    opt=minimize_scalar(lambda logt: -np.exp(logt)*graph(np.exp(logt),1,L=l)[0][0],bounds=(-9,2),method='bounded',options={'xatol':1e-10})
    tt=np.exp(opt.x); print('max',l,tt,-opt.fun)
print('J, lambda',J,LAM)
print('T_MeV tSM_s tX_s HSM_s-1 dH_s-1 dH_percent bgraph mix_keV u_keV')
for v in [2.,1.,.8,.3,.1,.08,.05,.03,.02,.01]:
    i=np.argmin(abs(T-v)); b,m,u,d=graph(v,J,lam=LAM)
    print('%5.2f %10.5g %10.5g %11.5g %11.5g %9.5g %12.5g %12.5g %12.5g'%(T[i],t0[i],tx_time[i],h0[i],hx[i]-h0[i],100*(hx[i]/h0[i]-1),b[0],1000*m[0],1000*u[0]))
print('null lambda exact',np.max(abs(graph(T,J,lam=0)[1])))
# Relative finite-grid convergence and continuity of free-streaming massive relic.
mask=(T<1.8)&(T>.015)
err=np.gradient(np.log(rx),np.log(a),edge_order=2)+3*(1+px/rx)
print('relic continuity relative max',np.max(abs(err[mask])))
# Stable species overcloses, if extended unchanged to present.
n0=410.73/2*(10.75/106.75)*(4/11)
print('stable omega h2',2*J*1e6*n0/1.053672e4)
