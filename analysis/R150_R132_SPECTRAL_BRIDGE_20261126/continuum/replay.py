#!/usr/bin/env python3
"""R150 two-contact continuum: independent reconstruction + point hybridization.
No abundance fitting. Energies measured in E*=J/N^2, temperature y=T/E*.
Python 3, NumPy, SciPy. Source R150 graph.py commit 7d4f844b, report 26 Nov 2026.
"""
import json, math
from pathlib import Path
import numpy as np
from scipy.linalg import eigvalsh
from scipy.optimize import brentq
from scipy.special import logsumexp

PI=np.pi

def dense(N,u,g,h,phi):
    """Original signed shift in port-first order; h/N^1.5 in dimensionless adjacency."""
    S=np.zeros((N,N))
    S[(np.arange(N)+1)%N,np.arange(N)]=1
    S[0,-1]=1 if phi==0 else -1
    K=np.zeros((N+1,N+1))
    K[0,0]=-u
    K[1:,1:]=N*N*(2*np.eye(N)-S-S.T)
    K[1,1]-=g*N
    K[0,1]=K[1,0]=h*np.sqrt(N)
    return eigvalsh(K,check_finite=False)

def m(E,phi):
    """2 f'(0+)/f(0) for the contact-active parity sector."""
    if E==0:return 0. if phi==0 else -4.
    if E<0:
        k=np.sqrt(-E); t=np.tanh(k/2)
        return -2*k*t if phi==0 else -2*k/t
    q=np.sqrt(E)
    return 2*q*np.tan(q/2) if phi==0 else -2*q/np.tan(q/2)

def continuum(u,g,h,phi,kmax=18):
    """Independent continuum roots via strictly monotone Weyl function.
    Nodal modes appended separately; pole coincidences handled explicitly.
    Thermal truncation: at least kmax Dirichlet intervals per phase.
    """
    n=np.arange(kmax+1)
    ps=((2*n+1)*PI)**2 if phi==0 else ((2*n+2)*PI)**2
    nod=((2*(n+1))*PI)**2 if phi==0 else ((2*n+1)*PI)**2
    poles=list(ps); extra=[]
    if h==0:extra.append(-u)
    elif -u<ps[-1]:
        if np.any(np.isclose(ps,-u,rtol=0,atol=1e-10)):
            extra.append(-u) # shared pole: orthogonal combination at this energy
        else:poles.append(-u)
    poles=sorted(poles)
    def f(E):return m(E,phi)+g-(h*h/(E+u) if h else 0.)
    lo=-max(100.,2*abs(u)+10,4*(abs(g)+abs(h)+1)**2)
    while f(lo)>=0:lo*=2
    roots=[]
    for b in poles:
        hi=b-max(1e-10,abs(b)*2e-13)
        if f(lo)*f(hi)>=0:
            raise RuntimeError(('bracket',lo,hi,f(lo),f(hi),u,g,h,phi))
        roots.append(brentq(f,lo,hi,xtol=2e-12,rtol=1e-14))
        lo=b+max(1e-10,abs(b)*2e-13)
    return np.sort(np.r_[roots,nod,extra])

def stat(e,y):
    b=logsumexp(-e/y); p=np.exp(-e/y-b)
    U=float(p@e); S=float(b+U/y); C=float(p@((e-U)/y)**2)
    return np.array([b,U,S,C])

def mix(parts,y):
    """parts=(spectrum, multiplicity), stable direct sum without tiling."""
    logs=np.array([stat(e,y)[0]+np.log(w) for e,w in parts if w>0])
    ss=np.array([stat(e,y) for e,w in parts if w>0]); l=logsumexp(logs)
    p=np.exp(logs-l); U=p@ss[:,1]; S=l+U/y
    C=p@(ss[:,3]+((ss[:,1]-U)/y)**2)
    return np.array([l,U,S,C])

def dif(a,b,y):
    # F_pi - F_0, U_pi-U_0, S_pi-S_0, C_pi-C_0
    return np.array([y*(a[0]-b[0]),b[1]-a[1],b[2]-a[2],b[3]-a[3]])

def passive(N=None):
    if N is None:return (2*PI*np.arange(-30,31))**2
    return 4*N*N*np.sin(PI*np.arange(N+1)/(N+1))**2

