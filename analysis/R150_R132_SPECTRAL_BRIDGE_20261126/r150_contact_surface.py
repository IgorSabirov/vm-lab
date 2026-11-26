"""Independent audit of the R150 layer B contact at source commit 23c94f1473174500179c2fa454d773e2bf7686da. J=1, temperature t=T/J.
No abundance data; explicit distinction between isolated and direct-sum carriers.
"""
import json, math
import numpy as np
from scipy.linalg import eigvalsh
from scipy.optimize import minimize_scalar, brentq
from scipy.special import logsumexp, ive
from math import pi

V=.1*.07251310823341744/.1185

def eigs(n,v,sign):
    S=np.zeros((n,n)); S[(np.arange(n)+1)%n,np.arange(n)]=1
    S[0,-1]=sign
    A=S+S.T; A[0,0]+=v
    # energies relative to -2J; fixed port is -v
    return np.r_[-v,2-eigvalsh(A,check_finite=False)]

def gap(n,v):
    if v>=0:return 0.
    w=-v
    k=brentq(lambda k:2*np.sin(k)*np.tan(n*k/2)-w,0,np.nextafter(pi/n,0),xtol=1e-15)
    e0=4*np.sin(k/2)**2
    ea=min(w,4*np.sin(pi/(2*n))**2)
    return ea-e0

def logratio(ep,em,t):
    # subtract common zero-temperature ground energy before forming log differences
    b=min(ep.min(),em.min())
    return logsumexp(-(ep-b)/t)-logsumexp(-(em-b)/t)

def peak(n,v,mode='iso'):
    ep,em=eigs(n,v,1),eigs(n,v,-1)
    if mode!='iso':
        # contact on all active layers in both preparations; passive unaffected
        p=4*np.sin(pi*np.arange(n+1)/(n+1))**2
        p=np.tile(p,2*n+1)
        ep,em=np.r_[p,np.tile(ep,n-1)], np.r_[p,np.tile(em,n-1)] if mode=='all' else np.r_[p,np.tile(ep,n-2),em]
        # ep referenced in RHS before reassignment
    def f(logt):
        t=np.exp(logt)/n**2
        return t*logratio(ep,em,t)
    grid=np.linspace(-14,math.log(100*n),240)
    vals=np.array([f(a) for a in grid]); i=int(np.argmax(vals))
    cand=[(0.,float(em.min()-ep.min())),(float(np.exp(grid[i])/n**2),float(vals[i]))]
    for j in range(1,len(grid)-1):
        if vals[j]>vals[j-1] and vals[j]>vals[j+1] and vals[j]>max(vals)*.999:
            r=minimize_scalar(lambda x:-f(x),bounds=(grid[j-1],grid[j+1]),method='bounded',options={'xatol':1e-11})
            cand.append((float(np.exp(r.x)/n**2),float(-r.fun)))
    t,m=max(cand,key=lambda x:x[1]); g=cand[0][1]
    if abs(m-g)<2e-13: t,m=0.,g
    return dict(N=n,v=v,mode=mode,t_peak=t,peak=m,gap=g,N2_peak=n*n*m,N3_peak=n**3*m)

def theta(y):
    k=np.arange(-100,101); return np.exp(-4*pi*pi*k*k/y).sum(),np.exp(-4*pi*pi*(k+.5)**2/y).sum()

def port_phi(y,u):
    k=np.arange(-100,101); r=u/y
    p=logsumexp(-4*pi*pi*k*k/y); a=logsumexp(-4*pi*pi*(k+.5)**2/y)
    return y*(np.logaddexp(r,p)-np.logaddexp(r,a))

