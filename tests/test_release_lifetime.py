import unittest
import numpy as np
from scipy.sparse.linalg import splu,expm_multiply
from e002c_exp.model import build,operators
from e002c_exp.lifetimes import absorption_generator,accumulated_integral


class ReleaseLifetimeTests(unittest.TestCase):
    def test_source_off_loss_and_infinite_time_certificate(self):
        for label in ('QS','RR_QS'):
            m=build(dict(model=label,phi_over_pi=0.,detuning=0.,dephasing=.05))
            a,ix,res=absorption_generator(m);self.assertLess(res,1e-12)
            trace=np.eye(81).reshape(-1,order='F').astype(complex)
            sink=.5*operators()['n'][2][ix,:][:,ix].toarray().reshape(-1,order='F')
            # Source removed, sink loss retained: surviving one-excitation trace can only fall.
            self.assertLess(np.max(abs(a.getH()@trace+sink)),1e-12)
            dual=splu(a.getH().tocsc()).solve(-trace)
            self.assertLess(np.max(abs(a.getH()@dual+trace)),1e-10)
            self.assertGreater(np.linalg.eigvalsh(dual.reshape(81,81,order='F'))[0],0.)
            rho=np.zeros(6561,complex);rho[0]=1.
            trajectory=expm_multiply(a,rho,start=0,stop=400,num=201,traceA=a.diagonal().sum())
            survival=(trajectory@trace).real
            self.assertLess(np.diff(survival).max(),1e-10)
            self.assertLess(survival[-1],1e-4)
            self.assertGreater(np.vdot(dual,rho).real,0.)
            final,integral=accumulated_integral(a,rho[:,None],trace[:,None],400.)
            self.assertLess(abs((integral+dual.conj()@final)[0,0]-np.vdot(dual,rho)),1e-8)
            self.assertLess(np.max(abs(final[:,0]-trajectory[-1])),1e-9)


if __name__=='__main__':unittest.main()
