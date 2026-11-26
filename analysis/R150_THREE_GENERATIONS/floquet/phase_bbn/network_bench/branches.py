"""Map two minima of the imported reduced potential onto one illustrative domain."""
import numpy as np
from scipy.optimize import brentq
from upstream.bh_adapter import potential,phase_landmarks
from graph import TREF

def make_branch_table(path):
    b=-.10
    marks=phase_landmarks(b)
    T=np.unique(np.r_[np.geomspace(.001,10.,700),TREF])
    # Both extrema exist throughout; an imposed thermal history is an input.
    a=marks['a_coexist']+.012*np.tanh(np.log(TREF/T)/.12)
    def high_min(a):
        def da(u):
            return 1-1/(4*u*(1-u))-2*b*u*u-a
        return brentq(da,marks['u_birth'],.99)
    u=np.array([high_min(v) for v in a])
    gap=np.array([potential(v,x,b)-potential(0.,x,b) for v,x in zip(u,a)])
    # Delta F/T = k_dom Delta(S/N^2); k_dom is a freely chosen conversion.
    k_dom=16.
    np.savetxt(path,np.c_[T,T*k_dom*gap],delimiter=',',header='T_MeV,deltaF_1_minus_0_MeV',comments='')
    assert gap[0]>0 and gap[-1]<0 and abs(gap[np.argmin(abs(T-TREF))])<1e-12
    return {**marks,'k_dom':k_dom,'T_cross_MeV':TREF,'a_radius':.012,'logT_width':.12,
            'min_deltaF_over_T':k_dom*min(gap),'max_deltaF_over_T':k_dom*max(gap)}