def ppeak(u):
    grid=np.geomspace(.0001,500,650); vals=np.array([port_phi(y,u) for y in grid]); j=int(vals.argmax())
    g=max(0.,min(-u,pi*pi)); candidates=[(0.,g),(grid[j],vals[j])]
    if 0<j<len(grid)-1:
        r=minimize_scalar(lambda y:-port_phi(y,u),bounds=(grid[j-1],grid[j+1]),method='bounded');candidates.append((r.x,-r.fun))
    y,m=max(candidates,key=lambda x:x[1]);
    if m-g<1e-11:y,m=0.,g # numerical resolution only; see analytical boundary and high-precision witness
    return dict(u=u,y_peak_numeric=float(y),coefficient=float(m),zeroT=g,analytic_location='zeroT' if u<=-pi*pi/2 else 'interior',numeric_unresolved=bool(y==0 and u>-pi*pi/2))

# Strong repulsive-contact asymptotic at fixed y=N^2 T/J; perturbation of Dirichlet levels.
def strong(y,mode):
    n=np.arange(1,200); z=np.exp(-pi*pi*n*n/y); d=z.sum(); a,b=theta(y)
    s=np.sum((-1.)**(n+1)*n*n*z)
    if mode=='iso': return s/d if d else 1.
    if mode=='all': return s/(2*a+d)
    return s/(2*a+d) # same leading coefficient; one layer has one extra N dilution

def strong_peak(mode):
    r=minimize_scalar(lambda ly:-strong(np.exp(ly),mode),bounds=(-2,5),method='bounded'); y=np.exp(r.x)
    return dict(mode=mode,y=0. if mode=='iso' else float(y),normalized_peak=1. if mode=='iso' else float(-r.fun),coefficient=float((1. if mode=='iso' else -r.fun)*8*pi*pi/V),method='analytical bound S<=D' if mode=='iso' else 'scalar optimization of limiting function')

# Exact positive-winding series for positive v. Use powers of a nonnegative
# 2N-cycle matrix with v at both copies of the impurity. The off-block trace
# isolates odd winding. Iterate on dense columns via O(N^2) roll per power.
# To avoid high precision cancellations, rescale A by h=2+v, substochastic.
def pos_series(n,v):
    h=2+v; B=np.eye(2*n)[:,:n]; idx=np.arange(n)
    # coefficient a_k = 2 tr[(A_double/h)^k]_{opposite,original}
    # k>=n, probability of Poisson count with mean h*beta gives e^-h beta deltaZ
    kap=np.arccosh(h/2); beta0=n/(2*np.sinh(kap)); kmax=int(max(n+100, h*beta0*4+100))
    from scipy.special import gammaln
    out=np.zeros(kmax+1)
    for k in range(1,kmax+1):
        B=(np.roll(B,1,axis=0)+np.roll(B,-1,axis=0))/h + (v/h)*((np.arange(2*n)%n==0)[:,None])*B
        out[k]=2*np.sum(B[idx+n,idx])
    # use positive series for delta; denominator exact eigenvalues, including port
    ep=eigs(n,v,1); ep=ep+v # energies relative to port
    k=np.arange(n,kmax+1); coeff=out[n:]; good=coeff>0; k=k[good]; logcoef=np.log(coeff[good])-gammaln(k[good]+1)
    def logm(b):
        mu=h*b
        ld=logsumexp(logcoef+k*np.log(mu)-mu)
        lz=logsumexp(-b*ep)
        # M = -log(1-delta/Z+)/beta
        r=np.exp(ld-lz)
        return math.log(-math.log1p(-r)/b) if r>1e-200 else ld-lz-np.log(b)
    rr=minimize_scalar(lambda x:-logm(np.exp(x)),bounds=(np.log(beta0/2),np.log(beta0*2)),method='bounded',options={'xatol':1e-10})
    beta=np.exp(rr.x); logpeak=-rr.fun
    pref=8*np.sinh(kap)/np.sqrt(2*pi/np.tanh(kap))/(1-v/(2*np.sinh(kap)))
    # truncation upper bound on tail e^-mu sum a_k Pois <= 2n P(Pois>kmax)
    from scipy.stats import poisson
    tail=poisson.logsf(kmax,h*beta)+np.log(2*n)
    return dict(N=n,v=v,beta_peak=float(beta),beta_saddle=float(beta0),log_peak=float(logpeak),rate=float(-logpeak/n),kappa=float(kap),pref_ratio=float(np.exp(logpeak+n*kap)*np.sqrt(n)/pref),kmax=kmax,log_tail_bound=float(tail) if np.isfinite(tail) else None)


