import numpy as np, math, json

from scipy.linalg import expm

from scipy.special import expit, logsumexp, iv



np.set_printoptions(precision=10, suppress=True)



def graph(L, phi):

    n = L-1

    order = [0,\*range(2,L)]

    step = np.zeros((L,L),complex)

    step[1,1] = 1

    h = -1 if phi == np.pi else np.exp(1j\*phi)

    for j,t in enumerate(order):

        step[order[(j+1)%n],t] = h if j==n-1 else 1

    phases = np.r\_[0,(phi+2\*np.pi\*np.arange(n))/n]

    basis = np.zeros_like(step)

    basis[1,0] = 1

    for j,t in enumerate(order):

        basis[t,1:] = np.exp(-1j\*j\*phases[1:])/math.sqrt(n)

    assert np.allclose(step\@basis,basis\*np.exp(1j\*phases))

    assert np.allclose(basis.conj().T\@basis,np.eye(L))

    return step,basis,phases



def log_partition(L,phi,x):

    return float(logsumexp(x\*np.cos(graph(L,phi)[2])))



\# --- 1. partition ratios: reproduce results.json ---

ref = {"L3_x1":0.8128741635889264,"L3_x4":0.5182287157053217,"L3_x8":0.5003354344752348,

       "L7_x1":0.9999476751671529,"L7_x4":0.9701669578993742,"L7_x8":0.8275660230091844,

       "L9_x1":0.9999997518917476,"L9_x4":0.9978375929191501,"L9_x8":0.958712031563662,

       "L15_x1":0.9999999999999978,"L15_x4":0.9999999355766599,"L15_x8":0.9999459324664687}

print("=== partition ratios / closed-form leakage ===")

for L in (3,7,9,15):

    N=L-1

    for x in (1,4,8):

        z0,zp=[math.exp(log_partition(L,p,x)) for p in (0,np.pi)]

        diff=4\*N\*sum(iv(m\*N,x) for m in range(1,32,2))

        ok=math.isclose(z0-zp,diff,rel_tol=1e-8,abs_tol=4e-11)

        r=zp/z0

        print(f"L={L:2d} x={x}  Zpi/Z0={r:.16f} ref_match={abs(r-ref[f'L{L}\_x{x}'])<1e-12}  Bessel_id={ok}  eps=1-r={1-r:.3e}")



\# Result

\=== partition ratios / closed-form leakage ===

L= 3 x=1  Zpi/Z0=0.8128741635889264 ref_match=True  Bessel_id=True  eps=1-r=1.871e-01

L= 3 x=4  Zpi/Z0=0.5182287157053217 ref_match=True  Bessel_id=True  eps=1-r=4.818e-01

L= 3 x=8  Zpi/Z0=0.5003354344752348 ref_match=True  Bessel_id=True  eps=1-r=4.997e-01

L= 7 x=1  Zpi/Z0=0.9999476751671529 ref_match=True  Bessel_id=True  eps=1-r=5.232e-05

L= 7 x=4  Zpi/Z0=0.9701669578993742 ref_match=True  Bessel_id=True  eps=1-r=2.983e-02

L= 7 x=8  Zpi/Z0=0.8275660230091844 ref_match=True  Bessel_id=True  eps=1-r=1.724e-01

L= 9 x=1  Zpi/Z0=0.9999997518917476 ref_match=True  Bessel_id=True  eps=1-r=2.481e-07

L= 9 x=4  Zpi/Z0=0.9978375929191501 ref_match=True  Bessel_id=True  eps=1-r=2.162e-03

L= 9 x=8  Zpi/Z0=0.9587120315636620 ref_match=True  Bessel_id=True  eps=1-r=4.129e-02

L=15 x=1  Zpi/Z0=0.9999999999999978 ref_match=True  Bessel_id=True  eps=1-r=2.220e-15

L=15 x=4  Zpi/Z0=0.9999999355766599 ref_match=True  Bessel_id=True  eps=1-r=6.442e-08

L=15 x=8  Zpi/Z0=0.9999459324664687 ref_match=True  Bessel_id=True  eps=1-r=5.407e-05





import numpy as np, math

from scipy.linalg import expm

from scipy.special import expit, logsumexp, iv

def graph(L, phi):

    n=L-1; order=[0,\*range(2,L)]

    step=np.zeros((L,L),complex); step[1,1]=1

    h=-1 if phi==np.pi else np.exp(1j\*phi)

    for j,t in enumerate(order): step[order[(j+1)%n],t]=h if j==n-1 else 1

    phases=np.r\_[0,(phi+2\*np.pi\*np.arange(n))/n]

    basis=np.zeros_like(step); basis[1,0]=1

    for j,t in enumerate(order): basis[t,1:]=np.exp(-1j\*j\*phases[1:])/math.sqrt(n)

    return step,basis,phases

def log_partition(L,phi,x): return float(logsumexp(x\*np.cos(graph(L,phi)[2])))



