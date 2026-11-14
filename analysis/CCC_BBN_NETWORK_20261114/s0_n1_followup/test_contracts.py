import tempfile
import unittest
from pathlib import Path
import numpy as np
import common as c
import verify
import review

class Contracts(unittest.TestCase):
    def test_only_declared_rate_configuration_changes(self):
        configs={rid:c.config_for(rid,Path('/tmp/n1_test_cache')) for rid in ('F0','F_RATE','F_ATOL','F_REPEAT')}
        self.assertEqual(configs['F0'],configs['F_ATOL'])
        self.assertEqual(configs['F0'],configs['F_REPEAT'])
        self.assertEqual([k for k in configs['F0'] if configs['F0'][k]!=configs['F_RATE'][k]],['rate_grid_npts'])
        self.assertEqual(c.row_for('F_ATOL')['atol_scale'],.1)
        self.assertEqual(c.row_for('F0')['atol_scale'],1.)
    def test_unknown_id_rejected(self):
        with self.assertRaises(ValueError):c.row_for('R0')
    def test_neutron_budget_not_relaxed(self):
        plan=c.read(c.PKG/'PLAN.json')
        self.assertEqual(plan['numerical_budget'],c.read(c.PARENT_ROOT/'N1_PREREGISTRATION.json')['numerical_budget'])
        gate=verify.compare({'Y_n':3.996227098409122e-16},{'Y_n':3.9962849937164786e-16},plan)
        self.assertFalse(gate['Y_n']['pass'])
    def test_serialization_check_is_binary_sensitive(self):
        a=np.array([1.,np.nextafter(1.,2.),1e-300]);b=a.copy();b[1]=1.
        self.assertNotEqual(review.array_hash(a),review.array_hash(b))
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'values.txt';np.savetxt(f,a)
            self.assertEqual(review.array_hash(a),review.array_hash(np.loadtxt(f)))
    def test_inherited_conservation_detects_damage(self):
        result,trace,raw,manifest=verify.legacy.read_run(c.PARENT_ROOT,'R8')
        expected={e:manifest['network'][e] for e in ('HT','MT','LT')}
        verify.legacy.baryon('R8',result,raw,manifest['mass_numbers'],expected)
        raw['LT_Y']=raw['LT_Y'].copy();raw['LT_Y'][1,-2]+=.001
        with self.assertRaises(ValueError):verify.legacy.baryon('damaged',result,raw,manifest['mass_numbers'],expected)

if __name__=='__main__':unittest.main()
