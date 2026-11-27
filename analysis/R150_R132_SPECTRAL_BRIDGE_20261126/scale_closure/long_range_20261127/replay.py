"""Deterministic small numerical replay; no physical measurement or BBN fit.
numpy/scipy, common E0 at band minimum and common zero-energy port.
"""
import numpy as np
from scipy.linalg import eigh_tridiagonal
from scipy.optimize import brentq, minimize_scalar
from scipy.special import logsumexp
N=6; M=15.85/3.08622708259639589; target=1/np.pi**2
pi=np.pi
def bands(s,k,cut=20):
    n=np.arange(-cut,cut+1)
    return eigh_tridiagonal((2*n+k)**2+s/2,np.full(2*cut,-s/4),eigvals_only=True)
def band(s,k,cut=20):
    n=np.arange(-cut,cut+1)
    return eigh_tridiagonal((2*n+k)**2+s/2,np.full(2*cut,-s/4),select='i',select_range=(0,0))[0][0]
def hop(s,nk=1024,cut=20,r=12):
    k=np.linspace(-1,1,nk,endpoint=False)
    E=np.array([band(s,x,cut) for x in k])
    return -np.mean(E[None,:]*np.cos(np.arange(1,r+1)[:,None]*pi*k[None,:]),axis=1)
s=brentq(lambda s:hop(s,512,r=1)[0]-target,.5,12)
j=hop(s);sq=brentq(lambda s:(band(s,1)-band(s,0))/4-target,.5,12)
print('roots',s,sq,'Jr/J1',j/j[0])
print('curv',np.sum(np.arange(1,13)**2*j)/j[0])
assert abs(s-3.35203828064)<1e-8 and abs(sq-3.40181871215)<1e-8
print('width at s_F',(band(s,1)-band(s,0))/4,'J1 at s_width',hop(sq,r=1)[0])
def k(phi):return ((2*np.arange(N)+phi/pi)/N+1)%2-1
def hops(phi,R):return 2*np.sum((j[:R]/j[0])[:,None]*(1-np.cos(np.arange(1,R+1)[:,None]*pi*k(phi))),axis=0)
def f(x):return np.sqrt(M*M+2*M*x)-M
def calc(a,b,t):
    l0=logsumexp(np.r_[0,-a/t]);lp=logsumexp(np.r_[0,-b/t])
    return -np.expm1(lp-l0),np.exp(-l0),np.exp(-lp)
for R in range(1,7):
    a,b=hops(0,R),hops(pi,R)
    ds=[sum(b**p)-sum(a**p) for p in range(1,7)]
    p=next(i+1 for i,x in enumerate(ds) if abs(x)>1e-10)
    print('moment',R,p,ds[p-1])
    assert p==(N+R-1)//R
Emin=band(s,0)
a,b=[(np.array([band(s,x) for x in k(phi)])-Emin)/j[0] for phi in [0,pi]]
a0,b0=hops(0,1),hops(pi,1)
tlegacy=80/3.08622708259639589
models=[('NN NR',a0,b0),('NN f',f(a0),f(b0)),('Opt NR',a,b),('Opt f',f(a),f(b))]
for name,x,y in models:
    ra=(y[2]-y[1])/(y[1]-y[0]);rp=(x[3]-x[2])/(x[2]-x[1])
    print(name,'ratios',ra,rp,'legacy',calc(x,y,tlegacy)[0])
    if name.startswith('Opt'):print('zero',brentq(lambda t:calc(x,y,t)[0],1.5,10))
    grad=np.array([ra,-1-ra,1])/(y[1]-y[0])
    print('sigma ratio 1% independent level error',np.linalg.norm(grad*.01*y[:3]))
for t in [.1,.15,.2,.3,.5,.7,1,1.5,1.8,2,3,5,10,20,50]:
    print('T',t,*[calc(x,y,t)[0] for _,x,y in models])
for cut in [14,22,30,42]:
    A,B=[(np.array([bands(s,x,cut) for x in k(phi)])-Emin)/j[0] for phi in [0,pi]]
    print('cut',cut,'second min',min(A[:,1].min(),B[:,1].min()))
    for t in [1.5,1.8,2,tlegacy]:
        c1=calc(A[:,0],B[:,0],t)[0];cf=calc(A.ravel(),B.ravel(),t)[0]
        print('bands',t,c1,cf,calc(f(A.ravel()),f(B.ravel()),t)[0])
        if t==2:assert c1<0<cf
for name,x,y in [('NN',a0,b0),('Opt',a,b)]:
    def score(t):
        c,p,q=calc(x,y,t);cr,*_=calc(f(x),f(y),t)
        sig=p/q*np.sqrt((1-p)/p+(1-q)/q)/np.sqrt(5e6)
        return abs(cr-c)/sig
    for bounds in [(.02,.3),(.3,.9)]:
        op=minimize_scalar(lambda t:-score(t),bounds=bounds,method='bounded')
        print('optimum',name,op.x,score(op.x))
K=2*np.eye(6)-np.roll(np.eye(6),1,axis=0)-np.roll(np.eye(6),-1,axis=0)
lam,U=np.linalg.eigh(K);V=np.random.default_rng(7).normal(size=(6,6));V=(V+V.T)/2
D=2/(np.sqrt(1+2*lam[:,None]/M)+np.sqrt(1+2*lam[None,:]/M))
eps=1e-5;ev,EU=np.linalg.eigh(K+eps*V)
num=(EU@np.diag(f(ev))@EU.T-U@np.diag(f(lam))@U.T)/eps
err=np.max(abs(U.T@num@U-D*(U.T@V@U)))
print('Frechet max err',err)
assert err<2e-5
