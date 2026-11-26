"""Spin/frame reduction, Feshbach denominators and signed first-order refinements."""
import json
from pathlib import Path
import numpy as np
from scipy.linalg import block_diag, expm, null_space, solve, svdvals
from check import params, profile, shift, prolong, maxabs, pauli


def haar_moments():
    rng=np.random.default_rng(133150)
    N=200_000
    q=rng.normal(size=(N,4))
    q/=np.linalg.norm(q,axis=1)[:,None]
    v=q[:,1:]
    axis=np.array([1.,0.,0.])
    # X=q0 I+i*v.sigma, B=X sigma_x X^dagger.
    n=(q[:,:1]**2-np.sum(v*v,axis=1)[:,None])*axis+2*v[:,0,None]*v-2*q[:,:1]*np.cross(v,axis)
    for row,vec in zip(q[:8],n[:8]):
        X=row[0]*np.eye(2)+1j*np.einsum("i,ijk->jk",row[1:],pauli)
        assert maxabs(X@pauli[0]@X.conj().T-np.einsum("i,ijk->jk",vec,pauli))<1.e-13
    mean=n.mean(axis=0); cov=n.T@n/N
    rho=np.array([[.7,.2j],[-.2j,.3]])
    channel=sum(cov[i,j]*pauli[i]@rho@pauli[j] for i in range(3) for j in range(3))
    expected=(2*np.trace(rho)*np.eye(2)-rho)/3
    assert maxabs(cov-np.eye(3)/3)<.004
    return {"N":N,"seed":133150,"mean_norm":float(np.linalg.norm(mean)),
            "covariance":cov.tolist(),"covariance_error":maxabs(cov-np.eye(3)/3),
            "channel_error":maxabs(channel-expected)}


def q8_controls():
    mats=[s*x for s in [1.,-1.] for x in [np.eye(2),*(1j*pauli)]]
    def ix(x):
        return next(i for i,v in enumerate(mats) if maxabs(x-v)<1.e-12)
    J0=np.kron(np.ones((8,1))/np.sqrt(8),np.eye(4))
    J=np.vstack([block_diag(x,np.eye(2))/np.sqrt(8) for x in mats])
    bare=np.kron(np.array([[0.,1.],[1.,0.]]),np.eye(2))
    B=block_diag(*(np.block([[np.zeros((2,2)),x],[x.conj().T,np.zeros((2,2))]]) for x in mats))
    Ug=[]
    for g in mats:
        perm=np.zeros((8,8))
        for j,x in enumerate(mats): perm[ix(g@x),j]=1
        Ug.append(np.kron(perm,block_diag(g,np.eye(2))))
    PG=sum(Ug)/8
    errors=[maxabs(PG-J@J.conj().T),maxabs(B@J-J@bare),
            maxabs((np.eye(32)-PG)@B@PG),max(maxabs(B@U-U@B) for U in Ug)]
    Qbasis=null_space(J0.conj().T)
    Qflip=np.zeros((8,8))
    for j,x in enumerate(mats): Qflip[ix(-x),j]=1.
    odd=(np.eye(8)-Qflip)/2
    H0=np.kron(np.eye(8),np.diag([.5,.5,2.,2.]))+1.5*np.kron(odd,np.eye(4))
    h=.7
    H=H0+h*B
    qs=Qbasis.conj().T
    b=J0.conj().T@B@Qbasis
    results=[]
    for E in [-1.,-2.]:
        direct=h*h*b@solve(E*np.eye(28)-qs@H@Qbasis,b.conj().T)
        expected=h*h*np.array([1/(E-3.5)]*2+[1/(E-2.)]*2)
        errors.append(maxabs(direct-np.diag(expected)))
        reduced=solve(E*np.eye(4)-J0.conj().T@H@J0-direct,np.eye(4))
        errors.append(maxabs(J0.conj().T@solve(E*np.eye(32)-H,J0)-reduced))
        results.append([E,float(direct[0,0].real),float(direct[2,2].real)])
    assert max(errors)<1.e-12
    return {"physical_rank":int(np.linalg.matrix_rank(PG)),"equivariance_and_schur_max":max(errors),
            "constant_compression":maxabs(J0.conj().T@B@J0),
            "Qphysical_B_Pphysical":maxabs((np.eye(32)-PG)@B@PG),"feshbach_E_port_cycle":results}


