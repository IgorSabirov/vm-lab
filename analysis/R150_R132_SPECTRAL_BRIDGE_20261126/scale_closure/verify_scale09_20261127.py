"""Independent replay of selected SCALE-09/10/11 mathematical controls.
Requires numpy and scipy. Output is numeric evidence, not physical acceptance.
"""
import json
from math import pi, sqrt
import numpy as np
from scipy.optimize import brentq

def matrix(N,u=2,g=1,h=.5,phi=pi,d=None,h2=.5):
    # Exact real seam for the two declared phases only.
    if phi not in (0,pi):
        raise ValueError("phi must be 0 or pi")
    A=np.zeros((N+1,N+1))
    A[0,0]=-u
    A[1:,1:]=2*N*N*np.eye(N)
    j=np.arange(1,N)
    A[j,j+1]=A[j+1,j]=-N*N
    A[1,N]=A[N,1]=N*N if phi==pi else -N*N
    A[1,1]-=g*N
    A[0,1]=A[1,0]=h*sqrt(N)
    if d is not None:
        k=1+round(N*d)
        if not 1<k<=N or abs((k-1)/N-d)>1e-12:
            raise ValueError("need distinct exact marked lattice contact")
        A[0,k]=A[k,0]=h2*sqrt(N)
    return A

def determinant(E,u=2,g=1,h=.5):
    k=sqrt(abs(E))
    c=np.cos(k/2) if E>=0 else np.cosh(k/2)
    s=(np.sin(k/2) if E>=0 else np.sinh(k/2))/(2*k) if k else .25
    return (E+u)*c-(g*(E+u)-h*h)*s

def levels(N,m):
    return 4*N*N*np.sin(np.array(m)*pi/(2*N))**2

def ratio(v):
    return float((v[2]-v[1])/(v[1]-v[0]))

def main():
    roots=np.array([brentq(determinant,-4,-2)]+[
        brentq(determinant,((m-1)*pi)**2+1e-6,(m*pi)**2)
        for m in (1,3,5,7,9,11)])
    conv=[]
    for N in (12,24,48,96,192,384,768):
        ev=np.linalg.eigvalsh(matrix(N))
        # Validated ordering for this specific test (not a universal matcher).
        assert np.max(np.abs(ev[[2,4,6]]-levels(N,[1,3,5])))<1e-7
        err=ev[[0,1,3,5]]-roots[:4]
        conv.append(dict(N=N,first8=ev[:8].tolist(),error=err.tolist(),N2_abs_error=(abs(err)*N*N).tolist()))
    assert np.allclose(conv[-1]["N2_abs_error"],conv[-2]["N2_abs_error"],rtol=.002,atol=1e-6)
    sign=[]
    for phi in (pi,0):
        for d in (.25,1/3,.4,.5):
            e1=np.linalg.eigvalsh(matrix(120,g=0,phi=phi,d=d))
            e2=np.linalg.eigvalsh(matrix(120,g=0,phi=phi,d=d,h2=-.5))
            delta=float(max(abs(e1-e2)))
            if phi==pi and d==.5:
                assert delta<1e-7
            else:
                assert delta>.01
            sign.append(dict(phi=phi,d=d,max_delta=delta))
    ev=np.linalg.eigvalsh(matrix(48))
    assert np.max(abs(ev-np.linalg.eigvalsh(matrix(48,h=-.5))))<1e-9
    dark=[]
    for h2 in (.5,-.5):
        N=96
        A=matrix(N,g=0,d=.5,h2=h2)
        w,v=np.linalg.eigh(A)
        nod=levels(N,[1])[0]
        i=int(np.argmin(abs(w-nod))); p=v[:,i]
        coherent=float(abs((p[1]+p[1+N//2])/sqrt(2))**2)
        unshifted=sum(np.min(abs(wi-levels(N,np.arange(1,N,2))))<1e-8 for wi in w)
        assert abs(w[i]-nod)<1e-8 and abs(p[0])<1e-8 and unshifted==N//2
        assert abs(coherent-(0 if h2>0 else 2/N))<1e-9
        dark.append(dict(h2=h2,energy=float(w[i]),port_abs=float(abs(p[0])),coherent=coherent,unshifted=int(unshifted)))
    crossings=[]
    for h0 in (.02,.05,.2,.5):
        w=np.linalg.eigvalsh(matrix(400,u=-pi*pi,g=0,h=h0))
        crossings.append(dict(h=h0,levels=w[:3].tolist(),gap=float(w[2]-w[0]),leading=2*sqrt(2)*h0))
    R=[]
    for N in (6,7,8,10,12,16,64,128,1000):
        ra=ratio(levels(N,[1,3,5])); rp=ratio(levels(N,[2,4,6]))
        assert abs(ra-2*np.cos(2*pi/N))<1e-10
        assert abs(rp-ra+1/(1+ra))<1e-10
        R.append(dict(N=N,anti=ra,periodic=rp))
    fuhrer=[]
    for width in (30,65):
        a=.038099821114859614/.067; C=2*pi*132.485
        en=a*(np.arange(1,20)*pi/width)**2
        count=lambda mu: 2*C/pi*np.sqrt(np.maximum(mu-en,0)/a).sum()
        mu=brentq(lambda mu:count(mu)-200,0,.1)
        steps=2*a*np.sqrt((mu-en[en<mu])/a)*2*pi/C*1e6
        distinct=1/sum(1/steps)
        assert abs(count(mu)-200)<1e-6
        fuhrer.append(dict(width_nm=width,mu_meV=mu*1000,count=count(mu),
          orbital_steps_ueV=steps.tolist(),distinct_mean_ueV=distinct,mean_state_ueV=distinct/4))
    x=[]
    M=15.85; J=3.086227
    for k in ([1,3,5],[2,4,6]):
        e=4*J*np.sin(np.array(k)*pi/12)**2
        er=np.sqrt(M*M+2*M*e)-M
        x.append(dict(m=k,E_nr_keV=e.tolist(),E_rel_keV=er.tolist(),ratio_rel=ratio(er)))
    print(json.dumps(dict(scope="mathematical and conditional model checks only",physical_acceptance=False,
        roots=roots.tolist(),convergence=conv,relative_sign=sign,dark=dark,anticrossing=crossings,
        ratios=R,fuhrer=fuhrer,target_X=x),indent=2))

if __name__=="__main__":
    main()
