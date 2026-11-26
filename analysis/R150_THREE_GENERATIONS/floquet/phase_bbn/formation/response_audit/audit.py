"""Analytic and numerical extensions of the ten-cell R150 formation audit."""
import json
import math
import numpy as np
from trajectory import evaluate, energy_peak
from contact import trials as contact_trials
from scipy.integrate import quad
from scipy.linalg import expm, block_diag
from scipy.optimize import brentq, minimize_scalar
from scipy.special import expit, ive, zeta, logsumexp

def contrast(N,x):
    if x == 0:
        return 0.0
    # Remove exp(x) by using 1-cos(theta)=2 sin^2(theta/2).
    z=1+sum(np.exp(-2*x*np.sin(np.pi*np.arange(N)/N)**2))
    terms=[]
    for m in range(1,10001,2):
        terms.append(ive(m*N,x))
        if terms[-1] <= 1e-15 * sum(terms):
            break
    else:
        raise ArithmeticError('Bessel tail did not converge')
    return 4*N*sum(terms)/z

def x_at(N,target):
    if not (0<target<.5):
        raise ValueError('Require 0 < target < 1/2 for a finite positive root')
    upper = N*N
    while contrast(N, upper) < target:
        upper *= 2
    return brentq(lambda x: contrast(N,x)-target, 0, upper)

def scaling(c):
    k=np.arange(-64,65)
    def zb(shift):
        return 1 + sum(np.exp(-2 * np.pi ** 2 * c * (k + shift) ** 2))
    return 1-zb(.5)/zb(0)

def rates(B,b,gr,gd):
    a = expit(B)
    v = expit(b)
    return a,v,expit(B+gr)-a,expit(b+gd)-v

def reduced(B,b,gr,gd,wr=1.,wd=1.):
    a,v,A,D=rates(B,b,gr,gd)
    # state (1,<r>,<d>,<rd>), column convention.
    return np.array([[0.,0,0,0],[wr*a,-wr,wr*A,0],[wd*v,wd*D,-wd,0],
                     [0,wd*(v+D),wr*(a+A),-wr-wd]])

def four(B,b,gr,gd,wr=1.,wd=1.):
    states=[(0,0),(0,1),(1,0),(1,1)]
    Q=np.zeros((4,4))
    for i,(r,d) in enumerate(states):
        Q[states.index((1-r,d)),i]=wr*expit((1-2*r)*(B+gr*d))
        Q[states.index((r,1-d)),i]=wd*expit((1-2*d)*(b+gd*r))
    return Q-np.diag(Q.sum(axis=0))

def moments():
    M=np.array([[1,1,1,1],[0,0,1,1],[0,1,0,1],[0,0,0,1]])
    for B,b,gr,gd,wr,wd in [(.7,-.1,.4,-.8,.2,3),(.02,.3,.0,.5,0,1),(.71,-.1,-2.,1.,2.,0)]:
        assert np.allclose(M@four(B,b,gr,gd,wr,wd),reduced(B,b,gr,gd,wr,wd)@M)
    B = -math.log1p(-contrast(6, 4))
    g = math.log(2)
    def run(gr,gd):
        return expm(reduced(B,0,gr,gd))[:,0][1:]
    both = run(g, g)
    one = run(g, 0)
    other = run(0, g)
    off = run(0, 0)
    a,v,A,D=rates(B,0,g,g)
    susceptibility=a*v*(1-v)*(1-2/math.e)
    def klp(t):
        Q=four(B,0,g,g,0,1)
        prior=expm(four(B,0,g,g,1,0)*t)[:,0]
        h=expm(Q*t).T@M[2]
        return float(M[1]@prior),float((M[1]*prior)@h/(prior@h))
    return dict(bias=B,alphabeta=A*D,relaxation_rates=[1-math.sqrt(A*D),1+math.sqrt(A*D),2],
                susceptibility_D=susceptibility,irreducible_loop=(both-one-other+off).tolist(),
                posterior_without_physical_reverse=klp(1))

