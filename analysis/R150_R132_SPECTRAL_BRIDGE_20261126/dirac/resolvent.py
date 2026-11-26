"""Cell-integrated continuum Green kernel for the two real twists; no mode cutoff."""
import json
from pathlib import Path
import numpy as np
from scipy.linalg import eigvalsh, solve
from check import operators


def exp_remainder(t):
    # Stable exp(t)-1-t on small cells, including the complex-step derivative.
    if abs(t) >= .02:
        return np.expm1(t)-t
    out=0.
    term=t*t/2
    for k in range(2,12):
        out+=term
        term*=t/(k+1)
    return out


def green_rows(n, m, z, sign, contact):
    """E_n^* R(z) E_m for nested partitions; complex z analytically continued."""
    r=m//n
    assert m==r*n and sign in [-1,1]
    k=np.sqrt(z)
    a=1/(1-sign*np.exp(-k))
    b=sign*np.exp(-k)*a
    def kernel(x):
        return (a*np.exp(-k*x)+b*np.exp(k*x))/(2*k)
    def moments(size):
        t=k/size
        sh=np.sinh(t/2)/(t/2)
        column=kernel((np.arange(size)+.5)/size)*sh/np.sqrt(size)
        return sh,column
    sh,v_m=moments(m)
    _,v_n=moments(n)
    col=kernel(np.arange(m)/m)*sh**2/m
    col[0]=m*(a*exp_remainder(-k/m)+b*exp_remainder(k/m))/(k**3)
    differences=np.arange(n)[:,None]*r-np.arange(m)[None,:]
    cycle=np.zeros((n,m),dtype=col.dtype)
    for l in range(r):
        distance=differences+l
        cycle+=col[np.abs(distance)]
    cycle/=np.sqrt(r)
    L=np.diag([1/z,kernel(0.)])
    small=np.linalg.solve(np.eye(2)+contact@L,contact)
    R=np.empty((n+1,m+1),dtype=col.dtype)
    R[0,0]=1/z-small[0,0]/z**2
    R[0,1:]=-small[0,1]*v_m/z
    R[1:,0]=-small[1,0]*v_n/z
    R[1:,1:]=cycle-small[1,1]*np.outer(v_n,v_m)
    return R


def induced_norm(a):
    lam=eigvalsh(a@a.T,subset_by_index=[a.shape[0]-1]*2)[0]
    return float(np.sqrt(max(0.,lam)))


def defect(n, sign, z, pars, ratios=(2,4,8,16)):
    u,g,h=pars
    V=np.array([[-u,h],[h,-g]])
    K,_=operators(n,0 if sign==1 else np.pi,u,g,h)
    Rn=solve(K.real+z*np.eye(n+1),np.eye(n+1),assume_a="sym")
    C=green_rows(n,n,z,sign,V)
    assert np.max(abs(C-C.T))<2.e-12
    step=1.e-12
    # For self-adjoint real shifts, -dR/dz=R^2. Gram of the entire rectangular defect.
    R2=-green_rows(n,n,z+1j*step,sign,V).imag/step
    d=Rn-C
    gram=d@d.T+R2-C@C.T
    full=float(np.sqrt(eigvalsh(gram,subset_by_index=[n,n])[0]))
    restrictions={}
    for r in ratios:
        m=n*r
        coarse_lift=np.column_stack((Rn[:,0],np.repeat(Rn[:,1:],r,axis=1)/np.sqrt(r)))
        D=coarse_lift-green_rows(n,m,z,sign,V)
        restrictions[str(r)]=induced_norm(D)
    values=list(restrictions.values())+[full]
    assert all(a<=b+2.e-9 for a,b in zip(values,values[1:]))
    return {"N":n,"twist_sign":sign,"z":z,"restricted":restrictions,
            "continuum_input":full}


def images_check():
    """Independent direct image sum, complex twist, correct contact-to-cell midpoint."""
    out=[]
    for phi in [0.,np.pi,.63]:
        for z in [1.,4.]:
            k=np.sqrt(z)
            phase=np.exp(1j*phi)
            for x in [0.,.5/16,.1875,.5,.9375]:
                exact=(np.exp(-k*x)/(1-np.exp(-k)/phase)
                       +phase*np.exp(k*(x-1))/(1-phase*np.exp(-k)))/(2*k)
                for cutoff in [16,40,80]:
                    m=np.arange(-cutoff,cutoff+1)
                    val=np.sum(np.exp(1j*m*phi-k*abs(x-m)))/(2*k)
                    out.append([phi,z,x,cutoff,float(abs(val-exact))])
    assert max(v[-1] for v in out if v[-2]==80)<1.e-14
    return out


def fourier_audit():
    # Each plane wave is integrated over both cells, rather than sampled at a node.
    V=np.array([[-1.,2.],[2.,-2.]])
    rows=[]
    for n in [8,16]:
        for r in [2,8]:
            m=n*r
            for sign,phi in [(1,0.),(-1,np.pi)]:
                z=4.
                exact=green_rows(n,m,z,sign,V)
                for cutoff in [64,256,1024]:
                    # Complete symmetric pairs in the antiperiodic sector.
                    modes=np.arange(-cutoff,cutoff+int(sign==1))
                    wave=2*np.pi*modes+phi
                    weight=1/(wave**2+z)
                    def F(size):
                        centers=(np.arange(size)+.5)/size
                        return (np.exp(1j*centers[:,None]*wave)*np.sinc(wave/(2*np.pi*size))
                                / np.sqrt(size))
                    fn,fm=F(n),F(m)
                    cp=np.zeros((n+1,m+1),complex)
                    cp[0,0]=1/z
                    cp[1:,1:]=(fn*weight)@fm.conj().T
                    def Y(f):
                        y=np.zeros((len(f)+1,2),complex)
                        y[0,0]=1/z; y[1:,1]=f@weight
                        return y
                    small=solve(np.eye(2)+V@np.diag([1/z,weight.sum()]),V)
                    approx=cp-Y(fn)@small@Y(fm).conj().T
                    rows.append([n,r,sign,cutoff,float(np.linalg.norm(approx-exact,2))])
                assert rows[-1][-1]<rows[-3][-1]/10
    return rows


def main():
    rows=[defect(n,sign,z,(1,2,2))
          for sign in [1,-1] for z in [1.,4.] for n in [16,32,64,128,256]]
    controls=[defect(16,1,7.,p,(2,4)) for p in [(0,0,0),(1,1,1),(1,2,0)]]
    out={"basis":"orthonormal step functions; z in (K+z)^-1",
         "rows":rows,"singular_V_and_decoupled":controls,"image_sum_checks":images_check(),"fourier_cutoff_control":fourier_audit()}
    path=Path(__file__).with_suffix(".json")
    path.write_text(json.dumps(out,indent=2,allow_nan=False)+"\n")
    for row in rows:
        if row["N"] in [16,64,256]: print(row)


if __name__=="__main__":
    main()