def repulsive_low(n,w,y,mode):
    # Dimensionless y=N^2 T/J, retain all thermally relevant levels. The omitted
    # n>=81 levels have weight <= exp(-4*80^2/y) by the band dispersion bound.
    j=np.arange(1,min(n,81)); exact=4*n*n*np.sin(j*pi/(2*n))**2
    q=np.array([brentq(lambda q:2*np.sin(q/n)*np.tan((q-(k-1)*pi)/2)-w,
                       (k-1)*pi,k*pi-1e-10,xtol=1e-13) for k in j])
    shifted=4*n*n*np.sin(q/(2*n))**2
    z=np.exp(-exact/y); d=z*np.expm1((exact-shifted)/y)
    zp=z.sum()+d[j%2==1].sum()+np.exp(-w*n*n/y)
    dz=np.sum(np.where(j%2==1,d,-d))
    if mode=='iso': r=dz/zp
    else:
        k=np.arange(n+1); pp=np.exp(-4*n*n*np.sin(pi*k/(n+1))**2/y).sum()
        zfull=(2*n+1)*pp+(n-1)*zp
        r=(n-1 if mode=='all' else 1)*dz/zfull
    return -y/n**2*np.log1p(-r)

def low_peaks(n,w):
    out=[]
    for m in ('all','one'):
        r=minimize_scalar(lambda y:-repulsive_low(n,w,y,m),bounds=(2,30),method='bounded',options={'xatol':1e-8})
        out.append(dict(N=n,mode=m,y_peak=float(r.x),peak=float(-r.fun),scaled=float(-r.fun*n**(3 if m=='all' else 4))))
    return out

def independent_contacts(n,vp,vc,t):
    ep,em=eigs(n,vc,1),eigs(n,vc,-1); ep[0]=em[0]=-vp
    return t*logratio(ep,em,t)

def contact_sweep():
    n=6;t=.08/.1185
    rows=[]
    for vp,vc in [(0,0),(-V,0),(0,-V),(-V,-V),(V,V),(-1,-1),(-10,-10),(-100,-100)]:
        m=independent_contacts(n,vp,vc,t)
        rows.append(dict(v_port=vp,v_cycle=vc,contrast=float(-np.expm1(-m/t)),M_MeV=float(.1185*m)))
    r=minimize_scalar(lambda w:-independent_contacts(n,-np.exp(w),-np.exp(w),t),bounds=(-10,10),method='bounded')
    m=-r.fun
    return dict(rows=rows,negative_contact_peak_v=float(-np.exp(r.x)),contrast=float(-np.expm1(-m/t)),M_MeV=float(.1185*m))

def high_precision_witness():
    import mpmath as mp
    mp.mp.dps=90
    w=mp.mpf('4.9');y=mp.mpf('.09')
    p=mp.fsum(mp.exp(-4*mp.pi**2*k*k/y) for k in range(-10,11))
    a=mp.fsum(mp.exp(-4*mp.pi**2*(k+mp.mpf('.5'))**2/y) for k in range(-10,11))
    val=y*mp.log((p+mp.exp(-w/y))/(a+mp.exp(-w/y)))
    return {'u':-4.9,'y':.09,'excess_over_zeroT':mp.nstr(val-w,30)}


