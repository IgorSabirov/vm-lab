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

    def test_three_observable_residues_and_joint_calibration_witnesses(self):
        from three_observables import Fit, diagnostics, forward, rows
        previous=json.loads((EOS/'results.json').read_text())
        saved=json.loads((EOS/'three_results.json').read_text())
        data=[r for r in rows() if r['c2']>0]
        direct=diagnostics(data,previous)
        self.assertEqual(len(direct['central']),6)
        self.assertTrue(all(r['in_two_speed_profile'] for r in direct['central']))
        self.assertAlmostEqual(direct['thermal_significance']['0.9'],.3388061478)
        self.assertTrue(all(abs(m['moment_ratio']-1)<1e-11 for m in direct['damped_moment']))
        for row,ref in zip(data,saved['fits']['nominal']['rows']):
            fit=Fit(row,'nominal',np.ones(4))
            self.assertAlmostEqual(ref['fixed']['loss'],fit.fixed()['loss'],places=6)
            s=fit.eos.at_X(ref['free']['X'])
            z=ref['free']['z']
            u,v,f=forward(s,z)
            self.assertAlmostEqual(v*v+f*(u*u-v*v),z*z,places=10)
            self.assertAlmostEqual((u*v)**2/z**2,s.B,places=10)
        for scenario,witnesses in saved['coherent_calibration'].items():
            for mode,entry in witnesses.items():
                pulls=np.asarray(entry['pulls'])
                total=pulls@pulls
                for row,pred in zip(data,entry['predicted']):
                    y=np.array([row[k] for k in ('T_over_Tc','c1','c2','author_f2','author_fsum')])
                    sd=np.array([row[k] for k in ('err_T','err_c1','err_c2','err_f2','err_fsum')])
                    r=(pred-y)/sd
                    cov=np.eye(5)
                    if scenario=='density_correlated':
                        a=np.r_[1.,y[1:3]*sd[0]/(2*y[0]*sd[1:3]),0.,0.]
                        cov=np.diag(1-a**2)+np.outer(a,a)
                    total+=r@np.linalg.solve(cov,r)
                self.assertAlmostEqual(total,entry['loss'],places=6)
                a,b=entry['fitted_t'][-2:]
                if mode=='B_warmer':
                    self.assertGreaterEqual(b+1e-10,a)
                if mode=='B_colder':
                    self.assertGreaterEqual(a+1e-10,b)