def basis(N,phi):
    n = N + 1
    k = (2 * np.pi * np.arange(N) + phi) / N
    U = np.zeros((n, n), complex)
    U[1, 0] = 1
    U[[0,*range(2,n)],1:]=np.exp(-1j*np.arange(N)[:,None]*k)/np.sqrt(N)
    return np.r_[0.,k],U

def chemical(x=4,b=0,phi=np.pi,rotation=0,keep_blocks=False):
    N = 6
    L = N + 1
    k0, V0 = basis(N, 0)
    k1, V1 = basis(N, phi)
    cs,sn=np.cos(rotation),np.sin(rotation)
    V0[:,:2]=V0[:,:2]@np.array([[cs,-sn],[sn,cs]])
    E=np.r_[-x*np.cos(k0),-x*np.cos(k1)-b]
    I = np.eye(L)
    I[[0, 1]] = I[[1, 0]]
    W=block_diag(V0.conj().T@I@V0,V1.conj().T@I@V1)
    O=V1.conj().T@V0
    cap=np.block([[np.zeros_like(O),O.conj().T],[O,np.zeros_like(O)]])
    W2=abs(W)**2+abs(cap)**2
    Q = W2 * expit(E[None, :] - E[:, None])
    Q -= np.diag(Q.sum(axis=0))
    eq = np.exp(-E)
    eq /= eq.sum()
    assert np.allclose(Q*eq,(Q*eq).T)
    prior = np.zeros(2 * L)
    prior[:2] = 0.5
    d=np.r_[np.zeros(L),np.ones(L)]
    if not keep_blocks:
        return Q,prior,d,eq,Q[L:,:L].sum(axis=0)
    # CP jumps connect energy subspaces, resolving d but not arbitrarily chosen rays.
    groups=[]
    for start in (0,L):
        labels=np.round(E[start:start+L],10)
        groups.extend([np.flatnonzero(labels==e)+start for e in np.unique(labels)])
    jumps=[]
    for i in groups:
        for j in groups:
            S = W if (i[0]<L)==(j[0]<L) else cap
            mat=S[np.ix_(j,i)]*math.sqrt(expit(E[i[0]]-E[j[0]]))
            if np.linalg.norm(mat)>1e-12:
                jumps.append((i,j,mat,mat.conj().T@mat))
    # Only block-diagonal density matrices appear for the chosen initial condition.
    idx=[(i,j) for group in groups for i in group for j in group]
    rows,cols=np.array(idx).T
    def action(rho):
        out=np.zeros_like(rho)
        for i,j,K,A in jumps:
            sub=rho[np.ix_(i,i)]
            out[np.ix_(j,j)]+=K@sub@K.conj().T
            out[np.ix_(i,i)]-=(A@sub+sub@A)/2
        return out[rows,cols]
    G=np.zeros((len(idx),len(idx)),complex)
    for m,(i,j) in enumerate(idx):
        rho = np.zeros(W.shape, complex)
        rho[i, j] = 1
        G[:,m]=action(rho)
    trace=(rows==cols)
    assert np.allclose(trace@G,0) and np.allclose(G@np.diag(eq)[rows,cols],0)
    initial=np.diag(prior)[rows,cols]
    final=np.diag(d)[rows,cols]
    prob=float(np.real(final@expm(G)@initial))
    return prob

def mode_results():
    Q,p,d,eq,h=chemical()
    def response(t):
        return 0.5 * -math.expm1(-t) - d @ expm(t * Q) @ p
    tpeak=minimize_scalar(lambda t:-response(t),bounds=(0,4),method='bounded').x
    times=[.1,1,5,20,100]
    rotation=[]
    for a in (0,np.pi/8,np.pi/4):
        q,p0,end,w,_=chemical(rotation=a)
        rotation.append([float(a),float(end@expm(q)@p0),chemical(rotation=a,keep_blocks=True)])
    assert np.ptp([i[-1] for i in rotation])<1e-12
    hazards={str(b):[float(np.sum(chemical(b=b)[-1])),float(7*expit(b))] for b in (-1,0,1)}
    # Incremental information from a late bound state for the equal two-mode preparation.
    return dict(rotations=rotation,peak_time=float(tpeak),peak_contrast=float(response(tpeak)),
                equilibrium_contrast=float(.5-d@eq),amplification=float(response(tpeak)/(.5-d@eq)),
                hazards_sum_vs_claim=hazards,posterior_instant=float(h[0]/sum(h[:2])),
                posterior_long=float(p[0]),
                contrasts=[float(response(t)) for t in times])

