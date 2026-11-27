#!/usr/bin/env python3
"""Replay benzene/benzyl Wilson-flux and R149 incidence determinants (NumPy only)."""
import itertools, json, math
from pathlib import Path
import numpy as np

PHASES=[0.0,math.pi/3,math.pi/2,2*math.pi/3,math.pi]
CENTER=[2*math.pi*j/3 for j in range(3)]
I6,I7=np.eye(6,dtype=complex),np.eye(7,dtype=complex)

def a6(phi,seam=5):
    a=np.zeros((6,6),complex)
    for i in range(6):
        j=(i+1)%6; q=np.exp(1j*phi) if i==seam else 1.0
        a[i,j]=q; a[j,i]=np.conjugate(q)
    return a

def a7(phi,seam=5):
    a=np.zeros((7,7),complex); a[:6,:6]=a6(phi,seam); a[0,6]=a[6,0]=1
    return a

def incidence7(phi,seam=5):
    b=np.zeros((7,7),complex)
    for i in range(6):
        j=(i+1)%6; b[i,i]=1; b[i,j]=-np.exp(1j*phi) if i==seam else -1
    b[6,0]=1; b[6,6]=-1
    return b

def realdet(m):
    z=np.linalg.det(m)
    assert abs(z.imag)<2e-8,z
    return float(z.real)

