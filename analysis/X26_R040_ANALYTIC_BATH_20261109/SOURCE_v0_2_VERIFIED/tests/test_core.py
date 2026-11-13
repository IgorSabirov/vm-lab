import math
import unittest
import numpy as np

from x26r040.bath import TightBindingBath
from x26r040.model import R040Parameters
from x26r040.feshbach import (determinant_identity_residual, projected_resolvent_residual,
                              bath_density_eff, discrete_measure_atoms, reduced_measure_sum_rule)
from x26r040.bic import check_direct_bic, static_loading_invariant
from x26r040.continuum import ring_limit_scan, moment_checks
from x26r040.poles import classify_pole, solve_second_sheet_pole
from x26r040.fano import fano_profile
from x26r040.symmetry import check_z2_exchange


def fixture(tuned=True):
    p = R040Parameters(E_V=0.8,E_1=0.2,E_2=0.1,t_1=0.15,t_2=0.3,
                       gamma_d=0.2,kappa=1.0,g=0.22)
    return p.with_dark_tuning() if tuned else p


class TestBath(unittest.TestCase):
    def test_branch_signs_and_asymptotics(self):
        b = TightBindingBath(1.0,0.2)
        self.assertLess(b.green(0.1+1e-8j).imag,0.0)
        self.assertGreater(b.green(0.1-1e-8j,sheet="physical").imag,0.0)
        self.assertLess(b.green(0.1-1e-8j,sheet="II").imag,0.0)
        for z in (100.0+3.0j,-100.0+3.0j):
            self.assertLess(abs(b.green(z)-1.0/z),2e-4)

    def test_herglotz_sign_in_upper_half_plane(self):
        b = TightBindingBath(1.0,0.3)
        for z in (0.2+0.4j, -1.2+0.7j, 2.4+0.3j):
            self.assertLess(b.self_energy(z).imag, 0.0)

    def test_spectral_density_boundary(self):
        b = TightBindingBath(1.0,0.3)
        e=0.4; eta=1e-7
        numeric=-b.self_energy(e+1j*eta).imag/math.pi
        exact=b.j_density(e)
        self.assertAlmostEqual(numeric,exact,places=5)

    def test_ring_limit_off_axis(self):
        b = TightBindingBath(0.8,0.25)
        z=0.23+0.7j
        errors=[abs(b.finite_ring_green(z,n)-b.green(z)) for n in (32,64,128,256)]
        self.assertLess(errors[-1],errors[0])
        self.assertLess(errors[-1],1e-8)

    def test_bound_state_atoms_are_positive(self):
        p=fixture()
        atoms=discrete_measure_atoms(p)
        self.assertEqual(len(atoms),2)
        for atom in atoms:
            eig=np.linalg.eigvalsh(atom["residue"])
            self.assertGreaterEqual(float(eig.min()),-1e-12)

    def test_reduced_spectral_measure_sum_rule(self):
        from scipy.integrate import quad
        p=fixture()
        atom_sum=sum((a["residue"] for a in discrete_measure_atoms(p)),np.zeros((2,2),complex))
        cont=np.zeros((2,2),complex)
        for i in range(2):
            for j in range(2):
                cont[i,j]=quad(lambda e: bath_density_eff(e,p)[i,j].real,
                               p.bath().lower_edge+1e-8,p.bath().upper_edge-1e-8,
                               epsabs=1e-10,limit=300)[0]
        target=np.outer(p.v_PQ,p.v_PQ.conj())
        self.assertLess(np.linalg.norm(atom_sum+cont-target,ord="fro"),1e-7)
        result=reduced_measure_sum_rule(p)
        self.assertTrue(result["continuous_plus_point_sum_rule_pass"])


