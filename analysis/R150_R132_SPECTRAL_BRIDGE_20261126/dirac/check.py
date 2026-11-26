"""Independent matrix and quadrature checks for the R132/R133/R150 report."""
import json
import platform
from pathlib import Path

import numpy as np
import scipy
from scipy.integrate import quad
from scipy.linalg import eigvalsh, expm
from scipy.optimize import brentq

SEED = 132133150
rng = np.random.default_rng(SEED)


def maxabs(x):
    return float(np.max(np.abs(x)))


def shift(n, phi):
    out = np.diag(np.ones(n - 1, complex), 1)
    out[-1, 0] = np.exp(1j * phi)
    return out


def operators(n, phi, u, g, h):
    e = np.eye(n)
    derivative = n * (shift(n, phi) - e)
    kinetic = np.zeros((n + 1, n + 1), complex)
    kinetic[1:, 1:] = derivative.conj().T @ derivative
    contact = np.zeros_like(kinetic)
    contact[0, 0], contact[1, 1] = -u, -g * n
    contact[1, 0] = contact[0, 1] = h * np.sqrt(n)
    return kinetic + contact, contact


def lower_s(n):
    if n is None:
        return -np.pi**2
    return -4 * n**2 * np.sin(np.pi / (2 * n))**2


def hyper(s, n=None):
    if n is None:
        return np.sqrt(complex(s))
    return 2 * n * np.arcsinh(np.sqrt(complex(s)) / (2 * n))


def boundary_charge(s, n=None):
    t = hyper(s, n)
    v = t if n is None else n * np.sinh(t / n)
    return float((2 * v * np.tanh(t / 2)).real)


def ground_shift(u, g, h, n=None):
    floor = lower_s(n)
    if h == 0:
        if g == 0:
            return max(0.,u)
        sc = brentq(lambda s: boundary_charge(s, n) - g,
                    floor + 1.e-9, max(100., (abs(g)+5)**2), xtol=1.e-13)
        return max(u, sc)
    def equation(s):
        return boundary_charge(s, n) - g - h*h / (s-u)
    left = max(u, floor) + 1.e-10
    right = max(left + 1, 10.)
    while equation(right) < 0:
        right *= 2
    return brentq(equation, left, right, xtol=1.e-13)


def transfer_ratio(s, g_eff, n=None):
    t = hyper(s, n)
    v = t if n is None else n * np.sinh(t/n)
    transfer = 1. if t == 0 else np.sinh(t)/v
    discriminant = float((np.cosh(t) - g_eff * transfer / 2).real)
    if abs(discriminant - 1) < 2.e-12:
        return 1.
    assert discriminant > 1
    return discriminant + np.sqrt(discriminant**2 - 1)


def profile(s, r, x, n=None):
    t = hyper(s, n)
    if abs(t) < 1.e-9:
        return (1-x) + r*x, r-1 + 0*x
    w = (np.sinh(t*(1-x)) + r*np.sinh(t*x)) / np.sinh(t)
    dw = t*(-np.cosh(t*(1-x)) + r*np.cosh(t*x))/np.sinh(t)
    return w.real, dw.real


def params(u,g,h,n=None):
    s = ground_shift(u,g,h,n)
    a = np.sqrt(max(0., s-u))
    b = h/a if h else 0.
    r = 1. if h else transfer_ratio(s,g,n)
    return s,a,b,r


def finite_factor(n,phi,u,g,h):
    s,a,b,r = params(u,g,h,n)
    x = np.arange(n+1) / n
    w, _ = profile(s,r,x,n)
    # If r!=1 the Bloch profile lives on the cover: use w[N] on the last edge.
    A = np.zeros((n+1,n+1), complex)
    A[0,:2] = a,b*np.sqrt(n)
    A[1:,1:] = n*(np.diag(np.sqrt(w[:-1]/w[1:])) @ shift(n,phi)
                    - np.diag(np.sqrt(w[1:]/w[:-1])))
    K,_ = operators(n,phi,u,g,h)
    error = maxabs(A.conj().T @ A - K - s*np.eye(n+1))
    null = int(np.sum(np.linalg.svd(A,compute_uv=False) < 2.e-8))
    exact_null = int(a == 0) + int(r == 1 and phi == 0.)
    assert null == exact_null and error < 1.e-9
    return {"N":n, "phi":phi,"u":u,"g":g,"h":h,"s":s,
            "plus_zero":null,"minus_zero":null,"matrix_error":error,
            "ground_K":float(eigvalsh(K,subset_by_index=(0,0))[0])}


