"""Bounded check of the supplied R013 review, not a new selected experiment."""
import json, time, sys
from pathlib import Path
import numpy as np
import scipy
from scipy.linalg import expm

started = time.perf_counter()
I = np.eye(2, dtype=complex)
X = np.array([[0, 1], [1, 0]], dtype=complex)
Y = np.array([[0, -1j], [1j, 0]], dtype=complex)
Z = np.diag([1, -1]).astype(complex)
P = [X, Y, Z]
kron = np.kron
CN = np.array([[1,0,0,0],[0,1,0,0],[0,0,0,1],[0,0,1,0]], dtype=complex)
rho0 = (I + Z) / 2
gens = [kron(a, b) for a in P for b in P]
def coefficients(h):
    return np.array([np.trace(g @ h).real / 4 for g in gens])
def reduced(a):
    return np.trace(a.reshape(2,2,2,2), axis1=1, axis2=3)
def h_exact(J, s, n):
    N = sum(a*b for a,b in zip(n,P))
    return J*(np.cos(2*s)*kron(X,I)-np.sin(2*s)*kron(Y,N))
def channel_choi(J,s,t,m):
    c,b = np.cos(2*s),np.sin(2*s)
    us = [expm(-1j*J*t*(c*X-sign*b*Y)) for sign in (1,-1)]
    weights = [(1+m)/2,(1-m)/2]
    return sum(w*np.outer(u.reshape(-1,order='F'),u.reshape(-1,order='F').conj())/2 for w,u in zip(weights,us))

errors = {k:0.0 for k in ['access','hamiltonian','interaction_norm','purity','choi_spectrum','full_channel']}
directions = [np.array(a,dtype=float)/np.linalg.norm(a) for a in ([1,0,0],[0,1,0],[0,0,1],[1,2,3])]
cases = 0
for J in (0.7,1.0,-1.3):
    for s in (0.0025,0.02,0.2,0.7):
        for n in directions:
            N=sum(a*b for a,b in zip(n,P))
            W=expm(1j*s*kron(Z,N))@CN
            h=W@(J*kron(X,X))@W.conj().T
            errors['access']=max(errors['access'],float(np.max(abs(W@kron(Z,I)@W.conj().T-kron(Z,I)))))
            errors['hamiltonian']=max(errors['hamiltonian'],float(np.max(abs(h-h_exact(J,s,n)))))
            errors['interaction_norm']=max(errors['interaction_norm'],abs(float(np.linalg.norm(coefficients(h)))-abs(J*np.sin(2*s))))
            for t in (0.5, np.pi/(2*abs(J)), np.pi/abs(J)):
                U=expm(-1j*t*h)
                for m in (0.0,0.4,1.0):
                    tau=(I+m*N)/2
                    a=reduced(U@kron(rho0,tau)@U.conj().T)
                    actual=float(1-np.trace(a@a).real)
                    predicted=0.5*(1-m*m)*np.sin(2*s)**2*np.sin(2*J*t)**2
                    errors['purity']=max(errors['purity'],abs(actual-predicted))
                    eig=np.linalg.eigvalsh(channel_choi(J,s,t,m))
                    p=np.sin(J*t)**2*np.sin(2*s)**2
                    root=np.sqrt(max(0.,1-4*(1-m*m)*p*(1-p)))
                    expected=np.sort([0.,0.,(1-root)/2,(1+root)/2])
                    errors['choi_spectrum']=max(errors['choi_spectrum'],float(np.max(abs(eig-expected))))
                    up=expm(-1j*J*t*(np.cos(2*s)*X-np.sin(2*s)*Y))
                    um=expm(-1j*J*t*(np.cos(2*s)*X+np.sin(2*s)*Y))
                    for a_input in [I,X,Y,Z]:
                        exact=reduced(U@kron(a_input,tau)@U.conj().T)
                        mixture=(1+m)/2*up@a_input@up.conj().T+(1-m)/2*um@a_input@um.conj().T
                        errors['full_channel']=max(errors['full_channel'],float(np.max(abs(exact-mixture))))
                    cases+=1