def checks():
    det_error=0.; ncases=0; gap_error=0.; walk_cases=0
    for n in (2,4,6,14,30,60):
        for v in (-2.,-V,0.,V,.5,2.):
            z=3.+abs(v); kap=np.arccosh(z/2)
            for sign in (-1,1):
                e=eigs(n,v,sign)[1:]
                logdet=np.log(z-2+e).sum()
                pred=2*np.cosh(n*kap)-2*sign-v*np.sinh(n*kap)/np.sinh(kap)
                det_error=max(det_error,abs(logdet-np.log(pred)));ncases+=1
            if v<0:
                gap_error=max(gap_error,abs(gap(n,v)-(eigs(n,v,-1).min()-eigs(n,v,1).min())))
        if n<=14:
            for v in (-2,0,2):
                # With diagonal shift -min(v,0) the two integer matrices differ
                # only at the seam. Count the first flux-sensitive closed walks.
                mats=[]
                for sign in (-1,1):
                    S=np.zeros((n,n),dtype=object);S[(np.arange(n)+1)%n,np.arange(n)]=1;S[0,-1]=sign
                    A=S+S.T;A[0,0]+=v;A+=np.eye(n,dtype=object)*max(0,-v);mats.append(A)
                powers=[np.eye(n,dtype=object) for A in mats]
                for k in range(1,n+1):
                    powers=[P@A for P,A in zip(powers,mats)]
                    assert np.trace(powers[1])-np.trace(powers[0])==(4*n if k==n else 0)
                walk_cases+=1
    low_error=0.
    for n in (128,200):
        for y in (2.,5.,10.,20.,30.):
            ep,em=eigs(n,-V,1),eigs(n,-V,-1);t=y/n**2
            for m in ('iso','all','one'):
                if m=='iso':p,a=ep,em
                else:
                    pas=np.tile(4*np.sin(pi*np.arange(n+1)/(n+1))**2,2*n+1)
                    p=np.r_[pas,np.tile(ep,n-1)]
                    a=np.r_[pas,np.tile(em,n-1)] if m=='all' else np.r_[pas,np.tile(ep,n-2),em]
                ref=t*logratio(p,a,t)
                low_error=max(low_error,abs(ref-repulsive_low(n,V,y,m)))
    assert det_error<1e-10 and gap_error<1e-12 and low_error<1e-12
    return dict(determinant_cases=ncases,max_logdet_error=det_error,max_ground_gap_error=gap_error,walk_cases=walk_cases,max_low_spectral_vs_dense_M_over_J_error=low_error)

if __name__=='__main__':
    data={'definition':'A=S+S.T+vC; same contact in both holonomies; no BBN data', 'v_bench':V}
    data['bench']=[peak(n,v) for n in (6,8,10,12,14,30,60,100,200,500) for v in (-V,0,V) if v<=0 or n<=60]
    data['port_scaling']=[ppeak(u) for u in (-20,-10,-8,-6,-5.1,-5,-4.95,-4.9348022,-4.9,-4,-2,0,2,10,50,100)]
    data['port_finite']=[peak(n,u/n**2) for n in (32,128,512) for u in (-6,-4,2,10)]
    data['repulsive_continuum']=[peak(n,g/n) for n in (32,128,512) for g in (-1.,-4.,-16.,-64.)]
    data['negative_gap']=[{'N':n,'N3gap':n**3*gap(n,-V)} for n in (100,500,1000,5000,20000,100000)]
    # avoid massive direct-sum arrays: use moderate lengths for brute force carrier check
    data['carrier']=[peak(n,-V,m) for n in (14,30,60,100,200) for m in ('all','one')]
    data['strong_limits']=[strong_peak(m) for m in ('iso','all')]
    data['repulsive_large_carrier']=[r for n in (200,500,1000,2000,5000,20000) for r in low_peaks(n,V)]
    data['contact_sweep']=contact_sweep()
    data['near_boundary_witness']=high_precision_witness()
    data['checks']=checks()
    data['positive']=[pos_series(n,v) for v in (V,.5,2.) for n in (16,32,64,128,256)]
    print(json.dumps(data,indent=2,allow_nan=False))