def continuum_form(phi,u,g,h):
    s,a,b,r = params(u,g,h)
    p = complex(*rng.normal(size=2))
    z = rng.normal(size=4) + 1j*rng.normal(size=4)
    omega = phi + 2*np.pi*np.array([-2,-1,0,1])
    def f(x):
        waves = z*np.exp(1j*omega*x)
        return waves.sum(),(1j*omega*waves).sum()
    def energies(x):
        w,dw = profile(s,r,x)
        y,dy = f(x)
        return abs(dy - dw/w*y)**2, abs(dy)**2+s*abs(y)**2
    f0 = f(0)[0]
    lhs = quad(lambda x:energies(x)[0],0,1,epsabs=2.e-11)[0] + abs(a*p+b*f0)**2
    rhs = (quad(lambda x:energies(x)[1],0,1,epsabs=2.e-11)[0]
           + (s-u)*abs(p)**2 - g*abs(f0)**2 + 2*h*(p.conjugate()*f0).real)
    err = abs(lhs-rhs)
    assert err < 1.e-8
    return float(err)


def prolong(n,r,phi,linear):
    m = n*r
    J = np.zeros((m+1,n+1),complex)
    J[0,0] = 1
    for k in range(m):
        j, s = divmod(k,r)
        t = s/r if linear else 0.
        J[k+1,1+j] = (1-t)/np.sqrt(r)
        twist = np.exp(1j*phi) if j+1 == n else 1.
        J[k+1,1+(j+1)%n] += t*twist/np.sqrt(r)
    return J


def refinement(n,r,phi,u,g,h):
    m = n*r
    coarse,V = operators(n,phi,u,g,h)
    fine,U = operators(m,phi,u,g,h)
    J = prolong(n,r,phi,False)
    P = prolong(n,r,phi,True)
    residual = U@J - J@V
    leak = float(np.linalg.norm(residual,2))
    pred = np.sqrt((m-n)*(h*h+n*g*g))
    d = shift(n,phi) - np.eye(n)
    mass = np.eye(n+1,dtype=complex)
    mass[1:,1:] -= (1-1/r**2)/6 * d.conj().T @ d
    errs = [maxabs(J.conj().T@J-np.eye(n+1)),maxabs(J.conj().T@U@J-V),
            abs(leak-pred),maxabs(P.conj().T@fine@P-coarse),
            maxabs(P.conj().T@P-mass)]
    # Nested refinement in opposite factor orders, on the same marked circle.
    for linear in [True, False]:
        J1 = prolong(2*n,r,phi,linear) @ prolong(n,2,phi,linear)
        J2 = prolong(n*r,2,phi,linear) @ prolong(n,r,phi,linear)
        errs.extend([maxabs(J1-J2),maxabs(J1-prolong(n,2*r,phi,linear))])
    assert max(errs)<1.e-9
    return {"N":n,"M":m,"phi":phi,"g":g,"h":h,"leak":leak,
            "leak_on_port":float(np.linalg.norm(residual[:,0])),"max_error":max(errs)}


pauli = np.array([[[0,1],[1,0]],[[0,-1j],[1j,0]],[[1,0],[0,-1]]])
generators = .5j*pauli


def su2():
    q = rng.normal(size=4)
    q /= np.linalg.norm(q)
    return q[0]*np.eye(2) + 1j*np.einsum('j,jab->ab',q[1:],pauli)


def product(mats):
    v = np.eye(2)
    for a in mats:
        v = v @ a
    return v


