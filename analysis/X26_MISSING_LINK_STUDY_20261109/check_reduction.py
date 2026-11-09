"""Exact inherited R040 trimer reduction; diagnostic parameters, not ADD data."""
import json
from pathlib import Path
import numpy as np
from scipy.optimize import root

E1,E2,t1,t2,gamma,g,a,b=.2,.4,.1,.3,.2,.12,-1.,1.
ED=E1-t1*t2/gamma
EV=E1+t1*gamma/t2-t1*t2/gamma
h=np.array([[EV,t1],[t1,E1]],complex)
v=np.array([gamma,t2],complex)
d=np.array([t2,-gamma],complex);d/=np.linalg.norm(d)

def sigma(z,second=False):
 z=complex(z)
 s=g*g*(np.log(z-a)-np.log(z-b))
 return s-(2j*np.pi*g*g if second and z.imag<0 else 0)

def H3(delta=0):
 H=np.zeros((3,3),complex);H[:2,:2]=h;H[0,0]+=delta;H[:2,2]=v;H[2,:2]=v.conj();H[2,2]=E2
 return H

def reduced(z,delta=0,second=False):
 hp=h.copy();hp[0,0]+=delta
 return hp+np.outer(v,v.conj())/(z-E2-sigma(z,second))

def f3(z,delta=0,second=False):
 M=z*np.eye(3)-H3(delta);M[2,2]-=sigma(z,second);return np.linalg.det(M)

def f2(z,delta=0,second=False):return np.linalg.det(z*np.eye(2)-reduced(z,delta,second))

def solve(fun,delta):
 def rf(x):
  v=fun(complex(*x),delta,True);return [v.real,v.imag]
 r=root(rf,[ED+.7*delta,-.0001],tol=1e-11)
 z=complex(*r.x)
 assert np.linalg.norm(rf(r.x))<1e-11
 assert z.imag<0
 return z

def main():
 errors=[]
 for z in [.1+.2j,-.3+.17j,.7+.08j,.1-.1j]:
  for delta in [0,.01,-.015]:
   for second in [False,True]:
    den=z-E2-sigma(z,second);err=abs(f3(z,delta,second)-den*f2(z,delta,second));errors.append(err)
 assert max(errors)<1e-13
 # Full continuum resolvent on P is exactly the Schur complement.
 resolvent_errors=[]
 for z in [.1+.2j,-.3+.17j,.7+.08j]:
  M=z*np.eye(3)-H3();M[2,2]-=sigma(z)
  err=np.linalg.norm(np.linalg.inv(M)[:2,:2]-np.linalg.inv(z*np.eye(2)-reduced(z)))
  resolvent_errors.append(err)
 assert max(resolvent_errors)<1e-12
 assert np.linalg.norm(H3()@np.r_[d,0]-ED*np.r_[d,0])<1e-14
 assert abs(np.vdot(v,d))<1e-14
 # A real-axis spectral density after eliminating node 2 is rational/logarithmic,
 # and equals W_eff^dagger W_eff, not a constant ad-hoc coupling.
 density_errors=[]
 for E in np.linspace(-.8,.8,21):
  sb=g*g*np.log((E-a)/(b-E))-1j*np.pi*g*g
  den=E-E2-sb
  S=np.outer(v,v.conj())/den
  Jeff=-(S-S.conj().T)/(2j*np.pi)
  W=g*v.conj().reshape(1,2)/den
  density_errors.append(np.linalg.norm(Jeff-W.conj().T@W))
  assert np.linalg.eigvalsh(Jeff).min()>-1e-14
 assert max(density_errors)<1e-13
 poles=[]
 for delta in [-.01,.005,.01]:
  z3=solve(f3,delta);z2=solve(f2,delta)
  assert abs(z3-z2)<1e-10
  poles.append(dict(delta=delta,pole3=[z3.real,z3.imag],pole2=[z2.real,z2.imag],Gamma=-2*z3.imag))
 # Same declared 1x2 coupling can have a dark kernel that is NOT an eigenstate.
 W0=np.array([[.2,.3]])
 dn=np.array([.3,-.2]);dn/=np.linalg.norm(dn)
 Hgood=np.outer(dn,dn)*.1+(np.eye(2)-np.outer(dn,dn))*.4
 Hbad=np.diag([.1,.4])
 assert np.linalg.norm(Hgood@dn-.1*dn)<1e-14
 lam=np.vdot(dn,Hbad@dn)
 residual=np.linalg.norm(Hbad@dn-lam*dn);assert residual>.1
 # Existing trimer subfamily with an explicit exchange symmetry, no ADD mapping.
 R=np.array([[0,1,0],[1,0,0],[0,0,1]],complex)
 Hsym=np.array([[E1,t1,gamma],[t1,E1,gamma],[gamma,gamma,E2]],complex)
 dsym=np.array([1,-1,0],complex)/np.sqrt(2)
 symmetry_error=np.linalg.norm(R@Hsym@R-Hsym)
 assert symmetry_error<1e-14 and np.linalg.norm(Hsym@dsym-(E1-t1)*dsym)<1e-14
 broken=Hsym+np.diag([.01,-.01,0]);assert np.linalg.norm(R@broken@R-broken)>.01
 # Conditional geometry-to-spectrum candidate: Hermitian hopping on cycles.
 # kappa is an explicit model parameter, NOT obtained from ADD K.
 kappa=.5; chain_rows=[]
 for N in [32,64,128,256]:
  chain_errors=[]
  energies=2*kappa*np.cos(2*np.pi*np.arange(N)/N)
  for z in [.1+.2j,-.3+.17j,.7+.08j]:
   exact=1/(np.sqrt(z-2*kappa)*np.sqrt(z+2*kappa))
   finite=np.mean(1/(z-energies));chain_errors.append(abs(finite-exact))
  chain_rows.append(dict(N=N,max_local_resolvent_error=max(chain_errors)))
 assert chain_rows[-1]['max_local_resolvent_error']<1e-10
 result=dict(status='PASS',assumptions='R040 real-coupling trimer + explicitly assumed flat energy-normalized bath; no ADD-derived claim',
  parameters=dict(E1=E1,E2=E2,t1=t1,t2=t2,gamma=gamma,g=g,band=[a,b],EV_tuned=EV,ED=ED),
  determinant_identity_max_error=max(errors),projected_resolvent_max_error=max(resolvent_errors),
  effective_density_max_error=max(density_errors),selfconsistent_second_sheet_poles=poles,
  same_W_non_eigen_dark_vector_residual=float(residual),exchange_symmetry_trimer_error=float(symmetry_error),conditional_cycle_hopping_resolvent=chain_rows)
 Path(__file__).with_name('CHECKS.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
