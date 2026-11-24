"""Compare reciprocal two-coordinate responses for the Cambridge cold absorption spectrum."""
import numpy as np
from scipy.optimize import least_squares, minimize_scalar
from scipy.special import expit
from scipy.stats import chi2

LOW = np.array([-6.,-6.,-6.,-12.,-np.pi])
HIGH = np.array([6.,6.,6.,12.,np.pi])

def rank_one(s, stiffness1, stiffness2, coupling, damping, theta):
    cos, sin = np.cos(theta), np.sin(theta)
    d1, d2 = s*s+stiffness1, s*s+damping*s+stiffness2
    return (cos*cos*d2+sin*sin*d1-2*sin*cos*coupling)/(d1*d2-coupling*coupling)

def spectrum(theta, frequencies, family):
    s=-1j*frequencies
    if family=='rank_one':
        a,c,G=np.exp(theta[:3])
        k=np.sqrt(a*c*expit(theta[3]))
        H=rank_one(s,a,c,k,G,theta[4])
    else:
        w1,w2,g1,g2=np.exp(theta[:4])
        f=expit(theta[4])
        H=f/(s*s+g1*s+w1*w1)+(1-f)/(s*s+g2*s+w2*w2)
    return H.imag/np.pi

def fit_grid(frequencies, data, errors, family, starts):
    lo,hi=(LOW,HIGH) if family=='rank_one' else ([-6]*4+[-12],[6]*4+[12])
    def residual(v):
        return (spectrum(v,frequencies,family)-data)/errors
    outcomes=[]
    for start in starts:
        fit=least_squares(residual,start,bounds=(lo,hi),max_nfev=500,
                          ftol=1e-10,xtol=1e-10,gtol=1e-10)
        if fit.success:
            outcomes.append((float(2*fit.cost),fit.x))
    if not outcomes:
        raise RuntimeError(f'No converged fit for {family}')
    return min(outcomes,key=lambda pair:pair[0])

def compare_spectra(fit, table):
    w1,w2,g1,g2=fit['physical'][:4]
    f1,f2=fit['f1'],fit['f2component']
    f,obs,se=table.T
    coeff=sum(weight*g*np.array([1.,other_g**2-2*other_w**2,other_w**4])
              for weight,g,other_g,other_w in [(f1,g1,g2,w2),(f2,g2,g1,w1)])
    discriminant=coeff[1]**2-4*coeff[0]*coeff[2]
    G=g1+g2
    a=(g1*w2*w2+g2*w1*w1)/G
    c=w1*w1+w2*w2+g1*g2-a
    k=np.sqrt(a*c-w1*w1*w2*w2)
    np.testing.assert_allclose(np.polymul([1,g1,w1*w1],[1,g2,w2*w2]),
                               [1,G,a+c,G*a,a*c-k*k], rtol=1e-13)

    def loss(th):
        estimate=rank_one(-1j*f,a,c,k,G,th).imag/np.pi
        return float(np.sum(((estimate-obs)/se)**2))
    mesh=np.linspace(-np.pi/2,np.pi/2,721)
    loss_values=np.array([loss(v) for v in mesh])
    step=mesh[1]-mesh[0]
    minima=[minimize_scalar(loss,bounds=(v-step,v+step),method='bounded')
            for j,v in enumerate(mesh[:-1]) if loss_values[j]<=min(loss_values[(j-1)%720],loss_values[(j+1)%720])]
    fixed=min(minima,key=lambda v:v.fun)
    # A rank-one passive damper gives absorption proportional to one real affine square.
    freq=np.linspace(.01,2,113)
    det=((a-freq**2)*(c-freq**2-1j*G*freq)-k**2)
    for th in (0.,-.4,.7):
        expected=G*freq*((a-freq**2)*np.sin(th)-k*np.cos(th))**2/abs(det)**2
        np.testing.assert_allclose(expected,rank_one(-1j*freq,a,c,k,G,th).imag,atol=1e-12)
    start1=[np.log(a),np.log(c),np.log(G),np.log(k*k/(a*c-k*k)),fixed.x]
    points=[start1]+[[np.log(A),np.log(C),np.log(.7),v,th]
                     for A,C in [(.55,1.45),(1.45,.55),(1.,1.)] for v in (-2.,0.) for th in (-1.35,-.7,-.12,.35,1.2)]
    start2=[*np.log([w1,w2,g1,g2]),np.log(f1/f2)]
    best={}
    for family,starts in [('rank_one',points),('modal',[start2])]:
        loss_best,params=fit_grid(f,obs,se,family,starts)
        pred=spectrum(params,f,family)
        best[family]=dict(chi2=loss_best,parameter_count=5,dof=len(f)-5,
                          predictions=pred.tolist(),params=params.tolist(),number_starts=len(starts),
                          chi2_reference_tail=float(chi2.sf(loss_best,len(f)-5)))
    # The full matrix of two independent response channels tests dissipative rank.
    control=[]
    for name,K,C in [
        ('rank_one',np.array([[a,k],[k,c]]),np.diag([0.,G])),
        ('modal',np.diag([w1*w1,w2*w2]),np.diag([g1,g2]))]:
        freq_probe=1.0
        Z=K-freq_probe**2*np.eye(2)-1j*freq_probe*C
        H=np.linalg.inv(Z)
        A=(H-H.conj().T)/(2j)
        expected=freq_probe**2*np.linalg.det(C)/abs(np.linalg.det(Z))**2
        np.testing.assert_allclose(A,freq_probe*H.conj().T@C@H,atol=3e-14)
        np.testing.assert_allclose(np.linalg.det(A).real,expected,atol=1e-13)
        control.append({'family':name,'frequency_over_omegaB':freq_probe,'det_A':float(np.linalg.det(A).real),
                        'expected_det_A':float(expected)})
    return dict(matrix_response_control=control,input_columns=['frequency','absorption','se'],data=np.column_stack((f,obs,se)).tolist(),
                polynomial_u_desc=coeff.tolist(),discriminant=float(discriminant),
                fixed_poles_theta0_chi2=loss(0.), fixed_poles_free_angle_chi2=float(fixed.fun),
                fixed_poles_angle_rad=float(fixed.x),fits=best)
