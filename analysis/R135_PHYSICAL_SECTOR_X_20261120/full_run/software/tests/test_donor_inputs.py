import copy
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from r135.common import InputError, OpenInput, read_json, write_json, sha256
from r135.donor_inputs import (EntropyTableEOS, prepare, thin_wall_control, _readers,
                               running_alpha_s, scalar_partonic_width, nda_3to2)
from r135 import collisions, nucleation
from r135.nucleation import thin_wall
from r135.thermodynamics import EOSDomainError


def analytic_spec():
    return dict(kind='entropy_integral_table',phase='analytic',source='analytic s=2T-0.3 control',
                T_MeV=[1.,1.5,2.,3.],s_MeV3=[1.7,2.7,3.7,5.7],
                entropy_covariance_MeV6=(np.eye(4)*.01).tolist(),
                pressure_anchor={'T_MeV':2.,'p_MeV4':3.,'sigma_MeV4':.4,'source':'analytic anchor'},
                uncertainty_mode='diagonal_sensitivity')


def donor_config(cache):
    return {'cache':str(cache),'offline':True,'point_id':'XB-FMS-top-left','scale_method':'r0',
            'entropy_covariance_policy':'diagonal_sensitivity',
            'pressure_anchor_uncertainty':{'sigma_over_Tc4':0.,'kind':'diagnostic_fixed_anchor',
                                           'source':'diagnostic fixed anchor; physical error remains open'}}


def scalar_configuration():
    return {'source':'diagnostic assigned portal for regression only','m0_MeV':1000.,'M_MeV':1e7,
            'T_X_MeV':177.12589073634206,'T_gamma_MeV':34980.,'chi3':2.,'renormalization_scale_MeV':1000.,
            'energy_support':{'center_of_mass_energy_MeV':[1000.,1e6],
                              'source':'diagnostic bounded initial source','omitted_probability_bound':1e-10,
                              'maximum_omitted_probability':1e-8},
            'eft_applicability':{'maximum_energy_over_M':.1,'source':'diagnostic declared EFT margin'},
            'running_alpha_s':{'mu_MeV':[500.,1000.,2000.],'alpha_s':[.3,.2,.1],'nf_intervals':[3,3],
                               'thresholds_MeV':[],'renormalization_scheme':'MSbar','source':'diagnostic test table'},
            'partonic_applicability':{'minimum_scalar_mass_MeV':2000.,'maximum_alpha_s':.3,
                                      'source':'diagnostic bound, not a hadronic matching calculation'}}


def number_configuration():
    return {'source':'diagnostic FMS sensitivity preparation','m0_MeV':1000.,'B':1.,'N':3,
            'kinetic_equilibrium':{'source':'diagnostic assumed separation, not an X measurement',
               'rate_kind':'momentum_relaxation','required_ratio':10.,'minimum_rate_over_H':100.,
               'minimum_rate_over_chemical_rate':100.},
            'low_momentum_applicability':{'T_X_range_MeV':[1.,180.],'maximum_T_X_over_m0':.2,
                                          'source':'diagnostic finite temperature domain'}}


