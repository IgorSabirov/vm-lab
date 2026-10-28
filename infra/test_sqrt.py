import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np

from sqrt_exp.model import build_model, maxabs, measurement_model
from sqrt_exp.engine import initial
from sqrt_exp.task import execute
from prepare_sqrt_config import make
from verify_sqrt_report import verify


class SQRTTests(unittest.TestCase):
    def test_rate_table_and_square_root(self):
        from scipy.linalg import sqrtm
        p=np.array([0,1,1,0])/np.sqrt(2)
        pi=np.outer(p,p);q=np.diag(np.diag(pi));eye=np.eye(4)
        s=eye-(2-np.sqrt(2))*q
        np.testing.assert_allclose(s@s,eye-q,atol=1e-15)
        np.testing.assert_allclose(s,sqrtm(eye-q),atol=1e-15)
        states=[np.eye(4)[i] for i in [0,3,1,2]]+[p,np.array([0,1,-1,0])/np.sqrt(2)]
        expected=[[1,1,.5,.5,0,1],[1,1,.25,.25,.25,.25],[1,1,.5,.5,.5,.5]]
        for a,rates in zip([eye-pi,eye-q,s],expected):
            np.testing.assert_allclose([float(v@a.T@a@v) for v in states],rates,atol=1e-15)
        self.assertGreater(np.linalg.norm((eye-s)@(eye-s)-(eye-q)),.5)

    def test_design_and_initial_mixture(self):
        main=make('main');bench=make('calibration')
        self.assertEqual(len(main['cases']),48)
        self.assertEqual(sum(round(c['horizon']/c['dt']) for c in main['cases']),1080000)
        self.assertEqual(len(bench['cases']),24)
        self.assertEqual(sum(round(c['horizon']/c['dt']) for c in bench['cases']),24000)
        phase=[initial({'state':'phase','phase_index':i}) for i in range(4)]
        np.testing.assert_allclose(np.mean(phase,axis=0),initial({'state':'mix'}),atol=1e-15)

    def test_old_gates_unchanged_and_new_invariants(self):
        spec=importlib.util.spec_from_file_location('old_model',Path(__file__).parent/'fixtures'/'cont_model_v001.py')
        old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
        config=make('main')
        for k,p in config['models'].items():
            if not k.startswith('base_'):continue
            if p['gate_idle']!='S':
                h,j,*_=build_model(p);oh,oj,*_=old.build_model(p)
                self.assertEqual(maxabs(h-oh),0)
                self.assertTrue(all(n==on and maxabs(a-b)==0 for (n,a),(on,b) in zip(j,oj)))
            m=measurement_model(p,config['acceptance'])
            self.assertLess(max(m['checks'].values()),1e-10)

    def test_end_to_end_report_and_semantic_corruptions(self):
        config=make('main')
        config['runtime_forecast']={'expected_seconds':8.,'lower_seconds':0.,'upper_seconds':68.,'reference':'Local reduced T2 smoke, not VM calibration'}
        config['models']={k:v for k,v in config['models'].items() if k=='base_PS'}
        config['cases']=[dict(c,horizon=2.) for c in config['cases'] if c['model'] in config['models']]
        before=Path.cwd()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source';source.mkdir();(source/'sqrt_exp').mkdir()
            (source/'config.json').write_text(json.dumps(config))
            job=root/'job';job.mkdir()
            try:
                os.chdir(job)
                with patch.dict(os.environ,{'VM_JOB_ID':'SQRT_local_smoke_001','VM_SOURCE_COMMIT':'a'*40}):
                    code=execute(config,source,time.monotonic())
            finally:os.chdir(before)
            self.assertEqual(code,0)
            artifacts={'files/'+p.relative_to(job/'report').as_posix():p.read_bytes() for p in (job/'report').rglob('*') if p.is_file()}
            self.assertTrue(verify(artifacts)['passed'])
            self.assertLess(len(artifacts['files/RESULT.md']),24577)
            for mutation in ['flow','case','pass','manifest','version']:
                bad=dict(artifacts);m=json.loads(bad['files/metrics.json']);manifest=json.loads(bad['files/data_manifest.json'])
                cid=next(iter(m['cases']))
                if mutation=='flow':m['cases'][cid]['summary']['final_observables']['sink_flux']+=.1
                if mutation=='case':del m['cases'][cid]
                if mutation=='pass':m['cases'][cid]['summary']['stationarity']['passed']=True
                if mutation=='manifest':manifest['full_files'][0]['bytes']+=1
                if mutation=='version':m['source_commit']='b'*40
                bad['files/metrics.json']=json.dumps(m).encode();bad['files/data_manifest.json']=json.dumps(manifest).encode()
                with self.assertRaises(AssertionError,msg=mutation):verify(bad)


if __name__=='__main__':unittest.main()
