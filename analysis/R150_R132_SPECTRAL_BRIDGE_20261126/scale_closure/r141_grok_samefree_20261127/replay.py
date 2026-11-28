"""Reconstructed replay from published equations and Grok stdout.
Not Grok's original script. Not executed in the publication turn.
Requires numpy. Emits model outputs, no physical acceptance.
"""
import json
import numpy as np

N=6
M=15.85/3.08622708259639589
JR=np.array([1.,-.0895673535,.0130843932,-.0023203345,.000456704308,-.0000959440614])
I=np.eye(N,dtype=complex)
site=np.zeros(N,dtype=complex); site[0]=1
Q=I-np.outer(site,site.conj())

def shift(theta):
    s=np.roll(I,1,axis=0); s[0,-1]=np.exp(1j*theta)
    assert np.allclose(np.linalg.matrix_power(s,N),np.exp(1j*theta)*I)
    return s

def ring(R,theta):
    s=shift(theta)
    k=np.zeros((N,N),complex)
    for r,j in enumerate(JR[:R],1):
        sr=np.linalg.matrix_power(s,r)
        k+=j*(2*I-sr-sr.conj().T)
    return k

def fvals(l):
    disc=M*M+2*M*l
    if np.min(disc)<-1e-10: raise ValueError("outside real branch")
    return np.sqrt(np.maximum(disc,0))-M

def fmat(k):
    l,v=np.linalg.eigh(k)
    return (v*fvals(l))@v.conj().T

def parent_energy(e,kind):
    if kind=="in":
        if e < -M: raise ValueError("outside physical branch")
        return e+e*e/(2*M)
    return e

def bulk(k,kind):
    return fmat(k) if kind=="out" else k

def calibrate(R,kind,target_p=None):
    k=bulk(ring(R,0.),kind)
    l=parent_energy(-1.,kind)
    g=np.linalg.solve(k-l*I,site)
    g00=g[0].real
    gp=np.vdot(g,g).real
    if target_p is None:
        h2=-l/g00
        ep=0.
    else:
        h2=(1/target_p-1)/gp
        ep=l+h2*g00
    if h2 <=0: raise ValueError("invalid calibration")
    return np.sqrt(h2),ep

def eigs(R,theta,kind,h,ep):
    k=bulk(ring(R,theta),kind)
    H=np.zeros((N+1,N+1),complex)
    H[:N,:N]=k; H[N,N]=ep
    H[:N,N]=h*site; H[N,:N]=h*site.conj()
    l,v=np.linalg.eigh(H)
    return (fvals(l) if kind=="in" else l),v

def diagnostic(psi,theta):
    s=shift(theta)
    u=Q@psi; w=Q@(s+s.conj().T)@psi
    den=np.vdot(u,u).real
    if den < 1e-24: return None,None,None
    q=np.vdot(u,w).real/den
    r=np.linalg.norm(w-q*u)
    return float(q),float(r/np.linalg.norm(psi)),float(r/np.sqrt(den))

def state(R,theta,kind,h,ep,idx):
    e,v=eigs(R,theta,kind,h,ep)
    psi=v[:N,idx]
    q,rr,rm=diagnostic(psi,theta)
    return dict(R=R,theta=theta,kind=kind,h=float(h),Ep=float(ep),edge="lower" if idx==0 else "upper",E=float(e[idx]),Pp=float(abs(v[N,idx])**2),qhat=q,Rring=rr,Rmask=rm)

def main():
    # Exact NN identities and seam check.
    h,ep=calibrate(1,"NR")
    assert abs(h-2*np.sqrt(5)/3)<1e-12
    lo=state(1,0.,"NR",h,ep,0)
    ap=state(1,np.pi,"NR",h,ep,0)
    assert abs(lo["Pp"]-60/97)<1e-12
    assert abs(ap["E"]+.9921826165945062)<1e-10
    assert lo["Rring"]<1e-12 and ap["Rring"]<1e-12
    g=np.linalg.solve(ring(1,0)+I,site)
    assert np.allclose(g*40,[18,7,3,2,3,7])
    assert abs(np.vdot(g,g).real-111/400)<1e-12
    hpi=1.5
    assert abs(state(1,np.pi,"NR",hpi,0.,0)["Pp"]-12/19)<1e-12
    assert abs(state(1,np.pi,"NR",h,-1/81,0)["E"]+1)<1e-12
    rows=[]
    for R in (1,2,3,6):
        ho,po=calibrate(R,"out")
        p_ref=state(R,0.,"out",ho,po,0)["Pp"]
        for mode,target in (("Ep=0",None),("Pp=Pp_out_Ep0",p_ref),("Pp=60/97",60/97)):
            for kind in ("out","in"):
                h,ep=calibrate(R,kind,target)
                for theta in (0.,np.pi):
                    for idx in (0,-1):
                        row=state(R,theta,kind,h,ep,idx)
                        row["calibration"]=mode
                        if theta==0 and idx==0:
                            assert abs(row["E"]+1)<1e-11
                            if target is not None:
                                assert abs(row["Pp"]-target)<1e-11
                        rows.append(row)
    # Finite matrix hopping aliases and moment signatures (not Fourier recovery).
    hopping=[]; moments=[]
    for R in range(1,7):
        k=ring(R,0); a=fmat(k)
        d0=np.linalg.eigvalsh(k); dp=np.linalg.eigvalsh(ring(R,np.pi))
        moments.append(dict(R=R,Delta=[float(np.sum(dp**p)-np.sum(d0**p)) for p in range(1,7)]))
        if R in (1,2,3,6):
            hopping.append(dict(R=R,Krow=k[0,:4].real.tolist(),fKrow=a[0,:4].real.tolist()))
    print(json.dumps(dict(scope="reconstructed finite model only",NN=[lo,ap],states=rows,finite_hopping=hopping,shifted_moments=moments),indent=2))

if __name__=="__main__":
    main()
