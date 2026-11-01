"""Launch packaging and exact unmanaged BLAS identity; no physical solves."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from e002e_exp.runtime import ROOT, kernel_hash
from e002e_corr_exp.plan import implementation_manifest, implementation_hash, protocol_hash, thread_preflight
from experiments.e002e_corr.vm_entry import bind


class LaunchTests(unittest.TestCase):
    def test_unmanaged_blas_requires_exact_binaries_and_process_count(self):
        ref=json.loads((ROOT/'experiments/e002e_corr/unmanaged_blas_reference.json').read_text())
        good=dict(requested_threads={k:'1' for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS')},
                  threadpools=[],blas_library_identity=ref['libraries'],process_threads=1)
        self.assertEqual(thread_preflight(good)['status'],'PASS')
        changed=copy.deepcopy(good);changed['blas_library_identity'][0]['sha256']='0'*64
        for bad in (changed,dict(good,process_threads=None),dict(good,process_threads=2),dict(good,blas_library_identity=[])):
            with self.assertRaises(ValueError):thread_preflight(bad)

    def test_launcher_binding_rejects_missing_or_conflicting_source(self):
        self.assertEqual(bind({'source_commit':'FROM_VERIFIED_VM_LAUNCHER'},'a'*40)['source_commit'],'a'*40)
        for cfg,sha in (({},'a'*40),({'source_commit':'b'*40},'a'*40),({'source_commit':'FROM_VERIFIED_VM_LAUNCHER'},'')):
            with self.assertRaises(ValueError):bind(cfg,sha)

    def test_snapshot_preserves_kernel_and_carries_published_evidence(self):
        evidence=json.loads((ROOT/'experiments/e002e_corr/evidence.json').read_text())
        paths={x['path'] for x in implementation_manifest()}
        paths.add('experiments/e002e_corr/evidence.json')
        paths.update(x['path'] for x in evidence['baselines'])
        paths.update(x['path'] for x in evidence['sources'].values())
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);payload=root/'corr_payload'
            for name in paths:
                dest=payload/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
            shutil.copyfile(ROOT/'experiments/e002e_corr/vm_entry.py',root/'run.py')
            config=dict(address_space_limit_bytes=8*2**30,kernel_sha256=kernel_hash(),worker_config=dict(
                source_commit='FROM_VERIFIED_VM_LAUNCHER',implementation_sha256=implementation_hash(),protocol_sha256=protocol_hash()))
            (root/'config.json').write_text(json.dumps(config))
            env=dict(os.environ,VM_SOURCE_DIR=str(root),VM_SOURCE_COMMIT='a'*40,PYTHONPATH='')
            cmd=[sys.executable,str(root/'run.py'),'--audit']
            result=subprocess.run(cmd,cwd=d,env=env,capture_output=True,text=True,check=True)
            checked=json.loads(result.stdout)
            self.assertEqual(checked['numerical_work'],0)
            self.assertEqual(checked['kernel_sha256'],kernel_hash())
            for item in evidence['baselines']:
                self.assertTrue((payload/item['path']).is_file())
            damaged=payload/'e002e_corr_exp/core.py'
            damaged.write_text(damaged.read_text()+'\n# altered\n')
            rejected=subprocess.run(cmd,cwd=d,env=env,capture_output=True,text=True)
            self.assertNotEqual(rejected.returncode,0)
            self.assertIn('Payload implementation/protocol/kernel mismatch',rejected.stderr)


if __name__=='__main__':unittest.main()
