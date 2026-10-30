"""Fast algebra only: no engine, run, or report I/O."""
import unittest
import numpy as np
from e002c_exp.model import sector_hamiltonian,dark_projectors

class DarkProjectors(unittest.TestCase):
    def test_mask_numbering_and_sink_disconnected_component(self):
        expected=((),((0,1),),((1,2),),((0,1),(1,2)),
                  ((0,2),),((0,1),(0,2)),((1,2),(0,2)),((0,1),(1,2),(0,2)))
        pairs=((0,1),(1,2),(0,2))
        for mask,edges in enumerate(expected):
            h=sector_hamiltonian(mask)
            self.assertEqual(tuple(edge for edge in pairs if abs(h[edge])>0),edges)
        _,d,iso,inter,info=dark_projectors(sector_hamiltonian(1))
        self.assertEqual(info['D']['dimension'],2)
        self.assertTrue(np.allclose(iso,np.diag([1.,1.,0.])))
        self.assertTrue(np.allclose(d,iso));self.assertLess(np.linalg.norm(inter),1e-12)
        # Node 2 IS the sink. Both modes on the disconnected component 0--1
        # are dark; no coherence is needed to populate this component.
        self.assertLess(np.linalg.norm(iso@np.array([0.,0.,1.])),1e-12)
        mixture=np.diag([.5,.5,0.])
        self.assertAlmostEqual(np.trace(iso@mixture).real,1.)
        self.assertEqual(mixture[1,0],0.)

    def test_builder_phase_and_residuals(self):
        c=np.array([0.,0.,1.]);I=np.eye(3)
        for phi,dim in ((0.,1),(np.pi/2,0),(np.pi,1)):
            h=sector_hamiltonian(7,phi);k,d,iso,inter,info=dark_projectors(h)
            self.assertEqual(info['K']['dimension'],1);self.assertEqual(info['D']['dimension'],dim)
            self.assertLess(np.linalg.norm(c@k),1e-12);self.assertLess(np.linalg.norm(c@h@k),1e-12)
            for n in range(3):self.assertLess(np.linalg.norm(c@np.linalg.matrix_power(h,n)@d),1e-12)
            self.assertLess(np.linalg.norm((I-d)@h@d),1e-12)
            v=np.array([1,-np.exp(1j*phi),0])/np.sqrt(2)
            self.assertLess(np.linalg.norm(k@v-v),1e-12)
            if dim:self.assertLess(np.linalg.norm(d@v-v),1e-12)
        h=sector_hamiltonian(7,np.pi/2);k,*_=dark_projectors(h)
        self.assertAlmostEqual(np.linalg.norm(k@(c@h)),np.sqrt(2))

    def test_complex_star(self):
        h=sector_hamiltonian(6,theta=[.1,.7,-1.2],amplitudes=[1.,.7,1.3])
        _,d,iso,_,info=dark_projectors(h);c=np.array([0.,0.,1.])
        self.assertEqual(info['D']['dimension'],1);self.assertAlmostEqual(np.trace(iso).real,0)
        self.assertLess(np.linalg.norm(c@h@d),1e-12)
        self.assertLess(np.linalg.norm((np.eye(3)-d)@h@d),1e-12)

    def test_dark_weight_does_not_imply_coherence(self):
        _,d,*_=dark_projectors(sector_hamiltonian(7))
        rho=np.diag([.5,.5,0.]);self.assertAlmostEqual(np.trace(d@rho).real,.5)
        self.assertEqual(rho[0,1],0)
        rho=np.array([[.3,.1+.05j,0],[.1-.05j,.2,0],[0,0,.5]])
        self.assertAlmostEqual(np.trace(d@rho).real,.5*(rho[0,0]+rho[1,1]).real-rho[0,1].real)

if __name__=='__main__':unittest.main()