def group_checks():
    der,wrong,spin,vertical = [],[],[],[]
    dt=2.e-5
    for _ in range(32):
        links = [su2() for _ in range(3)]
        G = product(links)
        frames = [su2() for _ in range(4)]
        rotated = [frames[i]@links[i]@frames[i+1].conj().T for i in range(3)]
        v = rng.normal(size=2)+1j*rng.normal(size=2)
        spin.append(maxabs(product(rotated)@frames[-1]@v-frames[0]@G@v))
        for j in range(3):
            pre,post = product(links[:j+1]),product(links[j+1:])
            for T in generators:
                fd=(pre@expm(dt*T)@post-pre@expm(-dt*T)@post)/(2*dt)
                der.append(maxabs(fd-G@post.conj().T@T@post))
                wrong.append(maxabs(fd-G@T))
                if j < 2:
                    varied=links.copy()
                    varied[j]=links[j]@expm(dt*T)
                    varied[j+1]=expm(-dt*T)@links[j+1]
                    vertical.append(maxabs(product(varied)-G))
    assert max(der)<2.e-10 and max(wrong)>.1 and max(spin)<1.e-12
    assert max(vertical)<1.e-12
    return {"comparisons":len(der),"max_derivative_error":max(der),
            "max_wrong_frame_error":max(wrong),"max_spin_error":max(spin),
            "max_vertical_product_error":max(vertical)}


def exterior():
    gamma = []
    for j in range(3):
        c = np.zeros((8,8))
        for mask in range(8):
            c[mask^(1<<j),mask] = (-1)**((mask% (1<<j)).bit_count())
        gamma.append(c)
    return gamma, np.diag([(-1)**i.bit_count() for i in range(8)])


def act(x,mat,axis):
    return np.moveaxis(np.tensordot(mat,x,axes=(1,axis)),0,axis)