def relic():
    T = 0.08
    Tnu = T * (4 / 11) ** (1 / 3)
    nlim = 0.17
    rho_nu = 7 * np.pi ** 2 / 120 * Tnu ** 4
    def integrand(y,z):
        return y*y*math.hypot(y,z)*math.exp(-y)/(-math.expm1(-y))
    rows={}
    limits={N:x_at(N,.01) for N in (2,6,8,14)}
    for gs in (28.,106.75,202.):
        tx=Tnu*(10.75/gs)**(1/3)
        for gx in (1,7,126):
            density=gx*zeta(3)/np.pi**2*tx**3
            def diff(J):
                return gx*tx**4/(2*np.pi**2)*quad(integrand,0,90,args=(2*J/tx,),epsabs=1e-11)[0]/rho_nu
            nr=nlim*rho_nu/(2*density)
            floor=diff(0)
            assert np.isclose(floor,gx*(4/7)*(tx/Tnu)**4)
            cap=brentq(lambda J:diff(J)-nlim,0,nr*1.01) if floor<nlim else None
            rows[f'{gs}_{gx}']=dict(radiation_floor=floor,NR_Jmax=nr,exact_Jmax=cap,
                 valid_L_Tgamma=[N+1 for N,z in limits.items() if cap and z*T/2<cap],
                 valid_L_Tmom=[N+1 for N,z in limits.items() if cap and z*tx/2<cap])
    return dict(rho_1nu=rho_nu,Jmin_photon={N+1:z*T/2 for N,z in limits.items()},rows=rows)

def layer_control():
    results = {}
    for L in (3,7,9,15):
        theta = 2*np.pi*np.arange(L)/L
        log_a0 = logsumexp(4*np.cos(theta))
        log_api = logsumexp(4*np.cos(theta + np.pi/L))
        results[L] = dict(passive_imposed_flux_contrast=float(-np.expm1(log_api-log_a0)),
                          active_contrast=float(contrast(L-1,4)),
                          passive_low_T_deltaF_over_J=2*(1-math.cos(math.pi/L)))
    return results


def alternating_gates():
    B = -math.log1p(-contrast(6,4))
    g = math.log(2)
    R = four(B,0,g,g,1.,0.)
    D = four(B,0,g,g,0.,1.)
    full = expm(R+D)[:,0]
    def distance(segment, steps):
        p = np.linalg.matrix_power(segment, steps)[:,0]
        return float(np.sum(abs(p-full))/2)
    out = {}
    for steps in (1,2,4,16,64):
        r = expm(R/steps)
        d = expm(D/steps)
        half = expm(R/(2*steps))
        out[steps] = dict(ordered=distance(d@r,steps), symmetric=distance(half@d@half,steps))
    return out


def main():
    roots=[brentq(lambda c:scaling(c)-e,.01,1) for e in (.01,.1,.4)]
    return dict(layer_control=layer_control(), alternating_gates=alternating_gates(),
                local_contact=contact_trials(),
                finite_size=dict(targets=[.01,.1,.4],limit_c=roots,
                          eta_at_half=scaling(.5),by_N={n:[x_at(n,e)/n**2 for e in (.01,.1,.4)] for n in (6,14,64,256)},
                          cancellation={n:contrast(n,1.) for n in (6,14,30)}),
                energy_maxima={n:energy_peak(n,contrast) for n in (2,6,8,14,64)},
                moments=moments(),modes=mode_results(),screen=relic(),
                trajectory=evaluate(x_at))
if __name__ == '__main__':
    print(json.dumps(main(), indent=2))
