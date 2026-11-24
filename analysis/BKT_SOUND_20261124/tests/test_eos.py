import json
from pathlib import Path
import sys
import unittest
import numpy as np

EOS=Path(__file__).resolve().parents[1]/'eos'
sys.path.insert(0,str(EOS))
from inversion import D0, EquationOfState, components, evaluate, hf_pressure
from run import measured_rows
from resolution import compute

class SoundInversion(unittest.TestCase):
    def test_normal_eos_and_synthetic_recovery(self):
        eos=EquationOfState()
        self.assertAlmostEqual(eos.dc,eos.density(0.),places=12)
        for x in [-.08,0,.35,.8]:
            step=1e-5
            pprime=(eos.pressure(x+step)-eos.pressure(x-step))/(2*step*eos.g)
            self.assertAlmostEqual(pprime,eos.density(x),places=7)
            s=eos.state(eos.density(x))
            for frac in [.12,.55,.9]:
                z=np.sqrt(s.H*frac/(1-frac))
                fast,slow=s.speeds(z)
                self.assertAlmostEqual((fast*slow)**2,s.B*z**2,places=10)
                self.assertAlmostEqual(fast**2+slow**2,s.A+z**2,places=10)
                rec=components(s,(fast,slow),(.04,.05),rho=-.5)
                self.assertAlmostEqual(rec['Ds'],frac*s.D,places=6)
                self.assertAlmostEqual(rec['Ds_sum'],rec['Ds_product'],places=9)
        from scipy.optimize import brentq
        xp=eos.xc
        hf_density=brentq(lambda d:eos.g*d/np.pi+np.log(-np.expm1(-d))-xp,.1,30)
        self.assertAlmostEqual((hf_pressure(xp+step,eos.g)-hf_pressure(xp-step,eos.g))/(2*step),hf_density,places=7)

    def test_reference_and_decision_boundaries(self):
        saved=json.loads((EOS/'results.json').read_text())
        rows=measured_rows()
        self.assertEqual(len(rows),9)
        sound=[r for r in rows if r['c2']>0]
        self.assertEqual(len(sound),6)
        self.assertEqual([r['T_over_Tc'] for r in rows if r['c2']==0],saved['excluded_classification_zeros'])
        for row,stored in zip(sound,saved['records']):
            result,st=evaluate(row,profile=True)
            self.assertAlmostEqual(result['Ds'],stored['nominal']['Ds'],places=5)
            self.assertAlmostEqual(result['chi2'],stored['nominal']['chi2'],places=6)
            self.assertTrue(0<result['Ds']<st.D)
        j=saved['joint_fits']['baseline']
        self.assertGreaterEqual(np.min(np.linalg.eigvalsh(j['cov_Ds_local'])),-1e-8)
        self.assertFalse(any(j['active_bounds']))
        # Reconstruct the entire published global objective from independent raw inputs.
        n,T,q,gs=j['relative_scales']
        eos=EquationOfState(.64*gs)
        s=eos.at_X(np.array(j['fitted_X']))
        fast,slow=s.speeds(np.array(j['fit_z']))
        chi=sum(k*k for k in j['pulls']); scale=q*np.sqrt(n*gs)
        for i,r in enumerate(sound):
            chi+=((r['T_over_Tc']-D0*n/(T*s.D[i]))/r['err_T'])**2
            chi+=((r['c1']-scale*fast[i])/r['err_c1'])**2+((r['c2']-scale*slow[i])/r['err_c2'])**2
        self.assertAlmostEqual(chi,j['chi2'],places=7)
        res=compute(saved)
        self.assertGreater(res['second_speed']['z_all_correlation'][0],3)
        self.assertLess(res['temperature']['z_all_correlation'][1],1.96)
