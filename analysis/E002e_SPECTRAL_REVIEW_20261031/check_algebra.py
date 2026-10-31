"""Small counterexamples; no production model import or numerical evolution."""
import json, math, time
from fractions import Fraction as F
from pathlib import Path
import numpy as np

def solve_q0_2state(a,b,y):
    # Lx=-y, sum(x)=0. Valid for L=[[-a,b],[a,-b]].
    assert sum(y)==0
    x1=-y[0]/(a+b)
    return (-x1,x1)

def residual(a,b,x,y):
    return (-a*x[0]+b*x[1]+y[0],a*x[0]-b*x[1]+y[1])

def main():
    data={"scope":"small algebra only; no evolution or VM data","cases":[]}
    for gamma in (F(1,10),F(1),F(2)):
        rc=(F(1,2),F(1,2));rt=(1/(2+gamma),(1+gamma)/(2+gamma))
        y=(-gamma*rc[0],gamma*rc[0])
        exact=solve_q0_2state(1+gamma,F(1),y)
        linear=solve_q0_2state(F(1),F(1),y)
        observed=tuple(t-c for t,c in zip(rt,rc))
        assert exact==observed and residual(1+gamma,F(1),exact,y)==(0,0)
        assert sum(exact)==sum(linear)==0
        data["cases"].append({"gamma":str(gamma),"observed":str(observed[1]),
            "exact_bridge":str(exact[1]),"true_linear_response":str(linear[1]),
            "linear_relative_error":float(abs(linear[1]-observed[1])/abs(observed[1]))})
    L=np.array([[-1.,2.],[1.,-2.]])
    y=np.array([-2/3,2/3]);xmin=np.linalg.lstsq(L,-y,rcond=None)[0]
    assert np.max(abs(L@xmin+y))<1e-14 and abs(xmin.sum()-2/15)<1e-14
    data["unconstrained_minimum_norm"]={"x":xmin.tolist(),"trace":float(xmin.sum()),
        "correct_trace_zero_x":[-2/9,2/9]}
    r=np.array([-1.,1.]);ell=np.array([-.5,.5]);o=np.array([0.,1.]);inp=np.array([-.5,.5])
    w=(o@r)*(ell@inp);r2=r/2;ell2=2*ell
    assert ell@r==ell2@r2==1 and (o@r2)**2==(o@r)**2/4
    assert (o@r2)*(ell2@inp)==w
    data["rescaling"]={"right_square_before":float((o@r)**2),"right_square_after":float((o@r2)**2),"two_sided_before":float(w),"two_sided_after":float((o@r2)*(ell2@inp))}
    source=np.zeros((8,8));source[4:,0:4]=np.eye(4)
    coherence=np.zeros((8,8));coherence[2,1]=1
    out=source@coherence@source.T
    assert out[6,5]==1 and np.count_nonzero(out)==1
    data["source_transfers_coherence"]={"from_N1_pair":[2,1],"to_N2_pair":[6,5],"amplitude":float(out[6,5])}
    H=np.diag([0.,10.]);jump=np.array([[0.,math.sqrt(.02)],[0.,0.]])
    eye=np.eye(2);jj=jump.T@jump
    lindblad=-1j*(np.kron(eye,H)-np.kron(H.T,eye))+np.kron(jump,jump)-.5*(np.kron(eye,jj)+np.kron(jj.T,eye))
    eigenvalues=[complex(z) for z in np.linalg.eigvals(lindblad) if abs(z)>1e-12]
    assert len(eigenvalues)==3
    closest=min(eigenvalues,key=abs);slowest=min(eigenvalues,key=lambda z:-z.real)
    data["selection_counterexample"]={"nearest_zero":str(closest),"slowest_damping":str(slowest),"physical_example":"two-level amplitude damping Gamma=.02 and energy splitting 10"}
    assert closest!=slowest
    data["tail"]={"exp_minus_5":math.exp(-5),"exp_minus_10":math.exp(-10),"time_for_1e_minus_6_at_kappa_point1":math.log(1e6)/.1}
    normal=np.diag([-1.,-10.]);inp=np.array([1.,10.]);obs=np.ones(2)
    full=float(obs@np.linalg.solve(normal,-inp));partial=float(-obs[0]*inp[0]/normal[0,0])
    assert full==2 and partial==1 and np.array_equal(normal@normal.T,normal.T@normal)
    data["normal_truncation_counterexample"]={"generator_trace_zero_diagonal":[-1,-10],"input":[1,10],"observable":[1,1],"full_static_response":full,"slow_mode_only_response":partial,"interpretation":"50 percent truncation error with a normal generator"}
    data["dense_complex128_storage"]={"14580_bytes":14580**2*16,"46656_bytes":46656**2*16}
    data["passed"]=True
    Path(__file__).with_name("algebra_checks.json").write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(data,ensure_ascii=False))

if __name__=="__main__":main()
