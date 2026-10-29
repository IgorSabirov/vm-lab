"""Expected before execution: invalid controls and corrupt reports rejected.

The smoke calculation is T12 TEST ONLY, not a scientific feasibility result.
It must produce all eight cases and keep damage ineligible.
"""
import copy
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
import numpy as np

from e002b_exp.matching import derive_rates,scaled_rates,match
from e002b_exp.task import execute,validate_config
from e002b_exp.report import finalize
from e002_exp.model import measurement_model,maxabs
from verify_e002b_report import verify

ROOT=Path(__file__).resolve().parents[1]
CFG=json.loads((ROOT/'config.json').read_text())
TARGET=json.loads((ROOT/CFG['target_file']).read_text())


def synthetic():
    a={'I_hop_sink':1.};b={'I_hop_sink':1.}
    for e in ['01','12','02']:
        for x in [a,b]:
            x['pL'+e]=.2
            for k,v in [('break',.02),('background',.002),('idle',.008)]:x['event_rate__'+k+'_'+e]=v
        b['event_rate__renew_'+e]=.03
    return a,b


class E002bTests(unittest.TestCase):
    def test_analytic_rates_and_population_preserving_scaling(self):
        for v in ['QS','QQ']:
            p=CFG['models'][v];rates=derive_rates(TARGET['candidates'][v],p)
            for e,(a,b) in rates.items():
                t=TARGET['candidates'][v]['edges'][e]
                self.assertAlmostEqual(a*t['pR'],t['loss'],places=13)
                self.assertAlmostEqual((b+p['delta']+p['gamma_bg'])*t['pL'],t['loss'],places=13)
            doubled=scaled_rates(rates,p,2)
            for e,(a,b) in doubled.items():
                self.assertAlmostEqual((b+p['delta']+p['gamma_bg'])/(rates[e][1]+p['delta']+p['gamma_bg']),2)
            with self.assertRaises(ValueError):scaled_rates(rates,p,.5)
        bad=copy.deepcopy(TARGET['candidates']['QS']);bad['edges']['01']['loss']=1e-8
        with self.assertRaises(ValueError):derive_rates(bad,CFG['models']['QS'])

    def test_matching_grades_and_bad_controls(self):
        a,b=synthetic();l=CFG['matching']
        for hop,grade,state in [(1.049,'preferred_le_5pct','matched_control_found'),(1.051,'limited_gt5_le10pct','matched_control_found'),(1.099,'limited_gt5_le10pct','matched_control_found'),(1.101,'ineligible','structural_matched_hop_mismatch')]:
            b['I_hop_sink']=hop;x=match(a,b,l,True)
            self.assertEqual((x['grade'],x['state']),(grade,state))
        b['I_hop_sink']=1.;b['pL01']*=1.02
        self.assertEqual(match(a,b,l,True)['state'],'no_matched_control')
        a,b=synthetic();b['event_rate__idle_01']*=2
        self.assertEqual(match(a,b,l,True)['state'],'no_matched_control')
        self.assertEqual(match(a,b,l,False)['state'],'matching_numerical_failure')
        a,b=synthetic();a['I_hop_sink']=0.
        self.assertFalse(match(a,b,l,True)['damage_eligible'])
        a,b=synthetic();b['I_hop_sink']=float('nan')
        with self.assertRaises(ValueError):match(a,b,l,True)

    def test_config_mutations(self):
        validate_config(CFG,TARGET)
        bad=copy.deepcopy(CFG);bad['models']['RR_QS']['g']=.5
        with self.assertRaises(ValueError):validate_config(bad,TARGET)
        bad=copy.deepcopy(CFG);bad['models']['RR_QS']['rr_rates']['01'][1]*=2
        with self.assertRaises(ValueError):validate_config(bad,TARGET)
        bad=copy.deepcopy(CFG);bad['cases'].pop()
        with self.assertRaises(ValueError):validate_config(bad,TARGET)
        bad=copy.deepcopy(CFG);bad['cases'][1]['dt']=.01
        with self.assertRaises(ValueError):validate_config(bad,TARGET)
        bad=copy.deepcopy(CFG);bad['damage_plan']['allow_automatic_launch']=True
        with self.assertRaises(ValueError):validate_config(bad,TARGET)

    def test_structural_no_machine_and_edge_only_RR(self):
        for name,p in CFG['models'].items():
            m=measurement_model(p,CFG['acceptance'])
            for e in ['01','12','02']:
                for channel in ['form','idle']:
                    self.assertLessEqual(maxabs(m['rows'][m['index']['I_'+channel+e]]),1e-12)
            if name.startswith('RR_'):
                for label,op in m['jumps']:
                    if label.startswith(('renew_','idle_')):
                        block=op.toarray().reshape(8,27,8,27)
                        for i in range(8):
                            for j in range(8):
                                expected=block[0,:,0,:] if i==j else 0
                                self.assertLessEqual(maxabs(block[i,:,j,:]-expected),1e-12)

    def test_smoke_and_corrupt_package(self):
        cfg=copy.deepcopy(CFG);cfg['mode']='test';cfg['horizon']=12.
        cfg['runtime_forecast']['main_steps']=14400
        old_cwd=Path.cwd();old_env={k:os.environ.get(k) for k in ['VM_JOB_ID','VM_SOURCE_COMMIT']}
        with tempfile.TemporaryDirectory(prefix='e002b-smoke-') as temp:
            root=Path(temp)
            try:
                os.chdir(root);os.environ['VM_JOB_ID']='E002b_TEST_ONLY';os.environ['VM_SOURCE_COMMIT']='0'*40
                rc=execute(cfg,ROOT,time.monotonic())
            finally:
                os.chdir(old_cwd)
                for k,v in old_env.items():
                    if v is None:os.environ.pop(k,None)
                    else:os.environ[k]=v
            self.assertIn(rc,[0,1])
            result=verify(root/'report')
            self.assertEqual(result['cases'],8);self.assertEqual(result['steps'],14400)
            path=root/'report/metrics.json';m=json.loads(path.read_text())
            self.assertIn('test_mode_not_scientific',m['acceptance_blockers'])
            self.assertTrue(all(not v['damage_eligible'] for v in m['pair_decisions'].values()))
            self.assertLessEqual((root/'report/RESULT.md').stat().st_size,24*1024)
            bad=copy.deepcopy(m);bad['cases']['QS_fine']['reference']['I_hop_sink']+=.001
            path.write_text(json.dumps(bad))
            with self.assertRaises(AssertionError):verify(root/'report')
            bad=copy.deepcopy(m);bad['pair_decisions']['QS']['damage_eligible']=True
            path.write_text(json.dumps(bad))
            with self.assertRaises(AssertionError):verify(root/'report')
            path.write_text(json.dumps(m))
            # A successful arithmetic check does not override test/numerical blockers.
            self.assertEqual(verify(root/'report')['scientific_status'],'BLOCKED')
            # Budget failures remain explicit and revoke eligibility.
            m['protocol']['result_bytes_limit']=1
            checks=json.loads((root/'report/checks.json').read_text())
            checks=[c for c in checks if c['name'] not in {'runtime_gate','report_budget'}]
            self.assertEqual(finalize(root,m,checks,1.),1)
            self.assertEqual(verify(root/'report')['scientific_status'],'BLOCKED')
            blocked=json.loads(path.read_text())
            self.assertIn('report_budget',blocked['acceptance_blockers'])


if __name__=='__main__':unittest.main()
