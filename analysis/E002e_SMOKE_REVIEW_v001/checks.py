"""Algebraic review checks, not production G/R/F/T or a NESS experiment."""
import json
from pathlib import Path
import numpy as np
from scipy import sparse as sp

OUT = Path(__file__).parent

def mx(a):
    return float(np.max(abs(a.data if sp.issparse(a) else np.asarray(a)), initial=0))

def main():
    out = {}
    # Exact elimination of a two-state Markov generator at nonzero frequency.
    L = np.array([[-1., 2.], [1., -2.]])
    z = .7+.2j; b=np.array([1., -1.]); o=np.array([1., -1.])
    x = np.linalg.solve(z*np.eye(2)-L,b)
    rb=1/(z-L[1,1]); leff=L[0,0]+L[0,1]*rb*L[1,0]
    beff=b[0]+L[0,1]*rb*b[1]
    xt=beff/(z-leff)
    chi=(o[0]+o[1]*rb*L[1,0])*xt+o[1]*rb*b[1]
    wrong=beff/(z-(L[0,0]-L[0,1]*rb*L[1,0]))
    out['schur']=dict(correct_state_error=float(abs(xt-x[0])),
        correct_output_error=float(abs(chi-o@x)),wrong_sign_state_error=float(abs(wrong-x[0])),
        Leff_at_zero_correct=float(L[0,0]+L[0,1]/(-L[1,1])*L[1,0]),
        Leff_at_zero_wrong=float(L[0,0]-L[0,1]/(-L[1,1])*L[1,0]))
    assert abs(xt-x[0])<1e-14 and abs(chi-o@x)<1e-14 and abs(wrong-x[0])>.01
    bg=1.; res=-1.; cross=2*bg*res
    out['amplitude_vs_power']=dict(amplitude=bg+res,power=(bg+res)**2,
        interference=cross,wrong_amplitude_plus_interference=bg+res+cross)
    # Parseval is L2, while the declared correlation time is an L1 integral.
    A=3.; a=2.
    out['parseval']=dict(C0=A,decay=a,L1_normalized=1/a,
        proposed_integral_divided_by_variance=A/(2*a),L2_normalized_by_variance_squared=1/(2*a))
    assert out['parseval']['L1_normalized'] != out['parseval']['proposed_integral_divided_by_variance']
    a=.1; H=np.pi/2
    primitive=lambda t:np.exp(-a*t)*(-a*np.cos(t)+np.sin(t))/(1+a*a)
    tail=-(primitive(H+np.pi)-primitive(H))
    out['endpoint_tail']=dict(H=float(H),endpoint=float(np.exp(-a*H)*np.cos(H)),
        next_half_period_absolute_integral=float(tail))
    assert abs(out['endpoint_tail']['endpoint'])<1e-15 and tail>1
    # Previous exact G0 Fano profile; its width, not finite contrast, scales as v^2.
    J=1.; kl=kr=.5; aa=J*J+kl*kr/4; tb=J*J*kl*kr/aa**2; delta=.125
    rows=[]
    for v in (.5,1.):
        width=kl*v*v/(2*aa); D=-tb*delta**2/(delta**2+width**2)
        rows.append(dict(v=v,width=width,D=D))
    ratio=rows[0]['D']/rows[1]['D']
    out['G0_contrast']=dict(delta=delta,rows=rows,D_half_over_full=ratio,
        v_squared_prediction=.25,relative_contrast_at_zero='undefined because T(0)=0')
    assert ratio>3 and abs(ratio-.25)>1
    # Node operators, independently assembled from integer basis transitions.
    eye=np.eye(8); n=[]; up=[]
    for site in range(3):
        bit=1<<(2-site); n.append(np.diag([float(bool(k&bit)) for k in range(8)]))
        u=np.zeros((8,8),complex)
        for k in range(8):
            if not k&bit:u[k|bit,k]=1
        up.append(u)
    Z=[eye-2*x for x in n]; sectors=[np.diag([float(k.bit_count()==N) for k in range(8)]) for N in range(4)]
    rng=np.random.default_rng(20261031); a=rng.normal(size=(8,8))+1j*rng.normal(size=(8,8));rho=a@a.conj().T;rho/=np.trace(rho)
    current_err=0.
    for mask in (6,7):
        for phi in (0.,np.pi/2):
            for v in (0.,.5,1.):
                amps=[v if mask==7 else 1.,v if mask==6 else 1.,1.]; currents=[]
                for e,((i,j),theta) in enumerate(zip(((0,1),(1,2),(0,2)),(0.,0.,-phi))):
                    t=up[i]@up[j].conj().T
                    hh=amps[e]*(np.exp(1j*theta)*t+np.exp(-1j*theta)*t.conj().T) if mask&(1<<e) else 0*t
                    currents.append(1j*(hh@n[j]-n[j]@hh))
                for N,(ab,cd) in enumerate((((1,2),(1,4)),((5,6),(3,6))),start=1):
                    expected=(-2*amps[1]*rho[ab].imag,-2*(np.exp(-1j*phi)*rho[cd]).imag)
                    actual=[np.trace(sectors[N]@currents[e]@rho).real for e in (1,2)]
                    current_err=max(current_err,max(abs(np.array(expected)-actual)))
    out['sector_currents']=dict(cases=12,max_error=float(current_err),note='Deformed I12 uses v, not fixed J')
    assert current_err<1e-12
    rates=[]
    for i,j in ((4,2),(2,1),(4,1)):
        full=.5*.05*sum((zz[i,i]-zz[j,j])**2 for zz in Z)
        peer=.5*.05*(n[1][i,i]-n[1][j,j])**2
        rates.append(dict(basis_pair=[i,j],full=float(full),peer=float(peer)))
    out['dephasing']=rates;assert [x['full'] for x in rates]==[.2,.2,.2]
    # Mask-local Hamiltonian support versus its action on inter-mask coherences.
    es=np.array(list(np.ndindex(3,3,3)));maskids=((es==2)*[1,2,4]).sum(1)
    q=sp.kron(sp.eye(8),sp.diags((maskids==6).astype(float)),format='csr')
    p12=sp.diags((es[:,1]==2).astype(float));hop12=up[1]@up[2].conj().T+up[2]@up[1].conj().T
    hh=sp.kron(sp.csr_matrix(hop12),p12,format='csr');dh=-q@hh
    identity=sp.eye(216,format='csr');n2=sp.kron(sp.csr_matrix(n[2]),sp.eye(27),format='csr')
    aidx=2*27+8  # node010, edges(0,L,L), m6
    bidx=4*27+26 # node100, edges(L,L,L), m7; same N
    x=sp.csr_matrix((np.array([.5,.5]),([aidx,bidx],[bidx,aidx])),shape=(216,216))
    action=-1j*(dh@x-x@dh)
    cross_action=q@action@(identity-q)+(identity-q)@action@q
    w=np.array([(-1.)**(((node>>1)&1)+int(np.sum(edge==2))) for node in range(8) for edge in es]);W=sp.diags(w)
    newI=1j*((hh+dh)@n2-n2@(hh+dh))
    out['mask_deformation']=dict(commutator_error=mx(q@hh-hh@q),outside_H_error=mx((identity-q)@dh),
        direct_inter_mask_coherence_action=mx(cross_action),m6_I12_at_v0=mx(q@newI),
        antiunitary_H_deformation_error=mx(-W@dh.conjugate()@W-dh))
    assert out['mask_deformation']['commutator_error']<1e-12 and mx(q@newI)<1e-12
    assert mx(cross_action)>.1 and out['mask_deformation']['antiunitary_H_deformation_error']<1e-12
    # Finite curvature with a nonzero slope does not imply a local minimum.
    f=lambda e:1+e+e*e;D=f(0)-(f(-delta)+f(delta))/2
    out['finite_curvature']=dict(values=[f(-delta),f(0),f(delta)],D=D,
        curvature=-2*D/delta**2,center_below_both=f(0)<min(f(-delta),f(delta)))
    assert -2*D/delta**2>0 and not out['finite_curvature']['center_below_both']
    # Analytic one-excitation regenerative cycle, not a G1/G2 calculation.
    k=.8; kap=.5; tau=1/k+1/kap;renew=[]
    for pump in (.005,.05,.5):
        pg=1/(1+pump*tau);p=np.array([pg,pump*pg/k,pump*pg/kap])
        gen=np.array([[-pump,0,kap],[pump,-k,0],[0,k,-kap]])
        flux=kap*p[2];conditional=flux/(1-pg)
        renew.append(dict(pump=pump,occupation=float(1-pg),flux=float(flux),conditional_current=float(conditional),residual=mx(gen@p)))
        assert mx(gen@p)<1e-14 and abs(conditional-1/tau)<1e-13
    out['renewal_identity']=dict(tau=tau,rows=renew,scope='Analytic 3-state cycle verifies algebra; general G1 derivation in RESULT, no G1 NESS solved')
    out['status']='PASS';out['new_evolution_steps']=0;out['new_G_R_F_T_solutions']=0
    (OUT/'checks.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
