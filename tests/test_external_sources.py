"""Negative controls for source pinning, preregistration and packaging integrity."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import external_sources as ext
import evidence_compendium as pack


class ExternalEvidence(unittest.TestCase):
    def ready(self):
        return json.loads((ROOT/'infra/external/contracts/NUMERICAL_ENV.json').read_text())

    def test_registered_sources_validate(self):
        rows=ext.validate(ROOT)
        self.assertTrue({'ANTHROPIC_HP','ANTHROPIC_BOOTSTRAP'}.issubset({r['id'] for r in rows}))

    def test_publication_cannot_impersonate_git_or_lose_version(self):
        row=next(r for r in ext.validate(ROOT) if r['id']=='ANTHROPIC_HP')
        for updates in ({'source_sha':'a'*40}, {'publication_version':None},
                        {'source_record_sha256':'0'*64}, {'monitor_enabled':True}):
            changed=copy.deepcopy(row);changed.update(updates)
            with self.assertRaises(ValueError):ext.validate_publication(changed,ROOT)

    def test_unknown_tolerance_blocks_ready_contract(self):
        c=self.ready();c['criteria'][0]['absolute_tolerance']=None
        with self.assertRaises(ValueError):ext.validate_contract(c)

    def test_nan_and_negative_tolerances_rejected(self):
        for v in (float('nan'),float('inf'),-1,True):
            c=self.ready();c['criteria'][0]['absolute_tolerance']=v
            with self.assertRaises(ValueError):ext.validate_contract(c)

    def test_known_outcomes_cannot_become_confirmatory(self):
        c=self.ready();c['analysis_mode']='confirmatory'
        with self.assertRaisesRegex(ValueError,'Known outcomes'):ext.validate_contract(c)

    def test_draft_cannot_execute(self):
        c=self.ready();c['state']='DRAFT'
        with self.assertRaisesRegex(ValueError,'Draft'):ext.validate_contract(c)

    def test_no_automatic_acm_badge(self):
        c=self.ready();c['acm_badge_awarded']=True
        with self.assertRaisesRegex(ValueError,'ACM'):ext.validate_contract(c)

    def test_missing_preparation_receipt_rejected(self):
        c=self.ready();c['pre_execution_receipt_required']=False
        with self.assertRaises(ValueError):ext.validate_contract(c)

    def test_monitor_does_not_change_pinned_source(self):
        row={'id':'TEST','kind':'github','monitor_enabled':True,'repository':'author/project','source_sha':'a'*40,'links':['result:R127']}
        before=copy.deepcopy(row)
        def get(path):
            if '/commits/' in path:return {'sha':'b'*40,'commit':{'tree':{'sha':'c'*40}}}
            if '/compare/' in path:return {'status':'ahead','files':[{'filename':'model.cpp'}]}
            return {'default_branch':'main','license':{'spdx_id':'MIT'}}
        r=ext.inspect([row],get)
        self.assertEqual(row,before);self.assertEqual(len(r['changes']),1)
        self.assertFalse(r['changes'][0]['scientific_status_promoted'])

    def test_unreadable_source_not_reported_as_unchanged(self):
        row={'id':'TEST','kind':'github','monitor_enabled':True,'repository':'author/project'}
        def get(path):raise TimeoutError('Unavailable')
        self.assertEqual(len(ext.inspect([row],get)['errors']),1)

    def test_traversal_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with self.assertRaises(ValueError):ext.local(root,'../outside')
            (root/'x').symlink_to('/etc/hosts')
            with self.assertRaises(ValueError):ext.local(root,'x')

    def test_compendium_is_deterministic_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'data.txt').write_text('fixed input\n')
            (root/'spec.json').write_text(json.dumps({'files':['data.txt'],'scope':'test','reproduce':'read data.txt','raw_data':'data.txt','limitations':'fixture'}))
            one=pack.build(root,'spec.json',root/'one.zip');two=pack.build(root,'spec.json',root/'two.zip')
            self.assertEqual(one['sha256'],two['sha256']);self.assertTrue(pack.verify(root/'one.zip'))
            with zipfile.ZipFile(root/'one.zip') as z:content={n:z.read(n) for n in z.namelist()}
            content['data.txt']=b'changed'
            with zipfile.ZipFile(root/'bad.zip','w') as z:
                for n,b in content.items():z.writestr(n,b)
            with self.assertRaises(ValueError):pack.verify(root/'bad.zip')

    def test_duplicate_or_missing_package_member_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'data.txt').write_text('input')
            spec={'files':['data.txt','data.txt'],'scope':'test','reproduce':'none','raw_data':[],'limitations':[]}
            (root/'spec.json').write_text(json.dumps(spec))
            with self.assertRaises(ValueError):pack.build(root,'spec.json',root/'a.zip')
            spec['files']=['missing'];(root/'spec.json').write_text(json.dumps(spec))
            with self.assertRaises(ValueError):pack.build(root,'spec.json',root/'a.zip')

    def test_packaged_source_metadata_validates_without_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / 'metadata.zip'
            pack.build(ROOT, 'infra/external/COMPENDIUM.json', archive)
            target = root / 'unpacked'
            with zipfile.ZipFile(archive) as z:
                z.extractall(target)
            rows = ext.validate(target)
            primat = next(row for row in rows if row['id'] == 'PRIMAT')
            self.assertEqual(len(ext.resolve_resources(primat, target)['resources']), 20)


if __name__=='__main__':unittest.main()