def chemical_control(L,x,phi,b,verbose=False,tmax=1.0):

    sectors=[graph(L,0),graph(L,phi)]

    E=np.concatenate([-x\*np.cos(k[2])-d\*b for d,k in enumerate(sectors)])

    generator=np.zeros((2\*L,2\*L))

    def pair(i,j,strength):

        generator[j,i]=strength\*expit(E[i]-E[j]); generator[i,j]=strength\*expit(E[j]-E[i])

    interact=np.eye(L); interact[[0,1]]=interact[[1,0]]

    for d,(\_,basis,\_) in enumerate(sectors):

        tr=np.abs(basis.conj().T\@interact\@basis)\*\*2

        for i in range(L):

            for j in range(i+1,L): pair(d\*L+i,d\*L+j,tr[j,i])

    overlap=np.abs(sectors[1][1].conj().T\@sectors[0][1])\*\*2

    for i in range(L):

        for j in range(L): pair(i,L+j,overlap[j,i])

    generator[np.diag_indices(2\*L)]=-generator.sum(axis=0)

    eq=np.exp(-E-logsumexp(-E)); flux=generator\*eq

    assert np.allclose(flux,flux.T) and np.allclose(generator\@eq,0)

    assert np.linalg.matrix_rank(generator,tol=1e-10)==2\*L-1

    hazard=generator[L:,:L].sum(axis=0)

    prior=np.zeros(2\*L); prior[0:2]=.5

    final_D=np.r\_[np.zeros(L),np.ones(L)]

    ev=expm(generator\*tmax); h=ev.T\@final_D

    post=h\*prior/(h\@prior)

    out=dict(K=math.exp(log_partition(L,phi,x)-log_partition(L,0,x)),

             haz=[float(hazard[k]) for k in (0,1,1+(L-1)//2)],

             P_bound=float(h\@prior), post_fixed=float(post[0]),

             hazard_sum=float(hazard.sum()), hazard_mean=float(hazard.mean()),

             eq_bound=float(eq[L:].sum()))

    if verbose:

        out['hazard_all']=hazard.tolist()

        out['P_bound_t']=[float((expm(generator\*t).T\@final_D)@prior) for t in (0.1,0.5,1,2,5,20,100)]

    return out



print("=== CHEMICAL (state-resolved) CONTROL, L=7, x=4, b=0 ===")

for name,p in [('phi=0',0),('phi=pi',np.pi)]\:

    r=chemical_control(7,4,p,0,verbose=True)

    print(name, json.dumps({k:v for k,v in r.items() if k!='hazard_all'}, indent=None) if False else r)

print()

print("analytic phi=0:  0.5\*(1-exp(-1)) =",0.5\*(1-math.exp(-1)))

print("ref phi=pi:      0.2712383303451682")

print("sum rule: sum of hazards over complete mode basis = L\*expit(b) =",7\*expit(0))



\# Result

\=== CHEMICAL (state-resolved) CONTROL, L=7, x=4, b=0 ===

phi=0 {'K': 1.0, 'haz': [0.5, 0.5000000000000002, 0.5000000000000002], 'P_bound': 0.31606027941427883, 'post_fixed': 0.5000000000000001, 'hazard_sum': 3.500000000000001, 'hazard_mean': 0.5000000000000001, 'eq_bound': 0.49999999999999994, 'hazard_all': [0.5, 0.5000000000000002, 0.5000000000000002, 0.5000000000000002, 0.5000000000000002, 0.5000000000000002, 0.5000000000000002], 'P_bound_t': [0.04758129098202023, 0.1967346701436834, 0.31606027941427883, 0.43233235838169354, 0.4966310265004573, 0.4999999989694234, 0.500000000000006]}

phi=pi {'K': 0.9701669578993741, 'haz': [0.5, 0.3081787148711199, 0.6918212851288806], 'P_bound': 0.2712383303451682, 'post_fixed': 0.575958799118784, 'hazard_sum': 3.5000000000000027, 'hazard_mean': 0.5000000000000003, 'eq_bound': 0.49242880356382707, 'hazard_all': [0.5, 0.3081787148711199, 0.4352389030674658, 0.5647610969325351, 0.6918212851288806, 0.564761096932535, 0.43523890306746615], 'P_bound_t': [0.038699781737168606, 0.16402987693815918, 0.2712383303451682, 0.38933918738661655, 0.48005148294200906, 0.4924327248343694, 0.4924288035639375]}



analytic phi=0:  0.5\*(1-exp(-1)) = 0.31606027941427883

ref phi=pi:      0.2712383303451682

sum rule: sum of hazards over complete mode basis = L\*expit(b) = 3.5





import numpy as np, math

from scipy.linalg import expm

from scipy.special import expit, logsumexp

def graph(L,phi):

    n=L-1; order=[0,\*range(2,L)]

    step=np.zeros((L,L),complex); step[1,1]=1

    h=-1 if phi==np.pi else np.exp(1j\*phi)

    for j,t in enumerate(order): step[order[(j+1)%n],t]=h if j==n-1 else 1

    phases=np.r\_[0,(phi+2\*np.pi\*np.arange(n))/n]

    basis=np.zeros_like(step); basis[1,0]=1

    for j,t in enumerate(order): basis[t,1:]=np.exp(-1j\*j\*phases[1:])/math.sqrt(n)

    return step,basis,phases

def log_partition(L,phi,x): return float(logsumexp(x\*np.cos(graph(L,phi)[2])))



def overlap_controls(L=7,x=4,t=1.0,nu=1.0,g=None):

    states=[(r,d) for r in (0,1) for d in (0,1)]

    gb=log_partition(L,0,x)-log_partition(L,np.pi,x)

    def segment(g,gate_r,gate_d,t):

        g_r,g_d=(g,g) if np.isscalar(g) else g

        Q=np.zeros((4,4))

        for i,(r,d) in enumerate(states):

            j=states.index((1-r,d)); Q[j,i]=gate_r\*nu\*expit((1-2\*r)\*(gb+g_r\*d))

            j=states.index((r,1-d)); Q[j,i]=gate_d\*nu\*expit((1-2\*d)\*g_d\*r)

        Q[np.diag_indices(4)]=-Q.sum(axis=0)

        return expm(Q\*t)

    prior=np.array([1.,0,0,0]); r,d=np.array(states,dtype=float).T

    def protocol(g,stages):

        p=prior

        for a,b in stages: p=segment(g,a,b,t)@p

        return np.array([r\@p,d\@p,p[-1]])

    g=math.log(2.) if g is None else g

    out={}

    for key,st in [('overlap',[(1,1)]),('R_then_D',[(1,0),(0,1)]),('D_then_R',[(0,1),(1,0)])]\:

        base=protocol(0,st); c=protocol(g,st); out[key]=(base,c,c-base)

    out['only_D_to_R']=protocol((g,0),[(1,1)]); out['only_R_to_D']=protocol((0,g),[(1,1)])

    mid=segment(g,1,0,t)@prior; back=segment(g,0,1,t).T\@d; pf=back\@mid

    out['mid']=(float(r\@mid),float((r\*mid)@back/pf),float((r\*mid)@(1-back)/(1-pf)))

    return out,gb



out,gb=overlap_controls()

print("graph_bias ln(Z0/Zpi) =",gb)

for k in ('overlap','R_then_D','D_then_R'):

    b,c,d=out[k]; print(f"{k:9s} uncoupled={b}  coupled={c}  delta={d}")

print("only_D_to_R:",out['only_D_to_R']," only_R_to_D:",out['only_R_to_D'])

print("mid_R marginal / |d=1 / |d=0 :",out['mid'])

print()

print("ANALYTIC uncoupled closed forms (nu\*t=1):")

print("  P(r=1)=sigmoid(lnZ0/Zpi)\*(1-e^-1) =",expit(gb)\*(1-math.exp(-1)))

print("  P(d=1)=sigmoid(b=0)\*(1-e^-1)      =",0.5\*(1-math.exp(-1)))

print("  joint = product                    =",expit(gb)\*(1-math.exp(-1))\*0.5\*(1-math.exp(-1)))

print()

print("=== g-sensitivity: what delta_B_D reproduces a given g at T=80 keV ===")

for g in (math.log(2),0.1,0.012578451540634417,0.001):

    o,\_=overlap_controls(g=g)

    dP=o['overlap'][2]

    print(f" g={g:.6f}  dB_D=g\*T={g\*80:8.3f} keV   dP(r)={dP[0]\:.6e} dP(d)={dP[1]\:.6e} dP(r,d)={dP[2]\:.6e}")

print()

print("linear response coefficient dP(d)/dg at g->0:", (overlap_controls(g=1e-6)[0]['overlap'][2][1])/1e-6)



\# Result

graph_bias ln(Z0/Zpi) = 0.03028710075017571

overlap   uncoupled=[0.3208461883 0.3160602794 0.1014067359]  coupled=[0.3439218621 0.3395690729 0.142408467 ]  delta=[0.0230756738 0.0235087935 0.0410017311]

R_then_D  uncoupled=[0.3208461883 0.3160602794 0.1014067359]  coupled=[0.3208461883 0.3498625247 0.1352089812]  delta=[-0.            0.0338022453  0.0338022453]

D_then_R  uncoupled=[0.3208461883 0.3160602794 0.1014067359]  coupled=[0.3539693985 0.3160602794 0.1345299461]  delta=[ 0.0331232102 -0.            0.0331232102]

only_D_to_R: [0.3427506704 0.3160602794 0.1206397795]  only_R_to_D: [0.3208461883 0.3384138095 0.1210753435]

mid_R marginal / |d=1 / |d=0 : (0.32084618833651307, 0.38646317250511636, 0.2855353123768695)



ANALYTIC uncoupled closed forms (nu\*t=1):

  P(r=1)=sigmoid(lnZ0/Zpi)\*(1-e^-1) = 0.32084618833651307

  P(d=1)=sigmoid(b=0)\*(1-e^-1)      = 0.31606027941427883

  joint = product                    = 0.10140673593464465



\=== g-sensitivity: what delta_B_D reproduces a given g at T=80 keV ===

 g=0.693147  dB_D=g\*T=  55.452 keV   dP(r)=2.307567e-02 dP(d)=2.350879e-02 dP(r,d)=4.100173e-02

 g=0.100000  dB_D=g\*T=   8.000 keV   dP(r)=3.322568e-03 dP(d)=3.375417e-03 dP(r,d)=5.888519e-03

 g=0.012578  dB_D=g\*T=   1.006 keV   dP(r)=4.157309e-04 dP(d)=4.221508e-04 dP(r,d)=7.364930e-04

 g=0.001000  dB_D=g\*T=   0.080 keV   dP(r)=3.302486e-05 dP(d)=3.353280e-05 dP(r,d)=5.850243e-05



linear response coefficient dP(d)/dg at g->0: 0.03353029753849768





import numpy as np, math

from scipy.special import iv, ive, logsumexp

from scipy.optimize import brentq



def logZ(L,phi,x):

    N=L-1

    ph=np.r\_[0,(phi+2\*np.pi\*np.arange(N))/N]

    return float(logsumexp(x\*np.cos(ph)))

def eps(L,x):  # eps = 1 - Z(pi)/Z(0)

    return 1-math.exp(logZ(L,np.pi,x)-logZ(L,0,x))



print("=== BESSEL AUDIT at x=4 ===")

x=4.0

for L in (3,7,9,15):

    N=L-1

    lead=(x/2)\*\*N/math.factorial(N)

    c1=(x/2)\*\*2/(N+1)

    exact=iv(N,x)

    m3=iv(3\*N,x)

    print(f"L={L:2d} N={N:2d}: leading (x/2)^N/N! = {lead:.6e} | exact I_N(4) = {exact:.6e} | exact/lead = {exact/lead:.6f}"

          f" | 1st corr (x/2)^2/(N+1) = {c1:.6f} ({100\*c1:.2f}%) | I_3N/I_N = {m3/exact:.3e}")

print()

print("series terms for N=6, x=4 (relative to leading):")

N=6; tot=0

for k in range(8):

    t=(x/2)\*\*(2\*k)/(math.factorial(k)\*math.prod(range(N+1,N+k+1)) if k else 1.0)

    tot+=t; print(f"  k={k}: {t:.8f}   cumulative={tot:.8f}")

print()

print("=== effect of using the leading term only on dF (L=7,x=4,T=0.1 MeV) ===")

Z0=math.exp(logZ(7,0,4)); N=6

for name,IN in [("leading",2\*\*6/720),("+1st corr",2\*\*6/720\*(1+4/7)),("exact iv(6,4)",iv(6,4))]\:

    dZ=4\*N\*IN; e=dZ/Z0; dF=-math.log(1-e)\*100  # keV at T=0.1 MeV=100 keV

    print(f"  {name:14s} dZ={dZ:.6f} eps={e:.6f}  dF={dF:.4f} keV")

print()

print("=== J NO-GO: x required for a target thermal contrast eps ===")

print("   eps = 1 - Z(pi)/Z(0);  x = 2J/T;  J = x\*T/2;  T = 0.1 MeV")

rows=[]

for L in (3,7,9,15):

    N=L-1

    line=[f"L={L:2d} N={N:2d}"]

    for target in (0.01,0.1,0.5):

        xr=brentq(lambda xx: eps(L,xx)-target, 0.05, 400)

        line.append(f"eps={target}: x\*={xr:8.3f} J\*={xr\*0.1/2:7.3f} MeV  (x\*/N^2={xr/N\*\*2:.3f})")

    rows.append(" | ".join(line))

print("\n".join(rows))

print()

print("=== contrast at the three 'natural' choices of J ===")

for L in (7,9,15):

    N=L-1

    for label,x in [("x=4 (model)",4.0),("x=N (J=NT/2)",float(N)),("x=N^2/2",N\*\*2/2)]\:

        e=eps(L,x); dF=-math.log(1-e)\*100

        print(f" L={L:2d} {label:16s} x={x:7.2f}  eps={e:.4e}  dF={dF:.4e} keV @T=0.1MeV  J={x\*0.05:.3f} MeV")

print()

print("=== asymptotic law check: eps \~ 4N exp(-N^2/(2x)) / (sqrt(2 pi x)+N) ===")

for L,x in [(7,4),(7,8),(7,18),(9,8),(9,32),(15,8),(15,98)]\:

    N=L-1

    approx=4\*N\*math.exp(-N\*\*2/(2\*x))/(math.sqrt(2\*math.pi\*x)+N)

    print(f" L={L:2d} x={x:5.1f}: exact eps={eps(L,x):.4e}  gaussian approx={approx:.4e}  ratio={approx/eps(L,x):.3f}")



\# Result

execute error





import numpy as np, math

from scipy.special import iv, logsumexp

from scipy.optimize import brentq

def logZ(L,phi,x):

    N=L-1; ph=np.r\_[0,(phi+2\*np.pi\*np.arange(N))/N]

    return float(logsumexp(x\*np.cos(ph)))

def eps(L,x): return 1-math.exp(logZ(L,np.pi,x)-logZ(L,0,x))

def bias(L,x): return logZ(L,0,x)-logZ(L,np.pi,x)



print("=== supremum of the seam bias  ln(Z0/Zpi) ===")

for L in (3,7,9,15,31):

    xs=np.logspace(-2,4,400); vals=[bias(L,x) for x in xs]

    print(f" L={L:2d}: max over x in [0.01,1e4] = {max(vals):.10f}   ln2={math.log(2):.10f}   at x={xs[int(np.argmax(vals))]\:.1f}")

print()

print("=== J NO-GO: x\* needed for a target contrast eps (T=0.1 MeV) ===")

for L in (3,7,9,15):

    N=L-1; parts=[]

    for target in (0.01,0.1,0.4):

        xr=brentq(lambda xx: eps(L,xx)-target,0.05,2000)

        parts.append(f"eps={target:<4}: x\*={xr:8.2f}, J\*={xr\*0.05:7.3f} MeV, x\*/N^2={xr/N\*\*2:.3f}")

    print(f" L={L:2d} N={N:2d} | "+" | ".join(parts))

print()

print("=== contrast at 'natural' J choices, T=0.1 MeV ===")

for L in (7,9,15):

    N=L-1

    for lab,x in [("x=4 (model)",4.0),("x=N (J=NT/2)",float(N)),("x=N^2/2",N\*\*2/2)]\:

        e=eps(L,x); print(f" L={L:2d} {lab:15s} x={x:7.2f} J={x\*0.05:6.3f} MeV  eps={e:.4e}  dF={bias(L,x)\*100:.4e} keV")

print()

print("=== gaussian asymptote eps \~ 4N e^{-N^2/2x}/(sqrt(2 pi x)+N) ===")

for L,x in [(7,4),(7,8),(7,18),(9,8),(9,32),(15,8),(15,98)]\:

    N=L-1; ap=4\*N\*math.exp(-N\*\*2/(2\*x))/(math.sqrt(2\*math.pi\*x)+N)

    print(f" L={L:2d} x={x:5.1f}: exact={eps(L,x):.4e} approx={ap:.4e} ratio={ap/eps(L,x):.3f}")

print()

print("=== self-consistent coupling g = seam bias (mutual regime) vs g=ln2 ===")

from scipy.linalg import expm

from scipy.special import expit

def four(L,x,g,t=1.0):

    st=[(r,d) for r in (0,1) for d in (0,1)]; gb=bias(L,x)

    Q=np.zeros((4,4))

    for i,(r,d) in enumerate(st):

        j=st.index((1-r,d)); Q[j,i]=expit((1-2\*r)\*(gb+g\*d))

        j=st.index((r,1-d)); Q[j,i]=expit((1-2\*d)\*g\*r)

    Q[np.diag_indices(4)]=-Q.sum(axis=0)

    p=expm(Q\*t)@np.array([1.,0,0,0]); r,d=np.array(st,float).T

    return np.array([r\@p,d\@p,p[-1]])

for L in (7,9,15):

    gb=bias(L,4)

    for lab,g in [("g=ln2 (README)",math.log(2)),("g=bias (self-consistent)",gb),("g=1keV/80keV",1/80)]\:

        dd=four(L,4,g)-four(L,4,0.0)

        print(f" L={L:2d} {lab:26s} g={g:.6e}  dP(r)={dd[0]\:.4e} dP(d)={dd[1]\:.4e} dP(rd)={dd[2]\:.4e}")



\# Result

\=== supremum of the seam bias  ln(Z0/Zpi) ===

 L= 3: max over x in [0.01,1e4] = 0.6931471806   ln2=0.6931471806   at x=2105.3

 L= 7: max over x in [0.01,1e4] = 0.6931471806   ln2=0.6931471806   at x=2105.3

 L= 9: max over x in [0.01,1e4] = 0.6931471806   ln2=0.6931471806   at x=2105.3

 L=15: max over x in [0.01,1e4] = 0.6931471806   ln2=0.6931471806   at x=2105.3

 L=31: max over x in [0.01,1e4] = 0.6931471806   ln2=0.6931471806   at x=5362.0



\=== J NO-GO: x\* needed for a target contrast eps (T=0.1 MeV) ===









 L= 3 N= 2 | eps=0.01: x\*=    0.18, J\*=  0.009 MeV, x\*/N^2=0.045 | eps=0.1 : x\*=    0.65, J\*=  0.032 MeV, x\*/N^2=0.162 | eps=0.4 : x\*=    2.27, J\*=  0.114 MeV, x\*/N^2=0.568

 L= 7 N= 6 | eps=0.01: x\*=    2.96, J\*=  0.148 MeV, x\*/N^2=0.082 | eps=0.1 : x\*=    6.13, J\*=  0.306 MeV, x\*/N^2=0.170 | eps=0.4 : x\*=   17.18, J\*=  0.859 MeV, x\*/N^2=0.477

 L= 9 N= 8 | eps=0.01: x\*=    5.51, J\*=  0.276 MeV, x\*/N^2=0.086 | eps=0.1 : x\*=   10.92, J\*=  0.546 MeV, x\*/N^2=0.171 | eps=0.4 : x\*=   30.24, J\*=  1.512 MeV, x\*/N^2=0.472

 L=15 N=14 | eps=0.01: x\*=   17.66, J\*=  0.883 MeV, x\*/N^2=0.090 | eps=0.1 : x\*=   33.47, J\*=  1.674 MeV, x\*/N^2=0.171 | eps=0.4 : x\*=   91.81, J\*=  4.591 MeV, x\*/N^2=0.468



\=== contrast at 'natural' J choices, T=0.1 MeV ===

 L= 7 x=4 (model)     x=   4.00 J= 0.200 MeV  eps=2.9833e-02  dF=3.0287e+00 keV

 L= 7 x=N (J=NT/2)    x=   6.00 J= 0.300 MeV  eps=9.5072e-02  dF=9.9900e+00 keV

 L= 7 x=N^2/2         x=  18.00 J= 0.900 MeV  eps=4.1040e-01  dF=5.2830e+01 keV

 L= 9 x=4 (model)     x=   4.00 J= 0.200 MeV  eps=2.1624e-03  dF=2.1647e-01 keV

 L= 9 x=N (J=NT/2)    x=   8.00 J= 0.400 MeV  eps=4.1288e-02  dF=4.2165e+00 keV

 L= 9 x=N^2/2         x=  32.00 J= 1.600 MeV  eps=4.1253e-01  dF=5.3193e+01 keV

 L=15 x=4 (model)     x=   4.00 J= 0.200 MeV  eps=6.4423e-08  dF=6.4423e-06 keV

 L=15 x=N (J=NT/2)    x=  14.00 J= 0.700 MeV  eps=2.8912e-03  dF=2.8954e-01 keV

 L=15 x=N^2/2         x=  98.00 J= 4.900 MeV  eps=4.1435e-01  dF=5.3503e+01 keV



\=== gaussian asymptote eps \~ 4N e^{-N^2/2x}/(sqrt(2 pi x)+N) ===

 L= 7 x=  4.0: exact=2.9833e-02 approx=2.4209e-02 ratio=0.811

 L= 7 x=  8.0: exact=1.7243e-01 approx=1.9325e-01 ratio=1.121

 L= 7 x= 18.0: exact=4.1040e-01 approx=5.3076e-01 ratio=1.293

 L= 9 x=  8.0: exact=4.1288e-02 approx=3.8841e-02 ratio=0.941

 L= 9 x= 32.0: exact=4.1253e-01 approx=5.3076e-01 ratio=1.287

 L=15 x=  8.0: exact=5.4068e-05 approx=1.2706e-05 ratio=0.235

 L=15 x= 98.0: exact=4.1435e-01 approx=5.3076e-01 ratio=1.281



\=== self-consistent coupling g = seam bias (mutual regime) vs g=ln2 ===

 L= 7 g=ln2 (README)             g=6.931472e-01  dP(r)=2.3076e-02 dP(d)=2.3509e-02 dP(rd)=4.1002e-02

 L= 7 g=bias (self-consistent)   g=3.028710e-02  dP(r)=1.0022e-03 dP(d)=1.0178e-03 dP(rd)=1.7756e-03

 L= 7 g=1keV/80keV               g=1.250000e-02  dP(r)=4.1314e-04 dP(d)=4.1952e-04 dP(rd)=7.3190e-04

 L= 9 g=ln2 (README)             g=6.931472e-01  dP(r)=2.3174e-02 dP(d)=2.3204e-02 dP(rd)=4.0780e-02

 L= 9 g=bias (self-consistent)   g=2.164748e-03  dP(r)=7.1514e-05 dP(d)=7.1591e-05 dP(rd)=1.2566e-04

 L= 9 g=1keV/80keV               g=1.250000e-02  dP(r)=4.1326e-04 dP(d)=4.1371e-04 dP(rd)=7.2619e-04

 L=15 g=ln2 (README)             g=6.931472e-01  dP(r)=2.3181e-02 dP(d)=2.3181e-02 dP(rd)=4.0763e-02

 L=15 g=bias (self-consistent)   g=6.442334e-08  dP(r)=2.1279e-09 dP(d)=2.1279e-09 dP(rd)=3.7368e-09

 L=15 g=1keV/80keV               g=1.250000e-02  dP(r)=4.1326e-04 dP(d)=4.1326e-04 dP(rd)=7.2574e-04





import math

hbar=6.582119569e-16      # eV\*s

Mpl=1.22089e28            # eV

def H_s(T_MeV,gstar=3.36):           # H in 1/s

    T=T_MeV\*1e6

    return 1.66\*math.sqrt(gstar)\*T\*T/Mpl/hbar

def H_MeV(T_MeV,gstar=3.36):

    T=T_MeV\*1e6; return 1.66\*math.sqrt(gstar)\*T\*T/Mpl/1e6

print("H(T=0.1 MeV, g\*=3.36) =",H_s(0.1),"1/s   (snippet: 3.7864e-3)")

print("H(T=0.08)             =",H_s(0.08))

print()

print("=== S_max = ln(omega0/H): ceiling on the instanton action ===")

print("  omega0 = J/hbar (attempt frequency).  J from x=2J/T at T=0.1 MeV.")

for L in (7,9,15):

    N=L-1

    for lab,x in [("x=4",4.0),("x=N",float(N)),("x=0.17N^2",0.17\*N\*N),("x=N^2/2",N\*N/2)]\:

        J=x\*0.1/2; om=J\*1e6/hbar; S=math.log(om/H_s(0.1))

        print(f" L={L:2d} {lab:10s} J={J:7.3f} MeV  omega0={om:.4e} 1/s  S_max={S:7.3f}   Gamma/H at S=50: {math.exp(S-50):.3e}")

print()

print("=== temperature dependence of the ceiling (J FIXED, x=2J/T evolves) ===")

for J in (0.2,0.9,4.9):

    print(f" J={J} MeV:")

    for T in (1.0,0.5,0.3,0.2,0.1,0.08,0.05,0.03):

        gs=10.75 if T>0.4 else 3.36

        S=math.log(J\*1e6/hbar/H_s(T,gs)); x=2\*J/T

        print(f"   T={T:5.2f} MeV g\*={gs:5.2f} x={x:8.2f}  S_max={S:7.3f}")



\# Result

H(T=0.1 MeV, g\*=3.36) = 0.003786477869422765 1/s   (snippet: 3.7864e-3)

H(T=0.08)             = 0.0024233458364305697



\=== S_max = ln(omega0/H): ceiling on the instanton action ===

  omega0 = J/hbar (attempt frequency).  J from x=2J/T at T=0.1 MeV.

 L= 7 x=4        J=  0.200 MeV  omega0=3.0385e+20 1/s  S_max= 52.739   Gamma/H at S=50: 1.548e+01

 L= 7 x=N        J=  0.300 MeV  omega0=4.5578e+20 1/s  S_max= 53.145   Gamma/H at S=50: 2.322e+01

 L= 7 x=0.17N^2  J=  0.306 MeV  omega0=4.6490e+20 1/s  S_max= 53.165   Gamma/H at S=50: 2.368e+01

 L= 7 x=N^2/2    J=  0.900 MeV  omega0=1.3673e+21 1/s  S_max= 54.243   Gamma/H at S=50: 6.965e+01

 L= 9 x=4        J=  0.200 MeV  omega0=3.0385e+20 1/s  S_max= 52.739   Gamma/H at S=50: 1.548e+01

 L= 9 x=N        J=  0.400 MeV  omega0=6.0771e+20 1/s  S_max= 53.433   Gamma/H at S=50: 3.096e+01

 L= 9 x=0.17N^2  J=  0.544 MeV  omega0=8.2648e+20 1/s  S_max= 53.740   Gamma/H at S=50: 4.210e+01

 L= 9 x=N^2/2    J=  1.600 MeV  omega0=2.4308e+21 1/s  S_max= 54.819   Gamma/H at S=50: 1.238e+02

 L=15 x=4        J=  0.200 MeV  omega0=3.0385e+20 1/s  S_max= 52.739   Gamma/H at S=50: 1.548e+01

 L=15 x=N        J=  0.700 MeV  omega0=1.0635e+21 1/s  S_max= 53.992   Gamma/H at S=50: 5.417e+01

 L=15 x=0.17N^2  J=  1.666 MeV  omega0=2.5311e+21 1/s  S_max= 54.859   Gamma/H at S=50: 1.289e+02

 L=15 x=N^2/2    J=  4.900 MeV  omega0=7.4444e+21 1/s  S_max= 55.938   Gamma/H at S=50: 3.792e+02



\=== temperature dependence of the ceiling (J FIXED, x=2J/T evolves) ===

 J=0.2 MeV:

   T= 1.00 MeV g\*=10.75 x=    0.40  S_max= 47.553

   T= 0.50 MeV g\*=10.75 x=    0.80  S_max= 48.939

   T= 0.30 MeV g\*= 3.36 x=    1.33  S_max= 50.542

   T= 0.20 MeV g\*= 3.36 x=    2.00  S_max= 51.353

   T= 0.10 MeV g\*= 3.36 x=    4.00  S_max= 52.739

   T= 0.08 MeV g\*= 3.36 x=    5.00  S_max= 53.186

   T= 0.05 MeV g\*= 3.36 x=    8.00  S_max= 54.126

   T= 0.03 MeV g\*= 3.36 x=   13.33  S_max= 55.147

 J=0.9 MeV:

   T= 1.00 MeV g\*=10.75 x=    1.80  S_max= 49.057

   T= 0.50 MeV g\*=10.75 x=    3.60  S_max= 50.443

   T= 0.30 MeV g\*= 3.36 x=    6.00  S_max= 52.046

   T= 0.20 MeV g\*= 3.36 x=    9.00  S_max= 52.857

   T= 0.10 MeV g\*= 3.36 x=   18.00  S_max= 54.243

   T= 0.08 MeV g\*= 3.36 x=   22.50  S_max= 54.690

   T= 0.05 MeV g\*= 3.36 x=   36.00  S_max= 55.630

   T= 0.03 MeV g\*= 3.36 x=   60.00  S_max= 56.651

 J=4.9 MeV:

   T= 1.00 MeV g\*=10.75 x=    9.80  S_max= 50.751

   T= 0.50 MeV g\*=10.75 x=   19.60  S_max= 52.138

   T= 0.30 MeV g\*= 3.36 x=   32.67  S_max= 53.741

   T= 0.20 MeV g\*= 3.36 x=   49.00  S_max= 54.552

   T= 0.10 MeV g\*= 3.36 x=   98.00  S_max= 55.938

   T= 0.08 MeV g\*= 3.36 x=  122.50  S_max= 56.384

   T= 0.05 MeV g\*= 3.36 x=  196.00  S_max= 57.324

   T= 0.03 MeV g\*= 3.36 x=  326.67  S_max= 58.346





import math

from scipy.optimize import brentq

from scipy.special import logsumexp, zeta

import numpy as np

hbar=6.582119569e-16; Mpl=1.22089e28

def gstar(T):

    # crude e+-annihilation interpolation: photons + e± + 3 nu

    if T>0.5: return 10.75

    if T<0.05: return 3.36

    return 3.36+(10.75-3.36)\*(T-0.05)/0.45

def H_s(T): 

    t=T\*1e6; return 1.66\*math.sqrt(gstar(T))\*t\*t/Mpl/hbar

def logZ(L,phi,x):

    N=L-1; ph=np.r\_[0,(phi+2\*np.pi\*np.arange(N))/N]; return float(logsumexp(x\*np.cos(ph)))

def eps(L,x): return 1-math.exp(logZ(L,np.pi,x)-logZ(L,0,x))



print("=== FREEZE-OUT of the seam vs its VISIBILITY  (J fixed, S = c\*J/T = c\*x/2) ===")

print("  Gamma_r = (J/hbar) exp(-c\*J/T);   freeze-out: Gamma_r = H")

print("  visibility: eps >= 0.01  ->  x_vis ;  T_vis = 2J/x_vis")

for L in (7,9,15):

    N=L-1

    x_vis=brentq(lambda xx: eps(L,xx)-0.01,0.05,2000)

    x_10 =brentq(lambda xx: eps(L,xx)-0.10,0.05,2000)

    for J in (0.2,0.9,1.674,4.9):

        Tv=2\*J/x_vis; Tv10=2\*J/x_10

        line=f" L={L:2d} J={J:5.3f} MeV  T_vis(eps=.01)={Tv:6.3f}  T_vis(eps=.1)={Tv10:6.3f} |"

        for c in (1,2,4):

            f=lambda T: math.log(J\*1e6/hbar)-c\*J/T-math.log(H_s(T))

            try:

                Tf=brentq(f,0.005,5.0)

                line+=f" c={c}: T_frz={Tf:6.3f}"

            except ValueError:

                line+=f" c={c}: T_frz=  none "

        print(line)

print()

print("  BBN reference windows: n/p freeze-out \~0.7-0.8 MeV; D-bottleneck \~0.08 MeV; D burning ends \~0.03 MeV")

print()

print("=== eps and dF at the D-bottleneck T=0.08 MeV for those J ===")

for L in (7,9,15):

    for J in (0.2,0.9,1.674,4.9):

        x=2\*J/0.08; e=eps(L,x)

        print(f" L={L:2d} J={J:5.3f}  x={x:8.2f}  eps={e:.4e}  dF={-math.log(1-e)\*80:9.4f} keV  (ceiling T ln2={80\*math.log(2):.2f} keV)")



\# Result

\=== FREEZE-OUT of the seam vs its VISIBILITY  (J fixed, S = c\*J/T = c\*x/2) ===

  Gamma_r = (J/hbar) exp(-c\*J/T);   freeze-out: Gamma_r = H

  visibility: eps >= 0.01  ->  x_vis ;  T_vis = 2J/x_vis

 L= 7 J=0.200 MeV  T_vis(eps=.01)= 0.135  T_vis(eps=.1)= 0.065 | c=1: T_frz=  none  c=2: T_frz= 0.007 c=4: T_frz= 0.014

 L= 7 J=0.900 MeV  T_vis(eps=.01)= 0.607  T_vis(eps=.1)= 0.294 | c=1: T_frz= 0.016 c=2: T_frz= 0.032 c=4: T_frz= 0.065

 L= 7 J=1.674 MeV  T_vis(eps=.01)= 1.129  T_vis(eps=.1)= 0.546 | c=1: T_frz= 0.029 c=2: T_frz= 0.060 c=4: T_frz= 0.123

 L= 7 J=4.900 MeV  T_vis(eps=.01)= 3.306  T_vis(eps=.1)= 1.599 | c=1: T_frz= 0.087 c=2: T_frz= 0.180 c=4: T_frz= 0.371

 L= 9 J=0.200 MeV  T_vis(eps=.01)= 0.073  T_vis(eps=.1)= 0.037 | c=1: T_frz=  none  c=2: T_frz= 0.007 c=4: T_frz= 0.014

 L= 9 J=0.900 MeV  T_vis(eps=.01)= 0.326  T_vis(eps=.1)= 0.165 | c=1: T_frz= 0.016 c=2: T_frz= 0.032 c=4: T_frz= 0.065

 L= 9 J=1.674 MeV  T_vis(eps=.01)= 0.607  T_vis(eps=.1)= 0.307 | c=1: T_frz= 0.029 c=2: T_frz= 0.060 c=4: T_frz= 0.123

 L= 9 J=4.900 MeV  T_vis(eps=.01)= 1.777  T_vis(eps=.1)= 0.898 | c=1: T_frz= 0.087 c=2: T_frz= 0.180 c=4: T_frz= 0.371

 L=15 J=0.200 MeV  T_vis(eps=.01)= 0.023  T_vis(eps=.1)= 0.012 | c=1: T_frz=  none  c=2: T_frz= 0.007 c=4: T_frz= 0.014

 L=15 J=0.900 MeV  T_vis(eps=.01)= 0.102  T_vis(eps=.1)= 0.054 | c=1: T_frz= 0.016 c=2: T_frz= 0.032 c=4: T_frz= 0.065

 L=15 J=1.674 MeV  T_vis(eps=.01)= 0.190  T_vis(eps=.1)= 0.100 | c=1: T_frz= 0.029 c=2: T_frz= 0.060 c=4: T_frz= 0.123

 L=15 J=4.900 MeV  T_vis(eps=.01)= 0.555  T_vis(eps=.1)= 0.293 | c=1: T_frz= 0.087 c=2: T_frz= 0.180 c=4: T_frz= 0.371



  BBN reference windows: n/p freeze-out \~0.7-0.8 MeV; D-bottleneck \~0.08 MeV; D burning ends \~0.03 MeV



\=== eps and dF at the D-bottleneck T=0.08 MeV for those J ===

 L= 7 J=0.200  x=    5.00  eps=5.9170e-02  dF=   4.8794 keV  (ceiling T ln2=55.45 keV)

 L= 7 J=0.900  x=   22.50  eps=4.5093e-01  dF=  47.9628 keV  (ceiling T ln2=55.45 keV)

 L= 7 J=1.674  x=   41.85  eps=4.9633e-01  dF=  54.8663 keV  (ceiling T ln2=55.45 keV)

 L= 7 J=4.900  x=  122.50  eps=5.0000e-01  dF=  55.4518 keV  (ceiling T ln2=55.45 keV)

 L= 9 J=0.200  x=    5.00  eps=6.4534e-03  dF=   0.5179 keV  (ceiling T ln2=55.45 keV)

 L= 9 J=0.900  x=   22.50  eps=3.2056e-01  dF=  30.9185 keV  (ceiling T ln2=55.45 keV)

 L= 9 J=1.674  x=   41.85  eps=4.5865e-01  dF=  49.0953 keV  (ceiling T ln2=55.45 keV)

 L= 9 J=4.900  x=  122.50  eps=4.9991e-01  dF=  55.4375 keV  (ceiling T ln2=55.45 keV)

 L=15 J=0.200  x=    5.00  eps=6.8159e-07  dF=   0.0001 keV  (ceiling T ln2=55.45 keV)

 L=15 J=0.900  x=   22.50  eps=2.8601e-02  dF=   2.3214 keV  (ceiling T ln2=55.45 keV)

 L=15 J=1.674  x=   41.85  eps=1.6297e-01  dF=  14.2313 keV  (ceiling T ln2=55.45 keV)

 L=15 J=4.900  x=  122.50  eps=4.5364e-01  dF=  48.3587 keV  (ceiling T ln2=55.45 keV)





import math, numpy as np

from scipy.integrate import quad

from scipy.special import zeta

from scipy.optimize import brentq

hbar=6.582119569e-16; Mpl=1.22089e28; me=0.51099895; mN=938.9; eta=6.1e-10

f=(4/11)\*\*(1/3)

print("=== Delta N_eff: relativistic decoupled sector (real scalar, g=1) ===")

for gdec in (10.75,28.,61.75,106.75,202.):

    r=(10.75/gdec)\*\*(1/3); rx=r\*f; dN=(4/7)\*r\*\*4

    print(f" g\_\*s(dec)={gdec:7.2f}  T_X/T_nu={r:.4f}  T_X/T_gamma={rx:.4f}  dNeff(g=1)={dN:.4f}   (4/7)(11/4)^(4/3)={(4/7)\*(11/4)\*\*(4/3):.4f}")

print()

print("=== Delta N_eff if X becomes NON-RELATIVISTIC with conserved number, m_X=2J ===")

Tg=0.08; Tnu=Tg\*f

rho1nu=(7/4)\*(math.pi\*\*2/15)\*Tnu\*\*4

print(f" T_gamma={Tg} MeV, T_nu={Tnu:.5f} MeV, rho_1nu={rho1nu:.4e} MeV^4")

for gdec in (28.,106.75,202.):

    Tx=(10.75/gdec)\*\*(1/3)\*f\*Tg

    nX=zeta(3)/math.pi\*\*2\*Tx\*\*3

    row=f" g_dec={gdec:6.2f} T_X={Tx:.5f} MeV n_X(g=1)={nX:.3e} MeV^3 |"

    for m in (0.4,1.8,3.35,9.8):

        row+=f" m={m:4.2f}: dNeff={m\*nX/rho1nu:7.3f}"

    print(row)

print(" -> for L=7 (g_X=7 internal states) multiply by 7; for the full R150 core |V|=3L(L-1)=126 multiply by 126")

print()

print("=== TRACE BUDGET Theta_SM during BBN (back-reaction on a universally coupled mediator) ===")

def Theta_e(T):

    a=me/T

    I=quad(lambda x: math.sqrt(max(x\*x-a\*a,0))/(math.exp(x)+1),a,a+60,limit=200)[0]

    return 4\*me\*\*2\*T\*\*2/(2\*math.pi\*\*2)\*I

for T in (0.5,0.3,0.2,0.1,0.08,0.05):

    nb=eta\*2\*zeta(3)/math.pi\*\*2\*T\*\*3

    gs=10.75 if T>0.4 else 3.36

    rho=gs\*math.pi\*\*2/30\*T\*\*4

    Tb=mN\*nb; Te=Theta_e(T); Tnuc_max=8.0\*nb; Tnuc_real=7.07\*0.247\*nb

    print(f" T={T:4.2f}  rho_rad={rho:.3e}  Theta_e={Te:.3e}  Theta_b={Tb:.3e}  Theta_nuc(real)={Tnuc_real:.3e}"

          f" | Theta_nuc/Theta_e={Tnuc_real/Te:.2e}  Theta_nuc/Theta_b={Tnuc_real/Tb:.2e}  Theta_nuc/rho={Tnuc_real/rho:.2e} (README budget 8MeV: {Tnuc_max/rho:.2e})")

print()

print("=== sigma-mediator: static susceptibility window ===")

T=0.08; nb=eta\*2\*zeta(3)/math.pi\*\*2\*T\*\*3

H=1.66\*math.sqrt(3.36)\*(T\*1e6)\*\*2/Mpl/1e6   # MeV

print(f" n_b={nb:.3e} MeV^3, H={H:.3e} MeV = {H\*1e6:.3e} eV")

for fD in (1e-5,1e-4,1e-3):

    nD=fD\*nb

    for dBd_keV in (1.0,7.7,55.45):

        dBd=dBd_keV\*1e-3

        m=sqrt=nD\*\*0.5/dBd\*\*0.5   # B_D'=1 (MeV/MeV)

        print(f"  n_D/n_b={fD:.0e}  target dB_D={dBd_keV:6.2f} keV -> m_sigma = {m\*1e6:9.4f} eV  (m/H={m/H:.2e})")

print(" -> m_sigma \~ 0.01-0.3 eV, i.e. 22-24 orders ABOVE H: the criterion m<\~H is neither necessary nor sufficient")



\# Result

\=== Delta N_eff: relativistic decoupled sector (real scalar, g=1) ===

 g\_\*s(dec)=  10.75  T_X/T_nu=1.0000  T_X/T_gamma=0.7138  dNeff(g=1)=0.5714   (4/7)(11/4)^(4/3)=2.2016

 g\_\*s(dec)=  28.00  T_X/T_nu=0.7268  T_X/T_gamma=0.5188  dNeff(g=1)=0.1595   (4/7)(11/4)^(4/3)=2.2016

 g\_\*s(dec)=  61.75  T_X/T_nu=0.5584  T_X/T_gamma=0.3985  dNeff(g=1)=0.0555   (4/7)(11/4)^(4/3)=2.2016

 g\_\*s(dec)= 106.75  T_X/T_nu=0.4652  T_X/T_gamma=0.3321  dNeff(g=1)=0.0268   (4/7)(11/4)^(4/3)=2.2016

 g\_\*s(dec)= 202.00  T_X/T_nu=0.3761  T_X/T_gamma=0.2685  dNeff(g=1)=0.0114   (4/7)(11/4)^(4/3)=2.2016



\=== Delta N_eff if X becomes NON-RELATIVISTIC with conserved number, m_X=2J ===

 T_gamma=0.08 MeV, T_nu=0.05710 MeV, rho_1nu=1.2241e-05 MeV^4

 g_dec= 28.00 T_X=0.04150 MeV n_X(g=1)=8.706e-06 MeV^3 | m=0.40: dNeff=  0.284 m=1.80: dNeff=  1.280 m=3.35: dNeff=  2.382 m=9.80: dNeff=  6.970

 g_dec=106.75 T_X=0.02657 MeV n_X(g=1)=2.284e-06 MeV^3 | m=0.40: dNeff=  0.075 m=1.80: dNeff=  0.336 m=3.35: dNeff=  0.625 m=9.80: dNeff=  1.828

 g_dec=202.00 T_X=0.02148 MeV n_X(g=1)=1.207e-06 MeV^3 | m=0.40: dNeff=  0.039 m=1.80: dNeff=  0.177 m=3.35: dNeff=  0.330 m=9.80: dNeff=  0.966

 -> for L=7 (g_X=7 internal states) multiply by 7; for the full R150 core |V|=3L(L-1)=126 multiply by 126



\=== TRACE BUDGET Theta_SM during BBN (back-reaction on a universally coupled mediator) ===

 T=0.50  rho_rad=2.210e-01  Theta_e=7.085e-03  Theta_b=1.744e-08  Theta_nuc(real)=3.243e-11 | Theta_nuc/Theta_e=4.58e-09  Theta_nuc/Theta_b=1.86e-03  Theta_nuc/rho=1.47e-10 (README budget 8MeV: 6.72e-10)

 T=0.30  rho_rad=8.954e-03  Theta_e=1.599e-03  Theta_b=3.767e-09  Theta_nuc(real)=7.006e-12 | Theta_nuc/Theta_e=4.38e-09  Theta_nuc/Theta_b=1.86e-03  Theta_nuc/rho=7.82e-10 (README budget 8MeV: 3.58e-09)

 T=0.20  rho_rad=1.769e-03  Theta_e=3.639e-04  Theta_b=1.116e-09  Theta_nuc(real)=2.076e-12 | Theta_nuc/Theta_e=5.70e-09  Theta_nuc/Theta_b=1.86e-03  Theta_nuc/rho=1.17e-09 (README budget 8MeV: 5.38e-09)

 T=0.10  rho_rad=1.105e-04  Theta_e=9.658e-06  Theta_b=1.395e-10  Theta_nuc(real)=2.595e-13 | Theta_nuc/Theta_e=2.69e-08  Theta_nuc/Theta_b=1.86e-03  Theta_nuc/rho=2.35e-09 (README budget 8MeV: 1.08e-08)

 T=0.08  rho_rad=4.528e-05  Theta_e=1.905e-06  Theta_b=7.143e-11  Theta_nuc(real)=1.329e-13 | Theta_nuc/Theta_e=6.97e-08  Theta_nuc/Theta_b=1.86e-03  Theta_nuc/rho=2.93e-09 (README budget 8MeV: 1.34e-08)

 T=0.05  rho_rad=6.909e-06  Theta_e=2.000e-08  Theta_b=1.744e-11  Theta_nuc(real)=3.243e-14 | Theta_nuc/Theta_e=1.62e-06  Theta_nuc/Theta_b=1.86e-03  Theta_nuc/rho=4.69e-09 (README budget 8MeV: 2.15e-08)



\=== sigma-mediator: static susceptibility window ===

 n_b=7.608e-14 MeV^3, H=1.595e-24 MeV = 1.595e-18 eV

  n_D/n_b=1e-05  target dB_D=  1.00 keV -> m_sigma =    0.0276 eV  (m/H=1.73e+16)

  n_D/n_b=1e-05  target dB_D=  7.70 keV -> m_sigma =    0.0099 eV  (m/H=6.23e+15)

  n_D/n_b=1e-05  target dB_D= 55.45 keV -> m_sigma =    0.0037 eV  (m/H=2.32e+15)

  n_D/n_b=1e-04  target dB_D=  1.00 keV -> m_sigma =    0.0872 eV  (m/H=5.47e+16)

  n_D/n_b=1e-04  target dB_D=  7.70 keV -> m_sigma =    0.0314 eV  (m/H=1.97e+16)

  n_D/n_b=1e-04  target dB_D= 55.45 keV -> m_sigma =    0.0117 eV  (m/H=7.34e+15)

  n_D/n_b=1e-03  target dB_D=  1.00 keV -> m_sigma =    0.2758 eV  (m/H=1.73e+17)

  n_D/n_b=1e-03  target dB_D=  7.70 keV -> m_sigma =    0.0994 eV  (m/H=6.23e+16)

  n_D/n_b=1e-03  target dB_D= 55.45 keV -> m_sigma =    0.0370 eV  (m/H=2.32e+16)

 -> m_sigma \~ 0.01-0.3 eV, i.e. 22-24 orders ABOVE H: the criterion m<\~H is neither necessary nor sufficient





import math, numpy as np

from scipy.special import logsumexp, zeta

from scipy.optimize import brentq

hbar=6.582119569e-16; Mpl=1.22089e28; eta=6.1e-10; f=(4/11)\*\*(1/3)

def logZ(L,phi,x):

    N=L-1; ph=np.r\_[0,(phi+2\*np.pi\*np.arange(N))/N]; return float(logsumexp(x\*np.cos(ph)))

def eps(L,x): return 1-math.exp(logZ(L,np.pi,x)-logZ(L,0,x))

T=0.08; Tnu=T\*f; rho1nu=(7/4)\*(math.pi\*\*2/15)\*Tnu\*\*4

def Jmin(L,e=0.01,T=0.08):

    return brentq(lambda x: eps(L,x)-e,0.02,3000)\*T/2

def Jmax(gdec,gX=1,dN=0.17):

    Tx=(10.75/gdec)\*\*(1/3)\*f\*T; nX=gX\*zeta(3)/math.pi\*\*2\*Tx\*\*3

    return dN\*rho1nu/nX/2      # m_X = 2J

print("=== L1 SCREEN: intersection of visibility (J>=Jmin) and Delta N_eff (J<=Jmax), T=0.08 MeV ===")

print(" assumption: X is a thermal relic, number conserved after decoupling, m_X = 2J, g_X internal states")

for gdec in (28.,106.75,202.):

    for gX in (1,7,126):

        print(f"  g_dec={gdec:6.2f} g_X={gX:3d}: J_max={Jmax(gdec,gX):.4f} MeV", end="")

    print()

print()

for L in (3,7,9,15):

    jm=Jmin(L)

    print(f" L={L:2d}: J_min(eps>=1%)={jm:.4f} MeV | ", end="")

    for gdec in (28.,106.75,202.):

        jM=Jmax(gdec,1)

        ok = "OPEN  x%.2f"%(jM/jm) if jM>jm else "EMPTY"

        print(f"g_dec={gdec:6.2f},gX=1: {ok:12s}", end=" ")

    print()

print()

print("=== seam bias / g at the live point, and the resulting toy deltas ===")

from scipy.linalg import expm

from scipy.special import expit

def four(L,x,g,t=1.0):

    st=[(r,d) for r in (0,1) for d in (0,1)]; gb=logZ(L,0,x)-logZ(L,np.pi,x)

    Q=np.zeros((4,4))

    for i,(r,d) in enumerate(st):

        j=st.index((1-r,d)); Q[j,i]=expit((1-2\*r)\*(gb+g\*d))

        j=st.index((r,1-d)); Q[j,i]=expit((1-2\*d)\*g\*r)

    Q[np.diag_indices(4)]=-Q.sum(axis=0)

    p=expm(Q\*t)@np.array([1.,0,0,0]); r,d=np.array(st,float).T

    return np.array([r\@p,d\@p,p[-1]])

for L,J in [(7,0.15),(7,0.30),(7,0.44),(15,0.71)]\:

    x=2\*J/T; e=eps(L,x); bias=-math.log(1-e)

    gpos=7.7/80; gneg=-32.0/80

    dp=four(L,x,gpos)-four(L,x,0.0); dn=four(L,x,gneg)-four(L,x,0.0)

    S=math.log(J\*1e6/hbar/(1.66\*math.sqrt(3.36)\*(T\*1e6)\*\*2/Mpl/hbar))

    print(f" L={L:2d} J={J:4.2f} x={x:6.2f} eps={e:.4f} dF={bias\*80:6.2f} keV  S_max={S:.2f}"

          f" | dP(d) at g=+7.7/80: {dp[1]\:+.5f} ; at g=-32/80: {dn[1]\:+.5f}")



\# Result

\=== L1 SCREEN: intersection of visibility (J>=Jmin) and Delta N_eff (J<=Jmax), T=0.08 MeV ===

 assumption: X is a thermal relic, number conserved after decoupling, m_X = 2J, g_X internal states

  g_dec= 28.00 g_X=  1: J_max=0.1195 MeV  g_dec= 28.00 g_X=  7: J_max=0.0171 MeV  g_dec= 28.00 g_X=126: J_max=0.0009 MeV

  g_dec=106.75 g_X=  1: J_max=0.4557 MeV  g_dec=106.75 g_X=  7: J_max=0.0651 MeV  g_dec=106.75 g_X=126: J_max=0.0036 MeV

  g_dec=202.00 g_X=  1: J_max=0.8622 MeV  g_dec=202.00 g_X=  7: J_max=0.1232 MeV  g_dec=202.00 g_X=126: J_max=0.0068 MeV



 L= 3: J_min(eps>=1%)=0.0072 MeV | g_dec= 28.00,gX=1: OPEN  x16.65 g_dec=106.75,gX=1: OPEN  x63.48 g_dec=202.00,gX=1: OPEN  x120.12 

 L= 7: J_min(eps>=1%)=0.1186 MeV | g_dec= 28.00,gX=1: OPEN  x1.01  g_dec=106.75,gX=1: OPEN  x3.84  g_dec=202.00,gX=1: OPEN  x7.27  

 L= 9: J_min(eps>=1%)=0.2206 MeV | g_dec= 28.00,gX=1: EMPTY        g_dec=106.75,gX=1: OPEN  x2.07  g_dec=202.00,gX=1: OPEN  x3.91  

 L=15: J_min(eps>=1%)=0.7065 MeV | g_dec= 28.00,gX=1: EMPTY        g_dec=106.75,gX=1: EMPTY        g_dec=202.00,gX=1: OPEN  x1.22  



\=== seam bias / g at the live point, and the resulting toy deltas ===

 L= 7 J=0.15 x=  3.75 eps=0.0240 dF=  1.94 keV  S_max=52.90 | dP(d) at g=+7.7/80: +0.00324 ; at g=-32/80: -0.01281

 L= 7 J=0.30 x=  7.50 eps=0.1533 dF= 13.31 keV  S_max=53.59 | dP(d) at g=+7.7/80: +0.00346 ; at g=-32/80: -0.01374

 L= 7 J=0.44 x= 11.00 eps=0.2739 dF= 25.60 keV  S_max=53.97 | dP(d) at g=+7.7/80: +0.00370 ; at g=-32/80: -0.01472

 L=15 J=0.71 x= 17.75 eps=0.0102 dF=  0.82 keV  S_max=54.45 | dP(d) at g=+7.7/80: +0.00322 ; at g=-32/80: -0.01272





import numpy as np, math

def graph(L,phi):

    n=L-1; order=[0,\*range(2,L)]

    step=np.zeros((L,L),complex); step[1,1]=1

    h=-1 if phi==np.pi else np.exp(1j\*phi)

    for j,t in enumerate(order): step[order[(j+1)%n],t]=h if j==n-1 else 1

    return step

print("dim ker i(F-F^dag) on the active layer K1 (+) C\_{L-1}:")

for L in (3,5,7,9,15,4,6):

    row=[]

    for phi in (0,np.pi):

        F=graph(L,phi); A=1j\*(F-F.conj().T)

        ev=np.linalg.eigvalsh(A); row\.append(int((abs(ev)<1e-10).sum()))

    print(f"  L={L:2d} ({'odd ' if L%2 else 'even'}):  n0={row[0]}, npi={row[1]},  contrast={row[0]-row[1]}")

print()

print("transient/equilibrium amplification of the seam effect on P_bound:")

print("  t=1 : 0.3160602794 - 0.2712383303 =",0.31606027941427883-0.2712383303451682)

print("  t->inf: 0.5 - 0.4924288036 =",0.5-0.4924288035639375)

print("  ratio =", (0.31606027941427883-0.2712383303451682)/(0.5-0.4924288035639375))

print("  eps/(2(2-eps)) =",0.0298330421006258/(2\*(2-0.0298330421006258)))

print()

print("fraction of the theoretical ceiling realised at L=7,x=4:",0.03028710075017571/math.log(2))

print("delta_B_D window from delta_NN in (-0.0025,0.0006), B_D=2224.6 keV, factor 5.7701:")

print("  ",-0.0025\*5.7701\*2224.6, " ... ",0.0006\*5.7701\*2224.6," keV")

print("  g=ln2 needs",math.log(2)\*80,"keV -> overshoot factor",math.log(2)\*80/(0.0006\*5.7701\*2224.6))



\# Result

dim ker i(F-F^dag) on the active layer K1 (+) C\_{L-1}:

  L= 3 (odd ):  n0=3, npi=1,  contrast=2

  L= 5 (odd ):  n0=3, npi=1,  contrast=2

  L= 7 (odd ):  n0=3, npi=1,  contrast=2

  L= 9 (odd ):  n0=3, npi=1,  contrast=2

  L=15 (odd ):  n0=3, npi=1,  contrast=2

  L= 4 (even):  n0=2, npi=2,  contrast=0

  L= 6 (even):  n0=2, npi=2,  contrast=0



transient/equilibrium amplification of the seam effect on P_bound:

  t=1 : 0.3160602794 - 0.2712383303 = 0.044821949069110634

  t->inf: 0.5 - 0.4924288036 = 0.007571196436062522

  ratio = 5.920061571196104

  eps/(2(2-eps)) = 0.007571196436172674



fraction of the theoretical ceiling realised at L=7,x=4: 0.0436950500551829

delta_B_D window from delta_NN in (-0.0025,0.0006), B_D=2224.6 keV, factor 5.7701:

   -32.09041115  ...  7.7016986759999995  keV

  g=ln2 needs 55.451774444795625 keV -> overshoot factor 7.199940789373415