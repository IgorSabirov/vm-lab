"""Mutation controls for domain checks and one-admission/multi-receipt execution."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

# unittest discovery -s infra also permits the explicit package imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from infra.adapters import add_f2
from infra.adapters.domain_verify import verify
from infra.package_runner import check_admission, bounded
from infra.autonomy.execution_policy import digest

ROOT = Path(__file__).resolve().parents[1]
CONFIG = dict(seed=20261115, initial_vertices=6, steps=4, bit_probability=.5, radius=2)


class Adapters(unittest.TestCase):
    def test_add_finite_trajectory_and_independent_mutation_control(self):
        raw=add_f2.run(ROOT,None,CONFIG)
        self.assertEqual(verify('add_f2',raw,CONFIG)['status'],'PASS')
        for change in (lambda x:x['trajectory']['rows'][-1]['p_by_bit'].__setitem__(0,99),
                       lambda x:x.update(variant='ADD_R129'),
                       lambda x:x['trajectory']['rows'].pop()):
            bad=copy.deepcopy(raw);change(bad)
            with self.assertRaises(AssertionError):verify('add_f2',bad,CONFIG)

    def test_one_reservation_binds_all_sections(self):
        plan={'package_id':'fixture_package','source_commit':'a'*40,'sections':[{'id':'a'},{'id':'b'}]}
        row={'id':plan['package_id'],'source_sha':'a'*40,'execution_plan_sha256':digest(plan),
             'executor':'local','status':'RESERVED'}
        admission={'admitted':True,'ledger_blob_sha':'b'*40,'reservation':row}
        check_admission(plan,admission)
        changed=copy.deepcopy(plan);changed['sections'].append({'id':'hidden'})
        with self.assertRaises(ValueError):check_admission(changed,admission)
        admission['reservation']['status']='COMPLETED'
        with self.assertRaises(ValueError):check_admission(plan,admission)

    def test_deadline_preserves_log_and_kills_worker(self):
        with tempfile.TemporaryDirectory() as t:
            folder=Path(t)
            with self.assertRaisesRegex(RuntimeError,'budget exceeded'):
                bounded([sys.executable,'-c','import time;print("started",flush=True);time.sleep(10)'],
                        folder,{},.1,512*1024**2,1024**2,folder)
            self.assertIn('started',(folder/'stdout.log').read_text())

    def test_serbian_exact_math_is_not_the_ambiguity_flag(self):
        config={'fixtures':[{'id':'degenerate','sides':[1,1,2],
                           'expected_inertia':[1,0,1],'category':'exact_degenerate'}]}
        # Shared four-fixture receipt is required; this deliberately cannot pass.
        raw={'build_passed':True,'matrices':[[[1,-1],[-1,1]]],
             'observed':{'counts':[[1,0,1]]}}
        with self.assertRaises(AssertionError):verify('serbian_signature',raw,config)


if __name__=='__main__':unittest.main()
