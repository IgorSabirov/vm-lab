"""Export-contract tests on synthetic time series, with no evolution."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from scipy.integrate import simpson

from e002c_exp.window_export import extract, digest, reconstruct, dump, run

ROOT=Path(__file__).resolve().parents[1]


class WindowExportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.config=json.loads((ROOT/'experiments/e002c/window_export_v001.json').read_text())
        schema=json.loads((ROOT/'window_schema.json').read_text())
        si={n:i for i,n in enumerate(schema['series'])};di={n:i for i,n in enumerate(schema['diagnostics'])}
        for source in self.config['sources']:
            label=source['label'];case=source['case_id']
            new=self.root/source['run_id']/'full'/case
            new.mkdir(parents=True)
            weights=[.5,.1,.1,.02,.18,.035,.045,.02]
            block=np.zeros((9,8,8),complex);scale={'QS':1.,'IC':.85,'RR':.75}[label]
            for mask,p in enumerate(weights):
                b=np.eye(8,dtype=complex)*p/8
                for i,j,c in [(1,2,-.005j),(5,6,-.006j),(1,4,-.007j),(3,6,-.008j),(2,4,-.002)]:
                    b[i,j]=c*p*scale;b[j,i]=b[i,j].conjugate()
                block[mask+1]=b
            block[0]=block[1:].sum(axis=0)
            frame=reconstruct(block[None])
            np.savez(new/'certificates.npz',time=np.arange(0.,201.,2.),blocks=np.repeat(block[None],101,axis=0))
            scalar=np.zeros(len(si));diagnostic=np.zeros(len(di));scalar[si['h']]=frame['h'].sum()
            for mask in range(8):
                scalar[si[f'p_m{mask}']]=frame['p'][0,mask]
                diagnostic[di[f'I12_m{mask}']]=frame['current_components'][0,mask,:2].sum()
                diagnostic[di[f'I02_m{mask}']]=frame['current_components'][0,mask,2:].sum()
                for field,key in [('d_isolated','isolated_N1'),('d_interference','interference_N1')]:
                    diagnostic[di[f'{field}_m{mask}']]=frame[key][0,mask]
                if mask in (6,7):
                    for tag in ['C01','c01']:
                        diagnostic[di[f'{tag}_m{mask}_re']]=frame[tag][0,mask].real
                        diagnostic[di[f'{tag}_m{mask}_im']]=frame[tag][0,mask].imag
            source['github_T200_anchors']['blocks_T200']=digest(block.tobytes())
            for name,count,step in [('series',1001,.2),('diagnostics',101,2.)]:
                row=scalar if name=='series' else diagnostic
                a=np.repeat(row[None],count,axis=0);a[:,0]=np.round(np.arange(count)*step,10)
                np.savez(new/f'{name}.npz',values=a)
                source['github_T200_anchors'][name+'_T200']=digest(a[-1].tobytes())
            case_info=dict(id=case,dt=.005,phi_over_pi=0,detuning=0,dephasing=.05,horizon=200)
            dump(new/'model.json',dict(case=case_info,alpha=None))
            dump(new/'summary.json',dict(case=case_info,failed=None,stationarity={'pass_gate':True}))
            source['certificates_sha256']=digest((new/'certificates.npz').read_bytes())
            source['model_sha256']=digest((new/'model.json').read_bytes())

    def tearDown(self):
        self.temp.cleanup()

    def execute(self):
        return extract(self.config,self.root,self.root/'out',dict(run_id='test',source_commit='0'*40))

    def test_full_export_reconstructs_all_models_and_weights(self):
        m=self.execute()
        self.assertEqual(m['work']['matrix_blocks'],162)
        self.assertEqual(len(m['source_files']),15)
        np.testing.assert_allclose(self.config['simpson_normalized_weights'],simpson(np.eye(6),x=np.arange(190,201,2),axis=0)/10,rtol=0,atol=1e-15)
        for name,v in m['models'].items():
            self.assertLess(abs(v['means']['h']-v['means']['h_N1']-v['means']['h_N2']),1e-14)
            self.assertLess(max(m['verification'][name]['errors'].values()),1e-10)

    def test_missing_window_point_is_rejected_after_hash_validation(self):
        s=self.config['sources'][0];p=self.root/s['run_id']/'full'/s['case_id']/'certificates.npz'
        with np.load(p) as z: a={k:z[k] for k in z.files}
        a['time'][97]=193.;np.savez(p,**a);s['certificates_sha256']=digest(p.read_bytes())
        with self.assertRaisesRegex(ValueError,'coverage mismatch'):self.execute()

    def test_complete_report_contract(self):
        work=self.root/self.config['run_id'];work.mkdir()
        with patch.dict('os.environ',{'VM_SOURCE_COMMIT':'0'*40}):
            run(self.config,work)
        report=work/'report'
        checks=json.loads((report/'checks.json').read_text())
        self.assertEqual(checks['failures'],[])
        self.assertEqual(checks['runtime_gate']['status'],'PASS')
        self.assertLessEqual((report/'RESULT.md').stat().st_size,24*1024)
        self.assertLessEqual(sum(p.stat().st_size for p in report.rglob('*') if p.is_file()),1048576)
        manifest=json.loads((report/'data_manifest.json').read_text())
        self.assertEqual(len(manifest['exported']),8)
        for item in manifest['exported']:
            data=(report/item['path']).read_bytes()
            self.assertEqual(len(data),item['bytes'])
            self.assertEqual(digest(data),item['sha256'])

    def test_changed_source_hash_is_rejected(self):
        self.config['sources'][0]['certificates_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'hash mismatch'):self.execute()

    def test_wrong_published_anchor_is_rejected(self):
        self.config['sources'][0]['github_T200_anchors']['blocks_T200']='0'*64
        with self.assertRaisesRegex(ValueError,'Published T200 mismatch'):self.execute()


if __name__=='__main__':
    unittest.main(verbosity=2)