def results(N,u,g,h,y):
    e0,ep=[dense(N,u,g,h,p) if N else continuum(u,g,h,p) for p in (0,PI)]
    a,b=stat(e0,y),stat(ep,y); c=passive(N)
    iso=dif(a,b,y)
    if N:
        p0=mix([(c,2*N+1),(e0,N-1)],y)
        pall=mix([(c,2*N+1),(ep,N-1)],y)
        # log1p avoids cancellation in diluted contrast; U/S/C from mixture.
        pone=mix([(c,2*N+1),(e0,N-2),(ep,1)],y)
        one=dif(p0,pone,y)*N
        one[0]=-N*y*np.log1p(-np.exp(a[0]-p0[0])*(-np.expm1(b[0]-a[0])))
        return iso,dif(p0,pall,y),one
    p0=mix([(c,2),(e0,1)],y); pall=mix([(c,2),(ep,1)],y)
    # First variation at changed fraction f=0; analytic one-limit moments.
    w0=np.exp(a[0]-p0[0]); wp=np.exp(b[0]-p0[0]); U=p0[1]
    U1=wp*(b[1]-U)-w0*(a[1]-U)
    F1=y*(w0-wp); S1=(U1-F1)/y
    C1=wp*(b[3]+((b[1]-U)/y)**2-p0[3])-w0*(a[3]+((a[1]-U)/y)**2-p0[3])
    return iso,dif(p0,pall,y),np.array([F1,U1,S1,C1])

def neg_count(u,g,h,phi):
    threshold=0. if phi==0 else 4.
    if u==0 and h!=0:return 1
    geff=g-h*h/u if u else g
    return int(u>0)+int(geff>threshold+1e-10)

def invert(levels):
    """Three contact-active levels (E,phase), no thermal or BBN data."""
    E=np.array([r[0] for r in levels]); M=np.array([m(e,p) for e,p in levels]);
    A=np.column_stack([M,E,np.ones_like(E)])
    u,g,c=np.linalg.solve(A,-E*M); h2=u*g-c
    return np.array([u,g,h2]),float(np.linalg.cond(A))