def cylindrical():
    # Local function basis 1 and sqrt(2)*g_ij. Clifford fiber: exterior C^3.
    gamma, parity = exterior()
    local = np.zeros((40,40),complex)
    for j,T in enumerate(generators):
        derivative = np.zeros((5,5),complex)
        derivative[1:,1:]=np.kron(np.eye(2),T)
        local += -1j*np.kron(derivative,gamma[j])
    assert maxabs(local-local.conj().T)<1.e-13
    grading = np.kron(np.eye(5),parity)
    weights = {0:.6,1:1.4,2:1.}
    def D(x,ids):
        out=np.zeros_like(x)
        for axis,i in enumerate(ids):
            v=act(x,weights[i]*local,axis)
            for k in range(axis):
                v=act(v,grading,k)
            out+=v
        return out
    def insert(x,ids,j):
        final=sorted([*ids,j])
        slots=[slice(None)]*len(final)
        slots[final.index(j)]=0
        a=np.zeros((40,)*len(final),complex)
        a[tuple(slots)]=x
        return a,final
    x=rng.normal(size=40)+1j*rng.normal(size=40)
    x/=np.linalg.norm(x)
    ends=[]
    errs=[]
    for seq in [(0,1),(1,0)]:
        v,ids=x,[2]
        for j in seq:
            dv=D(v,ids)
            nv,newids=insert(v,ids,j)
            rhs,_=insert(dv,ids,j)
            errs.append(maxabs(D(nv,newids)-rhs))
            v,ids=nv,newids
        ends.append(v)
    errs.append(maxabs(ends[0]-ends[1]))
    # Compression of multiplication by Re(g_11) on the retained Haar subspace.
    # Re(g11)=(g11+g22)/2. Triple products of fundamental entries integrate to 0.
    obs=np.zeros((5,5))
    obs[0,1]=obs[1,0]=obs[0,4]=obs[4,0]=1/(2*np.sqrt(2))
    obs=np.kron(obs,np.eye(8))
    v=ends[0]
    lhs=D(act(v,obs,2),[0,1,2])-act(D(v,[0,1,2]),obs,2)
    comm=local@obs-obs@local
    rhs,_=insert(comm@x,[2],0)
    rhs,_=insert(rhs,[0,2],1)
    errs.append(maxabs(lhs-rhs))
    y=np.zeros_like(v)
    y[8,0,:]=x  # degree-zero spin fiber with a nonconstant new function
    vertical=np.linalg.norm(D(y,[0,1,2])-act(y,local,2))
    assert max(errs)<1.e-12 and vertical>.1
    # Named two-block witness, input (x,u,z), output (u,a,z).
    # u=xy survives the merge; z=ab survives the split. New relative slots
    # carry independent positive weights. Indices here encode persistent names.
    weights.update({3:.8, 4:1.7})
    old_ids=[0,1,4]
    new_ids=[1,3,4]
    psi=rng.normal(size=(40,)*3)+1j*rng.normal(size=(40,)*3)
    psi/=np.linalg.norm(psi)
    def merge_then_split(v):
        return insert(v[0], [1,4], 3)[0]
    def split_then_merge(v):
        return insert(v, old_ids, 3)[0][0]
    out=merge_then_split(psi)
    mixed_err=maxabs(out-split_then_merge(psi))
    mixed_D=maxabs(D(out,new_ids)-merge_then_split(D(psi,old_ids)))
    co=act(psi,obs,1)
    mixed_comm=maxabs(D(act(out,obs,0),new_ids)-act(D(out,new_ids),obs,0)
                      -merge_then_split(D(co,old_ids)-act(D(psi,old_ids),obs,1)))
    # Common Q transports the named slot decoration. Reorder [u,a,z] to [a,z,u]
    # in a graded tensor basis, including the Koszul sign.
    odd=(1-np.diag(grading))/2
    sign=1-2*odd[:,None,None]*np.mod(odd[None,:,None]+odd[None,None,:],2)
    def relabel(v):
        return (sign*v).transpose(1,2,0)
    q_err=maxabs(D(relabel(out),[3,4,1])-relabel(D(out,new_ids)))
    assert max(mixed_err,mixed_D,mixed_comm,q_err)<1.e-12
    mixed={"two_orders":mixed_err,"D_intertwiner":mixed_D,
           "commutator":mixed_comm,"graded_relabel":q_err,
           "norm_in":float(np.linalg.norm(psi)),"norm_out":float(np.linalg.norm(out))}
    return {"named_blocks":mixed,"local_dimension":40,"fine_dimension":40**3,"path_and_D_and_comm_error":max(errs),
            "commutator_norm_on_probe":float(np.linalg.norm(lhs)),"relative_D_norm_on_probe":float(vertical)}


def nodal(n,m=3):
    v=np.zeros(n+1)
    vf=np.zeros(2*n+1)
    v[1:]=np.sqrt(2/n)*np.sin(m*np.pi*np.arange(n)/n)
    vf[1:]=np.sqrt(1/n)*np.sin(m*np.pi*np.arange(2*n)/(2*n))
    w=prolong(n,2,np.pi,True)@v
    w=w/np.linalg.norm(w)
    leak=float(np.linalg.norm(w-vf*np.vdot(vf,w)))
    c=np.cos(m*np.pi/(2*n))
    assert abs(leak-abs(1-c)/np.sqrt(2*(1+c*c)))<1.e-13
    exact=4*n*n*np.sin(m*np.pi/(2*n))**2
    k,_=operators(n,np.pi,1,2,2)
    assert np.linalg.norm(k@v-exact*v)<1.e-9
    return {"N":n,"wave_number":m,"normalized_linear_ray_leak":leak,
            "dispersion":float(exact)}


