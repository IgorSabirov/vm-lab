"""Hessians on the three hot knots and Coulomb sensitivity of the early weak rates."""
from dataclasses import replace
from functools import lru_cache
from itertools import combinations,product
import os
import numpy as np
from scipy.special import expit,roots_legendre
from runner import BENCH,Config,History,net
os.environ['R150_BENCH']=str(BENCH)
from weak_pilot import early, ME, Q0
from bench import KNOTS

ALPHA=1/137.035999
TOL=1e-10


def hot_name(v):
    return 'hot_'+'_'.join(f'{i if i else 0:g}' for i in v)


def manifest():
    jobs={hot_name((0,0,0)):('hot',[0,0,0])}
    for step in (.5,1.):
        for i in range(3):
            for a in (-step,step):
                v=np.zeros(3);v[i]=a
                jobs[hot_name(v)]=('hot',v.tolist())
        for i,j in combinations(range(3),2):
            for a,b in product((-step,step),repeat=2):
                v=np.zeros(3);v[i]=a;v[j]=b
                jobs[hot_name(v)]=('hot',v.tolist())
    for coulomb in (False,True):
        for lifetime in (False,True):
            for sign in (-1,1):
                jobs[f'weak_{int(coulomb)}_{int(lifetime)}_{sign}']=('weak',(coulomb,lifetime,.0003*sign))
    return jobs


@lru_cache(maxsize=None)
def quadrature(n):
    return roots_legendre(n)


def interval(a,b,n):
    x,w=quadrature(n)
    return a+(b-a)*(x+1)/2, w*(b-a)/2


def factor(e):
    velocity=np.sqrt((e-ME)*(e+ME))/e
    eta=2*np.pi*ALPHA/velocity
    return eta/(-np.expm1(-eta))


def rate(q,T,Tnu,sign,coulomb,n=100,vac=False):
    # Decay at zero temperature samples only the electron-proton final state.
    u,w=interval(0,np.sqrt(q-ME),n)
    e=ME+u*u
    weights=2*u*w
    if not vac:
        ext,w2=interval(q,q+50*max(T,Tnu),n)
        e=np.r_[e,ext];weights=np.r_[weights,w2]
    phase=e*np.sqrt((e-ME)*(e+ME))
    ff=factor(e) if coulomb else np.ones_like(e)
    if vac:
        return np.dot(weights,phase*(q-e)**2*ff)
    def chi(signed):
        k=signed-sign*q
        return k*k*expit(-k/Tnu)*expit(signed/T)
    pos,neg=(ff,1.) if sign==1 else (1.,ff)
    return np.dot(weights,phase*(chi(e)*pos+chi(-e)*neg))


def case(kind,params):
    h=History()
    if kind=='hot':
        y=np.zeros(len(KNOTS));y[3:6]=np.asarray(params)*.001
        profile=np.c_[np.r_[1e-5,KNOTS,30.],np.r_[0.,y,0.]]
        return net(h,Config(rtol=TOL),profile=profile)
    coulomb,lifetime,delta=params
    for t in (.2,.4,.7,1.):
        np.testing.assert_allclose(rate(Q0,t,t,-1,coulomb)/rate(Q0,t,t,1,coulomb),np.exp(-Q0/t),rtol=2e-10)
        for sign in (-1,1):
            np.testing.assert_allclose(rate(Q0+delta,t,t,sign,coulomb),rate(Q0+delta,t,t,sign,coulomb,160),rtol=3e-8)
    for i,(t,shape) in enumerate(zip(h.tw,early(h.tw))):
        if shape==0:continue
        q=Q0+delta*shape
        tn=np.interp(np.log(t),h.logT[::-1],h.Tnu[::-1])
        norm=rate(Q0,0,0,1,coulomb,vac=True)/rate(q,0,0,1,coulomb,vac=True) if lifetime else 1.
        for sign,table in [(1,h.wp),(-1,h.wn)]:
            table[i]*=norm*rate(q,t,tn,sign,coulomb)/rate(Q0,t,tn,sign,coulomb)
    return net(h,Config(rtol=TOL))
