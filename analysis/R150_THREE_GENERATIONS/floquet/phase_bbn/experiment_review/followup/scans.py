"""Predeclared temperature, sign, contact, threshold, memory and strict precision controls."""
from dataclasses import replace
from functools import lru_cache
import json
import numpy as np
from runner import BASE, History, net

STANDARD=(.06,.08)
TOL=1e-10


class Window(History):
    def __init__(self,amp,lo,hi):
        super().__init__()
        self.amp,self.lo,self.hi=amp,lo,hi
        assert self.names[0]=='npdg'

    def forward_rates(self,T):
        rates=super().forward_rates(T)
        if self.amp and self.lo<T<self.hi:
            phase=np.log(T/self.lo)/np.log(self.hi/self.lo)
            rates[0]*=1+self.amp*np.sin(np.pi*phase)**2
        return rates


def spec(amp=0.,window=STANDARD,lam=1.,reverse=True,power=0,rtol=TOL,tau=50.,clock=1.):
    # A zero amplitude has the identical dynamical meaning at every window.
    lo,hi=window if amp else STANDARD
    return (float(amp),float(lo),float(hi),float(lam),bool(reverse),int(power),float(rtol),float(tau),float(clock))


def label(s):
    a,lo,hi,l,r,k,t,tau,c=s
    return f'a{a:g}_w{lo:g}-{hi:g}_l{l:g}_r{int(r)}_k{k}_tol{t:g}_tau{tau:g}_c{c:g}'


def four(amp,**kwargs):
    # The zero-contact arms always retain the same k, tolerance, and clocks as the live arms.
    scale=kwargs.pop('lam',1.)
    return [spec(amp,lam=l,reverse=r,**kwargs) for l,r in [(scale,True),(scale,False),(0.,True),(0.,False)]]


@lru_cache(maxsize=1)
def manifest():
    entries=set()
    for w,amplitudes in [(STANDARD,[-.2,-.1,-.05,0,.05,.1,.2]),((.04,.05),[-.1,.1]),((.10,.13),[-.1,.1])]:
        for a in amplitudes:
            entries.add(spec(a,window=w))
    for l in (-2,-1,-.5,0,.5,1,2):
        for a in (0.,.1): entries.update(four(a,lam=l))
    for k in (1,2,3):
        for a in (0.,.1): entries.update(four(a,power=k))
    for a in (0.,.1): entries.update(four(a,rtol=1e-11))
    for tau in (10.,50.,200.):
        for clock in (.1,1.,10.):
            for rev in (False,True):entries.add(spec(tau=tau,clock=clock,reverse=rev))
    return {label(k):k for k in sorted(entries)}


def case(a,lo,hi,l,r,k,tol,tau,clock):
    track=(k==0 and tol==TOL and l==1.)
    c=replace(BASE,lam=BASE.lam*l,reverse=r,forward_np_power=k,rtol=tol,tau=tau,graph_clock=clock)
    return net(Window(a,lo,hi),c,track=track)
