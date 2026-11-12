import copy
from datetime import datetime,timezone
import hashlib,json,tempfile
from pathlib import Path
import unittest
from run_contract import validate_plan,canonical_hash,check_authorization,verify_receipt,validate_events

def plan():
 return {'schema':'vm-lab-run-plan-v1','run_id':'fixture_run_001','source':{'commit':'a'*40,'tree_sha':'b'*40,'input_manifest_sha256':'c'*64,'config_sha256':'d'*64},'command':{'entrypoint':'run.py','args':[]},'authorization':{'authority':'user','reference':'fixture-only','scope':'fixture','duration':'persistent','expires_at':None},'budget':{'forecast_seconds':10,'hard_wall_seconds':20,'memory_limit_mib':128,'disk_limit_mib':64},'executor':{'kind':'sandbox','id':'fixture'},'acceptance':{'required_artifacts':['PROCESS.json','report.txt']},'scientific_acceptance':'SEPARATE_USER_REVIEW'}

class Contracts(unittest.TestCase):
 def test_exact_approval_not_just_run_id(self):
  p=plan();a={'authority':'user','reference':'fixture-only','run_id':p['run_id'],'plan_sha256':canonical_hash(p)};check_authorization(p,a)
  p['source']['commit']='e'*40
  with self.assertRaisesRegex(ValueError,'exact plan'):check_authorization(p,a)
 def test_route_budget_expiry_and_path(self):
  for change in [lambda p:p['budget'].update(forecast_seconds=601,hard_wall_seconds=700),lambda p:p['budget'].update(forecast_seconds=float('nan')),lambda p:p['authorization'].update(expires_at='2000-01-01T00:00:00Z'),lambda p:p['command'].update(entrypoint='../bad.py')]:
   p=plan();change(p)
   with self.assertRaises(ValueError):validate_plan(p)
 def test_tampered_and_failed_receipts(self):
  p=plan();p['authorization']['expires_at']='2000-01-01T00:00:00Z'
  with tempfile.TemporaryDirectory() as t:
   d=Path(t);(d/'report.txt').write_text('expected failure is still evidence')
   (d/'PROCESS.json').write_text(json.dumps({'run_id':p['run_id'],'source_commit':p['source']['commit'],'state':'FAILED','technical_gate':'REVIEW_REQUIRED','scientific_confirmation':False}))
   files=[{'path':f.name,'size_bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in d.iterdir()]
   m={'run_id':p['run_id'],'source_commit':p['source']['commit'],'plan_sha256':canonical_hash(p),'files':files};(d/'RESULT_MANIFEST.json').write_text(json.dumps(m))
   self.assertEqual(verify_receipt(d,p)['process_state'],'FAILED');(d/'report.txt').write_text('tampered')
   with self.assertRaisesRegex(ValueError,'hash mismatch'):verify_receipt(d,p)
 def test_terminal_execution_cannot_silently_restart(self):
  events=[{'sequence':i,'state':s,'observed_at':f'2026-11-12T00:00:0{i}Z'} for i,s in enumerate(['PREPARED','SUBMITTED','RUNNING','COMPLETED'])];validate_events(events)
  events.append({'sequence':4,'state':'RUNNING','observed_at':'2026-11-12T00:00:04Z'})
  with self.assertRaises(ValueError):validate_events(events)
if __name__=='__main__':unittest.main()
