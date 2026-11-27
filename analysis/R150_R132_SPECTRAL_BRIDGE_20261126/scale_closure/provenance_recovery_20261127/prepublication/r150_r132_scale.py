"""R150--R132: geometry/dispersion/refinement checks; no abundance inputs.
All primary computations dimensionless. Dimensionful example is a conditional
model, not a measurement of the R150 carrier.
"""
import json, math
import numpy as np
from scipy.optimize import minimize_scalar, brentq
from scipy.special import logsumexp, expit

HBARC=197.3269804 # MeV fm
HBAR=6.582119569e-22 # MeV s

def shift(n,phi):
    S=np.roll(np.eye(n,dtype=complex),1,axis=0)
    S[0,-1]=np.exp(1j*phi)
    return S

def active(n,phi):
    # Active layer length L=n+1; port is a separate fixed point.
    F=np.zeros((n+1,n+1),complex); F[0,0]=1; F[1:,1:]=shift(n,phi)
    return F

def check(n,phi,rng):
    F=active(n,phi); eye=np.eye(n+1); d=F-eye
    D=np.block([[0*eye,d.conj().T],[d,0*eye]])
    A=2*eye-F-F.conj().T
    theta=np.r_[0,2*np.pi*np.arange(n)/n+phi/n]
    s=2*np.abs(np.sin(theta/2)); theta_abs=np.abs(np.angle(np.exp(1j*theta)))
    ev=np.linalg.eigvalsh(D); exp=np.sort(np.r_[s,-s]); spectral=max(abs(ev-exp))
    error=np.max(abs(d.conj().T@d-A))
    assert max(error,spectral)<1e-12
    assert max(abs(2*np.arcsin(np.clip(s/2,0,1))-theta_abs))<1e-7
    f=rng.normal(size=n+1); ell=rng.uniform(.1,2,size=n+1)
    # source representation with outgoing links; for column shift the edge
    # index is chosen by its destination. Weighted incidence d=W(F-I).
    # Then each row sees f_source-f_destination. The loop contributes zero.
    B=np.diag(1/ell)@d
    z=B@np.diag(f)-np.diag(f)@B
    lip=np.linalg.norm(z,2)
    expected=max(abs(f[1:]-np.roll(f[1:],1))/ell[1:])
    assert abs(lip-expected)<1e-12
    return float(max(error,spectral)),float(abs(lip-expected))

def heat_delta(n,y):
    # y=n^2 T/J. Ground-shifted H_th/J has energies 4 sin^2(theta/2).
    k=np.arange(n)
    a=-4*n*n*np.sin(np.pi*k/n)**2/y
    b=-4*n*n*np.sin(np.pi*(k+.5)/n)**2/y
    return y*(np.logaddexp(0,logsumexp(a))-np.logaddexp(0,logsumexp(b)))

def heat_lim(y):
    k=np.arange(-200,201,dtype=float)
    a=-4*np.pi**2*k*k/y; b=-4*np.pi**2*(k+.5)**2/y
    return y*(np.logaddexp(0,logsumexp(a))-np.logaddexp(0,logsumexp(b)))

def full_heat_delta(n,y,twist):
    # Full stable carrier at L=n+1: 2L-1 passive cycles of length L;
    # L-2 active layers, each fixed port + length-n cycle.
    L=n+1; A=L-2; P=2*L-1
    k=np.arange(n); l=np.arange(L)
    z0=np.exp(-4*n*n*np.sin(np.pi*k/n)**2/y).sum()
    zp=np.exp(-4*n*n*np.sin(np.pi*(k+.5)/n)**2/y).sum()
    zpass=np.exp(-4*n*n*np.sin(np.pi*l/L)**2/y).sum()
    baseline=P*zpass+A*(1+z0)
    count=A if twist=='all' else 1
    return -y*np.log1p(-count*(z0-zp)/baseline)

def full_lim(y,twist):
    k=np.arange(-200,201,dtype=float)
    z0=np.exp(-4*np.pi**2*k*k/y).sum()
    zp=np.exp(-4*np.pi**2*(k+.5)**2/y).sum()
    if twist=='all':return -y*np.log1p(-(z0-zp)/(1+3*z0))
    # limit n times full_heat_delta for just one twisted active layer.
    return y*(z0-zp)/(1+3*z0)

def maximize(f):
    opt=minimize_scalar(lambda logy:-f(np.exp(logy)),bounds=(math.log(.1),math.log(70)),method='bounded',options={'xatol':1e-11})
    return float(np.exp(opt.x)),float(-opt.fun)

def entropy(n,beta):
    x=beta*2*abs(np.sin(np.pi*np.arange(n)/n))
    # R132 on connected cycle, not extra fixed port.
    return float(2*np.sum(np.logaddexp(0,-x)+x*expit(-x)))

def invert_entropy(n,S):
    if not 2*np.log(2)<S<2*n*np.log(2):raise ValueError('outside finite positive-T inverse')
    return brentq(lambda beta:entropy(n,beta)-S,1e-10,10000,xtol=1e-12)

