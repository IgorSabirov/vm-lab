import unittest
import json
import tempfile
from pathlib import Path
import numpy as np
from e002c_exp.retry_search import search
from e002c_exp.retry_verify import verify_report
from e002c_exp.export import digest
from e002c_exp.ic_status import decide_ic_status


class RetrySearchTests(unittest.TestCase):
    def test_all_coordinates_and_six_targets(self):
        wanted=np.array([.09,.12,.18])
        def f(a):return np.r_[a,a*a]
        count=[]
        def evaluate(a,index):
            count.append(index)
            return f(a),True,None
        r=search(evaluate,f(wanted),np.array([.07,.07,.12]))
        self.assertLess(r['selected']['maximum_error'],1e-3)
        self.assertEqual(r['computations'],len(count))
        self.assertEqual(r['calls'],r['computations']+r['cache_hits'])
        self.assertLessEqual(r['calls'],141)
        self.assertFalse(r['hop_in_objective'])
        for s in r['starts']:
            self.assertTrue(all(c['star_distinct']==3 for c in s['coverage']))
            self.assertIn('message',s['optimizer'])
    def test_invalid_values_never_become_candidate(self):
        r=search(lambda a,i:([np.nan]*6,False,'not_stationary'),np.ones(6),np.ones(3)*.1)
        self.assertIsNone(r['selected']);self.assertEqual(r['calls'],21)
        self.assertTrue(all(s['optimizer']['nfev']==0 for s in r['starts']))
    def test_seventh_transport_value_rejected(self):
        with self.assertRaises(ValueError):search(lambda a,i:(np.ones(7),True,None),np.ones(6),np.ones(3)*.1)
    def test_bounds_and_clipped_stars(self):
        r=search(lambda a,i:(np.ones(6),True,None),np.ones(6),np.array([1e-4,2.,.1]))
        self.assertTrue(all(1e-4<=min(x['alpha'])<=max(x['alpha'])<=2 for x in r['records']))
        self.assertTrue(all(c['star_distinct']>=2 for s in r['starts'] for c in s['coverage']))
    def test_report_verifier_rejects_false_coverage_values_and_status(self):
        summaries=[];fields=['pL01','pL12','pL02','ell01','ell12','ell02']
        def evaluate(a,index):
            summaries.append(dict(case=dict(id=f'RETRY_FIT_{index:03d}',dt=.02,family='retry_fit'),horizon=200.,
                steps=10000,rhs_calls=40000,scalar_records=1001,diagnostic_records=101,failed=None,
                stationarity=dict(pass_gate=True),reference=dict(zip(fields,np.ones(6)))))
            return np.ones(6),True,None
        fit=search(evaluate,np.ones(6),np.ones(3)*.1)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'selected_alpha.json').write_text(json.dumps(fit['selected']))
            fit['selected_alpha_sha256']=digest(p/'selected_alpha.json')
            m=dict(trajectory_summaries=summaries,work=dict(steps=10000*len(summaries),rhs_calls=40000*len(summaries)),
                fit=fit,target=[1.]*6,target_fields=fields,validation=None,transport=None,ic_status=decide_ic_status(fit,None))
            (p/'checks.json').write_text(json.dumps(dict(volume_pass=True,failures=[])))
            def save(): (p/'metrics.json').write_text(json.dumps(m))
            save();self.assertEqual(verify_report(p)['status'],'VERIFIED_RETRY_REPORT')
            m['fit']['starts'][0]['coverage'][0]['distinct']+=1;save()
            with self.assertRaises(ValueError):verify_report(p)
            m['fit']['starts'][0]['coverage'][0]['distinct']-=1
            m['fit']['records'][0]['values'][0]=2.;save()
            with self.assertRaises(ValueError):verify_report(p)
            m['fit']['records'][0]['values'][0]=1.
            m['ic_status']['ic_structural_status']='no_match_found_within_declared_search';save()
            with self.assertRaises(ValueError):verify_report(p)


if __name__=='__main__':unittest.main()
