import copy
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import numpy as np
from scipy.sparse.linalg import expm_multiply
from prepare_j0_config import make
from verify_j0_report import verify
from j0_exp.checks import operator_checks
from j0_exp.task import execute
from sqrt_exp.model import measurement_model

class J0Tests(unittest.TestCase):
    def test_fixed_design_and_inventory(self):
        c=make()
        self.assertEqual(len(c['cases']),24)
        self.assertEqual(sum(round(x['horizon']/x['dt']) for x in c['cases']),720000)
        self.assertEqual(sum(round(x['horizon']/c['integration']['rho_interval'])+1 for x in c['cases']),2424)
        for v in ['PP','PQ','PS','QP','QQ','QS']:
            a=dict(c['models']['j0_'+v]);b=dict(c['models']['j1_'+v]);a.pop('J');b.pop('J');self.assertEqual(a,b)
        self.assertGreater(c['runtime_forecast']['expected_seconds'],0)

    def test_nontrivial_analytic_drain(self):
        c=make()
        # Deliberately occupied sink, unlike the actual run. Checks transient stock drain.
        ket=np.zeros(216,complex);ket[np.ravel_multi_index((0,0,1,1,1,1),(2,2,2,3,3,3))]=1
        v=np.outer(ket,ket.conj()).reshape(-1,order='F')
        for variant in ['QQ','QS']:
            p=c['models']['j0_'+variant];m=measurement_model(p,c['acceptance']);operator_checks(m,p,1e-10)
            evolved=expm_multiply(m['L']*2,v)
            n2=(m['rows'][m['index']['n2']]@evolved)[0].real
            self.assertAlmostEqual(n2,np.exp(-p['kappa_out']*2),places=12)
            # Deliberate broken-hop observable must be detected, not just observed zero on initial RRR.
            bad=dict(m);bad['rows']=m['rows'].tolil(copy=True);bad['rows'][m['index']['I_hop_sink'],0]=1.;bad['rows']=bad['rows'].tocsr()
            with self.assertRaises(ValueError):operator_checks(bad,p,1e-10)

    def test_complete_short_pipeline_and_corruptions(self):
        c=make();c['mode']='main'
        for case in c['cases']:case['horizon']=2.
        c['runtime_forecast'].update(expected_seconds=30.,lower_seconds=0.,upper_seconds=300.,reference='Local T2 test budget; not a VM timing measurement')
        before=Path.cwd()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source';source.mkdir();(source/'config.json').write_text(json.dumps(c))
            job=root/'job';job.mkdir()
            try:
                os.chdir(job)
                with patch.dict(os.environ,{'VM_JOB_ID':'J0_local_smoke_v001','VM_SOURCE_COMMIT':'a'*40}):
                    code=execute(c,source,time.monotonic())
            finally:os.chdir(before)
            self.assertEqual(code,0)
            artifacts={'files/'+p.relative_to(job/'report').as_posix():p.read_bytes() for p in (job/'report').rglob('*') if p.is_file()}
            self.assertTrue(verify(artifacts)['passed'])
            self.assertLessEqual(len(artifacts['files/RESULT.md']),24576)
            for mutation in ['flow','ratio','lost_case','false_stationarity','manifest']:
                bad=dict(artifacts);m=json.loads(bad['files/metrics.json']);manifest=json.loads(bad['files/data_manifest.json']);cid='j1_PP_mix'
                if mutation=='flow':m['cases'][cid]['summary']['final_observables']['sink_flux']+=.1
                elif mutation=='ratio':m['interventions'][0]['ratio']+=.1
                elif mutation=='lost_case':del m['cases'][cid]
                elif mutation=='false_stationarity':m['cases'][cid]['summary']['stationarity']['passed']=True
                elif mutation=='manifest':manifest['full_files'][0]['bytes']+=1
                bad['files/metrics.json']=json.dumps(m).encode();bad['files/data_manifest.json']=json.dumps(manifest).encode()
                with self.assertRaises(AssertionError,msg=mutation):verify(bad)

if __name__=='__main__':unittest.main()
