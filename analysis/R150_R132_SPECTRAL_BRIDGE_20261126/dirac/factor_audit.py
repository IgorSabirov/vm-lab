"""Wrong-jump witness, finite heat trace, and KMS on the whole finite spectrum."""
import json
from pathlib import Path
import numpy as np
import mpmath as mp
from scipy.linalg import eigh, svdvals
from scipy.optimize import brentq
from scipy.special import roots_legendre
from check import operators,params,profile,shift,ground_shift


def jump_test():
    s=ground_shift(1.,2.,2.)
    k=np.sqrt(s)
    rootfn=lambda c:2-k*(np.tanh(k*c)+np.tanh(k*(1-c)))
    bracket=[float(rootfn(c)) for c in [.02,.499]]
    assert np.prod(bracket)>0
    cw=brentq(rootfn,1,2,xtol=1.e-14)
    rng=np.random.default_rng(3)
    nodes,weights=roots_legendre(96)
    x=(1+nodes)/2
    weights/=2
    coeff=rng.normal(size=7)+1j*rng.normal(size=7)
    f0=coeff.sum()
    pp=.7+.2j
    ans=[]
    for phi in [0.,np.pi,.63]:
        omega=2*np.pi*np.arange(-3,4)+phi
        e=coeff[:,None]*np.exp(1j*omega[:,None]*x)
        f=e.sum(axis=0); df=1j*omega@e
        alpha=np.sqrt(s-1)
        exact=(s-1)*abs(pp)**2+weights@(abs(df)**2+s*abs(f)**2)-2*abs(f0)**2+4*(pp.conjugate()*f0).real
        for c in [.5,cw,1-cw]:
            W=k*np.tanh(k*(x-c))
            residual=abs(alpha*pp+2/alpha*f0)**2+weights@abs(df-W*f)**2-exact
            expected=0 if c==.5 else 4/(s-1)*abs(f0)**2
            assert abs(residual-expected)<1.e-9
            ans.append([phi,c,float(residual),float(expected)])
    return {"s":s,"effective":2+4/(s-1),"wrong_interval_values":bracket,
            "right_center":cw,"forms":ans,
            "strong_port_s":ground_shift(5.,2.,.5)}


def polished_levels(seeds,n,sign):
    # Real finite characteristic equation at x=1-E/(2N²), with complex analytic continuation.
    def poly(E):
        theta=2*mp.asin(mp.sqrt(E)/(2*n))
        return ((E+1)*2*(mp.cos(n*theta)-sign)
                +(4-2*(E+1))*mp.sin(n*theta)/(n*mp.sin(theta)))
    levels=[]
    for seed in seeds:
        v=mp.mpf(float(seed))
        root=mp.findroot(poly,(v-mp.mpf('0.00001'),v+mp.mpf('0.00001')),tol=mp.mpf('1e-39'))
        assert abs(mp.im(root))<mp.mpf('1e-38') and abs(v-root)<mp.mpf('1.e-6')
        levels.append(mp.re(root))
    assert all(a<b for a,b in zip(levels,levels[1:]))
    return levels


def entropy():
    n=300
    spec=[]
    heat=[]
    for phi,sign in [(0.,1),(np.pi,-1)]:
        k,_=operators(n,phi,1.,2.,2.)
        ev=eigh(k.real,eigvals_only=True)
        spec.append(polished_levels(ev,n,sign))
        s,a,b,r=params(1.,2.,2.,n)
        w,_=profile(s,r,np.arange(n+1)/n,n)
        A=np.zeros_like(k); A[0,:2]=[a,b*np.sqrt(n)]
        A[1:,1:]=n*(np.diag(np.sqrt(w[:-1]/w[1:]))@shift(n,phi)-np.diag(np.sqrt(w[1:]/w[:-1])))
        heat_D=2*np.exp(-svdvals(A)**2/3).sum()
        heat_K=2*np.exp(-s/3)*np.exp(-ev/3).sum()
        assert abs(heat_K-heat_D)<1.e-9
        heat.append([sign,float(heat_D),float(heat_K)])
    def eta(x):
        t=abs(x)
        return mp.log1p(mp.exp(-t))+t*mp.exp(-t)/(1+mp.exp(-t))
    sN=-spec[0][0]
    rows=[]
    for denom in [3,6,12]:
        beta=mp.mpf(1)/denom
        dK=sum(eta(beta*l) for l in spec[0])-sum(eta(beta*l) for l in spec[1])
        dD=2*(sum(eta(beta*mp.sqrt(l+sN)) for l in spec[0])-sum(eta(beta*mp.sqrt(l+sN)) for l in spec[1]))
        rows.append({"denom":denom,"delta_S_K":mp.nstr(dK,32),"delta_S_D":mp.nstr(dD,32)})
    return {"N":n,"levels_per_phase":n+1,"precision_digits":mp.mp.dps,"sN":mp.nstr(sN,35),
            "KMS":rows,"independent_singular_value_heat":heat}


if __name__=="__main__":
    mp.mp.dps=55
    out={"jump":jump_test(),"entropy":entropy()}
    mp.mp.dps=75
    repeat=entropy()
    assert repeat["KMS"]==out["entropy"]["KMS"] and repeat["sN"]==out["entropy"]["sN"]
    out["precision_repeat"]={"digits":75,"all_printed_KMS_digits_agree":True}
    text=json.dumps(out,indent=2,allow_nan=False)
    Path(__file__).with_suffix(".json").write_text(text+"\n")
    print(text)