class EntropyIntegrationTests(unittest.TestCase):
    def test_pressure_is_exact_entropy_integral_and_density_is_consistent(self):
        eos=EntropyTableEOS(analytic_spec())
        for t in (1.,1.25,1.5,1.75,2.6,3.):
            y=eos.at(t)
            self.assertAlmostEqual(y['p_MeV4'],t*t-.3*t-.4,places=13)
            self.assertAlmostEqual(y['s_MeV3'],2*t-.3,places=13)
            self.assertAlmostEqual(y['rho_MeV4'],t*t+.4,places=13)
            self.assertAlmostEqual(y['cv_MeV3'],2*t,places=12)
            self.assertAlmostEqual(eos.temperature_for_density(y['rho_MeV4']),t,places=11)
        t=1.73;h=1e-5
        self.assertAlmostEqual((eos.at(t+h)['p_MeV4']-eos.at(t-h)['p_MeV4'])/(2*h),eos.at(t)['s_MeV3'],places=9)
        self.assertAlmostEqual((eos.at(t+h)['rho_MeV4']-eos.at(t-h)['rho_MeV4'])/(2*h),eos.at(t)['cv_MeV3'],places=9)

    def test_covariance_contains_integrated_node_correlations_and_common_anchor(self):
        eos=EntropyTableEOS(analytic_spec());y=eos.at(1.5)
        self.assertAlmostEqual(y['p_sigma_MeV4']**2,.16+.01*(.25**2+.25**2),places=13)
        self.assertAlmostEqual(y['rho_sigma_MeV4']**2,.16+.01*(1.75**2+.25**2),places=13)
        self.assertAlmostEqual(eos.at(2.)['p_sigma_MeV4'],.4,places=13)
        spec=analytic_spec();spec['anchor_entropy_covariance_MeV7']=[.01]*4
        y=EntropyTableEOS(spec).at(1.5)
        self.assertAlmostEqual(y['p_sigma_MeV4']**2,.16+.00125-.01,places=13)

    def test_no_phase_extrapolation_or_invalid_thermodynamic_branch(self):
        eos=EntropyTableEOS(analytic_spec())
        with self.assertRaises(EOSDomainError):eos.at(.999)
        with self.assertRaises(EOSDomainError):eos.at(3.001)
        bad=analytic_spec();bad['s_MeV3'][2]=2.
        with self.assertRaises(InputError):EntropyTableEOS(bad)
        bad=analytic_spec();bad['s_MeV3']=[4,5,6,8]
        with self.assertRaisesRegex(InputError,'acausal'):EntropyTableEOS(bad)
        bad=analytic_spec();bad['pressure_anchor']['p_MeV4']=100
        with self.assertRaisesRegex(InputError,'nonpositive energy'):EntropyTableEOS(bad)

    def test_unknown_or_inconsistent_covariance_is_not_silently_zeroed(self):
        bad=analytic_spec();bad.pop('uncertainty_mode')
        with self.assertRaises(OpenInput):EntropyTableEOS(bad)
        bad=analytic_spec();bad['entropy_covariance_MeV6'][0][0]=-.1
        with self.assertRaises(InputError):EntropyTableEOS(bad)
        bad=analytic_spec();bad['anchor_entropy_covariance_MeV7']=[1]*4
        with self.assertRaisesRegex(InputError,'positive semidefinite'):EntropyTableEOS(bad)

    def test_running_coupling_uses_matched_flavour_knots_and_no_extrapolation(self):
        spec={'mu_MeV':[100.,200.,400.],'alpha_s':[.3,.2,.1],'nf_intervals':[3,4],
              'thresholds_MeV':[200.],'threshold_matching_source':'diagnostic matched threshold',
              'threshold_prescription':'continuous_matched_table','source':'diagnostic running table',
              'renormalization_scheme':'MSbar'}
        self.assertAlmostEqual(running_alpha_s(spec,math.sqrt(100*200))['alpha_s'],.25,places=13)
        self.assertEqual(running_alpha_s(spec,300)['n_f'],4)
        with self.assertRaises(OpenInput):running_alpha_s(spec,99.)
        bad=copy.deepcopy(spec);bad['thresholds_MeV']=[250.]
        with self.assertRaises(InputError):running_alpha_s(bad,300.)
        bad=copy.deepcopy(spec);bad.pop('threshold_matching_source')
        with self.assertRaises(OpenInput):running_alpha_s(bad,300.)


