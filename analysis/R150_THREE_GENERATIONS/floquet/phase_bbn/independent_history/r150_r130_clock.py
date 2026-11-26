"""Independent finite checks of the R130/R150 clock bridge. No BBN inputs.
Conventions: F=Q I, U=exp(i G), physical H=-hbar G/tau.
The stable word coordinates (u,v,t) follow R150 floquet/CORE.md.
"""
import json, itertools, math
import numpy as np
from scipy.linalg import expm

HBAR=6.582119569e-22 # MeV s
C=299792458.0

def perm(mapping):
    return np.eye(len(mapping))[:,mapping]

def lift_cycle(n):
    k=np.arange(n); theta=2*np.pi*k/n
    theta=np.where(theta>np.pi+1e-12,theta-2*np.pi,theta)
    V=np.exp(-2j*np.pi*np.outer(k,k)/n)/np.sqrt(n)
    return (V*theta)@V.conj().T

def layer(L):
    n=L-1; Q=perm([(t+1)%L for t in range(L)])
    v=np.eye(L)[:,0]-np.eye(L)[:,1]
    I=np.eye(L)-np.outer(v,v); Gi=np.pi*np.outer(v,v)/2
    F=Q@I; Gq=lift_cycle(L)
    ix=[0,*range(2,L)]; Gf=np.zeros((L,L),complex)
    Gf[np.ix_(ix,ix)]=lift_cycle(n)
    T=I@perm([(1-t)%L for t in range(L)])
    assert np.max(abs(T@F@T-F.T))<1e-12
    assert np.max(abs(expm(1j*Gf)-F))<1e-12
    assert np.max(abs(expm(1j*Gq)@expm(1j*Gi)-F))<1e-12
    b=np.eye(L)[:,1]; s=np.zeros(L); a=np.zeros(L)
    s[ix]=1/np.sqrt(n); a[ix]=(-1.)**np.arange(n)/np.sqrt(n)
    assert np.max(abs(F@a+a))<1e-12
    assert np.max(abs(T@a-a))<1e-12
    even=(Gf+T@Gf@T)/2
    assert np.max(abs(even-np.pi*np.outer(a,a)))<1e-12
    K=I.T@Gq@I+Gi; V=np.column_stack([b,s]); d=np.linalg.eigvalsh(V.T@K@V)
    slopes=[*d,float((a@K@a).real)]
    expected=[0.,L*np.pi/(2*n),np.pi/(2*n)]
    assert np.max(abs(np.array(slopes)-expected))<1e-12
    # Independent perturbation of the two pulse duration multipliers.
    dI=Gi; dQ=I.T@Gq@I
    eq=np.linalg.eigvalsh(V.T@dQ@V); ei=np.linalg.eigvalsh(V.T@dI@V)
    assert np.max(abs(eq))<1e-12
    assert abs((a@dQ@a).real)<1e-12
    # Compare the clock phase lift against the thermodynamic and sine operators.
    # Any exponent of either candidate acts equally on a suitable pair that F separates.
    therm=-(F+F.T); sine=1j*(F-F.T)
    assert np.linalg.norm(sine@a)<1e-12 and np.linalg.norm(sine@s)<1e-12
    assert np.linalg.norm(F@s-F@a)>1
    x=2*np.pi/n
    # for n>2, conjugate phase pair of thermodynamic spectrum is degenerate
    thermo_obstruction=n>2 and abs(np.sin(x))>1e-12
    assert np.max(abs(np.abs(Gq[0,1:])-np.pi/(L*np.sin(np.pi*np.arange(1,L)/L))))<1e-12
    return dict(L=L,zero_index=2,pi_index=1,grading_even_norm=float(np.linalg.norm(even,2)),
                phase_spacing=2*np.pi/n,shared_pulse_slopes=slopes,
                Q_only_zero_slopes=eq.tolist(),I_only_zero_slopes=ei.tolist(),
                Q_only_pi_slope=float((a@dQ@a).real),I_only_pi_slope=float((a@dI@a).real),
                thermal_generator_obstruction=bool(thermo_obstruction),
                exact_log_error=float(np.max(abs(expm(1j*Gf)-F))))

def stable_indices(L):
    states=[(u,v,t) for u in range(L) for v in range(L) for t in range(L)
            if u==0 or v==0 or (u-v)%L==1]
    # For L>=3, pairs satisfying u-v=1 with a zero already lie in passive set.
    def active(u,v):return u!=0 and v!=0 and (u-v)%L==1
    def interact(w):
        u,v,t=w
        return (u,v,1-t if active(u,v) and t in (0,1) else t)
    def F(w):
        u,v,t=interact(w); return (u,v,(t+1)%L)
    def T(w):
        u,v,t=w;return interact(((-v)%L,(-u)%L,(u-v-t)%L))
    st=set(states); assert len(st)==3*L*(L-1)
    assert all(T(T(w))==w and F(T(F(T(w))))==w for w in st)
    # trace of grading on eigenphase +/- sectors, obtained on each orbit.
    visited=set(); counts={'+': [0,0], '-':[0,0]}
    for w in states:
        if w in visited:continue
        cyc=[]; z=w
        while z not in visited:cyc.append(z);visited.add(z);z=F(z)
        assert z==w
        N=len(cyc)
        for phase,key in [(1,'+'),(-1,'-')]:
            if phase==-1 and N%2:continue
            counts[key][0]+=1
            if T(w) in cyc:counts[key][1]+=phase**cyc.index(T(w))
    assert counts['+'][1]==3 and counts['-'][1]==1
    return dict(L=L,dimension=len(st),zero_dim=counts['+'][0],zero_index=counts['+'][1],pi_dim=counts['-'][0],pi_index=counts['-'][1])

def transport(w,channels):
    am=sum(1<<(2*c) for c in range(channels));bm=2*am
    return tuple((w[i]&bm)|(w[(i+1)%len(w)]&am) for i in range(len(w)))

def swap_layers(w,channels):
    # Swap a_i with b_i; then swap a_i with b_{i+1} (disjoint register pairs).
    am=sum(1<<(2*c) for c in range(channels));bm=2*am
    v=tuple(((x&am)<<1)|((x&bm)>>1) for x in w)
    return tuple(((v[(i+1)%len(w)]&bm)>>1)|((v[(i-1)%len(w)]&am)<<1) for i in range(len(w)))

def check_transport():
    count=0
    for c,top in [(1,6),(2,3)]:
        for n in range(1,top+1):
            for w in itertools.product(range(4**c),repeat=n):
                q2=transport(transport(w,c),c)
                # Q^2 in moving vertex labels; rotate list by one to restore original frame.
                assert q2[-1:]+q2[:-1]==swap_layers(w,c)
                count+=1
    # Physical half-link transport time if v=c; examples, not a prediction of scale.
    scales=[]
    for a in (1.616255e-35,1e-15,1e-12,1e-9):
        tau=a/(2*C)
        scales.append(dict(edge_m=a,tau_s=tau,pi_gap_MeV=np.pi*HBAR/tau))
    return count,scales

if __name__=='__main__':
    n,scales=check_transport()
    data=dict(active_layers=[layer(L) for L in range(3,32,2)],stable_carriers=[stable_indices(L) for L in range(3,32,2)],transport_words=n,clock_scale_examples=scales)
    print(json.dumps(data,indent=2))
