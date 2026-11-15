"""No LINX integration: admission boundaries, strict-input preservation and cleanup."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import run as package
import worker
import bounded

class PackageTests(unittest.TestCase):
    def test_strict_numerical_contract_unchanged(self):
        old=package.read(HERE.parent/'identity/BBN_IDENTITY_CONTRACT.json');new=package.read(HERE/'BBN_IDENTITY_CONTRACT.json')
        for key in ('upstream_commit','network','species','matrix','interpolation','boundary_policy','dtype','device','q_by_reaction','background','bbn','criteria'):
            self.assertEqual(old[key],new[key],key)

    def test_calibration_cannot_be_a_strict_arm(self):
        from types import SimpleNamespace
        from datetime import datetime,timezone
        r={'admitted':True,'source_sha':'a'*40,'contract_sha256':worker.digest(HERE/'BBN_IDENTITY_CONTRACT.json'),
           'ledger_and_actions_checked':True,'reservation':{'source_sha':'a'*40},'observed_utc':datetime.now(timezone.utc).isoformat(),
           'policy_version':'20261115-sequential-no-daily-quota-v1','route':'github_actions','bounded_executor':True,'phase':'CALIBRATION_RESERVED'}
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'a.json';p.write_text(json.dumps(r));a=SimpleNamespace(execute=True,admission=p,source_sha='a'*40,calibration=False,role='native_pristine')
            with self.assertRaisesRegex(ValueError,'Measured strict'):worker.admission_check(a,{})
            a.calibration=True
            with patch.object(worker.subprocess,'check_output',return_value='a'*40+'\n'),patch.object(worker.subprocess,'run'):
                self.assertTrue(worker.admission_check(a,{})['admitted'])

    def test_calibrated_plan_stops_before_process_cap(self):
        with tempfile.TemporaryDirectory(dir=package.ROOT) as tmp,patch.dict(os.environ,{'SOURCE_SHA':'a'*40,'GITHUB_RUN_ID':'42'}):
            with patch.object(package,'OUT',Path(tmp)),patch.object(package,'digest',return_value='b'*64),patch.object(package.execution_policy,'validate'):
                with self.assertRaisesRegex(ValueError,'forecast exceeds'):package.calibrated_plan(1201)
                plan=package.calibrated_plan(100)
                self.assertEqual([t['forecast_seconds'] for t in plan['tasks']],[300,300])
                self.assertEqual(plan['budget']['package_seconds'],9900)

    def test_nonzero_exit_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            log=Path(tmp)/'x.log';r=bounded.run([sys.executable,'-c','raise SystemExit(7)'],log,{'wall_seconds':3,'memory_bytes':128*1024**2,'output_bytes':1024**2})
            self.assertEqual(r['exit_code'],7);self.assertTrue(r['process_exited'])

    def test_measured_plan_passes_existing_validator(self):
        with tempfile.TemporaryDirectory(dir=package.ROOT) as tmp,patch.dict(os.environ,{'SOURCE_SHA':'a'*40,'GITHUB_RUN_ID':'42'}):
            p=Path(tmp);(p/'CALIBRATION.json').write_text('{"test_fixture":true}\n')
            with patch.object(package,'OUT',p):
                plan=package.calibrated_plan(100)
                report=package.execution_policy.validate(plan,package.read(package.ROOT/'infra/autonomy/CONTROL.json')['limits'],root=package.ROOT)
                self.assertEqual(report['executor'],'github_actions');self.assertEqual(len(plan['tasks']),2)

    def test_wall_limit_reaps_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=bounded.run([sys.executable,'-c','import time;time.sleep(30)'],Path(tmp)/'x.log',{'wall_seconds':.15,'memory_bytes':128*1024**2,'output_bytes':1024**2})
            self.assertEqual(r['stop'],'WALL_LIMIT');self.assertTrue(r['process_exited'])
            with self.assertRaises(ProcessLookupError):os.kill(r['pid'],0)

    def test_external_supervisor_signal_reaps_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            log=Path(tmp)/'x.log';script="import sys;sys.path.insert(0,sys.argv[1]);from bounded import run;run([sys.executable,'-c','import time;time.sleep(30)'],sys.argv[2],{'wall_seconds':20,'memory_bytes':134217728,'output_bytes':1048576})"
            p=subprocess.Popen([sys.executable,'-c',script,str(HERE),str(log)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try:
                deadline=time.monotonic()+5
                while not log.exists() and time.monotonic()<deadline:time.sleep(.02)
                self.assertTrue(log.exists());time.sleep(.1);p.send_signal(signal.SIGTERM);p.wait(timeout=5)
                r=json.loads(Path(str(log)+'.guard.json').read_text());self.assertEqual(r['stop'],'SUPERVISOR_INTERRUPTED');self.assertTrue(r['process_exited'])
                with self.assertRaises(ProcessLookupError):os.kill(r['pid'],0)
            finally:
                if p.poll() is None:p.kill();p.wait()

if __name__=='__main__':unittest.main()
