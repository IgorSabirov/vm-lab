import copy
import csv
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import numpy as np
from r135 import thermodynamics,nucleation,collisions,history
from r135.history import CoupledModel,summarize,decay_moments,equilibrium_relic_density,NSTATE
from r135.common import G_NEWTON_MEV_MINUS2,HBAR_MEV_S,InputError,OpenInput,read_json,write_json

def fixture():
 eos={'phases':{'hot':{'kind':'pressure_polynomial','coefficients':[-1,0,0,0,2],'T_range_MeV':[.005,2],'source':'diagnostic bag'},'cold':{'kind':'pressure_polynomial','coefficients':[0,0,0,0,1],'T_range_MeV':[.005,2],'source':'diagnostic bag'}},'transitions':[{'hot':'hot','cold':'cold','T_c_MeV':1,'latent_heat_MeV4':4}]}
 initial={'source':'diagnostic initial surface','T_X_MeV':1,'T_gamma_MeV':.5,'T_nu_MeV':.5,'T_free_MeV':.1,'scale_factor':1,'eta_b_gamma':6e-10,'phase_fraction':0,'time_s':0,'surface':'first_cooling_Tc'}
 H0=math.sqrt(8*math.pi*G_NEWTON_MEV_MINUS2*(7+2*.5**4+.1**4)/3)/HBAR_MEV_S
 kernel={'T_MeV':[.005,1.01],'S3_over_T':[20,20],'prefactor_MeV4':[(H0*HBAR_MEV_S)**4*1000*math.exp(20)]*2,'source':'diagnostic rate','prefactor_source':'diagnostic rate'}
 wall={'friction_MeV4':.5,'conductivity_MeV3':20,'reference_temperature_MeV':1,'max_abs_speed':.999,'max_relative_temperature_difference':1,'T_range_MeV':[.005,2], 'friction_source':'diagnostic','conductivity_source':'diagnostic','domain_source':'diagnostic'}
 collisions={'source':'diagnostic transfer','thermal_channels':[{'id':'em','recipient':'gamma','kind':'matched_power_law','power':4,'coefficient_unit':'MeV^0/s','amplitudes':[0,math.sqrt(.1*H0),math.sqrt(.05*H0)],'phase_weights':{'hot':.1,'cold':1},'T_range_MeV':[.001,2],'source':'diagnostic independent transfer'}]}
 config={'_mode':'validation','thermal_path':'exchange_during_transition','phase_model':'homogeneous_growth','neutrino_closure':'thermal','thermal_closure_source':'diagnostic exact thermal reservoirs','recipient_eos':{s:{'kind':'radiation','rho_over_T4':1,'source':'diagnostic radiation'} for s in ['gamma','nu','free']},'samples':129,'rtol':1e-7,'atol_relative':1e-10,'max_step_H0':.05,'duration_H0':10,'balance_rtol':1e-6}
 return config,eos,kernel,wall,collisions,initial


class HistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)
        cls.args=fixture()
        config,eos,kernel,wall,collision,initial=copy.deepcopy(cls.args)
        # Exercise the real P1/P5/P6 artifacts and P1's initial-surface naming.
        initial['a0']=initial.pop('scale_factor');initial['eta_b']=initial.pop('eta_b_gamma')
        initial['neutrinos']={'kind':'thermal','T_MeV':initial['T_nu_MeV']};initial['phase']='hot'
        p1=cls.root/'p1';p5=cls.root/'p5';p6=cls.root/'p6';p7=cls.root/'p7'
        for p in (p1,p5,p6,p7):p.mkdir()
        scale={'anchor':{'value':1,'sigma':0,'unit':'MeV','source':'diagnostic','origin':'diagnostic'},
               'ratio':{'value':1,'sigma':0,'unit':'1','source':'diagnostic','origin':'diagnostic'}}
        thermodynamics.run({'eos':eos,'scale':scale,'initial_history':initial},{},p1)
        nucleation.run({'nucleation':kernel,'wall':wall},{},p5)
        collision['thermalization']={'status':'EXPLICIT_DIAGNOSTIC_THERMAL_LIMIT','source':'diagnostic reservoir definition'}
        collisions.run({'model':collision},{},p6)
        cls.result=history.run(config,{'eos_bundle':p1/'eos_bundle.json','initial_history':p1/'initial_history.json',
              'nucleation_definition':p5/'nucleation_definition.json','wall_transport':p5/'wall_transport.json',
              'collision_model':p6/'collision_model.json','thermalization_model':p6/'thermalization_model.json'},p7)
        cls.balances=read_json(p7/'balance.json');cls.payload=read_json(p7/'channel_history.json')
        with (p7/'phase_history.csv').open() as f:rows=list(csv.DictReader(f))
        cls.rows={c:[r for r in rows if r['corner']==c] for c in collisions.CORNERS}

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_all_five_independent_histories_and_both_energy_measures(self):
        self.assertEqual(self.result['software_status'],'PASS')
        self.assertEqual(set(self.payload['histories']),set(collisions.CORNERS))
        for corner,meta in self.balances['corners'].items():
            self.assertLess(meta['max_relative_sector_balance'],1e-6)
            self.assertLess(meta['max_relative_radiation_balance'],1e-6)
            self.assertEqual(set(meta['landmarks']),{'1','10'})
            rows=self.rows[corner]
            for row in rows:
                self.assertAlmostEqual(sum(float(row[f'Q_{s}_MeV4_s']) for s in history.SECTORS),0,places=12)
            self.assertGreater(float(rows[-1]['I']),float(rows[len(rows)//2]['I']))
        full=self.balances['corners']['11full']['landmarks']['10']['delivered_energy_over_a0cubed_L']['gamma']
        additive=self.balances['corners']['11add']['landmarks']['10']['delivered_energy_over_a0cubed_L']['gamma']
        self.assertGreater(full,additive)
        self.assertEqual(self.balances['corners']['00']['landmarks']['10']['delivered_energy_over_a0cubed_L']['gamma'],0)

    def test_bidirectional_thermal_phase_feedback_is_nonzero(self):
        a,b=self.rows['00'],self.rows['11full']
        for field in ('T_X_MeV','wall_temperature_MeV','wall_speed','phase_fraction'):
            self.assertGreater(max(abs(float(x[field])-float(y[field])) for x,y in zip(a,b)),1e-5,field)
        model=CoupledModel(*copy.deepcopy(self.args));state=model.y0.copy();state[1]=.9
        state[9]=.1;state[10]=-.75/math.pi*math.log(.8)
        _,first=model.evaluate(.1,state,'11full')
        state[10]=-.75/math.pi*math.log(.3)
        _,second=model.evaluate(.1,state,'11full')
        self.assertNotEqual(first['Q'][1],second['Q'][1])
        slower_args=copy.deepcopy(self.args);slower_args[3]['conductivity_MeV3']=5
        slower=CoupledModel(*slower_args)
        _,slow=slower.evaluate(.1,state,'11full')
        self.assertLess(slow['wall_speed'],second['wall_speed'])
        self.assertLess(slow['f_dot_s_inv'],second['f_dot_s_inv'])
        self.assertLess(abs(slow['wall_heat_residual_MeV4']),1e-12)

    def test_exact_isolation_does_not_reactivate_at_a_numerical_fraction(self):
        args=list(copy.deepcopy(self.args));args[0]['thermal_path']='isolated_during_transition'
        model=CoupledModel(*args);state=model.y0.copy();state[1]=.9;state[10]=100
        _,row=model.evaluate(8,state,'11full')
        self.assertEqual(row['phase_fraction'],1)
        self.assertTrue(row['isolation_active'])
        np.testing.assert_array_equal(row['Q'],np.zeros(5))

    def test_numerical_refinement_preserves_delivered_energy(self):
        args=list(copy.deepcopy(self.args));args[0].update(rtol=1e-9,atol_relative=1e-12,max_step_H0=.025)
        records,meta=CoupledModel(*args).solve('11full')
        refined=summarize(records,meta)
        baseline=self.balances['corners']['11full']
        for n in ('1','10'):
            coarse=baseline['landmarks'][n]['delivered_energy_over_a0cubed_L']['gamma']
            fine=refined['landmarks'][n]['delivered_energy_over_a0cubed_L']['gamma']
            self.assertLess(abs(coarse-fine)/abs(fine),2e-6)

    def test_equilibrium_control_is_its_own_declared_limit(self):
        result=history.equilibrium_mixed_phase(1.471,.2928,[.5,.9,.99,1])
        times=result['H0_delta_t']
        self.assertAlmostEqual(times[-1],.9666654828620107,places=12)
        self.assertAlmostEqual(times[2]-times[0],.7253620346375697,places=12)

    def test_checkpoint_continues_same_boundaries_and_binds_wall(self):
        args=copy.deepcopy(self.args);args[0].update(samples=33,max_step_H0=.15,rtol=1e-6)
        model=CoupledModel(*args);captured=[]
        def capture(path,data):
            if data.get('tau')==1:captured.append(copy.deepcopy(data))
        with patch('r135.history.write_json',side_effect=capture):
            full,meta=model.solve('00',checkpoint=Path('unused.json'))
        self.assertEqual(len(captured),1)
        with tempfile.TemporaryDirectory() as td:
            cp=Path(td)/'checkpoint.json';write_json(cp,captured[0])
            resumed,rmeta=model.solve('00',resume=cp)
            self.assertEqual([x['time_s'] for x in full],[x['time_s'] for x in resumed])
            np.testing.assert_array_equal([x['rho'] for x in full],[x['rho'] for x in resumed])
            args[3]['conductivity_MeV3']=19
            with self.assertRaisesRegex(InputError,'binding mismatch'):CoupledModel(*args).solve('00',resume=cp)

    def test_postconfinement_and_inverse_decay_detailed_balance(self):
        args=list(copy.deepcopy(self.args));args[4]={'source':'declared zero direct scattering','thermal_channels':[]}
        n,_=equilibrium_relic_density(1,2)
        args[0]['relic']={'id':'test','source':'diagnostic MB relic','mass_MeV':2,'kinetic_model':'relativistic_MB',
              'excluded_from_phase_eos':True,'instant_thermalization':True,'channels':[{'id':'gg','recipient':'gamma',
              'kind':'supplied_width','width_MeV':.2*HBAR_MEV_S,'daughter_masses_MeV':[0,0],'source':'diagnostic width'}]}
        args[5].update(surface='postconfinement',phase_fraction=1,T_gamma_MeV=1,T_nu_MeV=1,T_free_MeV=1,
                       relic_n_MeV3=n,relic_T_MeV=1)
        model=CoupledModel(*args);d,row=model.evaluate(0,model.y0,'00')
        self.assertLess(float(np.max(np.abs(row['Q']))),1e-14)
        self.assertLess(abs(d[5]*model.H0+3*row['H_s_inv']*n),1e-14)
        self.assertEqual(row['phase_fraction'],1)
        event=history.first_event([0,1],[1,1],.5)
        self.assertTrue(event['censored']);self.assertEqual(event['censoring'],'left')
        neqdil=equilibrium_relic_density(1,2)[1]/n
        m=decay_moments(n,neqdil,2,.2,1)
        self.assertAlmostEqual(m['number_source_MeV3_s'],0,places=14)
        self.assertAlmostEqual(m['recipient_energy_MeV4_s'],0,places=14)
        zero=decay_moments(n,neqdil,2,.2,0)
        self.assertAlmostEqual(zero['number_source_MeV3_s'],-.2*n*neqdil,places=14)
        self.assertAlmostEqual(zero['recipient_energy_MeV4_s'],.4*n,places=14)

    def test_pressureless_decay_requires_and_checks_inverse_bound(self):
        args=list(copy.deepcopy(self.args));args[4]={'source':'declared zero direct scattering','thermal_channels':[]}
        relic={'id':'test','source':'diagnostic cold relic','mass_MeV':100,'kinetic_model':'pressureless',
              'excluded_from_phase_eos':True,'instant_thermalization':True,'channels':[{'id':'gg','recipient':'gamma',
              'kind':'supplied_width','width_MeV':.2*HBAR_MEV_S,'daughter_masses_MeV':[0,0],'source':'diagnostic width'}]}
        args[0]['relic']=relic;args[0].update(samples=33,max_step_H0=.15,atol_relative=1e-12)
        args[5].update(surface='postconfinement',phase_fraction=1,relic_n_MeV3=.001,relic_T_MeV=0)
        with self.assertRaises(OpenInput):CoupledModel(*args)
        relic['inverse_decay_approximation']={'kind':'negligible_MB','source':'declared Boltzmann bound',
              'max_recipient_temperature_MeV':.8,'relative_energy_tolerance':1e-8}
        args[1]['phases']['hot']['T_range_MeV']=[.9,1.1]
        model=CoupledModel(*args);records,meta=model.solve('00')
        first,last=records[0],records[-1]
        ratio=last['relic_n_MeV3']*last['scale_factor']**3/(first['relic_n_MeV3']*first['scale_factor']**3)
        self.assertAlmostEqual(ratio,math.exp(-.2*(last['time_s']-first['time_s'])),delta=2e-6)
        self.assertLess(summarize(records,meta)['max_relative_sector_balance'],2e-6)

    def test_missing_collision_matching_and_thermal_proof_are_not_zero(self):
        args=list(copy.deepcopy(self.args));args[4]={'source':'known reaction','reactions':[{'id':'known'}],'thermal_channels':[]}
        with self.assertRaises(OpenInput):CoupledModel(*args)
        args=list(copy.deepcopy(self.args));args[0]['_mode']='conditional'
        with self.assertRaisesRegex(OpenInput,'thermal recipient closure'):CoupledModel(*args)

    def test_actual_uncertainty_draws_are_not_only_a_label(self):
        args=list(copy.deepcopy(self.args));config=args[0]
        config.update(samples=33,max_step_H0=.2,rtol=2e-6,atol_relative=1e-10)
        args[5].update(surface='postconfinement',phase_fraction=1)
        defs=dict(zip(('eos_bundle','nucleation_definition','wall_transport','collision_model','initial_history'),args[1:]))
        config['uncertainty_ensemble']={'source':'diagnostic independent sensitivity preparations','interpretation':'sensitivity_set',
              'draws':[{'id':'cold','overrides':{'initial_history':{'T_gamma_MeV':.4}}},
                       {'id':'warm','overrides':{'initial_history':{'T_gamma_MeV':.6}}}]}
        with tempfile.TemporaryDirectory() as td:
            result=history.propagate_uncertainty(config,defs,Path(td))
            self.assertEqual(result['status'],'SENSITIVITY_SET')
            self.assertEqual(result['draw_count'],2)
            self.assertTrue(all(x['status']=='COMPLETE' for x in result['draws']))
            energies=[x['corners']['11full']['landmarks']['10']['delivered_energy_over_a0cubed_L']['gamma'] for x in result['draws']]
            self.assertGreater(abs(energies[0]-energies[1]),1e-3)
            self.assertTrue((Path(td)/'cold'/'raw_history_11full.json').is_file())


if __name__=='__main__':unittest.main()
