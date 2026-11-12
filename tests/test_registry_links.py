import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('registry_links',ROOT/'tools/registry_links.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)


class RegistryIntegrity(unittest.TestCase):
    def fixture(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        dst=Path(tmp.name)
        for p in (mod.MAIN,mod.MAIN_MD,mod.QUESTIONS,mod.QUESTIONS_MD,mod.PREMISES):
            f=dst/p;f.parent.mkdir(parents=True,exist_ok=True);f.write_text((ROOT/p).read_text())
        data=json.loads((dst/mod.MAIN).read_text())
        for row in data['results']+data.get('external_reviews',[]):
            for p in row.get('managed_sources',[]):
                f=dst/p;f.parent.mkdir(parents=True,exist_ok=True);f.write_text((ROOT/p).read_text())
        mod.run(dst,True)
        return dst

    def change_main(self,root,fn):
        p=root/mod.MAIN;data=json.loads(p.read_text());fn(data)
        p.write_text(json.dumps(data,ensure_ascii=False))

    def test_current_snapshot(self):
        stale,g=mod.run(ROOT)
        self.assertEqual(stale,[])
        self.assertEqual(g['counts']['premise'],66)
        self.assertIn('premise:C01',{n['key'] for n in g['nodes']})
        self.assertIn('construct:C001',{n['key'] for n in g['nodes']})

    def test_duplicate_id_rejected(self):
        p=self.fixture();self.change_main(p,lambda d:d['results'].append(copy.deepcopy(d['results'][0])))
        with self.assertRaisesRegex(ValueError,'Duplicate'):mod.build(p)

    def test_unknown_parent_rejected(self):
        p=self.fixture();self.change_main(p,lambda d:d['results'][-1]['parent_result_ids'].append('R999'))
        with self.assertRaisesRegex(ValueError,'Dangling'):mod.build(p)

    def test_missing_premise_rejected(self):
        p=self.fixture();f=p/mod.PREMISES
        f.write_text('\n'.join(l for l in f.read_text().splitlines() if not l.startswith('| A01 |')))
        with self.assertRaisesRegex(ValueError,'66'):mod.build(p)

    def test_missing_managed_source_rejected(self):
        p=self.fixture();d=json.loads((p/mod.MAIN).read_text())
        (p/d['results'][-1]['managed_sources'][0]).unlink()
        with self.assertRaisesRegex(ValueError,'Missing managed'):mod.build(p)

    def test_stale_index_detected(self):
        p=self.fixture();(p/mod.OUT/'INDEX.json').write_text('{}')
        stale,_=mod.run(p);self.assertIn(mod.OUT+'/INDEX.json',stale)

    def test_scientific_status_not_inferred(self):
        p=self.fixture()
        self.change_main(p,lambda d:d['results'][-1].update(status='REVIEW_REQUIRED_BY_HUMAN'))
        mod.run(p,True)
        d=json.loads((p/mod.MAIN).read_text());self.assertEqual(d['results'][-1]['status'],'REVIEW_REQUIRED_BY_HUMAN')
        self.assertIn('REVIEW_REQUIRED_BY_HUMAN',(p/mod.MAIN_MD).read_text())

    def test_r122_boundary_drift_detected(self):
        p=self.fixture();f=p/mod.MAIN_MD
        f.write_text(f.read_text().replace('следующий интервал восстановления не считался','восстановление невозможно'))
        with self.assertRaisesRegex(ValueError,'R122'):mod.build(p)

    def test_generation_is_idempotent(self):
        p=self.fixture()
        self.assertEqual(mod.run(p)[0],[])

    def test_review_has_bidirectional_navigation(self):
        p=self.fixture();_,g=mod.build(p)
        incoming=mod.neighborhood(g,'question:U006')['incoming']
        self.assertTrue(any(e['source']=='review:CCC_TL_20261112' for e in incoming))
        for f in (mod.MAIN_MD,mod.QUESTIONS_MD,mod.PREMISES):
            self.assertIn('CCC_TL_20261112',(p/f).read_text())
        mirror=json.loads((p/mod.PREMISES.replace('.md','.json')).read_text())
        b06=next(x for x in mirror['entries'] if x['id']=='B06')
        self.assertIn('CCC_TL_20261112',b06['context_review_ids'])
        self.assertNotIn('CCC_TL_20261112',b06['direct_result_ids'])

    def test_unknown_review_relation_rejected(self):
        p=self.fixture();self.change_main(p,lambda d:d['external_reviews'][0]['links'][0].update(relation='proves_cosmology'))
        with self.assertRaisesRegex(ValueError,'Unknown review relation'):mod.build(p)

    def test_dangling_typed_review_reference_rejected(self):
        p=self.fixture();self.change_main(p,lambda d:d['external_reviews'][0]['links'][0].update(target='premise:C001'))
        with self.assertRaisesRegex(ValueError,'Dangling typed review'):mod.build(p)

    def test_excluded_links_not_positive_evidence(self):
        p=self.fixture();_,g=mod.build(p)
        for x in g['excluded_review_links']:
            self.assertFalse(any(e['source']==x['source'] and e['target']==x['target'] for e in g['edges']))

    def test_conflicting_review_decisions_rejected(self):
        p=self.fixture()
        def change(d):
            rev=d['external_reviews'][0]
            rev['excluded_links'][0]['target']=rev['links'][0]['target']
        self.change_main(p,change)
        with self.assertRaisesRegex(ValueError,'Contradictory'):mod.build(p)

    def test_evidence_edit_invalidates_index(self):
        p=self.fixture();d=json.loads((p/mod.MAIN).read_text())
        f=p/d['external_reviews'][0]['report'];f.write_text(f.read_text()+'\nChanged evidence.\n')
        self.assertIn(mod.OUT+'/INDEX.json',mod.run(p)[0])

    def test_missing_evidence_anchor_rejected(self):
        p=self.fixture();self.change_main(p,lambda d:d['external_reviews'][0]['links'][0].update(evidence=d['external_reviews'][0]['report']+'#missing'))
        with self.assertRaisesRegex(ValueError,'Missing review evidence anchor'):mod.build(p)

    def test_stale_question_and_premise_backlinks_detected(self):
        p=self.fixture()
        for f in (mod.QUESTIONS_MD,mod.PREMISES):
            path=p/f;path.write_text(mod.strip_block(path.read_text(),'external-review-links'))
        stale,_=mod.run(p)
        self.assertIn(mod.QUESTIONS_MD,stale);self.assertIn(mod.PREMISES,stale)


if __name__=='__main__':unittest.main()