def connection():
    rng=np.random.default_rng(133)
    Ts=.5j*pauli
    def sample():
        q=rng.normal(size=4); q/=np.linalg.norm(q)
        return q[0]*np.eye(2)+1j*np.einsum('i,ijk->jk',q[1:],pauli)
    I=np.eye(2)
    B1=np.kron(np.array([[0.,1.],[1.,0.]]),I)
    def U(x): return block_diag(x,I)
    def A(x,T): return block_diag(-x@T@x.conj().T,np.zeros((2,2)))
    dt=1e-5
    errs=[]; wrong=[]; curvature=[]; covobs=[]; refinements=[]
    for _ in range(20):
        x,a,b,c,k=[sample() for _ in range(5)]
        v=rng.normal(size=4)+1j*rng.normal(size=4)
        O=np.diag([1.,0.,.5,-1.])
        for T in Ts:
            plus=x@expm(dt*T); minus=x@expm(-dt*T)
            deriv=(U(plus)-U(minus))/(2*dt)
            errs.append(maxabs(deriv@v+A(x,T)@U(x)@v))
            wrong.append(maxabs(deriv@v-A(x,T)@U(x)@v))
            def dressed(y): return U(y)@O@U(y).conj().T
            dO=(dressed(plus)-dressed(minus))/(2*dt)
            covobs.append(maxabs(dO+A(x,T)@dressed(x)-dressed(x)@A(x,T)))
            for S in Ts:
                dAS=(A(plus,S)-A(minus,S))/(2*dt)
                dAT=(A(x@expm(dt*S),T)-A(x@expm(-dt*S),T))/(2*dt)
                AT=A(x,T); AS=A(x,S)
                curvature.append(maxabs(dAS-dAT+AT@AS-AS@AT-A(x,T@S-S@T)))
        left=U((a@b)@c); right=U(a@(b@c))
        moved=U((a@k.conj().T)@(k@b)@c)
        refinements.extend([maxabs(left-right),maxabs(left-moved),
                            maxabs(left@B1@left.conj().T-right@B1@right.conj().T)])
    assert max(errs+curvature+covobs)<2.e-9 and max(wrong)>.1 and max(refinements)<1.e-12
    return {"covariant_derivative":max(errs),"opposite_sign":max(wrong),
            "curvature":max(curvature),"covariant_commutator":max(covobs),"two_paths":max(refinements)}


def dirac(n,phi,pars=(1.,2.,2.)):
    s,a,b,r=params(*pars,n)
    w,_=profile(s,r,np.arange(n+1)/n,n)
    A=np.zeros((n+1,n+1),complex)
    A[0,:2]=a,b*np.sqrt(n)
    A[1:,1:]=n*(np.diag(np.sqrt(w[:-1]/w[1:]))@shift(n,phi)-np.diag(np.sqrt(w[1:]/w[:-1])))
    Z=np.zeros_like(A)
    return np.block([[Z,A.conj().T],[A,Z]])


def dirac_limits():
    rows=[]
    for phi in [0.,np.pi,.63]:
        for n in [8,16,32,64,128]:
            old=dirac(n,phi); new=dirac(2*n,phi)
            J=prolong(n,2,phi,False)
            H=block_diag(J,J)
            R=solve(old-1j*np.eye(len(old)),np.eye(len(old)))
            diff=solve(new-1j*np.eye(len(new)),H)-H@R
            lower=diff[2*n+1:,:n+1]; upper=diff[:2*n+1,n+1:]
            rows.append([n,phi,float(svdvals(diff)[0]),float(svdvals(lower)[0]),float(svdvals(upper)[0])])
        assert rows[-1][2]<rows[-5][2]/4
    return rows


def sampled_domain():
    from scipy.special import roots_legendre
    nodes,weights=roots_legendre(12)
    result=[]
    for pars in [(1.,2.,2.),(-4.,-2.,.4)]:
        u,g,h=pars
        s,a,b,_=params(*pars)
        for phi in [0.,np.pi,.63]:
            phase=np.exp(1j*phi); p=.8+.3j; r=.7-.4j
            def fields(x):
                e=np.exp(1j*phi*x)
                f=e*(1+.3*np.sin(2*np.pi*x))
                df=1j*phi*f+e*.6*np.pi*np.cos(2*np.pi*x)
                v=e*(.6+.2j-b*r*x+.15*np.sin(2*np.pi*x))
                dv=1j*phi*v+e*(-b*r+.3*np.pi*np.cos(2*np.pi*x))
                return f,df,v,dv
            for n in [8,16,32,64,128]:
                x=np.arange(n)/n
                samples=np.r_[p,fields(x)[0]/np.sqrt(n),r,fields(x+1/n)[2]/np.sqrt(n)]
                pts=x[:,None]+(1+nodes[None,:])/(2*n)
                f,df,v,dv=fields(pts)
                w,wp=profile(s,1.,pts)
                def cellavg(y): return (y@weights)/(2*np.sqrt(n))
                target=np.r_[a*r,cellavg(-dv-wp/w*v),a*p+b*fields(0.)[0],cellavg(df-wp/w*f)]
                diff=dirac(n,phi,pars)@samples-target
                result.append({"parameters":pars,"phi":phi,"N":n,"residual":float(np.linalg.norm(diff)),
                               "seam_magnitude":float(abs(diff[1]))})
            assert result[-1]["residual"]<.4*result[-5]["residual"]
    return result


if __name__=="__main__":
    data={"haar":haar_moments(),"Q8":q8_controls(),"connection":connection(),"dirac":dirac_limits(),"domain":sampled_domain()}
    result=json.dumps(data,indent=2,allow_nan=False)
    Path(__file__).with_suffix(".json").write_text(result+"\n")
    print(result)
