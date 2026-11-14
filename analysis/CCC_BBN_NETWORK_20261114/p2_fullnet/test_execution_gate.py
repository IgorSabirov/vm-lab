"""Regression checks for the discovered budget/cache serialization failures."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import fullnet_orchestrator as o

class ExecutionGate(unittest.TestCase):
    def test_probe_is_charged_once(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            o.append_ledger(root,{'run_id':'PROBE','exit_code':1,'wall_seconds':27})
            o.append_ledger(root,{'stage':'PROBE_SUMMARY','probe_wall_seconds':27})
            self.assertEqual(o.spent_seconds(root),27)

    def test_pair_near_600_exceeds_local_cap_after_probe(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            o.write_json(root/'CALIBRATION.json',{'probe_status':'COMPLETED','probe_wall_seconds':27,
                'probe_cpu_seconds':26,'probe_peak_rss_mib':100,'probe_result_sha256':'probe'})
            o.write_json(root/'FREEZE.json',{'source_commit':'source'})
            o.write_json(root/'PRODUCTION_CONFIG.json',{})
            o.append_ledger(root,{'run_id':'PROBE','exit_code':0,'wall_seconds':27})
            args=SimpleNamespace(run_root=str(root),low=300,central=500,high=590,basis='regression',auto_approve=False,publish=False)
            with patch.object(o,'run_root_arg',return_value=root),patch.object(o,'verify_frozen'),patch.dict(o.os.environ,{'GITHUB_ACTIONS':'false'}),contextlib.redirect_stdout(io.StringIO()):
                o.forecast(args)
            f=o.read_json(root/'FORECAST.json')
            self.assertEqual(f['package_seconds']['high'],617)
            self.assertEqual(f['native_route'],'FORECAST_EXCEEDS_EXECUTOR_CAP')

    def test_integer_temperature_would_change_fingerprint_serialization(self):
        p=o.read_json(o.PROFILE_PATH)['production_config']
        self.assertIs(type(p['T_start_cosmo_MeV']),float)
        q={**p,'T_start_cosmo_MeV':100}
        self.assertEqual(p,q)
        self.assertNotEqual(json.dumps(p,sort_keys=True),json.dumps(q,sort_keys=True))

if __name__=='__main__':unittest.main()