def run():
    out={"source_commit":"7d4f844bf08339963d8a775253ff5849224f1dcd","convention":"K in E*=J/N^2; h=signed point hybridization; N*one quantities", "baseline":[],"ground_table":[],"hybrid":[],"inertia":[],"inverse":[],"thermo":[],"ensembles":[]}
    # replay reported points, and g=4 threshold; compare both spectra and thermal functions
    for u,g,y in [(1,2,3),(5,5,3),(0,4,3),(0,0,5.1797551667),(-4,-2,3)]:
        ref=results(None,u,g,0,y)
        for N in (32,64,128,256):
            r=results(N,u,g,0,y)
            out['baseline'].append(dict(u=u,g=g,y=y,N=N,values=[x.tolist() for x in r],limit=[x.tolist() for x in ref],err_iso=abs(r[0][0]-ref[0][0])))
    # match attached ground energies with exact independent root equations
    for g in (-2,0,2,4,5):
        ep=[continuum(-100,g,0,p)[0] for p in (0,PI)]
        out['ground_table'].append(dict(g=g,e0=ep[0],epi=ep[1]))
    for u,g,h,y in [(1,2,.5,3),(1,2,1,3),(1,2,2,3),(1,2,4,3),(5,5,2,3),(-2,3,2,3),(0,4,1,3)]:
        ref=results(None,u,g,h,y)
        e0,ep=[continuum(u,g,h,p) for p in (0,PI)]
        for N in (32,64,128,256):
            r=results(N,u,g,h,y)
            er=max(np.max(np.abs(dense(N,u,g,h,p)[:6]-e[:6])) for p,e in [(0,e0),(PI,ep)])
            out['hybrid'].append(dict(u=u,g=g,h=h,y=y,N=N,values=[x.tolist() for x in r],limit=[x.tolist() for x in ref],err_iso=abs(r[0][0]-ref[0][0]),low6_max_error=er,lowest=[e0[:3].tolist(),ep[:3].tolist()]))
    # exact inertia, independent roots incl critical u=0 and near thresholds
    for u in (-5,-1,0,1,5):
        for g in (-2,0,2,4,6,10):
            for h in (0,.5,2,4):
                for p in (0,PI):
                    e=continuum(u,g,h,p,kmax=8); count=int(np.sum(e<-1e-8)); pred=neg_count(u,g,h,p)
                    assert count==pred,(u,g,h,p,e[:3],pred)
                    out['inertia'].append(dict(u=u,g=g,h=h,phi=p,negative=count,zeros=int(np.sum(abs(e)<1e-8))))
    # avoid shared poles and nodal roots for inverse; choose low active roots
    for u,g,h in [(1,2,.1),(1,2,.5),(1,2,1),(1,2,2),(1,2,4),(-2,3,2),(5,5,2)]:
        es=[]
        for p in (0,PI):
            for e in continuum(u,g,h,p,kmax=8)[:5]:
                if abs(e+u)<1e-8:continue
                if e>0 and abs(np.sin(np.sqrt(e)/2) if p==0 else np.cos(np.sqrt(e)/2))<1e-8:continue # nodal roots
                if abs(m(e,p)+g-h*h/(e+u))<1e-6:es.append((float(e),p))
        from itertools import combinations
        candidates=[]
        for rr in combinations(es,3):
            if len(set(p for e,p in rr))<2:continue
            try: rec,cond=invert(rr)
            except np.linalg.LinAlgError:continue
            candidates.append((cond,rr,rec))
        cond,rr,rec=min(candidates,key=lambda r:r[0])
        rng=np.random.default_rng(150132)
        errs=np.array([invert([(e+de,p) for (e,p),de in zip(rr,rng.normal(0,1e-4,3))])[0]-[u,g,h*h] for _ in range(1000)])
        out['inverse'].append(dict(u=u,g=g,h=h,levels=rr,recovered=rec.tolist(),condition=cond,rmse=np.sqrt(np.mean(errs*errs,axis=0)).tolist(),negative_h2_fraction=float(np.mean(errs[:,2]+h*h<0))))
    # response consistency: S=-dF/dy, U=F+y*S, C=dU/dy
    for u,g,h in [(1,2,0),(1,2,2),(-2,3,2)]:
        for y in (.3,1,3,10,30):
            r=results(None,u,g,h,y); d=1e-4*y
            rm,rp=[results(None,u,g,h,yy) for yy in (y-d,y+d)]
            for mode,v,a,b in zip(('iso','all','one'),r,rm,rp):
                out['thermo'].append(dict(u=u,g=g,h=h,y=y,mode=mode,F=v[0],U=v[1],S=v[2],C=v[3],entropy_res=abs(v[2]+(b[0]-a[0])/(2*d)),energy_res=abs(v[1]-v[0]-y*v[2]),heat_res=abs(v[3]-(b[1]-a[1])/(2*d))))
    # fixed fraction changed, direct-sum annealed vs frozen initial label probabilities
    for h in (0,2,4):
        u,g,y=1,2,3; a,b=[stat(continuum(u,g,h,p),y) for p in (0,PI)]
        C=stat(passive(),y)[0]; l=logsumexp([np.log(2)+C,a[0]])
        w=np.exp(a[0]-l); Fiso=y*(a[0]-b[0]); contrast=-np.expm1(-Fiso/y)
        for f in (.01,.1,.25,.5,1.):
            fa=-y*np.log1p(-f*w*contrast); fq=f*w*Fiso
            assert fa<=fq+1e-12
            out['ensembles'].append(dict(h=h,f=f,w=w,F_annealed=fa,F_frozen=fq,contrast=f*w*contrast))
    assert max(x['energy_res'] for x in out['thermo'])<1e-10
    assert max(x['entropy_res'] for x in out['thermo'])<1e-6
    assert max(x['heat_res'] for x in out['thermo'])<1e-6
    assert abs(out['baseline'][0]['limit'][0][0]-2.4463301467)<1e-9
    assert abs(out['baseline'][0]['limit'][1][0]-1.3328215470)<1e-9
    assert abs(out['baseline'][0]['limit'][2][0]-1.0761306593)<1e-9
    return out

if __name__=='__main__':
    data=run(); path=Path(__file__).with_name('results.json');path.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
    print('baseline',len(data['baseline']),'hybrid',len(data['hybrid']),'inertia',len(data['inertia']),'inverse',len(data['inverse']),'thermo',len(data['thermo']),'ensembles',len(data['ensembles']))
    for row in data['baseline']:
        if row['u']==1 and row['g']==2:print('baseline',row['N'],row['values'][0][0],row['err_iso'])
    for row in data['hybrid']:
        if row['N']==256:print('hybrid',row['u'],row['g'],row['h'],'F limits',[x[0] for x in row['limit']],'err',row['err_iso'],'ground',row['lowest'])
    for k in ('entropy_res','energy_res','heat_res'):print(k,max(x[k] for x in data['thermo']))
    print('inverse',data['inverse'])