def equal_ground():
    # An exactly tuned positive port/cycle degeneracy, with the shift fixed independently.
    u=1.5
    rows=[]
    for n in [8,16,32,64]:
        g=boundary_charge(u,n)
        w,_=profile(u,1.,np.arange(n+1)/n,n)
        for phi,expected in [(0.,2),(np.pi,1)]:
            K,_=operators(n,phi,u,g,0.)
            A=np.zeros((n+1,n+1),complex)
            A[1:,1:]=n*(np.diag(np.sqrt(w[:-1]/w[1:]))@shift(n,phi)
                         -np.diag(np.sqrt(w[1:]/w[:-1])))
            err=maxabs(A.conj().T@A-K-u*np.eye(n+1))
            nz=int(np.sum(np.linalg.svd(A,compute_uv=False)<1.e-9))
            assert nz==expected and err<1.e-9
            rows.append({"N":n,"u":u,"g":g,"phi":phi,"nullity":nz,"error":err})
    return rows


def marked_spin():
    # Exact Haar first moments already reproduced by the quaternion subgroup.
    # Equal discrete weights are represented in the Euclidean orthonormal basis.
    mats=[t*k for t in [1,-1] for k in [np.eye(2),*(1j*pauli)]]
    J=np.kron(np.ones((8,1))/np.sqrt(8),np.eye(4))
    lift=np.zeros_like(J,complex)
    contact=np.zeros((32,32),complex)
    plain=np.zeros((4,4),complex)
    plain[:2,2:]=plain[2:,:2]=np.eye(2)
    p=np.diag([1.,0])
    averaged=np.zeros((2,2),complex)
    for i,x in enumerate(mats):
        U=np.eye(4,dtype=complex)
        U[:2,:2]=x
        lift[4*i:4*i+4]=U/np.sqrt(8)
        contact[4*i:4*i+4,4*i:4*i+4]=U@plain@U.conj().T
        averaged+=x@p@x.conj().T/8
    zero=maxabs(J.conj().T@contact@J)
    second=maxabs(J.conj().T@contact@contact@J-np.eye(4))
    exact=maxabs(contact@lift-lift@plain)
    assert max(zero,second,exact,maxabs(averaged-.5*np.eye(2)))<1.e-13
    deriv=maxabs(generators[0])
    return {"subgroup_order":8,"naive_compression":zero,"second_moment_error":second,
            "naive_leak_operator_norm":float(np.linalg.norm(contact@J,2)),
            "covariant_intertwiner_error":exact,"projector_moment_gap":float(np.linalg.norm(averaged-averaged@averaged,2)),
            "nonzero_frame_derivative_entry":deriv}


def main():
    cases=[(1,2,0),(5,2,0),(0,0,0),(1,2,.5),(1,2,2),
           (-4,-2,.4),(-4,-2,0),(-2,-.5,0),(0,0,-1),(0,4,0)]
    rows=[]; quaderrs=[]
    for u,g,h in cases:
        for phi in [0.,np.pi,.63]:
            quaderrs.append(continuum_form(phi,u,g,h))
            for n in [8,16,32,64]:
                rows.append(finite_factor(n,phi,u,g,h))
    u,g,h=1,2,2
    conv = {str(n):ground_shift(u,g,h,n) for n in [16,32,64,128,256]}
    ref = [refinement(n,r,phi,1,g,h) for n in [4,8,16] for r in [2,3]
           for phi in [0.,np.pi,.63] for g,h in [(2,0),(0,1),(2,1),(0,0)]]
    output={"python":platform.python_version(),"numpy":np.__version__,"scipy":scipy.__version__,
            "seed":SEED,"finite_checks":rows,"max_factor_error":max(x["matrix_error"] for x in rows),
            "n_quadratures":len(quaderrs),"max_form_error":max(quaderrs),
            "periodic_shift_cont":ground_shift(u,g,h),"periodic_shift_N":conv,
            "refinement_checks":ref,"max_refinement_error":max(x["max_error"] for x in ref),
            "group":group_checks(),"cylinder":cylindrical(),
            "equal_ground":equal_ground(),"marked_spin":marked_spin(),"nodal_ray":[nodal(n) for n in [8,16,32,64]]}
    Path(__file__).with_name("checks.json").write_text(json.dumps(output,indent=2,allow_nan=False)+"\n")
    print(json.dumps({k:v for k,v in output.items() if k not in ["finite_checks","refinement_checks"]},indent=2))


if __name__=="__main__":
    main()
