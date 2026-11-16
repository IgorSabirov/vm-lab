"""No integration: catch accidental extra physics changes and bad eta mapping."""
import json
from pathlib import Path
import sys
import unittest
import common as c

class ContractTests(unittest.TestCase):
    def test_two_declared_points(self):
        rows=c.read(c.PKG/'PLAN.json')['runs']
        self.assertEqual([(r['id'],r['eta_factor']) for r in rows],[('ETA_LOW',.99),('ETA_HIGH',1.01)])
        self.assertTrue(all(r['mode']=='S0' and r['f0']==1 and r['alpha_s_inv']==0 for r in rows))
    def test_resolved_guard_rejects_other_physics(self):
        baseline=c.read(c.BASE/'S0_EXECUTION_MANIFEST.json')['resolved_defaults']
        changed={**baseline,'tau_n':879.0}
        with self.assertRaises(RuntimeError):c.validate_resolved(changed,'ETA_LOW')
        c.validate_resolved({**baseline,'Omegabh2':baseline['Omegabh2']*.99},'ETA_LOW')
    def test_no_duplicate_references(self):
        p=c.read(c.PKG.parent/'pipeline/PIPELINE.json')
        nodes={s['id']:s for s in p['stages']}
        self.assertEqual(nodes['S1_FULLNET']['kind'],'import')
        self.assertEqual(nodes['BH0']['kind'],'import')
        self.assertEqual(c.read(c.PKG.parent/'pipeline/RUN_REQUEST.json')['stages'],['S_ETA'])
    def test_worker_is_reused(self):
        s=(c.PKG/'worker.py').read_text()
        self.assertIn("s1_fullnet/worker.py",s)
        self.assertNotIn('solve_ivp=',s)

if __name__=='__main__':unittest.main()
