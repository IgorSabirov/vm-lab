#!/usr/bin/env python3
"""Fixed protocol spectral calibration, contact response and carrier tests.
All spectra synthetic; no BBN values used in calibration. Independent finite matrices.
"""
import json
from pathlib import Path
import numpy as np
from scipy.optimize import minimize_scalar
from scipy.linalg import eigvalsh
from replay import dense, continuum, m, stat, passive, results, invert, PI

def active(es,phi,N=None):
    j=np.arange(1,20) if phi==0 else np.arange(20)+.5
    nodes=(2*PI*j)**2 if N is None else 4*N*N*np.sin(PI*j/N)**2
    if N: nodes=nodes[j<N/2]
    # Remove exactly one contact-inactive mode at each known node, not every equal mode.
    a=list(es)
    for node in nodes:
        i=int(np.argmin(np.abs(np.array(a)-node)))
        if abs(a[i]-node)<1e-6:a.pop(i)
    return np.array(a)

def m_discrete(E,phi,N):
    if E==0:return m(E,phi)
    if E<0:
        k=2*N*np.arcsinh(np.sqrt(-E)/(2*N)); v=2*N*np.sinh(k/N)
        return -v*np.tanh(k/2) if phi==0 else -v/np.tanh(k/2)
    q=2*N*np.arcsin(np.sqrt(E)/(2*N)); v=2*N*np.sin(q/N)
    return v*np.tan(q/2) if phi==0 else -v/np.tan(q/2)

def recover_fixed(u,g,h,N=None):
    e=[active(dense(N,u,g,h,p) if N else continuum(u,g,h,p),p,N) for p in (0,PI)]
    levels=[(e[0][0],0),(e[0][1],0),(e[1][0],PI)]
    E=np.array([x[0] for x in levels]);
    M=np.array([m_discrete(x,p,N) if N else m(x,p) for x,p in levels]);
    A=np.column_stack([M,E,np.ones(3)]); U,G,C=np.linalg.solve(A,-E*M); H2=U*G-C
    pred=[active(dense(N,U,G,np.sqrt(max(0,H2)),p) if N else continuum(U,G,np.sqrt(max(0,H2)),p),p,N) for p in (0,PI)]
    hold=max(np.max(abs(pred[0][2:5]-e[0][2:5])),np.max(abs(pred[1][1:5]-e[1][1:5])))
    return dict(N=N,u=u,g=g,h=h,rec=[U,G,H2],condition=np.linalg.cond(A),holdout_max_error=hold,levels=levels)

def contact_weights(E,u,g,h,p):
    d=1e-5*max(1.,abs(E)); mp=(m(E+d,p)-m(E-d,p))/(2*d)
    a=h*h/(E+u)**2
    return a/(mp+a),1/(mp+a)

def main():
    out=dict(fixed_inverse=[],noise=[],scale=[],responses=[],scan=[],crossing=[])
    for u,g,h in [(1,2,.1),(1,2,.5),(1,2,2),(-2,3,2),(5,5,2)]:
        for N in (None,32,128,256):out['fixed_inverse'].append(recover_fixed(u,g,h,N))
    for h in (.001,.01,.03,.1,.5,2.):
        r=recover_fixed(1,2,h); rr=r['levels']; rng=np.random.default_rng(132150)
        samples=np.array([invert([(e+de,p) for (e,p),de in zip(rr,rng.normal(0,1e-4,3))])[0] for _ in range(2000)])
        out['noise'].append(dict(h=h,h2=h*h,rmse_h2=float(np.sqrt(np.mean((samples[:,2]-h*h)**2))),negative_fraction=float(np.mean(samples[:,2]<0))))
    # Recover a physical energy scale and arbitrary offset from nodal modes only.
    # Synthetic E*=0.02 MeV, Eref=0.137 MeV. These are not physical fits.
    E_star=.02; Eref=.137
    for N in (32,128,256,None):
        p0=4*N*N*np.sin(PI/(2*N))**2 if N else PI**2
        p1=4*N*N*np.sin(3*PI/(2*N))**2 if N else 9*PI**2
        obs0,obs1=Eref+E_star*p0,Eref+E_star*p1
        r=(obs1-obs0)/(p1-p0); ref=obs0-r*p0
        out['scale'].append(dict(N=N,E_star=r,Eref=ref,naive_continuum_E_star=(obs1-obs0)/(8*PI**2)))
    # Hellmann-Feynman weights vs finite matrix eigenvectors and numerical derivative.
    u,g,h=1,2,2; N=256
    for p in (0,PI):
        E=active(continuum(u,g,h,p),p)[0]; Pp,Pc=contact_weights(E,u,g,h,p)
        d=1e-5
        du=(continuum(u+d,g,h,p)[0]-continuum(u-d,g,h,p)[0])/(2*d)
        dg=(continuum(u,g+d,h,p)[0]-continuum(u,g-d,h,p)[0])/(2*d)
        assert abs(du+Pp)<1e-7 and abs(dg+Pc)<1e-7
        out['responses'].append(dict(phi=p,E=E,Pport=Pp,contact_density=Pc,du=du,dg=dg))
    for h in np.linspace(0,12,61):
        r=results(None,1,2,h,3)
        out['scan'].append(dict(h=h,iso=r[0][0],all=r[1][0],one=r[2][0],U_all=r[1][1],S_all=r[1][2]))
    opt=minimize_scalar(lambda h:-results(None,1,2,h,3)[1][0],bounds=(0,12),method='bounded')
    out['scan_peak']=dict(h=opt.x,F_all=-opt.fun)
    # Avoided crossing at E=-u=e0(g); h=0 case is exact degeneracy.
    g=2; e0=continuum(-100,g,0,0)[0]; u=-e0
    for h in (0,.01,.03,.1,.3,1.):
        e=continuum(u,g,h,0); gap=e[1]-e[0]
        out['crossing'].append(dict(u=u,g=g,h=h,gap=gap,ratio=gap/h if h else None))
    assert max(abs(np.array(x['rec'])-[x['u'],x['g'],x['h']**2]).max() for x in out['fixed_inverse'])<1e-7
    assert max(x['holdout_max_error'] for x in out['fixed_inverse'])<1e-6
    Path(__file__).with_name('calibration.json').write_text(json.dumps(out,indent=2,allow_nan=False)+'\n')
    for k in ['noise','scale','responses','crossing','scan_peak']:print(k,out[k])
    print('fixed inverse max residual',max(abs(np.array(x['rec'])-[x['u'],x['g'],x['h']**2]).max() for x in out['fixed_inverse']),'holdout',max(x['holdout_max_error'] for x in out['fixed_inverse']))
if __name__=='__main__':main()
