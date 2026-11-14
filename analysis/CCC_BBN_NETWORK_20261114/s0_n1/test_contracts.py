"""Mutation tests on known S0 evidence; no PRIMAT integration."""
import copy,json,tempfile,unittest
from pathlib import Path
import numpy as np
import common as c
import verify as v
import launch

class Contracts(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.result,cls.trace,cls.raw,cls.manifest=v.read_run('.', 'R0')
  cls.expected={e:cls.raw[e+'_species'].tolist() for e in ('HT','MT','LT')}
  cls.mass={n:1 if n in ('n','p') else int(v.re.search(r'\d+$',n).group()) for names in cls.expected.values() for n in names}
 def test_environment_loads_both_blas_libraries(self):
  paths=[q['filepath'] for q in c.env()['threadpools']]
  self.assertTrue(any('numpy.libs' in x for x in paths))
  self.assertTrue(any('scipy.libs' in x for x in paths))
 def test_unknown_and_read_only_run(self):
  for rid in ('R0','R9','CACHE_BG3000'):
   with self.assertRaises(ValueError):c.row_for(rid)
 def test_typed_inheritance(self):
  p=c.config_for('R1','/tmp/no-compute');self.assertIs(type(p['T_start_cosmo_MeV']),float);self.assertEqual(p['T_start_cosmo_MeV'],100.)
 def test_physics_change_rejected(self):
  p=copy.deepcopy(self.manifest['resolved_defaults']);p['Omegabh2']+=.001
  with self.assertRaises(RuntimeError):c.validate_resolved(p,'R1')
 def test_baseline_baryon_and_saha(self):
  b=v.baryon('R0',self.result,self.raw,self.mass,self.expected)
  self.assertGreater(b['handoffs']['HT_to_MT']['composite_Saha_sum_A_Y'],0)
  self.assertLess(b['eras']['LT']['max_in_era_drift'],1e-10)
 def test_wrong_species_order(self):
  r=dict(self.raw);r['LT_species']=r['LT_species'][::-1]
  with self.assertRaises(ValueError):v.baryon('bad',self.result,r,self.mass,self.expected)
 def test_missing_era(self):
  r=dict(self.raw);del r['MT_Y']
  with self.assertRaises(KeyError):v.baryon('bad',self.result,r,self.mass,self.expected)
 def test_nonfinite_and_mass_damage(self):
  for bad in (float('nan'),.05):
   r=dict(self.raw);r['HT_Y']=r['HT_Y'].copy();r['HT_Y'][0,1]=bad
   with self.assertRaises(ValueError):v.baryon('bad',self.result,r,self.mass,self.expected)
 def test_corrupt_cache_artifact_and_decomposition(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)
   for file in ('caches/weak.txt','BARYON_BUDGET.json'):
    c.write(root/file,{'initial':1,'drift':0});launch.manifest(root);c.verify_artifacts(root)
    (root/file).write_text('corrupted')
    with self.assertRaises(ValueError):c.verify_artifacts(root)
    (root/file).unlink()
 def test_grid_growth_and_sign_reversal(self):
  self.assertEqual(v.order([1.,1.1,.99],'rate','YPBBN')['status'],'REVIEW_REQUIRED')
  self.assertEqual(v.order([1.,1.1,1.3],'ode','YPBBN')['status'],'REVIEW_REQUIRED')
 def test_plateau_not_convergence(self):
  self.assertEqual(v.order([1.,1.,1.],'rate','YPBBN')['status'],'PLATEAU_UNRESOLVED')
 def test_fine_budget_breach_cannot_be_cancelled_by_joint(self):
  p=c.read(c.PKG/'N1_PREREGISTRATION.json');bound,kind=v.budget_for('YPBBN',p)
  self.assertGreater(v.delta(.247+2*bound,.247)[kind],bound)

if __name__=='__main__':unittest.main()