@unittest.skipUnless(os.getenv('R135_DONOR_CACHE'),'requires the verified pinned donor cache')
class ActualDonorPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cache=Path(os.environ['R135_DONOR_CACHE'])
        cls.config=donor_config(cls.cache)
        cls.prepared=prepare(cls.config)

    def test_real_nodes_boundary_and_portal_are_read_from_pinned_bytes(self):
        p=self.prepared;tc=p['eos']['transitions'][0]['T_c_MeV']
        self.assertAlmostEqual(p['scale']['ratio']['value'],.7457/4.21,places=14)
        self.assertAlmostEqual(p['scale']['ratio']['sigma'],.005039146701204892,places=14)
        self.assertEqual(len(p['scale_alternatives']),5)
        cold=EntropyTableEOS(p['eos']['phases']['cold']);hot=EntropyTableEOS(p['eos']['phases']['hot'])
        self.assertAlmostEqual(cold.at(tc)['s_MeV3']/tc**3,.2928,places=13)
        self.assertAlmostEqual(hot.at(tc)['s_MeV3']/tc**3,1.471,places=13)
        self.assertAlmostEqual(cold.at(tc)['p_MeV4'],hot.at(tc)['p_MeV4'],places=6)
        self.assertAlmostEqual((hot.at(tc)['rho_MeV4']-cold.at(tc)['rho_MeV4'])/tc**4,1.1782,places=13)
        self.assertFalse(p['production_precision_validated'])
        self.assertEqual(p['scale']['anchor']['origin'],'external_model')
        self.assertEqual(p['portal_control']['physical_width_status'],'OPEN_INPUT')
        self.assertAlmostEqual(p['portal_control']['K_gg'],5.923979762209211e-6,places=17)
        spectrum=p['relic_spectrum_control']
        self.assertEqual(len(spectrum['states']),12)
        self.assertEqual(spectrum['states'][1]['mass_MeV'],1390.)
        self.assertEqual(spectrum['states'][1]['spin_degeneracy'],5)
        self.assertEqual(spectrum['populations_and_reaction_network_status'],'OPEN_INPUT')
        frozen=json.loads((Path(__file__).resolve().parents[1]/'xb_reference/coordinates.json').read_text())
        ref=next(q for q in frozen['points'] if q['point_id']=='XB-FMS-top-left')
        for key in ('T_X_MeV','T_gamma_MeV','xi'):
            self.assertTrue(math.isclose(p['literature_preparation'][key],ref[key],rel_tol=2e-12),key)
        self.assertEqual(p['literature_preparation']['neutrino_preparation_status'].split(';')[0],'OPEN_INPUT')

    def test_source_alternatives_rescale_MeV_dimensions_without_changing_the_model_origin(self):
        cfg=copy.deepcopy(self.config);cfg['scale_method']='string_tension';other=prepare(cfg)
        ratio=other['eos']['transitions'][0]['T_c_MeV']/self.prepared['eos']['transitions'][0]['T_c_MeV']
        for kind,power in [('T_MeV',1),('s_MeV3',3),('entropy_covariance_MeV6',6)]:
            old=np.asarray(self.prepared['eos']['phases']['hot'][kind]);new=np.asarray(other['eos']['phases']['hot'][kind])
            np.testing.assert_allclose(new,old*ratio**power,rtol=3e-14)
        self.assertEqual(other['scale']['anchor']['origin'],'external_model')
        cfg['scale_method']='flow_beta_6.222'
        with self.assertRaises(OpenInput):prepare(cfg)
        cfg['allow_finite_a_scale']=True
        self.assertTrue(prepare(cfg)['scale']['ratio']['finite_a_mass'])

    def test_missing_uncertainty_and_undeclared_source_identity_are_rejected(self):
        for key in ('pressure_anchor_uncertainty','entropy_covariance_policy','scale_method'):
            cfg=copy.deepcopy(self.config);cfg.pop(key)
            with self.subTest(key=key),self.assertRaises(OpenInput):prepare(cfg)
        cfg=copy.deepcopy(self.config);cfg['point_id']='unregistered-physical-X'
        with self.assertRaises(InputError):prepare(cfg)
        cfg=copy.deepcopy(self.config);cfg['pressure_anchor_uncertainty'].pop('kind')
        with self.assertRaises(OpenInput):prepare(cfg)

    def test_corrupt_actual_cache_is_detected_before_using_primary_numbers(self):
        fetch,_,_=_readers()
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp)
            rows=fetch.sources()
            for row in rows.values():
                source=self.cache/row['sha256']
                if source.exists():(tmp/row['sha256']).symlink_to(source)
            damaged=tmp/rows['mp']['sha256'];damaged.unlink();damaged.write_bytes(b'x'*rows['mp']['bytes'])
            with self.assertRaisesRegex(InputError,'corrupt'):prepare(donor_config(tmp))

    def test_thin_wall_finite_a_control_retains_its_own_latent_heat_and_needs_prefactor(self):
        p=self.prepared;tc=p['interface_control']['T_c_MeV']
        cfg={'finite_a_diagnostic':True,'domain_source':'declared small-supercooling diagnostic',
             'maximum_supercooling_fraction':.03,'T_MeV':[tc*.98,tc*.99],
             'prefactor_MeV4':[1.,1.],'prefactor_source':'assigned dimensional prefactor for control only'}
        k=thin_wall_control(p,cfg)
        for t,dp,sig in zip(k['T_MeV'],k['delta_p_MeV4'],k['sigma_MeV3']):
            delta=1-t/tc
            self.assertAlmostEqual(thin_wall(t,dp,sig)['S3_over_T'],p['interface_control']['K']/(delta**2*(1-delta)),places=12)
        self.assertFalse(k['continuum_metastable_EOS'])
        self.assertEqual(k['physical_input_status'],'DIAGNOSTIC_ONLY')
        self.assertNotEqual(p['interface_control']['latent_heat_MeV4'],p['eos']['transitions'][0]['latent_heat_MeV4'])
        cfg.pop('prefactor_source')
        with self.assertRaises(OpenInput):thin_wall_control(p,cfg)

    def test_scalar_partial_width_respects_EFT_running_coupling_and_hadronic_gap(self):
        cfg=scalar_configuration()
        value=scalar_partonic_width(self.prepared,cfg)
        expected=8/(16*math.pi)*(1/30/(4*math.pi))**2*2.3**2*.2**2*4*1000.**9/(1e7)**8
        self.assertAlmostEqual(value['partial_width_MeV']/expected,1.,places=13)
        self.assertFalse(value['partonic_applicable'])
        self.assertFalse(value['usable_as_total_width'])
        self.assertEqual(value['hadronic_matching_status'],'OPEN_INPUT')
        self.assertEqual(value['status'],'PARTIAL_WIDTH_ONLY')
        cfg['M_MeV']=2e7
        self.assertAlmostEqual(scalar_partonic_width(self.prepared,cfg)['partial_width_MeV']/value['partial_width_MeV'],2**-8,places=15)
        cfg['M_MeV']=1e6
        with self.assertRaises(OpenInput):scalar_partonic_width(self.prepared,cfg)
        cfg=scalar_configuration();cfg['energy_support']['center_of_mass_energy_MeV'][0]=1001.
        with self.assertRaisesRegex(InputError,'cover the scalar decay energy'):
            scalar_partonic_width(self.prepared,cfg)

    def test_NDA_is_linear_in_B_dimensionful_and_requires_kinetic_relaxation(self):
        cfg=number_configuration()
        one=nda_3to2(self.prepared,cfg)
        self.assertAlmostEqual(one['coefficient_MeV_minus5']*1000.**5,(4*math.pi)**3/3**6,places=13)
        cfg['B']=3.
        self.assertAlmostEqual(nda_3to2(self.prepared,cfg)['coefficient_MeV_minus5']/one['coefficient_MeV_minus5'],3.,places=13)
        self.assertIsNone(one['B_probability_measure'])
        self.assertFalse(one['production_precision_validated'])
        cfg['kinetic_equilibrium']['minimum_rate_over_chemical_rate']=2.
        with self.assertRaises(OpenInput):nda_3to2(self.prepared,cfg)

    def test_P5_consumes_P1_artifact_without_relabelling_finite_a_as_physical(self):
        tc=self.prepared['interface_control']['T_c_MeV']
        thin={'finite_a_diagnostic':True,'domain_source':'diagnostic supercooling interval',
              'maximum_supercooling_fraction':.03,'T_MeV':[.98*tc,.99*tc],
              'prefactor_MeV4':[1.,1.],'prefactor_source':'diagnostic normalization'}
        wall={'friction_MeV4':tc**4,'conductivity_MeV3':tc**3,'reference_temperature_MeV':tc,
              'max_abs_speed':.9,'max_relative_temperature_difference':.05,'T_range_MeV':[.97*tc,tc],
              'friction_source':'diagnostic','conductivity_source':'diagnostic','domain_source':'diagnostic'}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'donor_inputs.json';write_json(source,self.prepared)
            output=root/'p5'
            result=nucleation.run({'donor_thin_wall':thin,'wall':wall},{'donor_inputs':source},output)
            self.assertEqual(result['software_status'],'PASS')
            self.assertEqual(result['evidence_status'],'DIAGNOSTIC')
            produced=read_json(output/'nucleation_definition.json')
            self.assertEqual(produced['prepared_input']['sha256'],sha256(source))
            self.assertEqual(produced['physical_input_status'],'DIAGNOSTIC_ONLY')
            self.assertTrue((output/'gw_source.json').is_file())
            self.assertGreater(nucleation.Kernel(produced).at(.985*tc)['S3_over_T'],0)
            with self.assertRaisesRegex(InputError,'not both'):
                nucleation.run({'donor_thin_wall':thin,'nucleation':produced,'wall':wall},
                               {'donor_inputs':source},root/'conflicting')
            missing=copy.deepcopy(thin);missing.pop('prefactor_MeV4')
            with self.assertRaises(OpenInput):
                nucleation.run({'donor_thin_wall':missing,'wall':wall},{'donor_inputs':source},root/'missing')

    def test_P6_partial_width_never_creates_a_total_decay_or_energy_source(self):
        model={'source':'explicit isolated diagnostic transfer','thermal_channels':[],
               'thermalization':{'status':'EXPLICIT_DIAGNOSTIC_THERMAL_LIMIT','source':'test-only reservoir'}}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'donor_inputs.json';write_json(source,self.prepared)
            result=collisions.run({'model':model,'donor_scalar_portal':scalar_configuration(),
                                   'donor_3to2':number_configuration()},
                                  {'donor_inputs':source},root/'p6')
            self.assertEqual(result['software_status'],'PASS')
            self.assertEqual(result['evidence_status'],'OPEN_INPUT')
            collision=read_json(root/'p6/collision_model.json')
            self.assertEqual(collision['definition'],model)
            self.assertEqual(len((root/'p6/decay_table.csv').read_text().splitlines()),1)
            self.assertFalse(read_json(root/'p6/scalar_portal_partial_width.json')['usable_as_total_width'])
            number=read_json(root/'p6/number_changing_model.json')
            self.assertEqual(number['prepared_input']['sha256'],sha256(source))
            self.assertEqual(number['mass_source']['origin'],'external_model')
            self.assertEqual(number['m0_MeV'],1000.)
            self.assertEqual(number['T_X_range_MeV'],[1.,180.])
            number_only=collisions.run({'model':model,'donor_3to2':number_configuration()},
                                      {'donor_inputs':source},root/'p6_number')
            self.assertEqual(number_only['evidence_status'],'CONDITIONAL')
            self.assertFalse((root/'p6_number/scalar_portal_partial_width.json').exists())

    def test_downstream_stages_reject_changed_donor_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'donor_inputs.json'
            bad=copy.deepcopy(self.prepared)
            bad['donor_provenance']['files']['fms']['sha256']='0'*64
            write_json(source,bad)
            with self.assertRaisesRegex(InputError,'source identity mismatch'):
                collisions.run({'donor_3to2':number_configuration()},{'donor_inputs':source},root/'p6')
            with self.assertRaisesRegex(OpenInput,'donor_inputs'):
                collisions.run({'donor_3to2':number_configuration()},{},root/'missing')


if __name__=='__main__':unittest.main()