def transformed(k):
    W=expm(1j*sum(a*b for a,b in zip(k,gens)))@CN
    return W
step=1e-6
def jac(op):
    cols=[]
    for a in np.eye(9)*step:
        wp,wm=transformed(a),transformed(-a)
        cols.append((coefficients(wp@op@wp.conj().T)-coefficients(wm@op@wm.conj().T))/(2*step))
    return np.column_stack(cols)
Df=jac(kron(Z,I)); Dg=jac(kron(X,X))
_,sv,Vh=np.linalg.svd(Df)
rank=int(np.sum(sv>1e-8)); T=Vh[rank:].T
singular=np.linalg.svd(Dg@T,compute_uv=False)
reproduction=[{'s':s,'interaction_norm':abs(np.sin(2*s)), 'purity_deficit':float(0.5*np.sin(2*s)**2*np.sin(1.)**2)} for s in (0,.0025,.005,.01,.02,.04)]
special=[]
for t in (0.5,np.pi/2,np.pi):
    eig=np.linalg.eigvalsh(channel_choi(1,.02,t,0))
    special.append({'t':t,'pure_Z_input_deficit':float(0.5*np.sin(.04)**2*np.sin(2*t)**2),'choi_rank':int(np.sum(eig>1e-10)),'choi_eigenvalues':eig.tolist()})
z_examples=[]
for name,tau in [('Z_eigenstate',(I+Z)/2),('X_eigenstate',(I+X)/2)]:
    U=expm(-.7j*kron(Z,Z)); a=reduced(U@kron((I+X)/2,tau)@U.conj().T)
    z_examples.append({'environment':name,'purity_deficit':float(1-np.trace(a@a).real)})

R={'QS':.0232643505,'RR':.0403535151,'IC':.0293867334}
F={'QS':.110926546776,'RR':.085234330506,'IC':.093463128}
A={'QS':.04645129616455532,'RR':.06793340061233791,'IC':.04589579900412754}
areas={k:{'H':20,'F_ss':F[k],'R':R[k],'absolute_from_published_R_H_F':20*F[k]*R[k],'signed':A[k], 'temporal_sign_cancellation':1-A[k]/(20*F[k]*R[k])} for k in R}
beta=(29.58-8.71)/(413-89); overhead=8.71-89*beta
runtime={'fit_from_rounded_points':{'intercept':overhead,'slope':beta,'prediction_3083':overhead+3083*beta},'published_3083_process_seconds':3352.798578846996,'transfer_validated':False}
passed=all(v<2e-12 for v in errors.values()) and rank==6 and np.max(abs(singular-2))<1e-8
out={'scope':'Independent 4x4 checks of supplied R013 claims and arithmetic on published summary values; no production E002e solve, no VM job', 'environment':{'python':sys.version.split()[0],'numpy':np.__version__,'scipy':scipy.__version__},'forecast':{'location':'AI_SANDBOX','expected_seconds':2,'upper_budget_seconds':30,'basis':'432 reduced-state checks on 4x4 matrices; no trajectories or high-dimensional solvers'},'cases':cases,'max_errors':errors,'rank_Df':rank,'tangent_dimension':9-rank,'tangent_singular_values':singular.tolist(),'reproduction':reproduction,'unitary_predicate_counterexamples':special,'ZZ_preparation_counterexample':z_examples,'CORR_summary_arithmetic':areas,'runtime_comparison':runtime,'pass':bool(passed),'elapsed_seconds':time.perf_counter()-started}
Path(__file__).with_suffix('.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:out[k] for k in ['cases','max_errors','rank_Df','tangent_singular_values','unitary_predicate_counterexamples','CORR_summary_arithmetic','runtime_comparison','pass','elapsed_seconds']},ensure_ascii=False,indent=2))
if not passed: raise SystemExit(1)
