import hashlib,json,tempfile,unittest
from pathlib import Path
from integrity import admit,final_manifest,audit_manifest,sha

class Integrity(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.p=Path(self.tmp.name)
        meta={k:k+'_fixture' for k in ['source_digest','manifest_digest','workload_digest','environment_fingerprint']}
        (self.p/'CALIBRATION.json').write_text(json.dumps({**meta,'technical_pass':True}))
        gate={**meta,'calibration_sha256':sha(self.p/'CALIBRATION.json'),'status':'TARGET_VM_CALIBRATION_PASS',
              'lower_seconds':1.,'expected_seconds':2.,'upper_seconds':3.,'hard_wall_seconds':4.}
        (self.p/'RUNTIME_GATE.json').write_text(json.dumps(gate))
        binding={**meta,'artifact_sha256':{k:sha(self.p/k) for k in ['CALIBRATION.json','RUNTIME_GATE.json']}}
        (self.p/'ADMISSION_BINDING.json').write_text(json.dumps(binding));self.h=sha(self.p/'ADMISSION_BINDING.json')
    def tearDown(self):self.tmp.cleanup()
    def test_valid_chain(self):admit(self.p,self.h)
    def test_calibration_byte_mutation_rejected(self):
        with (self.p/'CALIBRATION.json').open('a') as f:f.write(' ')
        with self.assertRaises(ValueError):admit(self.p,self.h)
    def test_forecast_byte_mutation_rejected(self):
        with (self.p/'RUNTIME_GATE.json').open('a') as f:f.write(' ')
        with self.assertRaises(ValueError):admit(self.p,self.h)
    def test_binding_mutation_rejected(self):
        with (self.p/'ADMISSION_BINDING.json').open('a') as f:f.write(' ')
        with self.assertRaises(ValueError):admit(self.p,self.h)
    def test_final_manifest_detects_late_change_and_reseals(self):
        before=final_manifest(self.p)
        self.assertEqual(audit_manifest(self.p,before),[])
        (self.p/'RUNTIME_GATE.json').write_text('{}')
        self.assertEqual(len(audit_manifest(self.p,before)),1)
        after=final_manifest(self.p)
        self.assertEqual(audit_manifest(self.p,after),[])
        self.assertNotIn('OUTPUT_MANIFEST.json',after)
    def test_chain_reference_rejected_even_with_updated_artifact_digest(self):
        g=json.loads((self.p/'RUNTIME_GATE.json').read_text());g['calibration_sha256']='0'*64
        (self.p/'RUNTIME_GATE.json').write_text(json.dumps(g))
        b=json.loads((self.p/'ADMISSION_BINDING.json').read_text());b['artifact_sha256']['RUNTIME_GATE.json']=sha(self.p/'RUNTIME_GATE.json')
        (self.p/'ADMISSION_BINDING.json').write_text(json.dumps(b))
        with self.assertRaises(ValueError):admit(self.p,sha(self.p/'ADMISSION_BINDING.json'))

if __name__=='__main__':unittest.main()
