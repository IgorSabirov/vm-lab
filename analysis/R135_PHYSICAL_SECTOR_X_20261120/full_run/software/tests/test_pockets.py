import copy
import unittest
import numpy as np
from r135.common import InputError, OpenInput
from r135.pockets import (C_CM_S, avrami_geometry, component_catalog,
                          projected_distribution, voxel_geometry, evolve_thermal_pocket)


class PocketTests(unittest.TestCase):
    def test_avrami_constant_rate_and_expansion_quadrature(self):
        t=np.linspace(0,1,401)
        h=dict(time_s=t,scale_factor=np.ones(len(t)),nucleation_rate_cm3_s=np.ones(len(t)),wall_speed=np.full(len(t),1/C_CM_S))
        result=avrami_geometry(h)
        self.assertAlmostEqual(result['I'][-1],np.pi/3,places=4)
        h['scale_factor']=np.exp(t)
        self.assertLess(avrami_geometry(h)['I'][-1],result['I'][-1])

    def test_projected_collapse_recovers_exponential_analytic_rate_and_jacobian(self):
        t=np.linspace(0,34,3401);speed=2.;istar=-np.log(.29)
        g=istar/(8*np.pi*speed**3)*np.exp(t-30)
        h=dict(time_s=t,scale_factor=np.ones(len(t)),nucleation_rate_cm3_s=g,wall_speed=np.full(len(t),speed/C_CM_S))
        r=projected_distribution(h,3000)
        self.assertAlmostEqual(r['old_fraction'],.29,places=6)
        expected=istar**4/(192*speed**3)*np.exp(-istar)
        self.assertLess(abs(r['projected_collapse_rate_cm3_s'][3000]/expected-1),2e-5)
        rate=np.array(r['projected_collapse_rate_cm3_s'])[3000:]
        expected_number=np.trapezoid((1-np.exp(-istar*np.exp(t[3000:]-30)))*rate,t[3000:])
        self.assertAlmostEqual(r['number_density_cm3']/expected_number,1,places=6)
        self.assertLess(r['terminal_old_fraction'],1e-20)
        self.assertLess(abs(r['mean_radius_cm']/speed-1.12),.03)
        h['wall_speed']=h['wall_speed']*np.linspace(1,1.1,len(t))
        with self.assertRaises(OpenInput):projected_distribution(h,3000)

    def test_periodic_component_volume_and_surface_do_not_duplicate_seams(self):
        mask=np.zeros((8,8,8),bool);mask[0,2,2]=mask[-1,2,2]=True
        result=component_catalog(mask,2.)
        self.assertEqual(len(result['components']),1)
        self.assertEqual(result['components'][0]['volume_cm3'],16)
        self.assertEqual(result['surface_grid_faces_cm2'],40)
        self.assertTrue(result['components'][0]['touches_periodic_seam'])
        self.assertEqual(result['percolation_status'],'NOT_INFERRED_FROM_SEAM_CONTACT')
        full=component_catalog(np.ones((4,4,4),bool),1.)
        self.assertEqual(full['surface_grid_faces_cm2'],0)

    def test_poisson_realizations_recover_survival_and_are_reproducible(self):
        t=np.linspace(0,1,101)
        h=dict(time_s=t,scale_factor=np.ones(len(t)),nucleation_rate_cm3_s=np.ones(len(t)),wall_speed=np.full(len(t),1/C_CM_S))
        results=[voxel_geometry(h,box_comoving_cm=6,cells=24,seed=s,snapshot_indices=[100]) for s in range(8)]
        fractions=[r['snapshots'][0]['old_fraction'] for r in results]
        self.assertLess(abs(np.mean(fractions)-np.exp(-np.pi/3)),.06)
        self.assertEqual(results[0],voxel_geometry(h,box_comoving_cm=6,cells=24,seed=0,snapshot_indices=[100]))
        for result in results:
            snap=result['snapshots'][0]
            self.assertAlmostEqual(sum(c['volume_cm3'] for c in snap['components'])/(6**3),snap['old_fraction'])

    def fixture(self):
        return dict(source='analytic control, not SU3 parameters',radius0_cm=C_CM_S,rho0_MeV4=1e-12,delta_v_MeV4=1e-11,g_trapped=1.,
                    time_s=np.linspace(0,8,161).tolist(),domain=dict(source='analytic Minkowski control',max_H_s_inv=0.,
                    thermal_massless_trapped_particles=True,negligible_wall_inertia=True,negligible_surface_energy=True,negligible_self_gravity=True))

    def test_pressure_feedback_and_analytic_terminal_radius(self):
        cfg=self.fixture();r=evolve_thermal_pocket(cfg)
        self.assertLess(r['wall_speed'][-1],1e-5)
        self.assertLess(abs(r['radius_cm'][-1]/r['terminal_radius_without_cooling_cm']-1),1e-6)
        self.assertLess(r['max_relative_energy_balance'],2e-8)
        alpha=cfg['delta_v_MeV4']/np.array(r['rho_MeV4'])
        analytic=(cfg['radius0_cm']/np.array(r['radius_cm']))**3*(1+10)/10-1
        np.testing.assert_allclose(1/alpha,analytic,atol=2e-8,rtol=2e-8)

    def test_cooling_changes_radius_and_balances_emitted_energy(self):
        cfg=self.fixture();uncool=evolve_thermal_pocket(cfg)
        cfg['surface_emissivity']=.02
        cool=evolve_thermal_pocket(cfg)
        self.assertLess(cool['radius_cm'][-1],uncool['radius_cm'][-1])
        self.assertGreater(cool['emitted_energy_MeV'][-1],0)
        self.assertLess(cool['max_relative_energy_balance'],2e-8)
        cfg['domain']['max_H_s_inv']=1
        with self.assertRaises(OpenInput):evolve_thermal_pocket(cfg)

    def test_cooling_to_cutoff_is_a_reported_event_not_a_negative_trial_failure(self):
        cfg=self.fixture();cfg.update(surface_emissivity=.1,time_s=np.linspace(0,12,241).tolist())
        result=evolve_thermal_pocket(cfg)
        self.assertEqual(result['termination'],'SMALL_RADIUS_REQUIRES_NEW_PHYSICS')
        self.assertAlmostEqual(result['radius_cm'][-1]/cfg['radius0_cm'],1e-4,places=10)
        self.assertLess(result['max_relative_energy_balance'],2e-8)

    def test_self_gravity_is_measured_even_if_boolean_claims_it_is_negligible(self):
        cfg=self.fixture();cfg.update(rho0_MeV4=1.,delta_v_MeV4=10.)
        with self.assertRaisesRegex(OpenInput,'compactness'):evolve_thermal_pocket(cfg)
        cfg=self.fixture();cfg['domain']['max_compactness']=1.6e-12
        r=evolve_thermal_pocket(cfg)
        self.assertEqual(r['termination'],'SELF_GRAVITY_REQUIRES_NEW_PHYSICS')
        self.assertAlmostEqual(r['max_compactness']/1.6e-12,1,places=7)


if __name__=='__main__':unittest.main()
