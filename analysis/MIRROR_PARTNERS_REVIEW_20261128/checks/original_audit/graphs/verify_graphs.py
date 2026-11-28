import json, itertools
import numpy as np
import sympy as sp
from pathlib import Path
out={}
configs={
'benzyl': ([(i,(i+1)%6) for i in range(6)]+[(0,6)],[0,5,4,3,2,1,6],6),
'path_P7': ([(0,1),(1,2),(2,3),(0,4),(4,5),(5,6)],[0,4,5,6,1,2,3],0),
'two_triangles': ([(1,2),(2,3),(3,1),(0,1),(4,5),(5,6),(6,4),(0,4)],[0,4,5,6,1,2,3],0)}
for name,(edges,perm,center) in configs.items():
    H=np.zeros((7,7));
    for i,j in edges: H[i,j]=H[j,i]=1
    R=np.eye(7)[perm]
    ev,U=np.linalg.eigh(H)
    Z=U[:,abs(ev)<1e-10]
    autos=[]
    E={frozenset(e) for e in edges}
    for p in itertools.permutations(range(7)):
        if all(frozenset((p[a],p[b])) in E for a,b in edges): autos.append(p)
    out[name]={
        'spectrum':ev.tolist(),'charpoly':str(sp.factor(sp.Matrix(H.astype(int)).charpoly().as_expr())),
        'nullspace_exact':[list(map(str,v)) for v in sp.Matrix(H.astype(int)).nullspace()],
        'mirror_commutator_2norm':float(np.linalg.norm(R@H-H@R,2)),
        'mirror_involution_2norm':float(np.linalg.norm(R@R-np.eye(7),2)),
        'mirror_even_dimension':int(np.count_nonzero(np.linalg.eigvalsh(R)>0)),
        'mirror_odd_dimension':int(np.count_nonzero(np.linalg.eigvalsh(R)<0)),
        'zero_mode_mirror_parities':np.linalg.eigvalsh(Z.T@R@Z).tolist(),
        'zero_mode_center_weights':[float(abs(z[center])**2) for z in Z.T],
        'automorphisms':autos,
    }

def H(phi,seam=5):
    a=np.zeros((7,7),complex)
    for i in range(6):
        j=(i+1)%6; q=np.exp(1j*phi) if i==seam else 1.
        a[i,j]=q; a[j,i]=np.conj(q)
    a[0,6]=a[6,0]=1
    return a

def psi(phi):
    z=np.zeros(7,complex); z[[1,3,5,6]]=[1,-1,1,-(1+np.exp(-1j*phi))]
    return z/np.linalg.norm(z)
R=np.eye(7)[configs['benzyl'][1]]
phase_rows=[]
for phi in (0.,0.3,0.9,np.pi/2,np.pi,1.7):
    hp=H(phi); p=psi(phi)
    Gplus=np.diag([1]+[np.exp(1j*phi)]*5+[1])
    Gminus=Gplus.conj()
    V=Gplus@R # Theta=V K
    phase_rows.append({
        'phi':phi,
        'Hpsi_2norm':float(np.linalg.norm(hp@p)),
        'Rpsi_minus_psi_2norm':float(np.linalg.norm(R@p-p)),
        'port_weight':float(abs(p[6])**2),
        'RHR_minus_H_2norm':float(np.linalg.norm(R@hp@R-hp,2)),
        'expected_RHR_minus_H_2norm':float(2*np.sqrt(2)*abs(np.sin(phi/2))),
        'RHR_minus_H_minus_phi_seam0_2norm':float(np.linalg.norm(R@hp@R-H(-phi,0),2)),
        'conjH_minus_H_minus_phi_seam5_2norm':float(np.linalg.norm(hp.conj()-H(-phi),2)),
        'GminusRHRGminusAdj_minus_H_minus_phi_2norm':float(np.linalg.norm(Gminus@R@hp@R@Gminus.conj().T-H(-phi),2)),
        'ThetaHThetaInv_minus_H_2norm':float(np.linalg.norm(V@hp.conj()@V.conj().T-hp,2)),
        'Theta_squared_minus_1_2norm':float(np.linalg.norm(V@V.conj()-np.eye(7),2)),
        'ThetaPsi_minus_expiphi_Psi_2norm':float(np.linalg.norm(V@p.conj()-np.exp(1j*phi)*p)),
        'bare_RK_H_RKInv_minus_H_2norm':float(np.linalg.norm(R@hp.conj()@R-hp,2)),
        'spectrum_phi_minus_phi':float(np.max(abs(np.linalg.eigvalsh(hp)-np.linalg.eigvalsh(H(-phi))))),
    })
out['phases']=phase_rows
# Show the erroneous concatenation is not a zero vector in vertex order.
b=np.array([1,-1,1,-2],complex)/np.sqrt(7)
wrong=np.r_[np.zeros(3),b]
out['basis_error']={
    'wrong_null_residual_2norm':float(np.linalg.norm(H(0)@wrong)),
    'wrong_overlap':float(np.vdot(wrong,R@wrong).real),
    'right_null_residual_2norm':float(np.linalg.norm(H(0)@psi(0))),
    'right_overlap':float(np.vdot(psi(0),R@psi(0)).real),
    'sublattice_to_vertex_order':[0,2,4,1,3,5,6],
}
path=Path(__file__).with_name('results.json'); path.write_text(json.dumps(out,indent=2,ensure_ascii=False))
print(json.dumps(out,indent=2,ensure_ascii=False))
