import copy
import json
import math
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import numpy as np
from r135.thermodynamics import (PhaseEOS,EOSBundle,EOSDomainError,ideal_gas,
                                 merge_pressure_tables,scale_from_anchor,run)


def cubic_table(lo=1,hi=4,n=9):
    t=np.linspace(lo,hi,n)
    return {"kind":"pressure_table","phase":"hot","source":"diagnostic analytic p=T^3",
            "T_MeV":t.tolist(),"p_MeV4":(t**3).tolist(),"p_sigma_MeV4":[1e-8]*n,
            "s_MeV3":(3*t*t).tolist(),"s_sigma_MeV3":[1e-8]*n,
            "rho_MeV4":(2*t**3).tolist(),"rho_sigma_MeV4":[1e-8]*n}


def bag_bundle():
    return {"phases":{
        "hot":{"kind":"pressure_polynomial","coefficients":[-1,0,0,0,2],"T_range_MeV":[.2,3],"source":"diagnostic bag EOS"},
        "cold":{"kind":"pressure_polynomial","coefficients":[0,0,0,0,1],"T_range_MeV":[.2,3],"source":"diagnostic bag EOS"}},
        "transitions":[{"hot":"hot","cold":"cold","T_c_MeV":1,"latent_heat_MeV4":4}]}


class ThermodynamicsTests(unittest.TestCase):
    def test_thermodynamic_derivatives_and_inverse(self):
        eos=PhaseEOS(cubic_table());t=2.3;s=eos.at(t);h=1e-5
        self.assertAlmostEqual(s['s_MeV3'],(eos.at(t+h)['p_MeV4']-eos.at(t-h)['p_MeV4'])/(2*h),places=7)
        self.assertAlmostEqual(s['rho_MeV4'],t*s['s_MeV3']-s['p_MeV4'],places=12)
        self.assertAlmostEqual(eos.temperature_for_density(2*t**3),t,places=11)
        self.assertGreater(s['cv_MeV3'],0)
        with self.assertRaises(EOSDomainError):eos.at(.9)

    def test_independent_entropy_and_pressure_offset_rejected(self):
        bad=cubic_table();bad['s_MeV3'][3]+=1
        with self.assertRaisesRegex(ValueError,'thermodynamic inconsistency'):PhaseEOS(bad)
        bad=bag_bundle();bad['phases']['hot']['coefficients'][0]-=.1
        with self.assertRaisesRegex(ValueError,'pressure zeros'):EOSBundle(bad)
        bad=bag_bundle();bad['transitions'][0]['latent_heat_MeV4']=1.025
        with self.assertRaisesRegex(ValueError,'latent heat'):EOSBundle(bad)

    def test_mixture_derivative_counts_latent_heat_once(self):
        eos=EOSBundle(bag_bundle());t=.9;f=.3;h=1e-6
        mix=eos.mixture(t,f)
        derivative=(eos.mixture(t,f+h)['rho_MeV4']-eos.mixture(t,f-h)['rho_MeV4'])/(2*h)
        self.assertAlmostEqual(mix['drho_df_MeV4'],derivative,places=9)
        self.assertAlmostEqual(eos.transitions[0]['derived_latent_heat_MeV4'],4)
        self.assertEqual(eos.Tc_MeV,1)
        self.assertEqual(EOSBundle({'definition':bag_bundle()}).Tc_MeV,1)

    def test_pressure_covariance_propagates_derivative(self):
        spec=cubic_table();eos=PhaseEOS(spec);t=2.1
        derivative=eos.basis(t,1)
        expected=np.sqrt(np.sum((derivative*1e-8)**2))
        self.assertAlmostEqual(eos.at(t)['s_sigma_MeV3'],expected,places=20)
        bad=copy.deepcopy(spec);bad['pressure_covariance_MeV8']=(-np.eye(9)).tolist()
        with self.assertRaisesRegex(ValueError,'positive semidefinite'):PhaseEOS(bad)

    def test_overlap_merge_and_ambiguity(self):
        spec=merge_pressure_tables([cubic_table(1,3),cubic_table(2,4)])
        eos=PhaseEOS(spec)
        self.assertAlmostEqual(eos.at(2.35)['p_MeV4'],2.35**3,places=10)
        bad=cubic_table(2,4);bad['p_MeV4']=[x+.01 for x in bad['p_MeV4']]
        with self.assertRaises(ValueError):merge_pressure_tables([cubic_table(1,3),bad])

    def test_thermal_gas_mass_limits_and_energy_derivative(self):
        photon=ideal_gas(2,0,2,'boson')
        self.assertAlmostEqual(photon['rho_MeV4'],math.pi**2*16/15)
        fermion=ideal_gas(2,0,2)
        self.assertAlmostEqual(fermion['rho_MeV4']/photon['rho_MeV4'],7/8)
        low=ideal_gas(.01,.511,4)
        self.assertLess(low['rho_MeV4']/(.01**4),1e-16)
        t=.5;h=1e-5;state=ideal_gas(t,.511,4)
        numeric=(ideal_gas(t+h,.511,4)['rho_MeV4']-ideal_gas(t-h,.511,4)['rho_MeV4'])/(2*h)
        self.assertAlmostEqual(state['cv_MeV3'],numeric,places=8)

    def test_scale_origin_and_stage_artifacts(self):
        scale={'anchor':{'value':2,'sigma':.1,'unit':'MeV','source':'diagnostic','origin':'parameter_scan'},
               'ratio':{'value':1.24,'sigma':.1,'unit':'1','source':'diagnostic','origin':'external_model'}}
        result=scale_from_anchor(scale)
        self.assertFalse(result['absolute_prediction'])
        self.assertAlmostEqual(result['T_c_MeV'],2.48)
        initial={'a0':1,'T_X_MeV':1.5,'T_gamma_MeV':2,'eta_b':6e-10,'phase':'hot',
                 'neutrinos':{'kind':'thermal','T_MeV':2},'source':'diagnostic initial surface'}
        with tempfile.TemporaryDirectory() as td:
            run({'eos':bag_bundle(),'scale':dict(scale,anchor=dict(scale['anchor'],value=1/1.24)),'initial_history':initial},{},Path(td))
            self.assertEqual(set(p.name for p in Path(td).iterdir()),{'scale.json','eos_bundle.json','initial_history.json'})
            loaded=json.loads((Path(td)/'eos_bundle.json').read_text())
            self.assertAlmostEqual(EOSBundle(loaded).at(1,'hot')['rho_MeV4'],7)


if __name__=='__main__':unittest.main()
