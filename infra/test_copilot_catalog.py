import json
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import copilot_catalog as c

class CatalogTests(unittest.TestCase):
    def test_collection_preserves_links_and_reports_partial_coverage(self):
        import base64
        def get(api, path):
            api.requests += 1
            receipt={'response_sha256':'a'*64, 'response_bytes':10, 'next_page_available':True}
            if '/search/' in path:
                return {'items':[{'full_name':'Org/Repo','private':False,'description':'Simulation'}], 'total_count':50, 'incomplete_results':False}, receipt
            if '/readme' in path:
                return {'content':base64.b64encode(b'https://github.com/Org/Extra').decode(), 'html_url':'https://github.com/Org/Catalog/blob/main/README.md', 'sha':'b'*40}, receipt
            return [{'full_name':'Org/Repo','private':False,'description':'Simulation'}], receipt
        with tempfile.TemporaryDirectory() as temp, patch.object(c.PublicAPI, 'get', get):
            output=Path(temp)
            c.prepare(output)
            rows=json.loads((output/'REGISTRY.json').read_text())['entries']
            self.assertIn('org/extra', {r['id'] for r in rows})
            self.assertEqual(sum(r['id']=='org/repo' for r in rows),1)
            coverage=json.loads((output/'COVERAGE.json').read_text())
            self.assertEqual(coverage['requests'],18)
            self.assertFalse(coverage['complete_github_coverage'])
            self.assertTrue(coverage['collection'][0]['remaining_pages_not_read'])
    def test_publisher_boundary(self):
        subprocess.run(['node', '--test', str(Path(__file__).with_name('copilot_catalog_publish.test.cjs'))],
                       check=True, capture_output=True, text=True, timeout=15)
    def package(self):
        return {'task': {'limits': {'selection_rows': 40}}, 'candidates': [{'id':'org/repo'}]}
    def selection(self):
        return {'summary':'Краткий вход в каталог по постановке Сейчас.', 'shortlist':[
            {'id':'org/repo','tags':['structure'],'reason':'Кандидат для изучения структуры.',
             'next_read':'Проверить README и описание модели.'}], 'gaps':['Не охвачен весь GitHub.']}
    def test_links_are_normalized_and_deduplicated(self):
        links=c.collect_links('[one](https://github.com/Org/Repo/blob/main/a.py) https://github.com/Org/Repo.git https://github.com/topics/test')
        self.assertEqual(links,['Org/Repo'])
        for bad in ['../x','a/..','https://evil.test/a/b','https://github.com/a/%2e%2e']:
            self.assertIsNone(c.repository_name(bad))
    def test_cap_retains_provenance_for_existing_entries(self):
        d={}
        self.assertTrue(c.add_entry(d,'Org/Repo',{'url':'first'},'a',cap=1))
        self.assertFalse(c.add_entry(d,'Org/Other',{'url':'second'},'b',cap=1))
        self.assertTrue(c.add_entry(d,'org/repo',{'url':'third'},'b',cap=1))
        self.assertEqual(len(d['org/repo']['origins']),2)
        self.assertFalse(d['org/repo']['execution_performed'])
    def test_private_or_mismatched_metadata_rejected(self):
        for meta in [{'full_name':'org/repo','private':True},{'full_name':'org/other','private':False}]:
            with self.assertRaises(ValueError):c.add_entry({},'org/repo',{},'a',meta)
    def test_selection_never_invents_repositories_or_scientific_status(self):
        self.assertEqual(c.validate_selection(self.selection(),self.package()),self.selection())
        for mutation in ('id','tags','status','duplicate'):
            d=self.selection()
            if mutation=='id': d['shortlist'][0]['id']='made/up'
            if mutation=='tags': d['shortlist'][0]['tags']=['scientifically-confirmed']
            if mutation=='status': d['shortlist'][0]['scientific_acceptance']=True
            if mutation=='duplicate': d['shortlist']*=2
            with self.assertRaises(ValueError):c.validate_selection(d,self.package())
    def test_http_budget_stops_before_network(self):
        api=c.PublicAPI({'http_requests':0,'collection_seconds':180})
        with patch('urllib.request.urlopen') as network:
            with self.assertRaises(RuntimeError):api.get('/search/repositories?q=x')
            network.assert_not_called()
    def test_failure_retains_full_response_without_repeat(self):
        package=self.package()
        package.update(source_sha='a'*40)
        package['task'].update(id='now-code-catalog-v1')
        package['task']['limits'].update(context_bytes=600000,inference_seconds=180)
        receipt={'returncode':0,'timed_out':False,'stdout':'not valid json'}
        with tempfile.TemporaryDirectory() as temp, patch.object(c,'invoke_native',return_value=receipt) as model:
            output=Path(temp)
            c.dump(output/'CONTEXT.json',package)
            with self.assertRaises(SystemExit):c.generate(output)
            self.assertEqual((output/'RAW_RESPONSE.txt').read_text(),'not valid json')
            self.assertTrue((output/'FAILURE.json').exists())
            self.assertEqual(model.call_count,1)
    def test_untrusted_description_cannot_inject_markdown(self):
        self.assertEqual(c.escape('<script>|[x]\ny'), '&lt;script&gt;\\|\\[x\\] y')

if __name__=='__main__':unittest.main()