def main():
    rng=np.random.default_rng(150132)
    err=lip=0.; nchecks=0
    for n in range(2,61,2):
        for phi in [0.,np.pi,.173,-.733]:
            a,b=check(n,phi,rng);err=max(err,a);lip=max(lip,b);nchecks+=1
    rows=[]
    yinf,finf=maximize(heat_lim)
    ensemble_rows=[]
    full_all_lim=maximize(lambda y:full_lim(y,"all"))
    full_one_lim=maximize(lambda y:full_lim(y,"one"))
    for n in [2,4,6,8,14,30,60,120,240,480,960,1920]:
        y,f=maximize(lambda y:heat_delta(n,y)); theta=2*np.pi/n;s=2*np.sin(np.pi/n)
        rows.append(dict(N=n,L=n+1,Tpeak_over_J=y/n**2,DFpeak_over_J=f/n**2,
                         N2_Tpeak_over_J=y,N2_DFpeak_over_J=f,
                         Dirac_lowest_over_exact_phase=s/theta,
                         J_over_epsilon_match_lowest=theta/s**2,
                         J_over_epsilon_match_pi=np.pi/4,
                         fixed_perimeter_quadratic_Tpeak_over_hbar2_2mC2=y))
        ya,fa=maximize(lambda y:full_heat_delta(n,y,'all'))
        yo,fo=maximize(lambda y:full_heat_delta(n,y,'one'))
        ensemble_rows.append(dict(N=n,L=n+1,all_twisted_N2_Tpeak_over_J=ya,all_twisted_N2_DFpeak_over_J=fa,
                                  one_twisted_N2_Tpeak_over_J=yo,one_twisted_N3_DFpeak_over_J=n*fo,
                                  all_twisted_zeroT_contrast=(n-1)/(4*n-1),one_twisted_zeroT_contrast=1/(4*n-1)))
    # KMS calibration test with synthetic entropy, at a known synthetic ratio.
    b=1.75; target=entropy(6,b); recovered=invert_entropy(6,target)
    assert abs(recovered-b)<1e-10
    # Independent two-line inverse on a synthetic relativistic dispersion.
    # Rest energy M and epsilon are recovered, third line is held out.
    M0=2.3; eps0=.8; svals=np.array([1.,np.sqrt(3),2.])
    E=eps0**2*svals**2/(np.sqrt(M0**2+eps0**2*svals**2)+M0)
    e1,e2=E[:2]; s1,s2=svals[:2]
    M=(s1**2*e2**2-s2**2*e1**2)/(2*(s2**2*e1-s1**2*e2))
    eps2=(e1**2+2*M*e1)/s1**2
    held=eps2*svals[2]**2/(np.sqrt(M**2+eps2*svals[2]**2)+M)
    assert abs(M-M0)<1e-12 and abs(eps2-eps0**2)<1e-12 and abs(held-E[2])<1e-12
    inverse=dict(synthetic_lines_MeV=E.tolist(),recovered_rest_MeV=M,recovered_epsilon_MeV=np.sqrt(eps2),predicted_third_MeV=held,holdout_error_MeV=abs(held-E[2]))
    # Example: known carrier mass and circumference, conditional, arbitrary diagnostic anchors.
    # Here C_phys is the circumference of the *configuration* ring if endowed with physical length.
    # Mass is expressed as rest energy in MeV. No mapping to any actual particle claimed.
    mass=100.; circumference=1000.; n=6; ell=circumference/n
    eps=HBARC/ell; J=eps**2/(2*mass); tau=HBAR/eps
    y,f=maximize(lambda y:heat_delta(n,y))
    examples=dict(mass_rest_energy_MeV=mass,circumference_fm=circumference,edge_fm=ell,epsilon_MeV=eps,J_MeV=J,
                  conditional_lightlike_tick_s=tau,nonrelativistic_lowest_gap_MeV=4*J*np.sin(np.pi/n)**2,
                  Tpeak_MeV=J*y/n**2,DFpeak_MeV=J*f/n**2,
                  max_p_c_over_M=2*eps/mass,warning='synthetic diagnostic only; not a hidden sector calibration')
    # Same perimeter refinement at fixed mass and quadratic dispersion preserves low energy,
    # while fixed-edge models preserve local J instead. Use ratios only.
    result=dict(matrix_checks=nchecks,max_spectral_operator_error=err,max_lipschitz_error=lip,
                continuum=dict(N2_Tpeak_over_J=yinf,N2_DFpeak_over_J=finf),rows=rows,full_ensemble=dict(rows=ensemble_rows,all_twisted_limit=dict(N2_Tpeak_over_J=full_all_lim[0],N2_DFpeak_over_J=full_all_lim[1]),one_twisted_limit=dict(N2_Tpeak_over_J=full_one_lim[0],N3_DFpeak_over_J=full_one_lim[1])),
                synthetic_KMS=dict(N=6,beta_epsilon=b,entropy_nats=target,recovered_beta_epsilon=recovered),
                two_line_inverse_synthetic=inverse,dimensionful_illustration=examples,abundance_inputs=False,physical_scale_calibrated=False)
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