def matchings(diag,edges):
    out={}
    for k in range(len(diag)//2+1):
        n=total=0
        for es in itertools.combinations(edges,k):
            vs=[v for e in es for v in e]
            if len(set(vs))!=2*k: continue
            n+=1; total+=math.prod(diag[v] for v in range(len(diag)) if v not in vs)
        out[str(k)]={"count":n,"weighted_sum":total,"signed":(-1)**k*total}
    return out

def fourier(detfn):
    vals=[detfn(p) for p in CENTER]; roots=[np.exp(1j*p) for p in CENTER]
    c0=sum(vals)/3; cp=sum(np.conjugate(roots[j])*vals[j] for j in range(3))/3
    cm=sum(roots[j]*vals[j] for j in range(3))/3
    return {"values":vals,"c0":float(complex(c0).real),
      "c_plus1":[float(complex(cp).real),float(complex(cp).imag)],
      "c_minus1":[float(complex(cm).real),float(complex(cm).imag)]}

def main():
    def z6(p): return realdet(3*I6-a6(p))
    def z7h(p): return realdet(3*I7-a7(p))
    def z7r(p): return realdet(I7+incidence7(p).conj().T@incidence7(p))
    phase=[]
    for p in PHASES:
        phase.append({"phi":p,"benzene":z6(p),"benzene_formula":322-2*math.cos(p),
          "benzyl_huckel":z7h(p),"benzyl_huckel_formula":822-6*math.cos(p),
          "benzyl_r149":z7r(p),"benzyl_r149_formula":788-4*math.cos(p)})
    center={"benzene_r149":fourier(z6),"benzyl_uniform_huckel":fourier(z7h),
      "benzyl_r149_incidence":fourier(z7r)}
    e6=[(i,(i+1)%6) for i in range(6)]; e7=e6+[(0,6)]
    loop={"benzene":{"matchings":matchings([3]*6,e6),"constant":322,"winding":"-2*cos(Phi)"},
      "benzyl_huckel":{"matchings":matchings([3]*7,e7),"constant":822,"winding":"-6*cos(Phi)"},
      "benzyl_r149":{"matchings":matchings([4,3,3,3,3,3,2],e7),"constant":788,"winding":"-4*cos(Phi)"}}
    zero=[]; dnu=1e-6
    for p in PHASES:
        A=a7(p); ev,V=np.linalg.eigh(A); j0=int(np.argmin(abs(ev)))
        psi=np.array([0,1,0,-1,0,1,-(1+np.exp(-1j*p))],complex); psi/=np.linalg.norm(psi)
        exact=(2+2*math.cos(p))/(5+2*math.cos(p)); es=[]; ovs=[]
        for dn in (-dnu,dnu):
            h=A.copy(); h[6,6]+=dn; e,v=np.linalg.eigh(h); j=int(np.argmax(abs(v.conj().T@psi)))
            es.append(float(e[j])); ovs.append(float(abs(np.vdot(psi,v[:,j]))**2))
        slope=(es[1]-es[0])/(2*dnu)
        zero.append({"phi":p,"zero_abs":float(abs(ev[j0])),"port_weight":exact,
          "eigenvector_port_weight":float(abs(psi[6])**2),"hf_slope":slope,
          "hf_error":float(slope-exact),"min_branch_overlap":min(ovs)})
    p=.731; A=a6(p); A7=a7(p); g00=np.linalg.inv(3*I6-A)[0,0]
    sh=realdet(3*I7-A7); sh_rhs=float((z6(p)*(3-g00)).real)
    sr=z7r(p); sr_rhs=2*z6(p)+144
    phi=.913; ref=np.linalg.eigvalsh(a6(phi)); inc=[]; seam=[]; deg=np.diag([3,2,2,2,2,2,1])
    for edge in range(6):
        b=incidence7(phi,edge); aa=a7(phi,edge)
        inc.append(float(np.max(abs(b.conj().T@b-(deg-aa)))))
        seam.append(float(np.max(abs(np.linalg.eigvalsh(a6(phi,edge))-ref))))
    grid=np.linspace(0,2*math.pi,129)
    residual={"benzene":max(abs(z6(float(q))-(322-2*math.cos(float(q)))) for q in grid),
      "benzyl_huckel":max(abs(z7h(float(q))-(822-6*math.cos(float(q)))) for q in grid),
      "benzyl_r149":max(abs(z7r(float(q))-(788-4*math.cos(float(q)))) for q in grid)}
    return {"status":"EXACT_FINITE_GRAPH_IDENTITIES_NUMERICALLY_REPLAYED","phase_sweep":phase,
      "center_z3_fourier":center,"loop_gas":loop,
      "chiral_zero_mode":{"A":[0,2,4],"B":[1,3,5,6],"abs_imbalance":1,
        "unnormalised_vector":"(0,1,0,-1,0,1,-(1+exp(-i*Phi)))",
        "norm_squared":"5+2*cos(Phi)","port_weight_formula":"(2+2*cos(Phi))/(5+2*cos(Phi))","phase_sweep":zero},
      "schur":{"phi":p,"huckel_direct":sh,"huckel_schur":sh_rhs,"huckel_residual":abs(sh-sh_rhs),
        "r149_direct":sr,"r149_schur":sr_rhs,"r149_residual":abs(sr-sr_rhs),"P5_cofactor":144},
      "gauge":{"max_incidence_identity_error":max(inc),"max_spectrum_change_moving_seam":max(seam),
        "seam_edges_tested":6},"max_formula_residuals_129_phase_grid":residual,
      "limits":["Uniform-diagonal Hückel determinant is not the R149 Laplacian determinant on the branched graph.",
        "Three Z3 samples alias winding sectors modulo 3 generally; this example has only 0,+/-1.",
        "Scalar U(1) probes are not the full SU(3) protocol.",
        "Finite Hückel graph only; no ab initio calibration or Fibonacci tail."]}

if __name__=="__main__":
    r=main(); Path(__file__).with_name("RESULTS.json").write_text(json.dumps(r,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps({"status":r["status"],"phase_sweep":r["phase_sweep"],
      "center_z3_fourier":r["center_z3_fourier"],"chiral_zero_mode":r["chiral_zero_mode"],
      "schur":r["schur"],"gauge":r["gauge"],"max_formula_residuals_129_phase_grid":r["max_formula_residuals_129_phase_grid"]},indent=2,ensure_ascii=False))
