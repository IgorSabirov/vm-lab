import math
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import numpy as np
from r135.nucleation import (bounce_o3,thin_wall,Kernel,FrictionWall,hydrodynamic_match,
                            NucleationDomainError,run)


def wall_spec():
    return {'friction_MeV4':10,'conductivity_MeV3':2,'reference_temperature_MeV':1,
            'max_abs_speed':.5,'max_relative_temperature_difference':.2,'T_range_MeV':[.5,1.5],
            'friction_source':'diagnostic linear pressure law','conductivity_source':'diagnostic conductivity',
            'domain_source':'diagnostic prescribed domain'}


class NucleationTests(unittest.TestCase):
    def test_bounce_converges_towards_thin_wall_limit(self):
        sigma=1/(6*math.sqrt(2));ratios=[]
        for eps in (.02,.01):
            result=bounce_o3([0,0,.25-3*eps,-.5+2*eps,.25],0,1,.5-6*eps,100,mesh_points=401)
            expected=thin_wall(1,eps,sigma)
            ratios.append(result['S3_MeV']/expected['S3_MeV'])
            self.assertLess(result['virial_relative_residual'],1e-4)
            self.assertLess(result['tail_relative'],1e-6)
            self.assertLess(abs(result['half_height_radius_MeV_inv']/expected['critical_radius_MeV_inv']-1),.03)
        self.assertLess(abs(ratios[1]-1),.02)
        self.assertLess(abs(ratios[1]-1),abs(ratios[0]-1)/3)

    def test_bounce_mesh_and_radius_convergence(self):
        eps=.02;args=([0,0,.25-3*eps,-.5+2*eps,.25],0,1,.5-6*eps)
        first=bounce_o3(*args,80,mesh_points=401)
        second=bounce_o3(*args,120,mesh_points=801,tolerance=2e-7)
        self.assertLess(abs(first['S3_MeV']/second['S3_MeV']-1),2e-5)
        with self.assertRaises(NucleationDomainError):bounce_o3(*args,1)

    def test_prefactor_is_mandatory_and_no_extrapolation(self):
        spec={'T_MeV':[.8,1],'S3_over_T':[10,20],'prefactor_MeV4':[.8**4,1],
              'source':'diagnostic action','prefactor_source':'diagnostic attempt rate'}
        kernel=Kernel(spec);state=kernel.at(.8)
        self.assertAlmostEqual(state['Gamma_MeV4'],.8**4*math.exp(-10))
        with self.assertRaises(NucleationDomainError):kernel.at(1.1)
        spec.pop('prefactor_source')
        with self.assertRaisesRegex(ValueError,'prefactor'):Kernel(spec)

    def test_flux_matching_energy_and_momentum(self):
        match=hydrodynamic_match(10,2,6,1)
        self.assertLess(abs(match['energy_flux_residual_MeV4']),1e-13)
        self.assertLess(abs(match['momentum_flux_residual_MeV4']),1e-13)
        self.assertTrue(0<match['v_plus']<1 and 0<match['v_minus']<1)
        with self.assertRaises(NucleationDomainError):hydrodynamic_match(10,1,6,2)

    def test_wall_heat_feedback_and_curvature(self):
        wall=FrictionWall(wall_spec())
        cold=wall.speed(.9,.9,2,4);hot=wall.speed(.9,1,2,4)
        self.assertLess(hot['v'],cold['v'])
        self.assertGreater(hot['heat_flux_MeV4'],0)
        self.assertAlmostEqual(cold['pressure_balance_residual_MeV4'],0,places=14)
        steady=wall.steady_speed(.9,.2,1)
        self.assertLess(abs(steady['heat_balance_residual_MeV4']),1e-12)
        self.assertGreater(steady['T_front_MeV'],.9)
        weaker=dict(wall_spec(),conductivity_MeV3=.5)
        self.assertLess(FrictionWall(weaker).steady_speed(.9,.2,1)['v'],steady['v'])
        pocket=wall.pocket_contraction(10,1,.9,.9,2,4)
        self.assertLess(pocket['d_radius_dt_natural'],-cold['v'])
        with self.assertRaises(NucleationDomainError):wall.speed(.9,1.3,2,4)

    def test_stage_outputs_computational_kernel(self):
        config={'nucleation':{'kind':'thin_wall','T_MeV':[.8,.9],'delta_p_MeV4':[.2,.1],
                 'sigma_MeV3':[.1,.1],'prefactor_MeV4':[.8**4,.9**4],
                 'source':'diagnostic thin wall','prefactor_source':'diagnostic prefactor'},'wall':wall_spec()}
        with tempfile.TemporaryDirectory() as td:
            result=run(config,{},Path(td))
            self.assertEqual(result['software_status'],'PASS')
            self.assertTrue((Path(td)/'nucleation_kernel.csv').exists())
            self.assertTrue((Path(td)/'wall_transport.json').exists())
            self.assertTrue((Path(td)/'pocket_model.json').exists())


if __name__=='__main__':unittest.main()
