"""R149/R150 operator-identifiability checks. Python, numpy/scipy/mpmath.
All energies in J=1 units except optical depths. No physical data.
"""
import numpy as np
import mpmath as mp
from scipy.linalg import eigh, eigh_tridiagonal
from scipy.optimize import brentq
from scipy.special import logsumexp
N=6; M=15.85/3.08622708259639589; pi=np.pi
def S(phi):
    x=np.roll(np.eye(N,dtype=complex),1,axis=0)
    x[0,-1]=np.exp(1j*phi)
    assert np.linalg.norm(x.conj().T@x-np.eye(N))<1e-12
    assert np.linalg.norm(np.linalg.matrix_power(x,N)-np.exp(1j*phi)*np.eye(N))<1e-12
    return x
def K(phi):
    x=S(phi); return 2*np.eye(N)-x-x.conj().T
def f(x): return np.sqrt(M*M+2*M*x)-M
def matf(A):
    e,u=eigh(A); return (u*f(e))@u.conj().T
def hf(phi,j):
    x=S(phi)
    return 2*sum(j)*np.eye(N,dtype=complex)-sum(a*(np.linalg.matrix_power(x,r)+np.linalg.matrix_power(x.conj().T,r)) for r,a in enumerate(j,1))
q=np.linspace(0,2*pi,65536,endpoint=False)
j=np.array([-np.mean(f(2*(1-np.cos(q)))*np.cos(r*q)) for r in range(1,25)])
assert np.all(j[:12]>0)
print("M, Jt1, ratios, eta limit",M,j[0],j[:12]/j[0],np.exp(-np.arccosh(1+M/4)))
for R in [1,3,6,12,24]:
    err=max(np.linalg.norm(matf(K(phi))-hf(phi,j[:R]),ord=2) for phi in np.linspace(0,2*pi,129))
    print("equivalence",R,err)
    if R==24: assert err<1e-12
for phi in [.37,1.2,pi]:
    b=np.roll(np.eye(N),1,axis=0); b[0,-1]=np.cos(phi)
    print("real-cast control",phi,np.linalg.norm(b.T@b-np.eye(N),ord=2),max(abs(eigh(K(phi),eigvals_only=True)-eigh(2*np.eye(N)-b-b.T,eigvals_only=True))))
B=np.zeros((7,7),complex); B[0,1]=B[1,0]=1
def extend(A):
    H=np.zeros((7,7),complex); H[1:,1:]=A; return H
def Df(H,V):
    e,u=eigh(H); s=np.sqrt(1+2*e/M)
    return u@(2/(s[:,None]+s[None,:])*(u.conj().T@V@u))@u.conj().T
jo=[1,-.0895673535,.0130843932,-.0023203345,.0004567043,-.0000959441]
for name,F in [('NN',K),('Opt R6',lambda phi:hf(phi,jo))]:
    for phi in [0,pi,.37]:
        H=extend(F(phi)); D=Df(H,B); eps=1e-5
        err=np.max(abs((matf(H+eps*B)-matf(H))/eps-D))
        cent=np.max(abs((matf(H+eps*B)-matf(H-eps*B))/(2*eps)-D))
        hmax=np.sqrt((M/2)/np.linalg.inv(F(phi)+M/2*np.eye(N))[0,0].real)
        print("port",name,phi,D[0,1:],"forward/central/domain",err,cent,hmax)
        assert err<1e-6 and cent<1e-9
    for h in [.1,.5,1]:
        assert abs(matf(extend(F(pi))+h*B)[0,4])<1e-12
z7=np.exp(-eigh(extend(K(0)),eigvals_only=True)/.3).sum()
zr=1+np.exp(-eigh(K(0),eigvals_only=True)/.3).sum()
assert abs(z7-zr)<1e-13
print("canonical one particle",z7,zr)
def Hch(phi,m,amp=-.1):
    H=np.zeros((N,N),complex)
    for i in range(N):
        for r,a in [(1,1)]+([(2,amp)] if i in [0,2,4][:m] else []):
            z=-a*np.exp(1j*r*phi/N); H[(i+r)%N,i]+=z; H[i,(i+r)%N]+=z.conjugate()
    return H
def moments(a,b,n=6):
    return [np.trace(np.linalg.matrix_power(b,p)-np.linalg.matrix_power(a,p)).real for p in range(1,n+1)]
for m in range(4):
    ds=moments(Hch(0,m),Hch(pi,m)); p=next(i+1 for i,x in enumerate(ds) if abs(x)>1e-9)
    print("chord",m,p,ds[p-1]); assert p==6-m
ds=moments(hf(0,[1,1,1,-.5]),hf(pi,[1,1,1,-.5]))
print("cancellation",ds[:4]); assert np.allclose(ds[:3],[0,0,78])
mp.mp.dps=60
for t in [.5,1,2,5,80/3.08622708259639589]:
    tt=mp.mpf(t)
    z0=sum(mp.exp(-4*mp.sin(mp.pi*k/N)**2/tt) for k in range(N))
    zp=sum(mp.exp(-4*mp.sin(mp.pi*(k+mp.mpf('.5'))/N)**2/tt) for k in range(N))
    C=1-(1+zp)/(1+z0); lim=tt/4*mp.log(1+mp.mpf('.1')*abs(C)*(1+z0)/zp)
    print("winding scalar residual",t,mp.nstr(lim,16))
j2=mp.mpf('-.0895673535')
def c2(t):
    def Z(phi):
        return 1+sum(mp.exp(-2*(1-mp.cos((2*mp.pi*k+phi)/N)+j2*(1-mp.cos(2*(2*mp.pi*k+phi)/N)))/t) for k in range(N))
    return 1-Z(mp.pi)/Z(0)
for bracket in [(.4,.5),(1.4,1.6),(14,16)]:
    root=mp.findroot(c2,bracket); print("finite C zero",mp.nstr(root,25))
for t in [200,500,1000,2000]:
    n=np.arange(-150,151); a=(2*pi*n)**2+2*(1-np.cos(pi*n)); b=(2*pi*n+pi)**2+2*(1-np.cos((2*pi*n+pi)/2))
    c=-np.expm1(logsumexp(-b/t)-logsumexp(-a/t)); print("nonlocal continuum",t,t*t*c)
def band(s,k,cut=18):
    n=np.arange(-cut,cut+1)
    return eigh_tridiagonal((2*n+k)**2+s/2,np.full(2*cut,-s/4),select='i',select_range=(0,0))[0][0]
def optj(s,nk=512,nmax=12):
    k=np.linspace(-1,1,nk,endpoint=False); E=np.array([band(s,x) for x in k])
    return -np.mean(E[None,:]*np.cos(np.arange(1,nmax+1)[:,None]*pi*k[None,:]),axis=1)
for lim in [.01,.001,.0001]:
    s=brentq(lambda s:abs(optj(s,nmax=2)[1]/optj(s,nmax=2)[0])-lim,3,50)
    print("depth",lim,s,optj(s,nmax=2)[0])
s=brentq(lambda s:optj(s,nmax=1)[0]-1/pi**2,.5,12); jj=optj(s,1024,12)
d1,d2=moments(hf(0,jj/jj[0]),hf(pi,jj/jj[0]),2); tx=abs(d2)/(2*abs(d1))
print("thermal numerator crossover",d1,d2,tx,np.exp(-20.41685537958862/tx))
