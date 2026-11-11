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
        for row in data['results']:
            for p in row.get('managed_sources',[]):
                f=dst/p;f.parent.mkdir(parents=True,exist_ok=True);f.write_text('fixture')
        mod.run(dst,True)
        return dst

    def change_main(self,root,fn):
        p=root/mod.MAIN;data=json.loads(p.read_text());fn(data)
        p.write_text(json.dumps(data,ensure_ascii=False))

    def test_current_snapshot(self):
        stale,g=mod.run(ROOT)
        self.assertEqual(stale,[])
        self.assertEqual(g['counts']['premise'],66)
        self.assertEqual(g['counts']['obligation'],9)
        self.assertEqual(g['counts']['source'],4)
        self.assertIn('premise:C01',{n['key'] for n in g['nodes']})
        self.assertIn('obligation:N02',{n['key'] for n in g['nodes']})
        self.assertIn('construct:C001',{n['key'] for n in g['nodes']})

    def test_duplicate_id_rejected(self):
        p=self.fixture();self.change_main(p,lambda d:d['results'].append(copy.deepcopy(d['results'][0])))
        with self.assertRaisesRegex(ValueError,'Duplicate'):mod.build(p)

    def test_unknown_parent_rejected(self):
        p=self.fixture();self.change_main(p,lambda d:d['results'][-1]['parent_result_ids'].append('R999'))
        with self.assertRaisesRegex(ValueError,'Dangling'):mod.build(p)

    def test_missing_premise_rejected(self):
        p=self.fixture();f=p/mod.PREMISES
        f.write_text('\n'.join(l for l in f.read_text().splitlines() if 'premise-a01' not in l))
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

    def test_deep_links_are_generated(self):
        p=self.fixture()
        _,g=mod.run(p)
        index=(p/mod.OUT/'INDEX.md').read_text()
        self.assertIn('#r129',index)
        self.assertIn('#u010',index)
        self.assertIn('#premise-b03',index)
        self.assertIn('#obligation-n02',index)

    def test_managed_source_hash_changes_when_file_changes(self):
        p=self.fixture()
        _,before=mod.build(p)
        source=p/'analysis/G3_CONTACT_CAPACITY_20261111/REPORT.md'
        old=source.read_text()
        source.write_text(old+'\nchanged source snapshot\n')
        _,after=mod.build(p)
        before_nodes={n['key']:n for n in before['nodes']}
        after_nodes={n['key']:n for n in after['nodes']}
        key='source:analysis/G3_CONTACT_CAPACITY_20261111/REPORT.md'
        self.assertNotEqual(before_nodes[key]['git_blob_sha'],after_nodes[key]['git_blob_sha'])
        self.assertNotEqual(before_nodes[key]['sha256'],after_nodes[key]['sha256'])
    def test_r122_boundary_drift_detected(self):
        p=self.fixture();f=p/mod.MAIN_MD
        f.write_text(f.read_text().replace('следующий интервал восстановления не считался','восстановление невозможно'))
        with self.assertRaisesRegex(ValueError,'R122'):mod.build(p)


if __name__=='__main__':unittest.main()