class TestFeshbach(unittest.TestCase):
    def test_exact_schur_determinant_and_resolvent(self):
        p=fixture()
        for z in (0.23+0.71j,-0.51+0.43j,1.37+0.62j,0.3-0.2j):
            sheet="II" if z.imag < 0 else "physical"
            self.assertLess(determinant_identity_residual(z,p,sheet=sheet),1e-11)
            self.assertLess(projected_resolvent_residual(z,p,sheet=sheet),1e-11)

    def test_effective_density_psd_rank_one(self):
        p=fixture()
        j=bath_density_eff(0.2,p)
        ev=np.linalg.eigvalsh(j)
        self.assertGreaterEqual(float(ev.min()),-1e-12)
        self.assertLess(abs(float(ev[0])),1e-12)
        self.assertGreater(float(ev[1]),0.0)


class TestBICAndControls(unittest.TestCase):
    def test_direct_bic_in_band(self):
        result=check_direct_bic(fixture())
        self.assertEqual(result["verdict"],"BIC_IN_CONDITIONAL_R040_TIGHT_BINDING_MODEL")
        self.assertLess(result["eigen_equation_residual"],1e-12)
        self.assertTrue(result["normalizable_continuum_component"])

    def test_z2_symmetry_subfamily(self):
        p=R040Parameters(E_V=0.2,E_1=0.2,E_2=0.1,t_1=0.15,t_2=0.3,
                         gamma_d=0.3,kappa=1.0,g=0.22)
        result=check_z2_exchange(p)
        self.assertEqual(result["status"],"EXACT_Z2_EXCHANGE_SYMMETRY")
        bic=check_direct_bic(p)
        self.assertEqual(bic["mechanism_class"],"Z2_SYMMETRY_PROTECTED_BIC")

    def test_detuned_model_is_not_bic(self):
        result=check_direct_bic(fixture(tuned=False))
        self.assertEqual(result["verdict"],"DARK_VECTOR_NOT_EIGENSTATE")

    def test_static_no_load(self):
        p=fixture()
        psi=np.array([0.0,0.0,1.0],dtype=complex)
        result=static_loading_invariant(p,psi,np.linspace(0,20,11))
        self.assertTrue(result["static_no_loading_pass"])
        self.assertLess(result["max_absolute_drift"],1e-10)
        self.assertTrue(result["finite_bath_is_closed"])

    def test_wrong_sign_pole_rejected(self):
        result=classify_pole(0.3+0.01j,fixture())
        self.assertEqual(result["status"],"WRONG_SIGN_OR_NOT_DECAYING_POLE")
        self.assertIsNone(result["width"])

    def test_second_sheet_pole_is_self_consistent(self):
        p=R040Parameters(E_V=0.8,E_1=0.2,E_2=0.1,t_1=0.15,t_2=0.3,
                         gamma_d=0.2,kappa=1.0,g=0.22)
        seed=complex(np.linalg.eigvalsh(p.H3)[1],-0.02)
        result=solve_second_sheet_pole(p,seed)
        self.assertEqual(result["status"],"SECOND_SHEET_RESONANCE")
        self.assertGreater(result["width"],0.0)
        self.assertLess(result["scaled_residual"],1e-8)

    def test_fano_zero_is_not_a_bic_verdict(self):
        result=fano_profile(energy=1.0,resonance_energy=1.0,width=0.2,asymmetry_q=0.0)
        self.assertAlmostEqual(result["profile"],0.0,places=14)
        self.assertTrue(result["width_remains_nonzero_at_fano_zero"])
        self.assertEqual(result["status"],"FANO_LINE_SHAPE_ONLY_NOT_BIC_TEST")

    def test_finite_ring_never_claims_width(self):
        b=TightBindingBath(1.0,0.2)
        scan=ring_limit_scan(b,[16,32,64],[0.2+0.5j,-0.3+0.8j])
        self.assertTrue(all(row["Gamma_N_finite_ring"] is None for row in scan))
        self.assertLess(scan[-1]["max_abs_green_error_off_real_axis"],
                        scan[0]["max_abs_green_error_off_real_axis"])
        moments=moment_checks(b,64)
        self.assertLess(max(moments["absolute_errors"]),1e-10)


if __name__ == "__main__":
    unittest.main()
