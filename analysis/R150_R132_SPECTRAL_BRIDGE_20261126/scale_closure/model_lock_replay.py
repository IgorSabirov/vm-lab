"""Small deterministic numerical review; no physical fit, no BBN.
Dependencies: numpy, scipy. Optical J_width is quarter lowest band width.
"""
import numpy as np
from scipy.optimize import brentq
from math import pi, sqrt, exp

def lowest(s,q,cut=16):
    n=np.arange(-cut,cut+1)
    h=np.diag((2*n+q)**2+s/2)
    h+=np.diag(np.full(2*cut,-s/4),1)+np.diag(np.full(2*cut,-s/4),-1)
    return np.linalg.eigvalsh(h)[0]

def jwidth(s,cut=16):
    return (lowest(s,1,cut)-lowest(s,0,cut))/4

def deep(s):
    return 4/sqrt(pi)*s**.75*exp(-2*sqrt(s))

for cut in (12,16,24):
    root=brentq(lambda s:jwidth(s,cut)-1/pi**2,0,20)
    print("optical cutoff/root/J_width(4.463)",cut,root,jwidth(4.463,cut))
    assert abs(root-3.40181871215)<1e-9
print("deep descending root",brentq(lambda s:deep(s)-1/pi**2,1,20))

N=6
k=np.arange(N)
for t in (.2,.3,.5,1,2):
    z0=np.exp(-4*np.sin(pi*k/N)**2/t).sum()
    zp=np.exp(-4*np.sin(pi*(k+.5)/N)**2/t).sum()
    free=1-zp/z0
    iso=1-(1+zp)/(1+z0)
    port0=1/(1+z0); portp=1/(1+zp)
    assert abs(iso-(1-port0/portp))<1e-14
    print("T/J, free, iso",t,free,iso)

for N in (6,8,128):
    for phi in (0,pi):
        q=(2*pi*np.arange(N)+phi)/N
        q=(q+pi)%(2*pi)-pi
        dev=np.zeros_like(q)
        np.divide(q*q-4*np.sin(q/2)**2,q*q,out=dev,where=abs(q)>1e-12)
        print("N phi first modes dev %",N,phi,100*dev[:min(N//2+1,4)])

g=np.array([-6.6662363418,-7.9090804682,-1.2428441264])
for target in (.1,.3):
    print("budget",target,target/np.linalg.norm(g),target/sqrt(3)/abs(g))
