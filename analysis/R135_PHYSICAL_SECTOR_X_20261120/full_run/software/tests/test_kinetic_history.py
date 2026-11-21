import copy
import unittest
import tempfile
from pathlib import Path
import numpy as np
from r135 import history
from r135.kinetics import MomentumGrid
from r135.neutrino_rates import weak_rates_from_history
from r135.observations import validate_history, validate_weak_rates
from r135.common import InputError, OpenInput
from test_history import fixture


def kinetic_fixture():
    args=list(copy.deepcopy(fixture()))
    args[0].update(samples=33,rtol=2e-8,atol_relative=1e-11,neutrino_closure='momentum_grid')
    grid=MomentumGrid(np.linspace(0,5,13),degeneracy=1)
    species=[]
    for role in ('nu_e','antinu_e'):
        species.append(dict(name=role,role=role,sector='nu',statistics='fermion',degeneracy=1,
                            source='nonthermal diagnostic cells',q_edges_MeV=grid.q_edges.tolist(),
                            initial_occupation=(grid.fermi_dirac(1,.5)*(.7 if role=='nu_e' else 1)).tolist(),
                            operator=dict(kind='emission_absorption',bath='gamma',source='specified inverse rate control',
                                          emission_s_inv=[.0005]*grid.size,absorption_s_inv=[.01]*grid.size)))
    args[0]['kinetic_species']=species
    args[5].pop('T_nu_MeV')
    return args


class KineticHistoryTests(unittest.TestCase):
    def test_joint_p7_conservation_and_lossless_spectra_to_weak_rates(self):
        model=history.CoupledModel(*kinetic_fixture())
        rows,meta=model.solve('11full')
        summary=history.summarize(rows,meta)
        self.assertLess(summary['max_relative_sector_balance'],2e-6)
        self.assertLess(summary['max_relative_radiation_balance'],2e-6)
        h=history._payload(rows)
        self.assertEqual(h['neutrino_closure'],'momentum_grid')
        self.assertIn('f_nu_e',h)
        self.assertNotEqual(h['f_nu_e']['energy_edges_MeV'][0],h['f_nu_e']['energy_edges_MeV'][-1])
        validate_history(h)
        # Two actual P7 slices, not an independently manufactured history.
        small={k:[v[0],v[-1]] for k,v in h.items() if isinstance(v,list) and len(v)==len(rows)}
        for key in ('f_nu_e','f_antinu_e'):
            small[key]={k:[v[0],v[-1]] for k,v in h[key].items()}
        weak=weak_rates_from_history(small)
        validate_weak_rates(weak,small)
        self.assertTrue(all(v>0 for v in weak['lambda_n_to_p_s_inv']))
        self.assertFalse(weak['production_precision_validated'])
        self.assertGreater(abs(rows[-1]['Q'][2]),0)

    def test_kinetic_density_is_not_double_counted_and_bath_gets_reciprocal_source(self):
        args=kinetic_fixture();args[4]={'source':'zero thermal portals','thermal_channels':[]}
        model=history.CoupledModel(*args)
        derivative,row=model.evaluate(0,model.y0,'00')
        krho,_,_=model.kinetic.moments(model.y0,model.a0)
        self.assertEqual(model.y0[3],0)
        self.assertAlmostEqual(row['rho'][2],krho[2])
        self.assertAlmostEqual(row['Q'][1]+row['Q'][2],0,places=14)
        self.assertEqual(derivative[3],0)
        self.assertGreater(np.linalg.norm(derivative[history.NSTATE:]),0)

    def test_thermal_portal_to_resolved_distribution_is_rejected(self):
        args=kinetic_fixture();args[4]['thermal_channels'][0]['recipient']='nu'
        with self.assertRaises(OpenInput):history.CoupledModel(*args)
        args=list(copy.deepcopy(fixture()))
        args[0]['kinetic_species']=[dict(name='test',sector='free',source='diagnostic',statistics='fermion',
                                        degeneracy=1,q_edges_MeV=[0,1],initial_occupation=[.1])]
        args[5]['neutrinos']={'kind':'nonthermal','opaque_spectrum':'must not be discarded'}
        with self.assertRaises(OpenInput):history.CoupledModel(*args)
        args=kinetic_fixture();args[0]['kinetic_species'].pop()
        with self.assertRaises(OpenInput):history.CoupledModel(*args)

    def test_temperature_feedback_uses_actual_finite_bath_and_rejects_extrapolation(self):
        args=kinetic_fixture()
        for species in args[0]['kinetic_species']:
            n=len(species['initial_occupation'])
            species['operator']['emission_s_inv']={'kind':'bath_temperature_table','source':'specified diagnostic T-dependent coefficient',
                                                  'T_MeV':[.1,1.],'values_s_inv':[[.001]*n,[.01]*n]}
        model=history.CoupledModel(*args);state=model.y0.copy()
        d0,r0=model.evaluate(0,state,'00')
        state[2]=model.baths['gamma'].density(.8)
        d1,r1=model.evaluate(0,state,'00')
        self.assertGreater(r1['Q'][2],r0['Q'][2])
        self.assertGreater(np.linalg.norm(d1[history.NSTATE:]-d0[history.NSTATE:]),0)
        self.assertAlmostEqual(sum(r1['Q']),0,places=12)
        state[2]=model.baths['gamma'].density(1.1)
        with self.assertRaises(OpenInput):model.evaluate(0,state,'00')

    def test_auditor_reconstructs_kinetic_density_from_saved_occupations(self):
        from r135.audit import audit_p7
        from r135.common import read_json,write_json
        args=kinetic_fixture();config=args[0]
        # Test the auditor's moment reconstruction without a prescribed
        # constant emitter exhausting the unheated 00 photon reservoir.
        for item in config['kinetic_species']:item['operator']={'kind':'collisionless'}
        config.update({name:doc for name,doc in zip(('eos_bundle','nucleation_definition','wall_transport','collision_model','initial_history'),args[1:])})
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)
            self.assertEqual(history.run(config,{},out)['software_status'],'PASS')
            audit_p7({'root':out},quadrature_rtol=.5)
            payload=read_json(out/'channel_history.json')
            payload['histories']['00']['kinetic_species'][0][0]['occupation'][0]*=.5
            write_json(out/'channel_history.json',payload)
            with self.assertRaisesRegex(InputError,'kinetic energy moment'):
                audit_p7({'root':out},quadrature_rtol=.5)


if __name__=='__main__':unittest.main()
